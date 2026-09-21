"""Render calculator results without asking an LLM to reproduce money."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re
from typing import Any, Dict, Iterable, List, Tuple


def _safe(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ").strip()


def _money(value: Any) -> str:
    try:
        return f"{Decimal(str(value)).quantize(Decimal('0.01')):,.2f}"
    except (InvalidOperation, ValueError):
        return ""


_CALCULATOR_FIELD_TERMS = (
    "put, copy, post, list", "put/copy/post/list", "get, select", "s3 standard requests",
    "requests to s3", "gb-month", "read request units", "write request units",
    "lambda requests", "duration in milliseconds", "provisioned concurrency",
    "nat gateway", "data transfer out", "log data ingested", "custom metrics",
    "api gateway requests", "step functions state transitions",
)

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
        label = re.sub(r"\s+", " ", metric.casefold())
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


def _blank_cost_lines(result: Dict[str, Any], calculator_value: str = "") -> List[str]:
    currency = _safe(result.get("currency") or "USD")
    return [
        "",
        "### AWS Cost Summary",
        "",
        f"| Item | MRR and ARR in {currency} |",
        "|---|---:|",
        f"| {_calculator_item(result)} | {calculator_value} |",
        "| AWS MRR |  |",
        "| AWS ARR |  |",
    ]


def render_aws_pricing_section(result: Dict[str, Any]) -> str:
    status = str(result.get("status") or "needs_input")
    lines = []
    estimate_url = _safe(result.get("estimate_url"))
    calculator_url = estimate_url or "https://calculator.aws/"
    lines.append(f"**AWS Pricing Calculator Link:** {calculator_url}")

    region = _safe(result.get("region"))
    if region:
        lines.extend([
            "",
            f"The AWS estimate is built for the `{region}` region and is based on the "
            "workload assumptions set out below. Detailed service-level inputs remain editable through "
            "the AWS Pricing Calculator link.",
        ])

    if status == "hybrid_priced" and result.get("fallback_estimate"):
        fallback = result["fallback_estimate"]
        currency = _safe(result.get("currency") or "USD")
        calculator_monthly = _money(result.get("calculator_monthly_cost"))
        monthly = _money(fallback.get("monthly_base"))
        low = _money(fallback.get("monthly_low"))
        high = _money(fallback.get("monthly_high"))
        annual = _money(Decimal(str(fallback.get("monthly_base"))) * 12)
        priced_count = int(result.get("calculator_priced_services") or 0)
        planned_count = int(result.get("calculator_planned_services") or 0)
        cost_lines = [
            "",
            "### AWS Cost Summary",
            "",
            f"| Item | MRR and ARR in {currency} |",
            "|---|---:|",
        ]
        if calculator_monthly:
            cost_lines.append(
                f"| {_calculator_item(result, f'{priced_count} of {planned_count} services priced')} | "
                f"{currency} {calculator_monthly} per month |"
            )
        cost_lines.extend([
            f"| AWS workload planning range | {currency} {low}–{high} per month |",
            f"| AWS MRR (planning base case) | {currency} {monthly} |",
            f"| AWS ARR (planning base case) | {currency} {annual} |",
        ])
    elif status == "partial_priced" and result.get("estimate_url"):
        currency = _safe(result.get("currency") or "USD")
        calculator_monthly = _money(result.get("calculator_monthly_cost"))
        priced_count = int(result.get("calculator_priced_services") or 0)
        planned_count = int(result.get("calculator_planned_services") or 0)
        cost_lines = [
            "",
            "### AWS Cost Summary",
            "",
            f"| Item | MRR and ARR in {currency} |",
            "|---|---:|",
            f"| {_calculator_item(result, f'{priced_count} of {planned_count} services priced')} | {currency} {calculator_monthly} per month |",
            "| AWS MRR |  |",
            "| AWS ARR |  |",
        ] if calculator_monthly else _blank_cost_lines(result)
    elif status in {"priced", "url_only"} and result.get("estimate_url"):
        monthly = _money(result.get("monthly_cost"))
        if monthly:
            annual = _money(Decimal(str(result["monthly_cost"])) * 12)
            currency = _safe(result.get("currency") or "USD")
            cost_lines = [
                "",
                "### AWS Cost Summary",
                "",
                f"| Item | MRR and ARR in {currency} |",
                "|---|---:|",
                f"| {_calculator_item(result)} | {currency} {monthly} per month |",
                f"| AWS MRR | {currency} {monthly} |",
                f"| AWS ARR | {currency} {annual} |",
            ]
        else:
            cost_lines = _blank_cost_lines(result)
    elif status == "fallback_priced" and result.get("fallback_estimate"):
        fallback = result["fallback_estimate"]
        currency = _safe(result.get("currency") or "USD")
        monthly = _money(fallback.get("monthly_base"))
        low = _money(fallback.get("monthly_low"))
        high = _money(fallback.get("monthly_high"))
        annual = _money(Decimal(str(fallback.get("monthly_base"))) * 12)
        lines.extend([
            "",
            "The cost summary is a non-binding volumetric planning range rather than an AWS quote.",
        ])
        cost_lines = [
            "",
            "### AWS Cost Summary",
            "",
            f"| Item | MRR and ARR in {currency} |",
            "|---|---:|",
            f"| AWS Pricing Calculator (workload planning estimate) | {currency} {low}–{high} per month |",
            f"| AWS MRR (planning base case) | {currency} {monthly} |",
            f"| AWS ARR (planning base case) | {currency} {annual} |",
        ]
    elif status == "stale":
        cost_lines = _blank_cost_lines(result)
    else:
        cost_lines = _blank_cost_lines(result)

    metric_rows = _business_volume_rows(result.get("volume_metrics") or [])
    lines.extend([
        "",
        "### Estimated Volume Metrics",
        "",
        "| Metric | Estimated Volume |",
        "|---|---:|",
    ])
    lines.extend(f"| {metric} | {value} |" for metric, value in metric_rows)
    lines.extend(cost_lines)

    return "\n".join(lines).strip()
