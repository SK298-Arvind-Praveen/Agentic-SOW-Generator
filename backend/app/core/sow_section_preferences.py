"""Canonical SOW section customisation shared by preview and generation flows."""

from __future__ import annotations

import json
import re
from typing import Any, Iterable, List, Optional, Set


OPTIONAL_SECTION_IDS = (
    "background_context",
    "detailed_scope",
    "timeline",
    "signatures",
    "pricing",
    "project_team_effort",
    "solution_architecture",
    "open_clarifications",
    "out_of_scope",
    "assumptions_dependencies",
    "success_criteria",
    "testing_acceptance",
    "data_migration",
    "security_compliance",
    "deployment_cutover",
    "customer_responsibilities",
    "risks_mitigations",
    "operations_support",
    "governance_terms",
)

SECTION_LABELS = {
    "background_context": "Background and current state",
    "detailed_scope": "Detailed scope of work",
    "timeline": "Timeline and deliverables",
    "signatures": "Signatures",
    "pricing": "Pricing and implementation cost",
    "project_team_effort": "Project team effort",
    "solution_architecture": "Solution architecture and technical design",
    "open_clarifications": "Open clarifications",
    "out_of_scope": "Out of scope",
    "assumptions_dependencies": "Assumptions and dependencies",
    "success_criteria": "Success criteria",
    "testing_acceptance": "Testing and acceptance",
    "data_migration": "Data migration and readiness",
    "security_compliance": "Security, privacy and compliance",
    "deployment_cutover": "Deployment, cutover and rollback",
    "customer_responsibilities": "Customer responsibilities",
    "risks_mitigations": "Risks and mitigations",
    "operations_support": "Operations and support",
    "governance_terms": "Governance, reporting and terms",
}

MODE_SECTION_IDS = {
    "POC": {
        "background_context", "detailed_scope", "timeline", "signatures",
        "pricing", "project_team_effort", "solution_architecture",
        "open_clarifications", "out_of_scope", "assumptions_dependencies",
        "success_criteria",
    },
    "PROD": set(OPTIONAL_SECTION_IDS) - {"project_team_effort"},
    "POC_TO_PROD": set(OPTIONAL_SECTION_IDS) - {"project_team_effort"},
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

    unknown = sorted(set(value) - set(OPTIONAL_SECTION_IDS))
    if unknown:
        raise ValueError(f"Unknown SOW section option(s): {', '.join(unknown)}")
    requested = set(value)
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
    if normalised in {
        "purpose and scope of this deliverable",
        "deliverable scope at a glance",
        "executive summary and project overview",
        "scope at a glance",
    }:
        return None

    if "acceptance and signator" in normalised:
        return "signatures"
    if "project team effort" in normalised:
        return "project_team_effort"
    if "aws pricing" in normalised or "implementation cost" in normalised:
        return "pricing"
    if "timeline" in normalised or normalised == "duration of work":
        return "timeline"
    if "open clarification" in normalised:
        return "open_clarifications"
    if "out of scope" in normalised:
        return "out_of_scope"
    if "success criteria" in normalised:
        return "success_criteria"
    if "risk" in normalised and "mitigation" in normalised:
        return "risks_mitigations"
    if "day 2" in normalised or "operations and support" in normalised:
        return "operations_support"
    if "testing" in normalised or "deliverable acceptance" in normalised:
        return "testing_acceptance"
    if "data migration" in normalised or "data readiness" in normalised:
        return "data_migration"
    if any(word in normalised for word in ("security", "privacy", "compliance")):
        return "security_compliance"
    if any(word in normalised for word in ("deployment", "cutover", "rollback")):
        return "deployment_cutover"
    if "customer responsibil" in normalised:
        return "customer_responsibilities"
    if "customer dependencies" in normalised or normalised.startswith("assumption"):
        return "assumptions_dependencies"
    if "detailed" in normalised and "scope" in normalised:
        return "detailed_scope"
    if "architecture" in normalised or "technical specifications" in normalised:
        return "solution_architecture"
    if any(phrase in normalised for phrase in (
        "current state", "business context", "about ", "poc evidence",
        "production gap assessment",
    )):
        return "background_context"
    if any(phrase in normalised for phrase in (
        "change management", "project plan termination", "contacts and reporting",
        "marketing authorization", "terms and conditions",
    )):
        return "governance_terms"
    return None


def excluded_section_labels(selected: Iterable[str], mode: str) -> List[str]:
    selected_set = set(selected)
    return [
        SECTION_LABELS[item]
        for item in OPTIONAL_SECTION_IDS
        if item in available_section_ids(mode) and item not in selected_set
    ]
