"""Authentication, BU scoping, and shared section-catalogue persistence."""

from __future__ import annotations

import os
import re
import logging
import hashlib
import hmac
import secrets
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from botocore.config import Config as BotoConfig
from dotenv import load_dotenv
from flask import g, jsonify, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash


load_dotenv(Path(__file__).resolve().parents[2] / "config" / ".env")
logger = logging.getLogger(__name__)

BUSINESS_UNITS = (
    "GenAI",
    "Database Management",
    "Data Engineering",
    "Cloud",
    "MLOps",
)
BUSINESS_UNIT_BY_KEY = {
    re.sub(r"[^a-z0-9]+", "_", name.casefold()).strip("_"): name
    for name in BUSINESS_UNITS
}
BU_ROLE_BY_NAME = {
    "GenAI": "GENAI",
    "Database Management": "DATABASE_MANAGEMENT",
    "Data Engineering": "DATA_ENGINEERING",
    "Cloud": "CLOUD",
    "MLOps": "MLOPS",
}
BUSINESS_UNIT_BY_ROLE = {role: unit for unit, role in BU_ROLE_BY_NAME.items()}
USER_ROLES = ("ADMIN", *BU_ROLE_BY_NAME.values(), "USER")

DEFAULT_SECTION_CATALOGUE = [
    {"id": "document_version_control", "label": "Document Version Control"},
    {"id": "about_shellkode", "label": "About Shellkode"},
    {"id": "about_client", "label": "About Client"},
    {"id": "project_overview", "label": "Objective"},
    {"id": "scope_of_work", "label": "Scope of Work"},
    {"id": "architecture_diagram", "label": "Architecture Diagram"},
    {"id": "customer_dependencies", "label": "Customer Dependencies"},
    {"id": "assumptions", "label": "Assumptions"},
    {"id": "out_of_scope", "label": "Out of Scope"},
    {"id": "timelines_deliverables", "label": "Timelines and Deliverables"},
    {"id": "aws_pricing", "label": "AWS Pricing"},
    {"id": "customer_responsibilities", "label": "Customer Responsibilities"},
    {"id": "project_team_effort", "label": "Project Team Effort"},
    {"id": "open_clarifications", "label": "Open Clarifications"},
    {"id": "success_criteria", "label": "Success Criteria"},
    {"id": "project_plan_termination", "label": "Project Plan Termination"},
    {"id": "contacts_reporting", "label": "Contacts and Reporting"},
    {"id": "terms_conditions", "label": "Terms and Conditions"},
    {"id": "acceptance_signatories", "label": "Acceptance and Signatories"},
]
for _section in DEFAULT_SECTION_CATALOGUE:
    _section.update({
        "modes": ["poc", "production", "poc-to-production"],
        "custom": False,
        "prompt": "",
    })

SAMPLE_USERS = {
    "admin@shellkode.com": {"name": "Sample Admin", "role": "ADMIN", "business_unit": None},
    "genai@shellkode.com": {"name": "GenAI User", "role": "GENAI", "business_unit": "GenAI"},
    "database@shellkode.com": {"name": "Database User", "role": "DATABASE_MANAGEMENT", "business_unit": "Database Management"},
    "dataengineering@shellkode.com": {"name": "Data Engineering User", "role": "DATA_ENGINEERING", "business_unit": "Data Engineering"},
    "cloud@shellkode.com": {"name": "Cloud User", "role": "CLOUD", "business_unit": "Cloud"},
    "mlops@shellkode.com": {"name": "MLOps User", "role": "MLOPS", "business_unit": "MLOps"},
    "ananya.user@shellkode.com": {"name": "Ananya Rao", "role": "USER", "business_unit": "GenAI"},
    "rohan.user@shellkode.com": {"name": "Rohan Mehta", "role": "USER", "business_unit": "Cloud"},
    "priya.user@shellkode.com": {"name": "Priya Nair", "role": "USER", "business_unit": "Data Engineering"},
}
SAMPLE_PASSWORD = "Shellkode@123"


