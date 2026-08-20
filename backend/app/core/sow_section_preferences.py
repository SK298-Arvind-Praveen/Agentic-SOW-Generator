"""Canonical SOW section customisation shared by preview and generation flows."""

from __future__ import annotations

import json
import re
from typing import Any, Iterable, List, Optional, Set


OPTIONAL_SECTION_IDS = (
    "about_shellkode",
    "about_client",
    "project_overview",
    "scope_of_work",
    "architecture_diagram",
    "customer_dependencies",
    "assumptions",
    "out_of_scope",
    "timelines_deliverables",
    "aws_pricing",
    "customer_responsibilities",
    "project_team_effort",
    "open_clarifications",
    "success_criteria",
    "project_plan_termination",
    "contacts_reporting",
    "terms_conditions",
    "acceptance_signatories",
)

SECTION_LABELS = {
    "about_shellkode": "About Shellkode",
    "about_client": "About Client",
    "project_overview": "Project Overview",
    "scope_of_work": "Scope of Work",
    "architecture_diagram": "Architecture Diagram",
    "customer_dependencies": "Customer Dependencies",
    "assumptions": "Assumptions",
    "out_of_scope": "Out of Scope",
    "timelines_deliverables": "Timelines and Deliverables",
    "aws_pricing": "AWS Pricing",
    "customer_responsibilities": "Customer Responsibilities",
    "project_team_effort": "Project Team Effort",
    "open_clarifications": "Open Clarifications",
    "success_criteria": "Success Criteria",
    "project_plan_termination": "Project Plan Termination",
    "contacts_reporting": "Contacts and Reporting",
    "terms_conditions": "Terms and Conditions",
    "acceptance_signatories": "Acceptance and Signatories",
}

MODE_SECTION_IDS = {
    "POC": set(OPTIONAL_SECTION_IDS),
    "PROD": set(OPTIONAL_SECTION_IDS),
    "POC_TO_PROD": set(OPTIONAL_SECTION_IDS),
}

LEGACY_ID_ALIASES = {
    "background_context": "project_overview",
    "detailed_scope": "scope_of_work",
    "timeline": "timelines_deliverables",
    "signatures": "acceptance_signatories",
    "pricing": "aws_pricing",
    "solution_architecture": "architecture_diagram",
    "assumptions_dependencies": "assumptions",
    "testing_acceptance": "success_criteria",
    "data_migration": "scope_of_work",
    "security_compliance": "architecture_diagram",
    "deployment_cutover": "scope_of_work",
    "risks_mitigations": "assumptions",
    "operations_support": "customer_responsibilities",
    "governance_terms": "terms_conditions",
}


def available_section_ids(mode: str) -> Set[str]:
    return set(MODE_SECTION_IDS.get((mode or "POC").upper(), OPTIONAL_SECTION_IDS))


def parse_selected_section_ids(raw_value: Any, mode: str) -> List[str]:
    """Parse a request value while preserving legacy all-sections behaviour."""
    available = available_section_ids(mode)
    if raw_value is None or raw_value == "":
        return [item for item in OPTIONAL_SECTION_IDS if item in available]

    value = raw_value
    if isinstance(raw_value, str):
        try:
            value = json.loads(raw_value)
        except json.JSONDecodeError as exc:
            raise ValueError("selected_sow_sections must be a JSON array") from exc
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError("selected_sow_sections must be an array of section identifiers")

    unknown = sorted(set(value) - set(OPTIONAL_SECTION_IDS) - set(LEGACY_ID_ALIASES))
    if unknown:
        raise ValueError(f"Unknown SOW section option(s): {', '.join(unknown)}")
    requested = {LEGACY_ID_ALIASES.get(item, item) for item in value}
    return [item for item in OPTIONAL_SECTION_IDS if item in requested and item in available]


def _normalise_title(title: str) -> str:
    title = re.sub(r"^\s*\d+(?:\.\d+)*[.)]?\s*", "", str(title or ""))
    title = title.replace("{AUTHOR_ORG_SHORT}", "author organisation")
    title = title.replace("{COMPANY_NAME}", "customer")
    return re.sub(r"[^a-z0-9]+", " ", title.casefold()).strip()


def section_category(title: str) -> Optional[str]:
    """Return an optional category, or ``None`` for an always-included section."""
    raw = str(title or "")
    normalised = _normalise_title(raw)

    if "{PROJECT_TITLE}" in raw or normalised in {"table of contents", "table_of_contents"}:
        return None
    if normalised.startswith("document control"):
        return None
    if "acceptance and signator" in normalised:
        return "acceptance_signatories"
    if "about author organisation" in normalised:
        return "about_shellkode"
    if "about customer" in normalised:
        return "about_client"
    if normalised.startswith("project overview") or normalised in {
        "purpose and scope of this deliverable",
        "executive summary and project overview",
        "current state",
        "current state and business context",
        "poc evidence and outcomes",
        "production gap assessment",
    }:
        return "project_overview"
    if normalised in {"deliverable scope at a glance", "scope at a glance"}:
        return "scope_of_work"
    if "project team effort" in normalised:
        return "project_team_effort"
    if "implementation cost" in normalised:
        return "project_team_effort"
    if "aws pricing" in normalised:
        return "aws_pricing"
    if "timeline" in normalised or normalised == "duration of work":
        return "timelines_deliverables"
    if "open clarification" in normalised:
        return "open_clarifications"
    if "out of scope" in normalised:
        return "out_of_scope"
    if "success criteria" in normalised:
        return "success_criteria"
    if "testing" in normalised or "deliverable acceptance" in normalised:
        return "success_criteria"
    if any(phrase in normalised for phrase in (
        "technical specifications", "system design", "data migration", "data readiness",
        "security", "privacy", "compliance", "deployment", "cutover", "rollback",
    )):
        return "architecture_diagram"
    if "customer responsibil" in normalised:
        return "customer_responsibilities"
    if "customer dependencies" in normalised:
        return "customer_dependencies"
    if normalised.startswith("assumption") or ("risk" in normalised and "mitigation" in normalised):
        return "assumptions"
    if "detailed" in normalised and "scope" in normalised:
        return "scope_of_work"
    if "architecture" in normalised or "technical specifications" in normalised:
        return "architecture_diagram"
    if "project plan termination" in normalised:
        return "project_plan_termination"
    if "contacts and reporting" in normalised:
        return "contacts_reporting"
    if "terms and conditions" in normalised or "change management" in normalised or "marketing authorization" in normalised:
        return "terms_conditions"
    if "day 2" in normalised or "operations and support" in normalised:
        return "customer_responsibilities"
    return None


def excluded_section_labels(selected: Iterable[str], mode: str) -> List[str]:
    selected_set = set(selected)
    return [
        SECTION_LABELS[item]
        for item in OPTIONAL_SECTION_IDS
        if item in available_section_ids(mode) and item not in selected_set
    ]
