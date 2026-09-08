"""Deterministic quality controls shared by the SOW backend.

The LLM is responsible for synthesis and professional writing.  This module is
responsible for the things an LLM should not be trusted to enforce on its own:
type safety, provenance, missing-information handling, section completeness,
placeholder detection, and cross-stage normalization.
"""

from __future__ import annotations

import copy
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


UNKNOWN_VALUES = {
    "", "unknown", "not specified", "n/a", "na", "none", "null", "tbd",
    "to be determined", "to be confirmed", "not provided",
}

LIST_FIELDS = (
    "key_features", "aws_services", "confirmed_aws_services",
    "proposed_aws_services", "architecture_components", "use_cases",
    "success_metrics", "technical_requirements", "workflow_steps",
    "primary_personas", "compliance_requirements", "performance_requirements",
    "integration_details", "security_requirements", "assumptions",
    "planning_assumptions", "open_clarifications", "out_of_scope",
    "testing_approach", "architecture_notes", "dependencies",
    "key_deliverables", "functional_requirements", "non_functional_requirements",
    "data_sources", "risks_and_mitigations",
)

REQUIRED_GENERATED_KEYS = {
    "POC": {
        "document_control_and_basis", "project_overview",
        "current_state_and_business_context",
        "scope_of_work", "architecture_diagram", "assumptions",
        "open_clarifications", "out_of_scope", "success_criteria",
        "aws_pricing", "shellkode_implementation_cost",
    },
    "PROD": {
        "project_overview", "current_state_and_business_context",
        "scope_of_work",
        "technical_specifications_system_design", "architecture_integrations",
        "customer_dependencies", "assumptions", "open_clarifications",
        "out_of_scope", "timelines_and_deliverables", "testing_and_acceptance_plan",
        "success_criteria", "risks_and_mitigations", "day_2_operations_support",
    },
    "POC_TO_PROD": {
        "project_overview", "poc_evidence_and_outcomes",
        "production_gap_assessment", "scope_of_work",
        "technical_specifications_system_design", "architecture_integrations",
        "migration_cutover_and_rollback", "customer_dependencies", "assumptions",
        "open_clarifications", "out_of_scope", "timelines_and_deliverables",
        "testing_and_acceptance_plan", "success_criteria", "risks_and_mitigations",
        "day_2_operations_support",
    },
}


def is_known(value: Any) -> bool:
    """Return whether a value represents actual supplied/extracted information."""
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() not in UNKNOWN_VALUES
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (tuple, set)):
        return list(value)
    if isinstance(value, str):
        value = value.strip()
        if not value or value.lower() in UNKNOWN_VALUES:
            return []
        return [part.strip() for part in re.split(r"[;\n]+", value) if part.strip()]
    return [value]


def dedupe(items: Iterable[Any]) -> List[Any]:
    result: List[Any] = []
    seen = set()
    for item in items:
        if item is None:
            continue
        key = re.sub(r"\s+", " ", str(item)).strip().casefold()
        if not key or key in UNKNOWN_VALUES or key in seen:
            continue
        seen.add(key)
        result.append(item.strip() if isinstance(item, str) else item)
    return result


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        parsed = int(float(str(value).replace(",", "").strip()))
        return parsed if parsed > 0 else None
    except (TypeError, ValueError):
        return None