def normalise_business_unit(value: Optional[str]) -> Optional[str]:
    if value is None or not str(value).strip():
        return None
    key = re.sub(r"[^a-z0-9]+", "_", str(value).casefold()).strip("_")
    if key not in BUSINESS_UNIT_BY_KEY:
        raise ValueError(f"Unknown business unit: {value}")
    return BUSINESS_UNIT_BY_KEY[key]


@dataclass(frozen=True)
class Identity:
    email: str
    name: str
    role: str
    business_unit: Optional[str] = None
    roles: tuple[str, ...] = ()
    business_units: tuple[str, ...] = ()
    employee_id: Optional[int] = None

    def __post_init__(self) -> None:
        roles = tuple(dict.fromkeys(
            str(role).upper().strip() for role in (self.roles or (self.role,)) if str(role).strip()
        ))
        primary = "ADMIN" if "ADMIN" in roles else (roles[0] if roles else str(self.role).upper())
        units = list(self.business_units)
        if self.business_unit:
            units.insert(0, self.business_unit)
        units.extend(BUSINESS_UNIT_BY_ROLE[role] for role in roles if role in BUSINESS_UNIT_BY_ROLE)
        normalised_units = tuple(dict.fromkeys(
            unit for unit in (normalise_business_unit(value) for value in units) if unit
        ))
        object.__setattr__(self, "role", primary)
        object.__setattr__(self, "roles", roles)
        object.__setattr__(self, "business_unit", normalised_units[0] if normalised_units else None)
        object.__setattr__(self, "business_units", normalised_units)

    @property
    def is_admin(self) -> bool:
        return "ADMIN" in self.roles

    @property
    def is_user(self) -> bool:
        return self.roles == ("USER",)

    @property
    def is_bu_head(self) -> bool:
        return any(role in BUSINESS_UNIT_BY_ROLE for role in self.roles)

    def public_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RBACStore:
    def __init__(self) -> None:
        region = os.getenv("AWS_REGION", "us-east-1")
        table_name = os.getenv("DYNAMODB_TABLE_RBAC", "agentic-sow-rbac")
        self.table = boto3.resource(
            "dynamodb",
            region_name=region,
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            aws_session_token=os.getenv("AWS_SESSION_TOKEN"),
            config=BotoConfig(connect_timeout=2, read_timeout=3, retries={"max_attempts": 1}),
        ).Table(table_name)

    def get_user(self, email: str) -> Optional[Dict[str, Any]]:
        email = email.casefold().strip()
        try:
            response = self.table.get_item(Key={"PK": f"USER#{email}", "SK": "PROFILE"})
            return response.get("Item")
        except (BotoCoreError, ClientError) as exc:
            if not isinstance(exc, ClientError) or exc.response.get("Error", {}).get("Code") != "ResourceNotFoundException":
                logger.warning("RBAC user lookup failed: %s", exc)
            return None

    def authenticate(self, email: str, password: str) -> Optional[Identity]:
        email = email.casefold().strip()
        user = self.get_user(email)
        if user and user.get("status", "active") == "active":
            if check_password_hash(str(user.get("password_hash", "")), password):
                self._migrate_self_signup_role(user)
                return self._identity_from_item(user)

        if os.getenv("ENABLE_SAMPLE_USERS", "false").casefold() == "true":
            sample = SAMPLE_USERS.get(email)
            if sample and password == SAMPLE_PASSWORD:
                return Identity(email=email, roles=(sample["role"],), **sample)
        return None

    def active_identity(self, email: str) -> Optional[Identity]:
        """Load the current role and status so account changes revoke access immediately."""
        email = email.casefold().strip()
        user = self.get_user(email)
        if user:
            if user.get("status", "active") != "active":
                return None
            self._migrate_self_signup_role(user)
            return self._identity_from_item(user)
        if os.getenv("ENABLE_SAMPLE_USERS", "false").casefold() == "true":
            sample = SAMPLE_USERS.get(email)
            if sample:
                return Identity(email=email, roles=(sample["role"],), **sample)
        return None

    def _migrate_self_signup_role(self, item: Dict[str, Any]) -> None:
        """Persist the corrected USER role for records created by the old signup flow."""
        if (
            str(item.get("updated_by") or "").casefold() != "self-signup"
            or str(item.get("role") or "").upper() == "USER"
        ):
            return
        item["role"] = "USER"
        item["roles"] = ["USER"]
        item["updated_at"] = datetime.now(timezone.utc).isoformat()
        try:
            self.table.put_item(Item=item)
            logger.info("Migrated self-signup account %s to USER role", item.get("email"))
        except (BotoCoreError, ClientError) as exc:
            # Authorization remains safe because _identity_from_item also maps
            # this legacy record to USER even if the cleanup write is denied.
            logger.warning("Could not persist USER role migration for %s: %s", item.get("email"), exc)

    @staticmethod
    def _identity_from_item(item: Dict[str, Any]) -> Identity:
        legacy_role = str(item.get("role") or "USER").upper()
        # Self-registration has always represented an individual user.  Older
        # signup records incorrectly stored the selected BU as an authorization
        # role (for example GENAI); correct that legacy shape when it is read.
        self_registered = str(item.get("updated_by") or "").casefold() == "self-signup"
        roles = (
            ("USER",)
            if self_registered
            else tuple(str(role).upper() for role in (item.get("roles") or [legacy_role]))
        )
        effective_role = "USER" if self_registered else legacy_role
        units = tuple(str(unit) for unit in (item.get("business_units") or []) if str(unit).strip())
        return Identity(
            email=str(item.get("email") or "").casefold(),
            name=str(item.get("name") or item.get("email") or ""),
            role=effective_role,
            business_unit=normalise_business_unit(item.get("business_unit")),
            roles=roles,
            business_units=units,
            employee_id=RBACStore._normalise_employee_id(
                item.get("employee_id"), required=False
            ),
        )

    @staticmethod
    def _normalise_email(email: str) -> str:
        email = str(email).casefold().strip()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            raise ValueError("A valid email address is required")
        return email

    @classmethod
    def _normalise_shellkode_email(cls, email: str) -> str:
        email = cls._normalise_email(email)
        if not email.endswith("@shellkode.com"):
            raise ValueError("Email address must end with @shellkode.com")
        return email

    @staticmethod
    def _normalise_employee_id(employee_id: Any, *, required: bool = True) -> Optional[int]:
        """Return the numeric employee ID stored in DynamoDB.

        The optional SK- prefix is accepted for compatibility with records and
        clients created before employee IDs became numeric.
        """
        raw = str(employee_id if employee_id is not None else "").strip()
        if not raw:
            if required:
                raise ValueError("Employee ID is required")
            return None
        raw = re.sub(r"^SK-?", "", raw, flags=re.I)
        if not re.fullmatch(r"\d+", raw):
            if not required:
                return None
            raise ValueError("Employee ID must be a positive integer")
        value = int(raw)
        if value <= 0:
            raise ValueError("Employee ID must be a positive integer")
        return value

    @staticmethod
    def _normalise_role_and_unit(role: str, business_unit: Optional[str]) -> tuple[str, Optional[str]]:
        role = str(role).upper().strip()
        if role not in USER_ROLES:
            raise ValueError(f"Unknown role: {role}")
        if role == "ADMIN":
            return role, None
        if role in BUSINESS_UNIT_BY_ROLE:
            return role, BUSINESS_UNIT_BY_ROLE[role]
        unit = normalise_business_unit(business_unit)
        if not unit:
            raise ValueError("business_unit is required for a User")
        return role, unit

    @classmethod
    def _normalise_roles_and_units(
        cls, roles: Any, business_unit: Optional[str]
    ) -> tuple[list[str], list[str]]:
        values = roles if isinstance(roles, (list, tuple, set)) else [roles]
        clean = list(dict.fromkeys(str(role).upper().strip() for role in values if str(role).strip()))
        if not clean:
            clean = ["USER"]
        unknown = [role for role in clean if role not in USER_ROLES]
        if unknown:
            raise ValueError(f"Unknown role: {unknown[0]}")
        if "ADMIN" in clean:
            return ["ADMIN"], []
        if "USER" in clean and len(clean) > 1:
            raise ValueError("USER cannot be combined with administrator or business-unit roles")
        units = [BUSINESS_UNIT_BY_ROLE[role] for role in clean if role in BUSINESS_UNIT_BY_ROLE]
        selected_unit = normalise_business_unit(business_unit)
        if clean == ["USER"]:
            if not selected_unit:
                raise ValueError("business_unit is required for a User")
            units = [selected_unit]
        elif selected_unit and selected_unit not in units:
            raise ValueError("business_unit must correspond to one of the assigned roles")
        return clean, list(dict.fromkeys(units))

    @staticmethod
    def _public_user(item: Dict[str, Any]) -> Dict[str, Any]:
        role = str(item.get("role") or "USER").upper()
        roles = [str(value).upper() for value in (item.get("roles") or [role])]
        if str(item.get("updated_by") or "").casefold() == "self-signup":
            role, roles = "USER", ["USER"]
        business_units = [
            unit for unit in (
                normalise_business_unit(value)
                for value in (item.get("business_units") or [item.get("business_unit")])
            ) if unit
        ]
        employee_id = RBACStore._normalise_employee_id(
            item.get("employee_id"), required=False
        )
        return {
            "email": str(item.get("email", "")),
            "name": str(item.get("name", "")),
            "role": role,
            "roles": roles,
            "business_unit": normalise_business_unit(item.get("business_unit")),
            "business_units": list(dict.fromkeys(business_units)),
            "employee_id": employee_id,
            "email_verified": bool(item.get("email_verified", item.get("status") == "active")),
            "status": str(item.get("status", "active")),
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
        }

    def list_users(self) -> List[Dict[str, Any]]:
        response = self.table.scan()
        items = list(response.get("Items", []))
        while response.get("LastEvaluatedKey"):
            response = self.table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
            items.extend(response.get("Items", []))
        users = [
            self._public_user(item)
            for item in items
            if str(item.get("PK", "")).startswith("USER#") and item.get("SK") == "PROFILE"
        ]
        return sorted(users, key=lambda item: (item["role"] != "ADMIN", item["name"].casefold()))

    def create_user(
        self,
        *,
        email: str,
        name: str,
        role: str,
        business_unit: Optional[str],
        password: str,
        created_by: str,
        roles: Any = None,
        employee_id: Any = None,
    ) -> Dict[str, Any]:
        email = self._normalise_email(email)
        name = str(name).strip()
        if not name:
            raise ValueError("name is required")
        if len(str(password)) < 6:
            raise ValueError("password must contain at least 6 characters")
        clean_roles, business_units = self._normalise_roles_and_units(roles or [role], business_unit)
        role = clean_roles[0]
        business_unit = business_units[0] if business_units else None
        timestamp = datetime.now().isoformat()
        employee_id = self._normalise_employee_id(employee_id, required=False)
        item = {
            "PK": f"USER#{email}",
            "SK": "PROFILE",
            "email": email,
            "name": name,
            "role": role,
            "roles": clean_roles,
            "business_unit": business_unit or "",
            "business_units": business_units,
            "password_hash": generate_password_hash(str(password)),
            "status": "active",
            "email_verified": True,
            "created_at": timestamp,
            "updated_at": timestamp,
            "updated_by": created_by,
        }
        if employee_id is not None:
            item["employee_id"] = employee_id
        employee_key = (
            {"PK": f"EMPLOYEE#{employee_id}", "SK": "USER"}
            if employee_id is not None else None
        )
        employee_reserved = False
        try:
            if employee_key:
                self.table.put_item(
                    Item={**employee_key, "email": email, "employee_id": employee_id},
                    ConditionExpression="attribute_not_exists(PK)",
                )
                employee_reserved = True
            self.table.put_item(
                Item=item,
                ConditionExpression="attribute_not_exists(PK)",
            )
        except ClientError as exc:
            if employee_key and employee_reserved:
                self.table.delete_item(Key=employee_key)
            if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                raise ValueError("A user with this email or employee ID already exists") from exc
            raise
        except Exception:
            if employee_key and employee_reserved:
                self.table.delete_item(Key=employee_key)
            raise
        return self._public_user(item)

    def register_user(
        self, *, first_name: str, last_name: str, email: str, employee_id: Any,
        business_unit: str, password: str,
    ) -> tuple[Dict[str, Any], str]:
        first_name, last_name = str(first_name).strip(), str(last_name).strip()
        if not first_name or not last_name:
            raise ValueError("First name and last name are required")
        email = self._normalise_shellkode_email(email)
        employee_id = self._normalise_employee_id(employee_id)
        if len(str(password)) < 6:
            raise ValueError("Password must contain at least 6 characters")
        unit = normalise_business_unit(business_unit)
        if not unit:
            raise ValueError("Business unit is required")
        # Business-unit membership scopes the user's records; it does not grant
        # BU-head/account-management privileges.
        role = "USER"
        nonce = secrets.token_urlsafe(32)
        timestamp = datetime.now(timezone.utc).isoformat()
        item = {
            "PK": f"USER#{email}", "SK": "PROFILE", "email": email,
            "name": f"{first_name} {last_name}", "first_name": first_name,
            "last_name": last_name, "employee_id": employee_id,
            "role": role, "roles": [role], "business_unit": unit,
            "business_units": [unit], "password_hash": generate_password_hash(str(password)),
            "status": "pending_verification", "email_verified": False,
            "verification_nonce_hash": hashlib.sha256(nonce.encode()).hexdigest(),
            "verification_sent_at": timestamp, "created_at": timestamp,
            "updated_at": timestamp, "updated_by": "self-signup",
        }
        employee_key = {"PK": f"EMPLOYEE#{employee_id}", "SK": "USER"}
        try:
            self.table.put_item(
                Item={**employee_key, "email": email, "employee_id": employee_id},
                ConditionExpression="attribute_not_exists(PK)",
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                raise ValueError("An account with this employee ID already exists") from exc
            raise
        try:
            self.table.put_item(Item=item, ConditionExpression="attribute_not_exists(PK)")
        except ClientError as exc:
            self.table.delete_item(Key=employee_key)
            if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                raise ValueError("An account with this email already exists") from exc
            raise
        except Exception:
            self.table.delete_item(Key=employee_key)
            raise
        return self._public_user(item), nonce

    def verify_registration(self, email: str, nonce: str) -> Dict[str, Any]:
        email = self._normalise_shellkode_email(email)
        item = self.get_user(email)
        if not item:
            raise ValueError("Verification link is invalid")
        if item.get("status") == "active" and item.get("email_verified"):
            return self._public_user(item)
        actual = hashlib.sha256(str(nonce).encode()).hexdigest()
        if not hmac.compare_digest(actual, str(item.get("verification_nonce_hash") or "")):
            raise ValueError("Verification link is invalid or has already been used")
        timestamp = datetime.now(timezone.utc).isoformat()
        item.update({
            "status": "active", "email_verified": True, "verified_at": timestamp,
            "updated_at": timestamp,
        })
        item.pop("verification_nonce_hash", None)
        self.table.put_item(Item=item)
        return self._public_user(item)

    def renew_verification(self, email: str) -> str:
        email = self._normalise_shellkode_email(email)
        item = self.get_user(email)
        if not item or item.get("status") != "pending_verification":
            raise ValueError("No account is awaiting verification for this email")
        sent_at = str(item.get("verification_sent_at") or "")
        if sent_at:
            try:
                elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(sent_at)).total_seconds()
                if elapsed < 60:
                    raise ValueError("Please wait before requesting another verification email")
            except ValueError as exc:
                if "Please wait" in str(exc):
                    raise
        nonce = secrets.token_urlsafe(32)
        item["verification_nonce_hash"] = hashlib.sha256(nonce.encode()).hexdigest()
        item["verification_sent_at"] = datetime.now(timezone.utc).isoformat()
        item["updated_at"] = item["verification_sent_at"]
        self.table.put_item(Item=item)
        return nonce

    def begin_password_reset(self, email: str) -> Optional[tuple[str, str]]:
        """Create a single-use reset challenge for an active, verified account.

        Returning ``None`` for unknown/ineligible accounts lets the public API
        keep an enumeration-safe response while avoiding an email send.
        """
        try:
            email = self._normalise_shellkode_email(email)
        except ValueError:
            return None
        item = self.get_user(email)
        if not item or item.get("status") != "active" or not item.get("email_verified", True):
            return None
        sent_at = str(item.get("password_reset_sent_at") or "")
        if sent_at:
            try:
                elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(sent_at)).total_seconds()
                if elapsed < 60:
                    return None
            except ValueError:
                pass
        nonce = secrets.token_urlsafe(32)
        timestamp = datetime.now(timezone.utc).isoformat()
        item.update({
            "password_reset_nonce_hash": hashlib.sha256(nonce.encode()).hexdigest(),
            "password_reset_sent_at": timestamp,
            "updated_at": timestamp,
        })
        self.table.put_item(Item=item)
        return email, nonce

    def reset_password(self, email: str, nonce: str, password: str) -> None:
        email = self._normalise_shellkode_email(email)
        if len(str(password)) < 6:
            raise ValueError("Password must contain at least 6 characters")
        item = self.get_user(email)
        if not item or item.get("status") != "active":
            raise ValueError("Password reset link is invalid or has already been used")
        expected = str(item.get("password_reset_nonce_hash") or "")
        actual = hashlib.sha256(str(nonce).encode()).hexdigest()
        if not expected or not hmac.compare_digest(actual, expected):
            raise ValueError("Password reset link is invalid or has already been used")
        timestamp = datetime.now(timezone.utc).isoformat()
        item.update({
            "password_hash": generate_password_hash(str(password)),
            "password_changed_at": timestamp,
            "updated_at": timestamp,
        })
        item.pop("password_reset_nonce_hash", None)
        item.pop("password_reset_sent_at", None)
        self.table.put_item(Item=item)

    def update_user(self, email: str, updates: Dict[str, Any], updated_by: str) -> Dict[str, Any]:
        email = self._normalise_email(email)
        item = self.get_user(email)
        if not item:
            raise LookupError("User not found")
        name = str(updates.get("name", item.get("name", ""))).strip()
        if not name:
            raise ValueError("name is required")
        roles, business_units = self._normalise_roles_and_units(
            updates.get("roles", [updates.get("role", item.get("role", ""))]),
            updates.get("business_unit", item.get("business_unit")),
        )
        role = roles[0]
        business_unit = business_units[0] if business_units else None
        status = str(updates.get("status", item.get("status", "active"))).casefold()
        if status not in {"active", "inactive", "pending_verification"}:
            raise ValueError("status must be active, inactive, or pending_verification")
        item.update({
            "name": name,
            "role": role,
            "roles": roles,
            "business_unit": business_unit or "",
            "business_units": business_units,
            "status": status,
            "updated_at": datetime.now().isoformat(),
            "updated_by": updated_by,
        })
        if updates.get("password"):
            if len(str(updates["password"])) < 6:
                raise ValueError("password must contain at least 6 characters")
            item["password_hash"] = generate_password_hash(str(updates["password"]))
        self.table.put_item(Item=item)
        return self._public_user(item)

    def delete_user(self, email: str) -> None:
        email = self._normalise_email(email)
        item = self.get_user(email)
        if not item:
            raise LookupError("User not found")
        self.table.delete_item(Key={"PK": f"USER#{email}", "SK": "PROFILE"})
        raw_employee_id = str(item.get("employee_id") or "").strip()
        employee_id = self._normalise_employee_id(raw_employee_id, required=False)
        if employee_id is not None:
            keys = {f"EMPLOYEE#{employee_id}"}
            if raw_employee_id:
                keys.add(f"EMPLOYEE#{raw_employee_id.casefold()}")
            for key in keys:
                self.table.delete_item(Key={"PK": key, "SK": "USER"})

    def list_sections(self) -> List[Dict[str, Any]]:
        try:
            response = self.table.get_item(Key={"PK": "CONFIG", "SK": "SOW_SECTIONS"})
            sections = response.get("Item", {}).get("sections")
            if isinstance(sections, list):
                # Retire the former standalone Deliverables section even when
                # an older DynamoDB catalogue still contains it. Deliverables
                # are now represented inside Scope of Work.
                return [
                    section for section in sections
                    if str(section.get("id") or "").casefold() not in {
                        "deliverables", "scope_at_a_glance", "deliverable_scope_at_a_glance"
                    }
                    and str(section.get("label") or "").strip().casefold() != "deliverables"
                ]
        except (BotoCoreError, ClientError) as exc:
            if not isinstance(exc, ClientError) or exc.response.get("Error", {}).get("Code") != "ResourceNotFoundException":
                logger.warning("Section catalogue lookup failed: %s", exc)
        return [dict(item) for item in DEFAULT_SECTION_CATALOGUE]

    def save_sections(self, sections: List[Dict[str, Any]], updated_by: str) -> None:
        self.table.put_item(Item={
            "PK": "CONFIG",
            "SK": "SOW_SECTIONS",
            "sections": sections,
            "updated_by": updated_by,
            "updated_at": datetime.now().isoformat(),
        })


