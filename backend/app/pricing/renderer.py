"""Render calculator results without asking an LLM to reproduce money."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Dict


def _safe(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ").strip()


def _money(value: Any) -> str:
    try:
        return f"{Decimal(str(value)).quantize(Decimal('0.01')):,.2f}"
    except (InvalidOperation, ValueError):
        return ""


def render_aws_pricing_section(result: Dict[str, Any]) -> str:
    status = str(result.get("status") or "needs_input")
    missing = result.get("missing_inputs") or []
    assumptions = result.get("assumptions") or []
    lines = []
    estimate_url = _safe(result.get("estimate_url"))
    calculator_url = estimate_url or "https://calculator.aws/"
    lines.append(f"**AWS Pricing Calculator Link:** {calculator_url}")

    region = _safe(result.get("region"))
    if region:
        lines.extend([
            "",
            f"The estimate is based on the source-backed sizing inputs below for the `{region}` AWS region. "
            "The service-by-service configuration remains editable through the calculator link.",
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
        lines.extend([
            "",
            f"The editable AWS Calculator estimate currently prices {priced_count} of {planned_count} "
            "source-backed services. Its subtotal is retained below, but it is not presented as the total "
            "architecture cost. The planning total uses the complete workload volumetrics until the remaining "
            "service configurations are confirmed.",
        ])
        cost_lines = [
            "",
            "### AWS Cost Summary",
            "",
            f"| Item | MRR and ARR in {currency} |",
            "|---|---:|",
        ]
        if calculator_monthly:
            cost_lines.append(
                f"| AWS Calculator priced subtotal ({priced_count} of {planned_count} services) | "
                f"{currency} {calculator_monthly} per month |"
            )
        cost_lines.extend([
            f"| Whole-workload planning range | {currency} {low}–{high} per month |",
            f"| Planning MRR (base case) | {currency} {monthly} |",
            f"| Planning ARR (base case) | {currency} {annual} |",
        ])
        excluded = "; ".join(_safe(item) for item in fallback.get("excluded_costs") or [] if item)
        if excluded:
            cost_lines.extend(["", f"Excluded until specifically sized: {excluded}."])
    elif status == "partial_priced" and result.get("estimate_url"):
        currency = _safe(result.get("currency") or "USD")
        calculator_monthly = _money(result.get("calculator_monthly_cost"))
        priced_count = int(result.get("calculator_priced_services") or 0)
        planned_count = int(result.get("calculator_planned_services") or 0)
        lines.extend(["", (
            f"The AWS Calculator currently prices only {priced_count} of {planned_count} source-backed services. "
            "The subtotal is shown for inspection but no architecture-wide MRR or ARR is stated because the "
            "remaining workload lacks sufficient source-backed volumetrics."
        )])
        cost_lines = [
            "",
            "### AWS Cost Summary",
            "",
            f"| Item | Partial cost in {currency} |",
            "|---|---:|",
            f"| AWS Calculator priced subtotal | {currency} {calculator_monthly} per month |",
        ] if calculator_monthly else []
    elif status in {"priced", "url_only"} and result.get("estimate_url"):
        lines.extend([
            "",
            "AWS pricing remains subject to AWS rate changes, taxes, support plans, credits and negotiated discounts.",
        ])
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
                f"| AWS Pricing Calculator estimate | {currency} {monthly} per month |",
                f"| AWS MRR | {currency} {monthly} |",
                f"| AWS ARR | {currency} {annual} |",
            ]
        else:
            cost_lines = ["", "The estimate was validated and saved successfully; open the calculator link for the current calculated total."]
    elif status == "fallback_priced" and result.get("fallback_estimate"):
        fallback = result["fallback_estimate"]
        currency = _safe(result.get("currency") or "USD")
        monthly = _money(fallback.get("monthly_base"))
        low = _money(fallback.get("monthly_low"))
        high = _money(fallback.get("monthly_high"))
        annual = _money(Decimal(str(fallback.get("monthly_base"))) * 12)
        lines.extend([
            "",
            "The AWS calculator could not produce a complete service-level total, so the cost summary below is a "
            "non-binding volumetric planning estimate. It is not an AWS quote and must be replaced by the editable "
            "calculator estimate when service-specific sizing is confirmed.",
        ])
        cost_lines = [
            "",
            "### AWS Cost Summary",
            "",
            f"| Item | MRR and ARR in {currency} |",
            "|---|---:|",
            f"| Volumetric planning range | {currency} {low}–{high} per month |",
            f"| Planning MRR (base case) | {currency} {monthly} |",
            f"| Planning ARR (base case) | {currency} {annual} |",
        ]
        excluded = "; ".join(_safe(item) for item in fallback.get("excluded_costs") or [] if item)
        if excluded:
            cost_lines.extend(["", f"Excluded until specifically sized: {excluded}."])
    elif status == "stale":
        cost_lines = []
        lines.extend(["", (
            "AWS pricing must be recalculated because scope or pricing-relevant content changed after the estimate was created."
        )])
    else:
        cost_lines = []
        lines.extend(["", "AWS pricing is pending completion of a source-backed AWS Pricing Calculator estimate."])
        if result.get("error"):
            lines.extend(["", f"Calculator status: {_safe(result['error'])}"])

    metric_rows = []
    for item in result.get("volume_metrics") or []:
        if isinstance(item, dict) and item.get("metric") and item.get("value"):
            metric_rows.append((_safe(item["metric"]), _safe(item["value"])))
    if metric_rows:
        lines.extend([
            "",
            "### Estimated Volume Metrics",
            "",
            "| Metric | Estimated Volume |",
            "|---|---:|",
        ])
        lines.extend(f"| {metric} | {value} |" for metric, value in metric_rows)
    lines.extend(cost_lines)

    rows = []
    for item in assumptions:
        if isinstance(item, dict):
            rows.append((_safe(item.get("input")), _safe(item.get("basis")), _safe(item.get("status") or "Confirmed")))
    for item in missing:
        if isinstance(item, dict):
            rows.append((_safe(item.get("field") or item.get("input")), _safe(item.get("basis")), _safe(item.get("reason") or "Confirmation required")))
        elif item:
            rows.append((_safe(item), "", "Confirmation required"))
    if rows:
        lines.extend(["", "### Pricing Inputs and Open Confirmations", "", "| Pricing Input | Current Basis | Confirmation Needed |", "|---|---|---|"])
        lines.extend(f"| {a} | {b} | {c} |" for a, b, c in rows[:20])
    return "\n".join(lines).strip()
