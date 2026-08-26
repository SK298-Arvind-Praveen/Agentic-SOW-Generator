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
from werkzeug.security import check_password_hash


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

        if os.getenv("ENABLE_SAMPLE_USERS", "true").casefold() == "true":
            sample = SAMPLE_USERS.get(email)
            if sample and password == SAMPLE_PASSWORD:
                return Identity(email=email, **sample)
        return None

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
            g.current_identity = verify_token(header[7:].strip())
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