def _auth_secret() -> str:
    secret = os.getenv("AUTH_TOKEN_SECRET", "local-development-secret-change-me")
    environment = os.getenv("APP_ENV", os.getenv("FLASK_ENV", "development")).casefold()
    if environment in {"production", "prod"} and secret == "local-development-secret-change-me":
        raise RuntimeError("AUTH_TOKEN_SECRET must be configured in production")
    return secret


def _serializer() -> URLSafeTimedSerializer:
    secret = _auth_secret()
    return URLSafeTimedSerializer(secret, salt="agentic-sow-rbac")


def issue_token(identity: Identity) -> str:
    return _serializer().dumps(identity.public_dict())


def verify_token(token: str) -> Identity:
    max_age = int(os.getenv("AUTH_TOKEN_TTL_SECONDS", "28800"))
    data = _serializer().loads(token, max_age=max_age)
    return Identity(
        email=str(data["email"]),
        name=str(data["name"]),
        role=str(data["role"]).upper(),
        business_unit=normalise_business_unit(data.get("business_unit")),
        roles=tuple(data.get("roles") or [data["role"]]),
        business_units=tuple(data.get("business_units") or []),
        employee_id=data.get("employee_id"),
    )


def _verification_serializer() -> URLSafeTimedSerializer:
    secret = _auth_secret()
    return URLSafeTimedSerializer(secret, salt="agentic-sow-email-verification")


