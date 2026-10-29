"""Render calculator results without asking an LLM to reproduce money."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re
from typing import Any, Dict, Iterable, List, Tuple


def _safe(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ").strip()


def _money(value: Any) -> str:
    try:
        amount = Decimal(str(value))
        return f"{amount.quantize(Decimal('0.01')):,.2f}" if amount.is_finite() and amount >= 0 else ""
    except (InvalidOperation, ValueError):
        return ""


_CALCULATOR_FIELD_TERMS = (
    "put, copy, post, list", "put/copy/post/list", "get, select", "s3 standard requests",
    "requests to s3", "gb-month", "read request units", "write request units",
    "lambda requests", "duration in milliseconds", "provisioned concurrency",
    "nat gateway", "data transfer out", "log data ingested", "custom metrics",
    "api gateway requests", "step functions state transitions",
)


def _is_workflow_setting(label: str) -> bool:
    """Business rule deadlines and page sizes are not infrastructure volumes."""
    return bool(re.search(
        r'(?i)\b(?:regulatory\s+(?:tat|turnaround)|re[- ]?open(?:ing)?\s+(?:window|period)|'
        r'(?:escalation|reminder|acknowledg\w*)\s+(?:days?|time|deadlines?|intervals?)|'
        r'(?:records?|items?|results?|emails?)\s*(?:per|/)\s*page|page\s+size)\b', label))

_CANONICAL_VOLUME_METRICS = (
    ("Annual interaction volume (design point)", ("annual|year", "conversation|interaction|ticket|case|email")),
    ("Monthly interaction volume", ("month", "conversation|interaction|ticket|case|email")),
    ("Average message turns per interaction", ("turn|message",)),
    ("Interactions requiring model inference", ("inference|llm|model", "percentage|percent|share|conversation|interaction")),
    ("Interactions handled by deterministic journeys", ("deterministic|rule based|rule-based", "percentage|percent|share|conversation|interaction")),
    ("Bot-to-agent handovers", ("handover|hand-off|transfer", "agent|human")),
    ("Backend API calls", ("backend", "api|call")),
    ("Agent Assist AI actions", ("agent assist|copilot", "action|request|user")),
    ("Peak concurrent sessions", ("concurrent|concurrency", "session|user|agent|conversation|interaction")),
    ("Interaction history retention", ("retention|retain|archive", "conversation|interaction|ticket|case|email|history")),
)


def _business_volume_rows(items: Iterable[Any]) -> List[Tuple[str, str]]:
    """Render a stable business workload schema, leaving absent values blank.

    Calculator service fields remain available in the structured pricing result and
    terminal diagnostics, but are deliberately excluded from the SOW.
    """
    candidates: List[Tuple[str, str, str]] = []
    for item in items or []:
        if not isinstance(item, dict) or not item.get("metric") or not item.get("value"):
            continue
        metric = _safe(item["metric"])
        value = _safe(item["value"])
        label = re.sub(r"[_\s]+", " ", metric.casefold())
        if any(term in label for term in _CALCULATOR_FIELD_TERMS):
            continue
        candidates.append((metric, value, label))

    rows: List[Tuple[str, str]] = []
    used = set()
    for display_name, signal_groups in _CANONICAL_VOLUME_METRICS:
        matched_value = ""
        for index, (_metric, value, label) in enumerate(candidates):
            if index in used:
                continue
            if all(re.search(group, label, flags=re.I) for group in signal_groups):
                matched_value = value
                used.add(index)
                break
        # A share of conversations is not a count of API calls. Preserve the
        # supplied metric without silently changing its unit or inventing a rate.
        if display_name == "Backend API calls" and re.search(r"%|\bpercent", matched_value, re.I):
            display_name = "Interactions requiring backend API calls"
        rows.append((display_name, matched_value))
    return rows


def _environment_summary(result: Dict[str, Any]) -> str:
    environments = []
    for service in result.get("services") or []:
        if not isinstance(service, dict):
            continue
        environment = _safe(service.get("environment"))
        if environment and environment.casefold() != "shared" and environment not in environments:
            environments.append(environment)
    return " + ".join(environments)


def _calculator_item(result: Dict[str, Any], qualifier: str = "") -> str:
    details = [item for item in (_environment_summary(result), qualifier) if item]
    return "AWS Pricing Calculator" + (f" ({'; '.join(details)})" if details else "")


def render_aws_pricing_section(result: Dict[str, Any]) -> str:
    """Reference-style monthly summary; no invented environment split or costs."""
    status = str(result.get("status") or "needs_input")
    currency = _safe(result.get("currency") or "USD")
    region = _safe(result.get("region"))
    url = str(result.get("estimate_url") or "").strip()
    # Do not label the calculator homepage as a saved estimate.
    valid_url = bool(re.fullmatch(r"https://calculator\.aws/(?:#?/)?estimate\?id=[A-Za-z0-9_-]+", url))
    link = f"[AWS Pricing Calculator]({url})" if valid_url else ""
    # Keep business sizing concise and workload-specific, never ten generic empty rows.
    metrics = []
    for item in result.get("volume_metrics") or []:
        if not isinstance(item, dict) or not item.get("metric") or item.get("value") in (None, ""):
            continue
        label, value = _safe(item["metric"]), _safe(item["value"])
        label = re.sub(r"[_\s]+", " ", label).strip()
        if any(term in label.casefold() for term in _CALCULATOR_FIELD_TERMS) or _is_workflow_setting(label):
            continue
        if re.search(r"backend.*api", label, re.I) and re.search(r"%|\bpercent", value, re.I):
            label = "Interactions requiring backend API calls"
        pair = f"{label}: {value}"
        if pair not in metrics:
            metrics.append(pair)
    environment = _environment_summary(result)
    item = "AWS infrastructure" + (f" ({environment})" if environment else "")
    rows = []
    fallback = result.get("fallback_estimate") or {}
    if status in {"fallback_priced", "hybrid_priced"}:
        amount = _money(fallback.get("monthly_base"))
        low, high = _money(fallback.get("monthly_low")), _money(fallback.get("monthly_high"))
        qualifier = "Workload planning estimate"
        if status == "hybrid_priced" and link:
            qualifier += f"; calculator-priced components: {link}"
        rows.append((item, amount, qualifier))
    elif status == "partial_priced":
        # A partial calculator subtotal must never masquerade as the whole workload.
        rows.append(("Calculator-priced components only", _money(result.get("calculator_monthly_cost")), link))
        rows.append((item + " total", "", ""))
    elif status in {"priced", "url_only"}:
        rows.append((item, _money(result.get("monthly_cost")), link))
    else:
        rows.append((item, "", ""))
    lines = [f"| Item | Monthly ({currency}) | Estimate |", "|---|---:|---|"]
    lines.extend(f"| {label} | {amount} | {estimate} |" for label, amount, estimate in rows)
    lines.extend(['', '| Pricing basis | Details |', '|---|---|'])
    if region:
        lines.append(f'| AWS region | {region} |')
    for metric in metrics[:3]:
        label, _, value = metric.partition(': ')
        lines.append(f'| {label} | {value} |')
    if status in {'fallback_priced', 'hybrid_priced'}:
        if low and high:
            lines.append(f'| Monthly planning range | {currency} {low}–{high} |')
        lines.append('| Estimate basis | Non-binding planning estimate, not an AWS quote. |')
    if not region and not metrics and status not in {'fallback_priced', 'hybrid_priced'}:
        lines.append('| AWS region |  |')
    return "\n".join(lines).strip()