def classify_complexity(requirements: Dict[str, Any]) -> str:
    """Conservative planning classification; never presented as a user fact."""
    score = 0
    score += min(len(as_list(requirements.get("key_features"))) // 3, 2)
    score += min(len(as_list(requirements.get("integration_details"))), 3)
    score += min(len(as_list(requirements.get("compliance_requirements"))), 2)
    score += 1 if requirements.get("ui_required") else 0
    score += 1 if len(as_list(requirements.get("aws_services"))) >= 8 else 0
    volume = _positive_int(requirements.get("data_volume_gb")) or 0
    concurrency = _positive_int(requirements.get("concurrent_users")) or 0
    score += 1 if volume >= 100 else 0
    score += 1 if concurrency >= 100 else 0
    if score <= 2:
        return "simple"
    if score <= 5:
        return "moderate"
    if score <= 8:
        return "complex"
    return "enterprise"


def _recommended_duration(mode: str, complexity: str) -> int:
    if mode == "POC":
        return {"simple": 4, "moderate": 6, "complex": 8, "enterprise": 10}[complexity]
    return {"simple": 8, "moderate": 12, "complex": 16, "enterprise": 20}[complexity]


def _clarification(label: str, impact: str) -> str:
    return f"{label} - confirm before baseline approval; this affects {impact}."


def normalize_requirements(
    requirements: Dict[str, Any] | None,
    objective: str = "",
    mode: str = "POC",
) -> Dict[str, Any]:
    """Normalize requirements without silently converting unknowns into commitments."""
    mode = (mode or "POC").upper()
    req: Dict[str, Any] = copy.deepcopy(requirements or {})
    req["_original_objective"] = objective or req.get("_original_objective", "")
    req["_document_mode"] = mode

    for field in LIST_FIELDS:
        req[field] = dedupe(as_list(req.get(field)))

    data_characteristics = req.get("data_characteristics")
    if not isinstance(data_characteristics, dict):
        data_characteristics = {}
    req["data_characteristics"] = {
        "volume": data_characteristics.get("volume") if is_known(data_characteristics.get("volume")) else None,
        "format": data_characteristics.get("format") if is_known(data_characteristics.get("format")) else None,
        "access_pattern": data_characteristics.get("access_pattern") if is_known(data_characteristics.get("access_pattern")) else None,
        "retention": data_characteristics.get("retention") if is_known(data_characteristics.get("retention")) else None,
        "classification": data_characteristics.get("classification") if is_known(data_characteristics.get("classification")) else None,
    }

    accuracy = req.get("accuracy_metrics")
    if not isinstance(accuracy, dict):
        accuracy = {}
    target = accuracy.get("target_percentage")
    try:
        target = float(target) if target is not None else None
    except (TypeError, ValueError):
        target = None
    if target is not None and not 0 < target <= 100:
        target = None
    req["accuracy_metrics"] = {
        "target_percentage": target,
        "measurement_method": accuracy.get("measurement_method") if is_known(accuracy.get("measurement_method")) else None,
        "domain_constraints": accuracy.get("domain_constraints") if is_known(accuracy.get("domain_constraints")) else None,
    }

    for field in ("data_volume_gb", "concurrent_users", "duration_weeks", "mrr_estimate"):
        req[field] = _positive_int(req.get(field))

    complexity = classify_complexity(req)
    req["_complexity"] = complexity
    req["planning_duration_weeks"] = req.get("duration_weeks") or _recommended_duration(mode, complexity)
    req["timeline_is_assumption"] = req.get("duration_weeks") is None and not is_known(req.get("timeline"))

    if not is_known(req.get("project_overview")):
        req["project_overview"] = (
            f"The engagement will address the following stated need: {objective.strip()}"
            if objective.strip() else
            "The engagement objective requires confirmation during discovery."
        )

    provenance = req.get("requirements_provenance")
    if not isinstance(provenance, dict):
        provenance = {}
    req["requirements_provenance"] = provenance

    # Preserve the distinction between named services and an architect's proposal.
    explicit_services = dedupe(as_list(req.get("confirmed_aws_services")))
    proposed_services = dedupe(as_list(req.get("proposed_aws_services")))
    all_services = dedupe(as_list(req.get("aws_services")))
    if not explicit_services and provenance.get("aws_services") == "confirmed":
        explicit_services = all_services
    if not explicit_services and not proposed_services:
        proposed_services = all_services
    req["confirmed_aws_services"] = explicit_services
    req["proposed_aws_services"] = proposed_services
    req["aws_services"] = dedupe(explicit_services + proposed_services)

    clarifications = list(req.get("open_clarifications", []))
    assumptions = list(req.get("planning_assumptions", []))
    if req["timeline_is_assumption"]:
        assumptions.append(
            f"A {req['planning_duration_weeks']}-week planning horizon is used to structure the draft schedule; it is not a committed date baseline."
        )
        clarifications.append(_clarification("Target start date and committed duration", "milestones, staffing, and commercials"))
    if req.get("data_volume_gb") is None and not is_known(req["data_characteristics"].get("volume")):
        clarifications.append(_clarification("Representative and peak data volumes", "sizing, performance testing, and AWS cost"))
    if req.get("concurrent_users") is None:
        clarifications.append(_clarification("Expected users, peak concurrency, and transaction rate", "capacity and load-test acceptance"))
    if not req["performance_requirements"]:
        clarifications.append(_clarification("Latency, throughput, availability, RTO, and RPO targets", "non-functional acceptance"))
    if not req["accuracy_metrics"].get("target_percentage") and any(
        token in (objective or "").lower() for token in ("ai", "ml", "model", "extract", "classif", "agent")
    ):
        clarifications.append(_clarification("Benchmark dataset and AI quality threshold", "model validation and acceptance"))
    if not is_known(req["data_characteristics"].get("retention")):
        clarifications.append(_clarification("Retention, deletion, and archival policy", "data lifecycle controls and cost"))
    if not req["integration_details"]:
        clarifications.append(_clarification("External systems, owners, interfaces, and authentication methods", "integration scope and dependencies"))
    if not req["compliance_requirements"]:
        clarifications.append(_clarification("Applicable regulatory, privacy, and internal security standards", "security design and evidence"))

    req["open_clarifications"] = dedupe(clarifications)
    req["planning_assumptions"] = dedupe(assumptions)
    req.setdefault("confirmed_requirements", {})
    req.setdefault("source_basis", [])
    return req


def merge_requirement_extractions(extractions: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Merge chunk-level POC extractions without dropping later-document evidence."""
    merged: Dict[str, Any] = {}
    for extraction in extractions:
        if not isinstance(extraction, dict):
            continue
        for key, value in extraction.items():
            if isinstance(value, list):
                merged[key] = dedupe(as_list(merged.get(key)) + value)
            elif isinstance(value, dict):
                current = merged.get(key) if isinstance(merged.get(key), dict) else {}
                merged[key] = {**current, **{k: v for k, v in value.items() if is_known(v)}}
            elif is_known(value) and not is_known(merged.get(key)):
                merged[key] = value
    return merged


def clean_markdown_preserving_structure(text: str) -> str:
    """Remove generation debris while preserving headings, lists, and tables."""
    if not text:
        return text
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"^```(?:markdown|md|text)?\s*$", "", text, flags=re.I | re.M)
    text = re.sub(r"^```\s*$", "", text, flags=re.M)
    text = re.sub(r"(?m)^\s*(?:\*{3,}|_{3,})\s*$", "", text)
    text = re.sub(r"(?m)^\s*-{4,}\s*$", "", text)
    # Blank editable placeholders instead of printing synthetic values. Keep
    # narrative statements such as "the threshold is not specified in the BRD"
    # intact; only standalone values, list items, and table cells are cleared.
    display_unknowns = {
        "unknown", "not specified", "not provided", "n/a", "na", "none",
        "null", "tbd", "to be determined", "to be confirmed",
    }
    cleaned_lines: List[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = line.strip().strip("|").split("|")
            cleaned_cells = []
            for cell in cells:
                normalised = re.sub(r"[`*_]", "", cell).strip().casefold()
                cleaned_cells.append("" if normalised in display_unknowns else cell.strip())
            line = "| " + " | ".join(cleaned_cells) + " |"
        else:
            bullet = re.match(r"^(\s*[-*•]\s+)(.+?)\s*$", line)
            if bullet and re.sub(r"[`*_]", "", bullet.group(2)).strip().casefold() in display_unknowns:
                continue
            if re.sub(r"[`*_]", "", stripped).strip().casefold() in display_unknowns:
                line = ""
            else:
                line = re.sub(
                    r"(?i)(:\s*)(?:unknown|not specified|not provided|n/?a|none|null|tbd|to be determined|to be confirmed)\s*$",
                    r"\1",
                    line,
                )
        cleaned_lines.append(line)
    text = "\n".join(cleaned_lines)
    text = re.sub(r"[ \t]+$", "", text, flags=re.M)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def section_quality_issues(content: str, section_name: str = "") -> List[str]:
    issues: List[str] = []
    normalized = clean_markdown_preserving_structure(str(content or ""))
    if len(normalized) < 80:
        issues.append("content is missing or too short")
    lowered = normalized.lower()
    if any(marker in lowered for marker in ("generation failed", "please regenerate", "lorem ipsum")):
        issues.append("contains a generation-failure placeholder")
    if re.search(r"\b(?:xxx|tbd)\b|\{[A-Za-z_][^{}]*\}", normalized, re.I):
        issues.append("contains unresolved placeholders")
    if section_name and re.match(rf"^##\s+{re.escape(section_name)}\s*$", normalized, re.I):
        issues.append("contains only a duplicate section heading")
    return issues


def validate_generated_sections(
    sections: Dict[str, Any],
    mode: str,
    required_keys: Optional[Iterable[str]] = None,
) -> Tuple[List[str], List[str]]:
    """Return (missing_keys, quality_messages) for deterministic generation gating."""
    mode = (mode or "POC").upper()
    required = (
        set(required_keys)
        if required_keys is not None
        else REQUIRED_GENERATED_KEYS.get(mode, REQUIRED_GENERATED_KEYS["POC"])
    )
    missing = sorted(key for key in required if not sections.get(key))
    issues: List[str] = []
    for key, value in sections.items():
        if key in {"cover_page", "toc_structure"}:
            continue
        for issue in section_quality_issues(str(value or ""), key.replace("_", " ")):
            issues.append(f"{key}: {issue}")
    return missing, issues