def issue_verification_token(email: str, nonce: str) -> str:
    return _verification_serializer().dumps({"email": email.casefold().strip(), "nonce": nonce})


def verify_verification_token(token: str) -> tuple[str, str]:
    max_age = int(os.getenv("AUTH_VERIFICATION_TTL_SECONDS", "86400"))
    data = _verification_serializer().loads(str(token), max_age=max_age)
    return str(data["email"]), str(data["nonce"])


def _password_reset_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(_auth_secret(), salt="agentic-sow-password-reset")


def issue_password_reset_token(email: str, nonce: str) -> str:
    return _password_reset_serializer().dumps({"email": email.casefold().strip(), "nonce": nonce})


def verify_password_reset_token(token: str) -> tuple[str, str]:
    max_age = int(os.getenv("AUTH_PASSWORD_RESET_TTL_SECONDS", "3600"))
    data = _password_reset_serializer().loads(str(token), max_age=max_age)
    return str(data["email"]), str(data["nonce"])


def send_verification_email(email: str, token: str) -> None:
    app_url = os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/")
    source = os.getenv("AUTH_FROM_EMAIL", "no-reply@shellkode.com").strip()
    link = f"{app_url}/verify-account?token={token}"
    client = boto3.client(
        "ses",
        region_name=os.getenv("AWS_REGION", "us-east-1"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        aws_session_token=os.getenv("AWS_SESSION_TOKEN"),
        config=BotoConfig(connect_timeout=3, read_timeout=5, retries={"max_attempts": 2}),
    )
    client.send_email(
        Source=source,
        Destination={"ToAddresses": [email]},
        Message={
            "Subject": {"Data": "Verify your ShellKode SOW account", "Charset": "UTF-8"},
            "Body": {
                "Text": {"Data": f"Verify your account by opening this link:\n\n{link}\n\nThis link expires in 24 hours.", "Charset": "UTF-8"},
                "Html": {"Data": (
                    "<p>Welcome to the ShellKode SOW Management Portal.</p>"
                    f'<p><a href="{link}">Verify your account</a></p>'
                    "<p>This link expires in 24 hours.</p>"
                ), "Charset": "UTF-8"},
            },
        },
    )


def send_password_reset_email(email: str, token: str) -> None:
    app_url = os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/")
    source = os.getenv("AUTH_FROM_EMAIL", "no-reply@shellkode.com").strip()
    link = f"{app_url}/reset-password?token={token}"
    client = boto3.client(
        "ses",
        region_name=os.getenv("AWS_REGION", "us-east-1"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        aws_session_token=os.getenv("AWS_SESSION_TOKEN"),
        config=BotoConfig(connect_timeout=3, read_timeout=5, retries={"max_attempts": 2}),
    )
    client.send_email(
        Source=source,
        Destination={"ToAddresses": [email]},
        Message={
            "Subject": {"Data": "Reset your ShellKode SOW account password", "Charset": "UTF-8"},
            "Body": {
                "Text": {"Data": f"Reset your password by opening this link:\n\n{link}\n\nThis link expires in one hour. If you did not request this, ignore this email.", "Charset": "UTF-8"},
                "Html": {"Data": (
                    "<p>A password reset was requested for your ShellKode SOW Management Portal account.</p>"
                    f'<p><a href="{link}">Reset your password</a></p>'
                    "<p>This single-use link expires in one hour. If you did not request this, ignore this email.</p>"
                ), "Charset": "UTF-8"},
            },
        },
    )


def current_identity() -> Identity:
    return g.current_identity


def require_auth(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return jsonify({"success": False, "error": "Authentication required"}), 401
        try:
            token_identity = verify_token(header[7:].strip())
            g.current_identity = RBACStore().active_identity(token_identity.email)
            if not g.current_identity:
                return jsonify({"success": False, "error": "Account is inactive or no longer exists"}), 401
        except SignatureExpired:
            return jsonify({"success": False, "error": "Session expired"}), 401
        except (BadSignature, KeyError, ValueError):
            return jsonify({"success": False, "error": "Invalid session"}), 401
        return view(*args, **kwargs)
    return wrapped


def require_admin(view):
    @require_auth
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_identity().is_admin:
            return jsonify({"success": False, "error": "Administrator access required"}), 403
        return view(*args, **kwargs)
    return wrapped


def scoped_business_unit(identity: Identity, requested: Optional[str] = None) -> Optional[str]:
    if identity.is_admin:
        return normalise_business_unit(requested) if requested else None
    if requested:
        requested_unit = normalise_business_unit(requested)
        if requested_unit not in identity.business_units:
            raise ValueError("You do not have access to this business unit")
        return requested_unit
    return identity.business_unit if len(identity.business_units) == 1 else None


def item_is_visible(item: Dict[str, Any], identity: Identity, requested: Optional[str] = None) -> bool:
    target = scoped_business_unit(identity, requested)
    if identity.is_admin and target is None:
        return True
    if identity.is_user:
        owner_email = str(item.get("owner_email") or item.get("created_by_email") or "").casefold().strip()
        return bool(owner_email) and owner_email == identity.email.casefold().strip()
    try:
        item_unit = normalise_business_unit(item.get("business_unit"))
        return item_unit == target if target else item_unit in identity.business_units
    except ValueError:
        return False


def filter_visible_items(
    items: Iterable[Dict[str, Any]], identity: Identity, requested: Optional[str] = None
) -> List[Dict[str, Any]]:
    return [item for item in items if item_is_visible(item, identity, requested)]


def slugify_section_id(label: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", label.casefold()).strip("_")
    return value[:64]
