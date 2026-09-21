"""Canonical SOW section customisation shared by preview and generation flows."""

from __future__ import annotations

import json
import re
from typing import Any, Iterable, List, Optional, Set


OPTIONAL_SECTION_IDS = (
    "document_version_control",
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
    "document_version_control": "Document Version Control",
    "about_shellkode": "About Shellkode",
    "about_client": "About Client",
    "project_overview": "Objective",
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

RETIRED_SECTION_IDS = {
    "deliverables", "scope_at_a_glance", "deliverable_scope_at_a_glance",
}


def available_section_ids(mode: str) -> Set[str]:
    return set(MODE_SECTION_IDS.get((mode or "POC").upper(), OPTIONAL_SECTION_IDS))


def section_catalogue() -> List[dict]:
    try:
        from app.core.access_control import RBACStore
        return RBACStore().list_sections()
    except Exception:
        return [{"id": item, "label": SECTION_LABELS[item], "prompt": "", "custom": False}
                for item in OPTIONAL_SECTION_IDS]


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

    unknown = sorted(
        item for item in value
        if item not in available
        and item not in LEGACY_ID_ALIASES
        and not re.fullmatch(r"[a-z0-9_]{1,64}", item)
    )
    if unknown:
        raise ValueError(f"Unknown SOW section option(s): {', '.join(unknown)}")
    # Preserve the user's drag-and-drop order.  The previous set-based
    # normalisation silently restored the template's canonical order before the
    # request reached the writer.  Canonicalise legacy IDs and de-duplicate
    # stably instead.
    selected: List[str] = []
    seen: Set[str] = set()
    for item in value:
        canonical = LEGACY_ID_ALIASES.get(item, item)
        if canonical in RETIRED_SECTION_IDS:
            continue
        if (canonical in available or re.fullmatch(r"[a-z0-9_]{1,64}", canonical)) and canonical not in seen:
            selected.append(canonical)
            seen.add(canonical)
    return selected


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
    if normalised.startswith("document control") or normalised.startswith("document version control"):
        return "document_version_control"
    if "acceptance and signator" in normalised:
        return "acceptance_signatories"
    if (
        "about author organisation" in normalised
        or normalised in {"about shellkode", "about shellkode pvt ltd"}
    ):
        return "about_shellkode"
    if "about customer" in normalised:
        return "about_client"
    if normalised.startswith("project overview") or normalised in {
        "objective",
        "purpose and scope of this deliverable",
        "executive summary and project overview",
        "current state",
        "current state and business context",
        "poc evidence and outcomes",
        "production gap assessment",
        "production enablement plan",
    }:
        return "project_overview"
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
    if normalised == "scope of work" or ("detailed" in normalised and "scope" in normalised):
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


def infer_selected_section_ids(document_text: str, mode: str = "POC") -> List[str]:
    """Recover legacy section choices from a finalized SOW's visible headings.

    Older DynamoDB rows predate persisted section preferences. Regeneration must
    preserve their actual document shape instead of interpreting a missing field
    as the current template's all-sections default.
    """
    available = available_section_ids(mode)
    selected: List[str] = []
    seen: Set[str] = set()
    for raw_line in str(document_text or "").splitlines():
        numbering = re.match(r"^\s*\d+(?:\.(\d+))?[.)]?\s+", raw_line)
        if numbering and numbering.group(1) is not None:
            # Module/subsection headings must not activate unrelated optional
            # top-level sections (for example "Testing" inside Scope of Work).
            continue
        title = re.sub(r"^\s*\d+(?:\.\d+)*[.)]?\s*", "", raw_line).strip()
        # Ignore body prose and TOC page-number suffixes while accepting the
        # short top-level headings emitted by every supported template.
        title = re.sub(r"\s+\d+\s*$", "", title).strip()
        if not title or len(title) > 100:
            continue
        normalised = _normalise_title(title)
        if not numbering and not (
            normalised.startswith("about ")
            or normalised in {_normalise_title(value) for value in SECTION_LABELS.values()}
            or normalised in {"solution architecture aws", "timeline and deliverables"}
        ):
            continue
        category = section_category(title)
        if normalised.startswith("about ") and category is None:
            category = (
                "about_shellkode"
                if "shellkode" in normalised
                else "about_client"
            )
        if category in available and category not in seen:
            selected.append(category)
            seen.add(category)
    return selected
