"""Loss-minimising document chunking and section-specific evidence selection."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional


SECTION_TERMS = {
    "about client": {"company", "organisation", "business", "industry", "customer"},
    "objective": {"objective", "goal", "outcome", "purpose", "problem", "benefit"},
    "overview": {"overview", "background", "current", "problem", "outcome", "context"},
    "scope": {"scope", "requirement", "feature", "module", "workstream", "capability", "deliverable"},
    "deliverable": {"deliverable", "output", "milestone", "acceptance", "phase"},
    "architecture": {"architecture", "component", "service", "aws", "integration", "api", "data flow", "network"},
    "diagram": {"architecture", "component", "service", "integration", "flow", "system", "actor"},
    "dependenc": {"dependency", "prerequisite", "access", "input", "customer", "third-party"},
    "assumption": {"assumption", "condition", "basis", "subject to", "expected"},
    "out of scope": {"exclude", "excluded", "out of scope", "not included", "future"},
    "timeline": {"timeline", "schedule", "week", "month", "phase", "milestone", "duration", "date"},
    "pricing": {"pricing", "price", "cost", "budget", "estimate", "commercial", "consumption"},
    "responsibil": {"responsibility", "owner", "customer", "shellkode", "provide", "approve"},
    "team": {"team", "role", "resource", "effort", "person-day", "fte", "engineer"},
    "clarification": {"clarification", "confirm", "unknown", "pending", "tbd", "question"},
    "success": {"success", "metric", "acceptance", "target", "measure", "validation"},
    "termination": {"termination", "cancel", "notice", "exit", "suspension"},
    "contact": {"contact", "reporting", "governance", "meeting", "escalation", "stakeholder"},
    "terms": {"term", "condition", "liability", "payment", "confidential", "warranty"},
    "acceptance": {"acceptance", "signatory", "signature", "authorised", "approval"},
}


def _normalise(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _paragraphs(text: str) -> List[str]:
    """Create evidence-sized blocks without discarding tables or headings."""
    text = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    raw_parts = re.split(r"\n\s*\n", text)
    blocks: List[str] = []
    for raw in raw_parts:
        part = raw.strip()
        if not part:
            continue
        while len(part) > 4000:
            cut = part.rfind("\n", 0, 4000)
            if cut < 1000:
                cut = part.rfind(". ", 0, 4000)
                cut = cut + 1 if cut >= 1000 else 4000
            blocks.append(part[:cut].strip())
            part = part[cut:].strip()
        if part:
            blocks.append(part)
    return blocks


def chunk_document(text: str, max_chars: int = 120_000, overlap_chars: int = 6_000) -> List[str]:
    """Split a complete document on paragraph boundaries with bounded overlap."""
    max_chars = max(4_000, int(max_chars))
    overlap_chars = max(0, min(int(overlap_chars), max_chars // 3))
    blocks = _paragraphs(text)
    if not blocks:
        return []
    chunks: List[str] = []
    current: List[str] = []
    current_size = 0
    for block in blocks:
        extra = len(block) + (2 if current else 0)
        if current and current_size + extra > max_chars:
            chunk = "\n\n".join(current).strip()
            chunks.append(chunk)
            overlap: List[str] = []
            overlap_size = 0
            for prior in reversed(current):
                if overlap and overlap_size + len(prior) + 2 > overlap_chars:
                    break
                overlap.insert(0, prior)
                overlap_size += len(prior) + 2
            current = overlap
            current_size = len("\n\n".join(current))
        current.append(block)
        current_size += extra
    if current:
        final = "\n\n".join(current).strip()
        if not chunks or final != chunks[-1]:
            chunks.append(final)
    return chunks


def _requirement_terms(requirements: Optional[Dict[str, Any]]) -> set[str]:
    if not isinstance(requirements, dict):
        return set()
    values: List[str] = []
    for key in (
        "key_features", "functional_requirements", "aws_services",
        "integration_details", "key_deliverables", "data_sources",
    ):
        value = requirements.get(key)
        if isinstance(value, list):
            values.extend(map(str, value))
    words = re.findall(r"[a-z0-9][a-z0-9+.-]{2,}", " ".join(values).casefold())
    stop = {"with", "from", "that", "this", "will", "using", "shall", "into", "only", "service"}
    return {word for word in words if word not in stop}


def section_terms(section_name: str, requirements: Optional[Dict[str, Any]] = None) -> set[str]:
    lowered = str(section_name or "").casefold()
    terms = set(re.findall(r"[a-z0-9][a-z0-9+.-]{2,}", lowered))
    for marker, marker_terms in SECTION_TERMS.items():
        if marker in lowered:
            terms.update(marker_terms)
    terms.update(_requirement_terms(requirements))
    return terms


def select_section_evidence(
    text: str,
    section_name: str,
    requirements: Optional[Dict[str, Any]] = None,
    max_chars: int = 24_000,
) -> str:
    """Return diverse, source-order evidence relevant to one SOW section."""
    blocks = _paragraphs(text)
    if not blocks:
        return ""
    terms = section_terms(section_name, requirements)
    scored = []
    for index, block in enumerate(blocks):
        lowered = block.casefold()
        matches = sum(1 for term in terms if term in lowered)
        heading_bonus = 3 if re.match(r"^(?:#{1,6}\s+|\d+(?:\.\d+)*[.)]?\s+|[A-Z][A-Z &/-]{5,})", block) else 0
        table_bonus = 1 if block.count("|") >= 4 else 0
        score = matches + heading_bonus + table_bonus
        if score:
            scored.append((score, index, block))

    # If terminology is sparse, retain early source context rather than return
    # nothing. The authoritative structured baseline still carries all chunks.
    if not scored:
        scored = [(1, index, block) for index, block in enumerate(blocks[:6])]

    chosen = []
    used = 0
    for score, index, block in sorted(scored, key=lambda item: (-item[0], item[1])):
        if used + len(block) + 2 > max_chars and chosen:
            continue
        chosen.append((index, block))
        used += len(block) + 2
        if used >= max_chars:
            break
    chosen.sort(key=lambda item: item[0])
    return "\n\n".join(block for _, block in chosen)[:max_chars].strip()


def combined_source_text(
    supporting_context: Optional[str],
    rag_context: Optional[Dict[str, Any]],
) -> str:
    sources: List[str] = []
    if supporting_context:
        sources.append(str(supporting_context))
    rag_data = (rag_context or {}).get("rag_data", {}) if isinstance(rag_context, dict) else {}
    if isinstance(rag_data, dict) and rag_data.get("extracted_content"):
        sources.append(str(rag_data["extracted_content"]))
    return "\n\n".join(sources)
