"""Authentication, BU scoping, and shared section-catalogue persistence."""

from __future__ import annotations

import os
import re
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
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

    @property
    def is_admin(self) -> bool:
        return self.role == "ADMIN"

    @property
    def is_user(self) -> bool:
        return self.role == "USER"

    @property
    def is_bu_head(self) -> bool:
        return self.role in BUSINESS_UNIT_BY_ROLE

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
                return Identity(
                    email=email,
                    name=str(user.get("name") or email),
                    role=str(user.get("role", "")).upper(),
                    business_unit=(
                        normalise_business_unit(user.get("business_unit"))
                        or BUSINESS_UNIT_BY_ROLE.get(str(user.get("role", "")).upper())
                    ),
                )

        if os.getenv("ENABLE_SAMPLE_USERS", "false").casefold() == "true":
            sample = SAMPLE_USERS.get(email)
            if sample and password == SAMPLE_PASSWORD:
                return Identity(email=email, **sample)
        return None

    def active_identity(self, email: str) -> Optional[Identity]:
        """Load the current role and status so account changes revoke access immediately."""
        email = email.casefold().strip()
        user = self.get_user(email)
        if user:
            if user.get("status", "active") != "active":
                return None
            return Identity(
                email=email,
                name=str(user.get("name") or email),
                role=str(user.get("role", "")).upper(),
                business_unit=(
                    normalise_business_unit(user.get("business_unit"))
                    or BUSINESS_UNIT_BY_ROLE.get(str(user.get("role", "")).upper())
                ),
            )
        if os.getenv("ENABLE_SAMPLE_USERS", "false").casefold() == "true":
            sample = SAMPLE_USERS.get(email)
            if sample:
                return Identity(email=email, **sample)
        return None

    @staticmethod
    def _normalise_email(email: str) -> str:
        email = str(email).casefold().strip()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            raise ValueError("A valid email address is required")
        return email

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

    @staticmethod
    def _public_user(item: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "email": str(item.get("email", "")),
            "name": str(item.get("name", "")),
            "role": str(item.get("role", "")).upper(),
            "business_unit": normalise_business_unit(item.get("business_unit")),
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
    ) -> Dict[str, Any]:
        email = self._normalise_email(email)
        name = str(name).strip()
        if not name:
            raise ValueError("name is required")
        if len(str(password)) < 8:
            raise ValueError("password must contain at least 8 characters")
        role, business_unit = self._normalise_role_and_unit(role, business_unit)
        timestamp = datetime.now().isoformat()
        item = {
            "PK": f"USER#{email}",
            "SK": "PROFILE",
            "email": email,
            "name": name,
            "role": role,
            "business_unit": business_unit or "",
            "password_hash": generate_password_hash(str(password)),
            "status": "active",
            "created_at": timestamp,
            "updated_at": timestamp,
            "updated_by": created_by,
        }
        try:
            self.table.put_item(
                Item=item,
                ConditionExpression="attribute_not_exists(PK)",
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                raise ValueError("A user with this email already exists") from exc
            raise
        return self._public_user(item)

    def update_user(self, email: str, updates: Dict[str, Any], updated_by: str) -> Dict[str, Any]:
        email = self._normalise_email(email)
        item = self.get_user(email)
        if not item:
            raise LookupError("User not found")
        name = str(updates.get("name", item.get("name", ""))).strip()
        if not name:
            raise ValueError("name is required")
        role, business_unit = self._normalise_role_and_unit(
            updates.get("role", item.get("role", "")),
            updates.get("business_unit", item.get("business_unit")),
        )
        status = str(updates.get("status", item.get("status", "active"))).casefold()
        if status not in {"active", "inactive"}:
            raise ValueError("status must be active or inactive")
        item.update({
            "name": name,
            "role": role,
            "business_unit": business_unit or "",
            "status": status,
            "updated_at": datetime.now().isoformat(),
            "updated_by": updated_by,
        })
        if updates.get("password"):
            if len(str(updates["password"])) < 8:
                raise ValueError("password must contain at least 8 characters")
            item["password_hash"] = generate_password_hash(str(updates["password"]))
        self.table.put_item(Item=item)
        return self._public_user(item)

    def delete_user(self, email: str) -> None:
        email = self._normalise_email(email)
        if not self.get_user(email):
            raise LookupError("User not found")
        self.table.delete_item(Key={"PK": f"USER#{email}", "SK": "PROFILE"})

    def list_sections(self) -> List[Dict[str, Any]]:
        try:
            response = self.table.get_item(Key={"PK": "CONFIG", "SK": "SOW_SECTIONS"})
            sections = response.get("Item", {}).get("sections")
            if isinstance(sections, list):
                return sections
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


def _serializer() -> URLSafeTimedSerializer:
    secret = os.getenv("AUTH_TOKEN_SECRET", "local-development-secret-change-me")
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
        business_unit=(
            normalise_business_unit(data.get("business_unit"))
            or BUSINESS_UNIT_BY_ROLE.get(str(data.get("role", "")).upper())
        ),
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
    return identity.business_unit


def item_is_visible(item: Dict[str, Any], identity: Identity, requested: Optional[str] = None) -> bool:
    target = scoped_business_unit(identity, requested)
    if identity.is_admin and target is None:
        return True
    if identity.is_user:
        owner_email = str(item.get("owner_email") or item.get("created_by_email") or "").casefold().strip()
        return bool(owner_email) and owner_email == identity.email.casefold().strip()
    try:
        return normalise_business_unit(item.get("business_unit")) == target
    except ValueError:
        return False


def filter_visible_items(
    items: Iterable[Dict[str, Any]], identity: Identity, requested: Optional[str] = None
) -> List[Dict[str, Any]]:
    return [item for item in items if item_is_visible(item, identity, requested)]


def slugify_section_id(label: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", label.casefold()).strip("_")
    return value[:64]
