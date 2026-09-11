"""Evidence-gated AWS Pricing Calculator orchestration."""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import boto3

from app.core.bedrock_llm import BedrockLLM
from app.core.document_context import select_section_evidence
from .mcp_client import CalculatorMcpClient, PricingCalculatorError


def _json_object(text: str) -> Dict[str, Any]:
    value = str(text or "").strip()
    value = re.sub(r"^```(?:json)?\s*|\s*```$", "", value, flags=re.I)
    start, end = value.find("{"), value.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        parsed = json.loads(value[start:end + 1])
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _normalise_evidence(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _numeric_values(value: Any) -> set[str]:
    values: set[str] = set()
    if isinstance(value, dict):
        for child in value.values():
            values.update(_numeric_values(child))
    elif isinstance(value, list):
        for child in value:
            values.update(_numeric_values(child))
    elif isinstance(value, (str, int, float)) and not isinstance(value, bool):
        for token in re.findall(r"\d+(?:\.\d+)?", str(value)):
            try:
                normalised = format(Decimal(token).normalize(), "f")
                values.add("0" if normalised in {"-0", ""} else normalised)
            except InvalidOperation:
                values.add(token)
    return values


def _valid_aws_region(value: Any) -> bool:
    """Accept standard commercial AWS region identifiers, not prose."""
    return bool(re.fullmatch(r"[a-z]{2}(?:-gov)?-[a-z]+-\d", str(value or "").strip()))


def _field_contracts(fields: Any) -> Dict[str, Dict[str, Any]]:
    rows = fields.get("fields", []) if isinstance(fields, dict) else []
    return {
        str(row.get("id")): row
        for row in rows
        if isinstance(row, dict) and row.get("id")
    }


CALCULATOR_SERVICE_CODES = {
    "bedrock": ("amazon", "Amazon Bedrock (Amazon model provider)"),
    "sagemaker": ("sageMakerServerlessInference", "Amazon SageMaker Serverless Inference"),
    "api gateway": ("amazonApiGateway", "Amazon API Gateway"),
    "cognito": ("amazonCognito", "Amazon Cognito"),
    "cloudwatch": ("amazonCloudWatch", "Amazon CloudWatch"),
    "dynamodb": ("dynamoDbOnDemand", "Amazon DynamoDB on-demand capacity"),
    "simple storage service": ("amazonS3Standard", "Amazon S3 Standard"),
    "s3": ("amazonS3Standard", "Amazon S3 Standard"),
    "amazon s3": ("amazonS3Standard", "Amazon S3 Standard"),
    "simple notification service": ("standardTopics", "Amazon SNS Standard topics"),
    "sns": ("standardTopics", "Amazon SNS Standard topics"),
    "amazon sns": ("standardTopics", "Amazon SNS Standard topics"),
    "simple email service": ("amazonSimpleEmailService", "Amazon Simple Email Service"),
    "ses": ("amazonSimpleEmailService", "Amazon Simple Email Service"),
    "amazon ses": ("amazonSimpleEmailService", "Amazon Simple Email Service"),
    "lambda": ("aWSLambda", "AWS Lambda"),
    "secrets manager": ("awsSecretsManager", "AWS Secrets Manager"),
    "opensearch": ("amazonElasticsearchService", "Amazon OpenSearch Service"),
    "redshift": ("amazonRedshift", "Amazon Redshift"),
    "quicksight": ("amazonQuickSightReadersAuthorsSpice", "Amazon QuickSight"),
    "quick sight": ("amazonQuickSightReadersAuthorsSpice", "Amazon QuickSight"),
    "step functions": ("stepFunctionStandard", "AWS Step Functions Standard"),
}


def _scaled_numbers(value: Any) -> List[float]:
    """Read Indian/international volume notation without inventing a unit."""
    text = str(value or "").casefold().replace(",", "")
    scale = 1.0
    if "crore" in text:
        scale = 10_000_000.0
    elif "lakh" in text or "lac" in text:
        scale = 100_000.0
    elif "million" in text:
        scale = 1_000_000.0
    elif re.search(r"\d(?:\.\d+)?\s*k\b", text):
        scale = 1_000.0
    values = [float(item) * scale for item in re.findall(r"\d+(?:\.\d+)?", text)]
    return values


class AwsPricingService:
    """Turn source-backed sizing facts into a validated calculator estimate."""

    def __init__(
        self,
        config: Any,
        llm: Optional[Any] = None,
        client_factory: Optional[Callable[[], Any]] = None,
    ):
        self.config = config
        if llm is None:
            bedrock = boto3.client(
                "bedrock-runtime",
                region_name=config.BEDROCK_REGION,
                config=config.BOTO_CONFIG,
            )
            llm = BedrockLLM(config, bedrock)
        self.llm = llm
        self.client_factory = client_factory or self._default_client

    def _default_client(self):
        return CalculatorMcpClient(
            Path(self.config.AWS_PRICING_CALCULATOR_BUNDLE),
            node_binary=self.config.AWS_PRICING_NODE_BINARY,
            timeout=self.config.AWS_PRICING_TIMEOUT_SECONDS,
        )

    def generate(
        self,
        requirements: Dict[str, Any],
        metadata: Dict[str, Any],
        supporting_context: str = "",
    ) -> Dict[str, Any]:
        base = {
            "status": "needs_input",
            "currency": "USD",
            "region": str(metadata.get("pricing_region") or "").strip(),
            "estimate_url": None,
            "estimate_id": None,
            "monthly_cost": None,
            "monthly_by_service": {},
            "assumptions": [],
            "missing_inputs": [],
            "services": [],
            "volume_metrics": [],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "calculator_version": "1.3.0",
        }
        if not getattr(self.config, "AWS_PRICING_ENABLED", True):
            return {**base, "status": "disabled", "error": "AWS pricing integration is disabled"}

        source_text = "\n".join(filter(None, [
            supporting_context,
            str(requirements.get("_original_objective") or ""),
            str(requirements.get("_generation_guidance") or ""),
        ]))
        try:
            candidates = self._candidate_services(requirements, metadata, source_text)
            print(
                f"[PRICING] Planning region={base['region'] or 'not supplied'}; "
                f"candidate_services={len(candidates)}; source_chars={len(source_text)}",
                flush=True,
            )
            plan = self._plan(requirements, metadata, source_text)
            source_region = str(plan.get("region") or "").strip()
            if source_region and _normalise_evidence(source_region) not in _normalise_evidence(source_text):
                source_region = ""
            region = str(metadata.get("pricing_region") or source_region).strip()
            if region and not _valid_aws_region(region):
                base["missing_inputs"].append({
                    "field": "AWS region",
                    "basis": region,
                    "reason": "Enter a valid AWS region code such as ap-south-1",
                })
                region = ""
            base["region"] = region
            if not region:
                base["missing_inputs"].append({
                    "field": "AWS region", "basis": "", "reason": "Select or provide the deployment region"
                })

            planned_services = self._validated_plan_services(plan, candidates, source_text)
            base["volume_metrics"] = self._validated_volume_metrics(plan, source_text)
            print(
                f"[PRICING] Extracted source-backed services={len(planned_services)}/{len(candidates)}; "
                f"volume_metrics={len(base['volume_metrics'])}",
                flush=True,
            )
            # Show every confirmed source-backed input even when one missing
            # field prevents a calculator URL from being built.
            base["assumptions"] = self._assumption_rows(
                {**plan, "services": planned_services}, region
            )
            if not planned_services:
                for service_name in self._candidate_services(requirements, metadata, source_text)[:12]:
                    base["missing_inputs"].extend(self._missing_for_service(service_name))
                if not base["missing_inputs"]:
                    base["missing_inputs"].append({
                        "field": "AWS services",
                        "basis": "",
                        "reason": "Confirm which AWS services are required before estimating infrastructure cost",
                    })
            if not region or not planned_services:
                return self._pricing_fallback(
                    base, candidates, "calculator-ready region or service sizing was incomplete"
                )

            with self.client_factory() as client:
                entries = []
                for service in planned_services[:12]:
                    service = self._enrich_service_with_volumetrics(
                        service, base["volume_metrics"]
                    )
                    entry, missing = self._prepare_service(client, service, region)
                    base["missing_inputs"].extend(missing)
                    if entry:
                        for assumption in service.get("planning_assumptions") or []:
                            base["assumptions"].append({
                                "input": f"{service['service_name']} – planning basis",
                                "basis": str(assumption),
                                "status": "Proposed for calculator sizing",
                            })
                        entries.append(entry)
                        base["services"].append({
                            "service": service["service_name"],
                            "service_code": entry["service"],
                            "environment": service.get("environment") or "Shared",
                            "source": service.get("evidence_quote") or "Source requirements",
                        })
                        print(f"[PRICING] Mapped {service['service_name']} to calculator fields", flush=True)
                    else:
                        print(
                            f"[PRICING] Skipped {service['service_name']}: "
                            f"{len(missing)} required input(s) unresolved",
                            flush=True,
                        )
                if not entries:
                    print("[PRICING] No calculator-ready service configurations", flush=True)
                    return self._pricing_fallback(
                        base, candidates, "no service had a complete calculator field configuration"
                    )
                print(f"[PRICING] Building estimate with {len(entries)} service configuration(s)", flush=True)
                base["calculator_priced_services"] = len(entries)
                base["calculator_planned_services"] = len(planned_services)
                base["calculator_candidate_services"] = len(candidates)
                result = client.call("build_estimate", {
                    "services": json.dumps(entries, separators=(",", ":")),
                    "name": "SOW infrastructure estimate",
                    "partition": "aws",
                })
                if not isinstance(result, dict) or not result.get("sharable_url"):
                    failed = {
                        **base,
                        "status": "failed",
                        "error": self._calculator_message(result),
                    }
                    return self._pricing_fallback(
                        failed, candidates, "the AWS calculator did not return a saved estimate"
                    )
                base.update({
                    "status": "url_only",
                    "estimate_url": result.get("sharable_url"),
                    "estimate_id": result.get("aws_estimate_id") or result.get("estimate_id"),
                })
                print(f"[PRICING] Estimate link created id={base['estimate_id'] or 'unavailable'}", flush=True)

            if metadata.get("pricing_read_cost", True):
                cost = self._read_cost(str(base["estimate_url"]))
                if cost.get("monthlyCost") is not None:
                    base["monthly_cost"] = cost["monthlyCost"]
                    base["calculator_monthly_cost"] = cost["monthlyCost"]
                    base["monthly_by_service"] = cost.get("monthlyByService") or {}
                    base["status"] = "priced"
                    print(f"[PRICING] Monthly calculator total read successfully: {base['monthly_cost']}", flush=True)
                elif cost.get("error"):
                    base["cost_read_warning"] = cost["error"]
                    print(f"[PRICING] Estimate created; monthly total unavailable: {cost['error']}", flush=True)
            if base["status"] == "url_only" and base.get("monthly_cost") is None:
                return self._pricing_fallback(
                    base, candidates, "the saved calculator estimate total could not be read"
                )
            if (
                base["status"] == "priced"
                and len(entries) < len(planned_services)
                and base.get("missing_inputs")
            ):
                return self._pricing_fallback(
                    base,
                    candidates,
                    f"the calculator priced {len(entries)} of {len(planned_services)} source-backed services",
                )
            return base
        except (PricingCalculatorError, OSError, subprocess.SubprocessError) as exc:
            print(f"[PRICING] Calculator unavailable: {exc}", flush=True)
            return self._pricing_fallback(
                {**base, "status": "failed", "error": str(exc)},
                locals().get("candidates", []),
                "the AWS calculator runtime was unavailable",
            )
        except Exception as exc:
            print(f"[PRICING] Pricing workflow failed; generation halted: {exc}", flush=True)
            raise

    @staticmethod
    def _with_volumetric_fallback(
        result: Dict[str, Any],
        candidate_services: List[str],
        reason: str,
    ) -> Dict[str, Any]:
        """Produce a transparent planning range when the calculator cannot price.

        This deliberately estimates only interaction-driven platform usage. It
        does not pretend to reproduce an AWS quote or silently guess instance,
        telephony, storage-retention, support-plan or data-transfer settings.
        """
        metrics = [item for item in result.get("volume_metrics") or [] if isinstance(item, dict)]
        interaction_rows = []
        for item in metrics:
            label = str(item.get("metric") or "").casefold()
            value = str(item.get("value") or "")
            if not any(word in label for word in (
                "conversation", "interaction", "transaction", "ticket", "case", "email",
            )):
                continue
            numbers = _scaled_numbers(value)
            if not numbers:
                continue
            is_monthly = "month" in label or "per month" in value.casefold()
            is_annual = any(word in label for word in ("annual", "year")) or "per year" in value.casefold()
            if not is_monthly and not is_annual:
                continue
            monthly = numbers if is_monthly else [number / 12.0 for number in numbers]
            priority = 0 if ("design" in label or is_monthly) else 1
            interaction_rows.append((priority, monthly, str(item.get("metric") or "Workload volume")))
        if not interaction_rows or not candidate_services:
            if result.get("estimate_url"):
                return {
                    **result,
                    "status": "partial_priced",
                    "calculator_monthly_cost": result.get("calculator_monthly_cost", result.get("monthly_cost")),
                    "monthly_cost": None,
                }
            return result
        interaction_rows.sort(key=lambda row: row[0])
        volumes = interaction_rows[0][1]
        monthly_low, monthly_high = min(volumes), max(volumes)
        monthly_base = sorted(volumes)[len(volumes) // 2]

        turns = 1.0
        for item in metrics:
            label = str(item.get("metric") or "").casefold()
            if "turn" in label or "message" in label:
                numbers = _scaled_numbers(item.get("value"))
                if numbers:
                    turns = sum(numbers) / len(numbers)
                    break
        backend_ratio = 0.0
        for item in metrics:
            label = str(item.get("metric") or "").casefold()
            if "backend" in label and ("percent" in label or "%" in str(item.get("value") or "")):
                numbers = _scaled_numbers(item.get("value"))
                if numbers:
                    backend_ratio = min(1.0, (sum(numbers) / len(numbers)) / 100.0)
                    break

        # These are explicitly broad planning coefficients, not published AWS
        # prices: interaction orchestration + message/AI processing + API load.
        # The range absorbs model, token, cache and runtime variability until
        # the editable calculator has complete service-specific inputs.
        def estimate(volume: float, multiplier: float) -> float:
            messages = volume * max(1.0, turns)
            backend_calls = messages * backend_ratio
            base_cost = volume * 0.006 + messages * 0.00012 + backend_calls * 0.000003
            return round(max(1.0, base_cost * multiplier), 2)

        low = estimate(monthly_low, 0.45)
        base_cost = estimate(monthly_base, 1.0)
        high = estimate(monthly_high, 2.2)
        fallback = {
            "method": "volumetric_planning_range_v1",
            "reason": reason,
            "monthly_low": low,
            "monthly_base": base_cost,
            "monthly_high": high,
            "workload_metric": interaction_rows[0][2],
            "monthly_interactions_low": round(monthly_low),
            "monthly_interactions_base": round(monthly_base),
            "monthly_interactions_high": round(monthly_high),
            "average_turns": round(turns, 2),
            "backend_call_ratio": round(backend_ratio, 4),
            "excluded_costs": [
                "telephony and carrier charges",
                "reserved or provisioned capacity",
                "support plans, taxes, credits and discounts",
                "storage retention and data transfer without sourced quantities",
            ],
        }
        has_partial_calculator = bool(result.get("estimate_url"))
        updated = {
            **result,
            "status": "hybrid_priced" if has_partial_calculator else "fallback_priced",
            "monthly_cost": base_cost,
            "fallback_estimate": fallback,
        }
        if has_partial_calculator:
            updated["calculator_monthly_cost"] = result.get("calculator_monthly_cost")
        print(
            f"[PRICING] {'Partial calculator result supplemented' if has_partial_calculator else 'Calculator result unavailable'}; "
            f"volumetric fallback="
            f"{updated['currency']} {low:,.2f}-{high:,.2f}/month "
            f"(base {base_cost:,.2f}; interactions {monthly_low:,.0f}-{monthly_high:,.0f}/month)",
            flush=True,
        )
        return updated

    def _pricing_fallback(
        self,
        result: Dict[str, Any],
        candidate_services: List[str],
        reason: str,
    ) -> Dict[str, Any]:
        """Use deterministic arithmetic first, then a bounded LLM estimate.

        The LLM path is allowed only when at least one time-based business workload
        volume exists. It cannot create traffic volumes from page sizes, time limits,
        workflow counts, or other unrelated numeric facts.
        """
        deterministic = self._with_volumetric_fallback(result, candidate_services, reason)
        metrics = [item for item in result.get("volume_metrics") or [] if isinstance(item, dict)]
        workload_rows = []
        for item in metrics:
            label = str(item.get("metric") or "").casefold()
            value = str(item.get("value") or "")
            if not any(term in label for term in ("conversation", "interaction", "ticket", "case", "email", "transaction")):
                continue
            if not ("month" in label or "annual" in label or "year" in label or "per month" in value.casefold() or "per year" in value.casefold()):
                continue
            if _scaled_numbers(value):
                workload_rows.append(item)
        if not workload_rows or not candidate_services:
            print(
                "[PRICING] No time-based workload volume available; "
                "rendering blank volumetric and cost fields",
                flush=True,
            )
            return deterministic

        prompt = f"""Create a loose non-binding AWS monthly planning estimate from business volumetrics. Return JSON only.

SOURCE-BACKED WORKLOAD METRICS:
{json.dumps(workload_rows, default=str)}

PROPOSED AWS SERVICES:
{json.dumps(candidate_services)}

Return {{"monthly_low":number,"monthly_base":number,"monthly_high":number,"basis":["brief calculation assumption"]}}.

Rules:
- Currency is USD.
- Use the supplied workload values as the scale driver; do not invent another traffic volume.
- Include application runtime, integration, storage, observability and AI consumption only where the proposed services warrant them.
- Keep uncertainty broad and the base inside the low/high range.
- Do not include implementation fees, taxes, support plans, discounts, telephony carrier charges or commitments.
"""
        try:
            response = self.llm.generate(
                prompt,
                task="analysis",
                max_tokens=8192,
                temperature=0.0,
                call_name="AWS Pricing Volumetric Fallback",
                fallback_model_id=getattr(self.config, "WRITER_MODEL_ID", None),
            )
        except Exception as exc:
            print(f"[PRICING] LLM volumetric fallback unavailable: {exc}", flush=True)
            return deterministic
        estimate = _json_object(response.text)
        try:
            low = round(float(estimate.get("monthly_low")), 2)
            base_cost = round(float(estimate.get("monthly_base")), 2)
            high = round(float(estimate.get("monthly_high")), 2)
        except (TypeError, ValueError):
            print("[PRICING] LLM volumetric fallback returned no valid amount", flush=True)
            return deterministic
        if low <= 0 or not low <= base_cost <= high or high / low > 100:
            print("[PRICING] LLM volumetric fallback failed range validation", flush=True)
            return deterministic

        fallback = {
            "method": "llm_volumetric_planning_range_v1",
            "reason": reason,
            "monthly_low": low,
            "monthly_base": base_cost,
            "monthly_high": high,
            "workload_metric": str(workload_rows[0].get("metric") or "Business workload volume"),
            "planning_basis": [str(item) for item in estimate.get("basis") or [] if str(item).strip()][:6],
            "excluded_costs": [],
        }
        updated = {
            **deterministic,
            "status": "hybrid_priced" if result.get("estimate_url") else "fallback_priced",
            "currency": "USD",
            "monthly_cost": base_cost,
            "fallback_estimate": fallback,
        }
        print(
            f"[PRICING] LLM volumetric fallback=USD {low:,.2f}-{high:,.2f}/month "
            f"(base {base_cost:,.2f})",
            flush=True,
        )
        return updated

    def _plan(self, requirements: Dict[str, Any], metadata: Dict[str, Any], source_text: str) -> Dict[str, Any]:
        services = self._candidate_services(requirements, metadata, source_text)
        pricing_evidence = select_section_evidence(
            source_text,
            "AWS architecture infrastructure sizing pricing volume throughput retention users environments",
            requirements=requirements,
            max_chars=32000,
        )
        prompt = f"""Extract an AWS pricing input plan. Return JSON only.

ALLOWED SERVICES (do not add others):
{json.dumps(services)}

NORMALISED REQUIREMENTS:
{json.dumps(requirements, default=str)[:18000]}

AUTHORITATIVE SOURCE TEXT:
{pricing_evidence or '(none)'}

Return:
{{"region": null, "environments": [], "volume_metrics":[{{"metric":"business sizing metric", "value":"source value with unit", "evidence_quote":"short exact source quote"}}], "services": [{{"service_name":"exact allowed service", "environment":"name or Shared", "usage_facts":{{"source label":"source value"}}, "evidence_quote":"short exact quote supporting the service or its usage"}}], "missing_inputs":[]}}

Rules:
- Extract only numeric or categorical usage facts explicitly present in the source text.
- Capture cross-service business sizing facts such as annual/monthly interactions, turns per interaction, AI-routing percentages, handover percentage, API calls, users, concurrency and retention in volume_metrics.
- evidence_quote must be a short verbatim excerpt from the source text. Never fabricate a quote.
- A service's usage facts may combine values from separate source passages; each numeric value must still occur somewhere in the authoritative source.
- A proposed AWS service may be listed, but it needs source-backed usage facts before pricing.
- Do not create defaults, estimates, instance sizes, traffic, storage, retention, utilisation, redundancy or regions.
- User guidance may exclude/defer services but may not manufacture a sizing fact.
- missing_inputs may contain only rate-driving AWS consumption or configuration fields for an allowed service.
"""
        result = self.llm.generate(
            prompt,
            task="analysis",
            max_tokens=32768,
            temperature=0.0,
            call_name="AWS Pricing Input Plan",
            fallback_model_id=getattr(self.config, "WRITER_MODEL_ID", None),
        )
        parsed = _json_object(result.text)
        if not parsed:
            raise RuntimeError("AWS pricing input plan returned invalid or empty JSON")
        return parsed

    @staticmethod
    def _candidate_services(
        requirements: Dict[str, Any],
        metadata: Dict[str, Any],
        source_text: str = "",
    ) -> List[str]:
        services = list(requirements.get("confirmed_aws_services") or [])
        proposed = list(requirements.get("proposed_aws_services") or [])
        if not services and not proposed:
            # Compatibility for older normalized records created before source
            # provenance was split into confirmed/proposed collections.
            services.extend(requirements.get("aws_services") or [])
        elif metadata.get("pricing_include_proposed", True):
            services.extend(proposed)
        source = str(source_text or "").casefold()
        explicit_aliases = {
            "Amazon Bedrock": (r"\bamazon\s+bedrock\b", r"\bbedrock\b"),
            "AWS Lambda": (r"\baws\s+lambda\b", r"\blambda\b"),
            "Amazon S3": (r"\bamazon\s+s3\b", r"\bs3\b", r"\bsimple storage service\b"),
            "Amazon DynamoDB": (r"\bamazon\s+dynamodb\b", r"\bdynamodb\b"),
            "Amazon API Gateway": (r"\bamazon\s+api gateway\b", r"\baws\s+api gateway\b"),
            "Amazon Connect": (r"\bamazon\s+connect\b",),
            "Amazon Simple Email Service": (r"\bamazon\s+ses\b", r"\baws\s+ses\b", r"\bsimple email service\b"),
            "Amazon CloudWatch": (r"\bamazon\s+cloudwatch\b", r"\baws\s+cloudwatch\b", r"\bcloudwatch\b"),
            "Amazon Cognito": (r"\bamazon\s+cognito\b", r"\bcognito\b"),
            "Amazon OpenSearch Service": (r"\bamazon\s+opensearch(?: service)?\b", r"\bopensearch\b"),
            "Amazon Redshift": (r"\bamazon\s+redshift\b", r"\bredshift\b"),
            "Amazon QuickSight": (r"\bamazon\s+quicksight\b", r"\bquicksight\b", r"\bquick sight\b"),
            "AWS Step Functions": (r"\baws\s+step functions\b", r"\bstep functions\b"),
            "Amazon Simple Queue Service": (r"\bamazon\s+sqs\b", r"\baws\s+sqs\b"),
            "Amazon Simple Notification Service": (r"\bamazon\s+sns\b", r"\baws\s+sns\b"),
        }
        for canonical, patterns in explicit_aliases.items():
            if any(re.search(pattern, source) for pattern in patterns):
                services.append(canonical)

        # If objective JSON recovery fails, retain the same conservative,
        # capability-to-proposed-service bridge used by architecture planning.
        # These remain calculator candidates, never confirmed source facts.
        if metadata.get("pricing_include_proposed", True):
            capability_candidates = {
                "Amazon Bedrock": ("generative ai", "agentic ai", "foundation model"),
                "AWS Lambda": ("serverless", "event-driven processing", "workflow", "auto-assignment", "auto acknowledgement"),
                "Amazon API Gateway": ("api gateway", "api integration", "integration layer"),
                "Amazon S3": ("object storage", "data lake", "attachment storage", "historical data", "attachments"),
                "Amazon DynamoDB": ("nosql", "conversation state", "session state", "ticketing", "case management"),
                "Amazon CloudWatch": ("monitoring and alert", "observability", "sla breach", "tat status"),
                "Amazon Cognito": ("customer authentication", "user authentication"),
                "Amazon Connect": ("live agent", "agent handover", "contact centre"),
                "Amazon QuickSight": ("business intelligence", "analytics dashboard", "reporting dashboard", "manager dashboard"),
                "Amazon Simple Email Service": ("email desk", "auto-acknowledgement", "outbound email", "inbound email"),
                "Amazon OpenSearch Service": ("full-body keyword search", "full body keyword search", "search capability"),
                "AWS Step Functions": ("escalation matrix", "tat workflow", "workflow orchestration"),
            }
            for canonical, signals in capability_candidates.items():
                if any(signal in source for signal in signals):
                    services.append(canonical)
        return list(dict.fromkeys(str(item).strip() for item in services if str(item).strip()))

    @staticmethod
    def _missing_for_service(service_name: str) -> List[Dict[str, str]]:
        """Return concise rate-driving questions instead of generic project gaps."""
        name = str(service_name).strip()
        key = _normalise_evidence(name)
        catalog = {
            "lambda": "monthly invocations, average execution duration, memory allocation, and processor architecture",
            "connect": "monthly voice/chat interactions, average contact duration, telephony countries, and concurrent agents",
            "s3": "initial storage, monthly growth, request volumes, storage class, retention, and data transfer",
            "dynamodb": "stored data, monthly reads and writes, consistency mode, backup, and replication requirements",
            "bedrock": "model, monthly input/output tokens or requests, and provisioned-throughput requirements",
            "ses": "monthly outbound and inbound email volume, average message size, and attachment volume",
            "cloudwatch": "monthly log ingestion, retention, metrics, alarms, and dashboard counts",
            "cognito": "monthly active users, machine-to-machine requests, and advanced-security requirements",
            "quicksight": "author, reader, and admin counts; session usage; and SPICE capacity",
            "api gateway": "monthly API requests, API type, cache requirements, and outbound data transfer",
            "ec2": "instance family/size, instance count, operating system, hours per month, storage, and data transfer",
            "rds": "database engine, instance class/count, deployment model, storage, I/O, backup, and data transfer",
        }
        details = next((value for marker, value in catalog.items() if marker in key), None)
        if not details:
            details = "region-specific usage volume, capacity, operating duration, storage, and data-transfer inputs"
        return [{
            "field": f"{name} usage",
            "basis": "",
            "reason": f"Confirm {details}",
        }]

    @staticmethod
    def _validated_plan_services(plan: Dict[str, Any], allowed_services: List[str], source_text: str) -> List[Dict[str, Any]]:
        allowed = {
            _normalise_evidence(item): str(item)
            for item in allowed_services if str(item).strip()
        }
        source = _normalise_evidence(source_text)
        source_numbers = _numeric_values(source_text)
        valid = []
        for item in _as_list(plan.get("services")):
            if not isinstance(item, dict):
                continue
            key = _normalise_evidence(item.get("service_name"))
            quote = _normalise_evidence(item.get("evidence_quote"))
            usage = item.get("usage_facts")
            if key not in allowed or not isinstance(usage, dict) or not usage:
                continue
            # Reject invented LLM evidence. Whitespace and punctuation are
            # normalised, but the words and values must exist in the source.
            if not quote or quote not in source:
                continue
            cleaned = dict(item)
            cleaned["service_name"] = allowed[key]
            environment = str(cleaned.get("environment") or "").strip()
            if environment and _normalise_evidence(environment) not in source:
                cleaned["environment"] = "Shared"
            usage_numbers = _numeric_values(usage)
            if usage_numbers and not usage_numbers.issubset(source_numbers):
                continue
            valid.append(cleaned)
        return valid

    @staticmethod
    def _validated_volume_metrics(plan: Dict[str, Any], source_text: str) -> List[Dict[str, str]]:
        source = _normalise_evidence(source_text)
        rows: List[Dict[str, str]] = []
        seen = set()
        for item in _as_list(plan.get("volume_metrics")):
            if not isinstance(item, dict):
                continue
            metric = str(item.get("metric") or "").strip()
            value = str(item.get("value") or "").strip()
            quote = _normalise_evidence(item.get("evidence_quote"))
            if not metric or not value or not quote or quote not in source:
                continue
            if not _numeric_values(value).issubset(_numeric_values(quote)):
                continue
            key = (metric.casefold(), value.casefold())
            if key not in seen:
                rows.append({"metric": metric, "value": value, "status": "Source-backed"})
                seen.add(key)
        return rows[:16]

    def _prepare_service(self, client: Any, service: Dict[str, Any], region: str):
        name = str(service["service_name"])
        alias = self._calculator_service_code(name)
        if alias:
            code, calculator_name = alias
            print(
                f"[PRICING] Resolved {name} -> {calculator_name} ({code})",
                flush=True,
            )
        else:
            query = re.split(r"\s+(?:for|to)\s+", name, maxsplit=1, flags=re.I)[0].strip()
            search = client.call("search_services", {"query": query, "partition": "aws"})
            hit = self._select_service_hit(search, query)
            if not hit:
                return None, [{"field": name, "basis": "", "reason": "Service could not be resolved in AWS Pricing Calculator"}]
            code = str(hit.get("key") or hit.get("serviceCode") or hit.get("service_code") or "")
        if not code:
            return None, [{"field": name, "basis": "", "reason": "Calculator service code was unavailable"}]
        fields = client.call("get_service_fields", {"service": code, "partition": "aws"})
        deterministic = self._deterministic_config(code, service)
        if deterministic:
            mapped = {"config": deterministic, "missing_inputs": []}
            print(f"[PRICING] Applied source-backed sizing profile for {name}", flush=True)
        else:
            mapped = self._map_fields(service, region, fields)
        missing = _as_list(mapped.get("missing_inputs"))
        config = mapped.get("config")
        if missing or not isinstance(config, dict) or not config:
            return None, [
                item if isinstance(item, dict) else {"field": f"{name} usage", "basis": "", "reason": str(item)}
                for item in (missing or ["Required calculator fields could not be mapped from source evidence"])
            ]
        source_facts = service.get("usage_facts") or {}
        source_numbers = _numeric_values(source_facts)
        contracts = _field_contracts(fields)
        mapped_numbers: set[str] = set()
        categorical_errors: List[str] = []
        categorical_source = _normalise_evidence(
            json.dumps(source_facts, default=str) + " "
            + str(service.get("evidence_quote") or "") + " "
            + " ".join(str(item) for item in service.get("planning_assumptions") or [])
        )
        for field_id, value in config.items():
            if str(field_id) not in contracts:
                categorical_errors.append(str(field_id))
                continue
            contract = contracts.get(str(field_id), {})
            if contract.get("type") == "dropdown":
                selected = next(
                    (
                        option for option in contract.get("options", [])
                        if isinstance(option, dict) and str(option.get("id")) == str(value)
                    ),
                    None,
                )
                label = _normalise_evidence((selected or {}).get("label"))
                if not label or label not in categorical_source:
                    categorical_errors.append(str(contract.get("label") or field_id))
            else:
                mapped_numbers.update(_numeric_values(value))
        if categorical_errors:
            return None, [{
                "field": f"{name} categorical configuration",
                "basis": ", ".join(categorical_errors),
                "reason": "A calculator option was not explicitly supported by source evidence",
            }]
        if mapped_numbers - source_numbers:
            return None, [{
                "field": f"{name} usage mapping",
                "basis": ", ".join(sorted(source_numbers)),
                "reason": "Calculator mapping introduced a numeric value not present in source evidence",
            }]
        config["region"] = region
        config["description"] = f"{service.get('environment') or 'Shared'} workload"
        return {
            "service": code,
            "instance": str(service.get("environment") or "Shared")[:48],
            "group": str(service.get("environment") or "Shared")[:48],
            "config": config,
        }, []

    @staticmethod
    def _calculator_service_code(name: str) -> Optional[tuple[str, str]]:
        key = _normalise_evidence(name)
        for marker, value in sorted(
            CALCULATOR_SERVICE_CODES.items(), key=lambda item: len(item[0]), reverse=True
        ):
            if re.search(rf"\b{re.escape(marker)}\b", key):
                return value
        return None

    @staticmethod
    def _deterministic_config(code: str, service: Dict[str, Any]) -> Dict[str, Any]:
        """Map derived, auditable planning facts to known calculator contracts.

        The vendored calculator uses service-specific child codes and field IDs.
        These mappings avoid asking an LLM to rediscover stable schema while
        still returning no configuration when the required sizing fact is absent.
        """
        facts = service.get("usage_facts") or {}

        def number(label: str) -> Optional[float]:
            values = _scaled_numbers(facts.get(label))
            return values[0] if values else None

        def clean(value: float) -> str:
            return str(int(value)) if float(value).is_integer() else str(round(value, 4))

        if code == "aWSLambda":
            requests = number("derived monthly invocations")
            duration = number("planning average duration ms")
            memory = number("planning memory MB")
            if requests is not None and duration is not None and memory is not None:
                return {
                    "numberOfRequests": {"value": clean(requests), "unit": "perMonth"},
                    "durationOfEachRequest": clean(duration),
                    "sizeOfMemoryAllocated": {"value": clean(memory), "unit": "mb|NA"},
                    # Both toggles are required by the calculator catalogue even
                    # when provisioned concurrency is not being priced.
                    "selectArchitectureRequests": "1",
                    "selectArchitectureConcurrency": "1",
                }
        elif code == "amazonApiGateway":
            requests = number("derived monthly API requests")
            if requests is not None:
                return {
                    "numberOfAPIRequests": {"value": clean(requests), "unit": "perMonth"},
                }
        elif code == "dynamoDbOnDemand":
            reads = number("derived monthly reads")
            writes = number("derived monthly writes")
            storage = number("planning storage GB")
            if reads is not None and writes is not None and storage is not None:
                return {
                    "dataStorageSize": {"value": clean(storage), "unit": "gb|NA"},
                    "writeRateId": {"value": clean(writes), "unit": "perMonth"},
                    "readRateId": {"value": clean(reads), "unit": "perMonth"},
                }
        elif code == "amazonS3Standard":
            storage = number("planning active storage GB")
            if storage is not None:
                return {
                    "s3StandardStorageSize": {"value": clean(storage), "unit": "gb|NA"},
                }
        elif code == "amazonCloudWatch":
            ingestion = number("planning monthly log ingestion GB")
            if ingestion is not None:
                return {
                    "sizeOfStandardLogsDataIngested": {
                        "value": clean(ingestion), "unit": "gb|NA"
                    },
                }
        return {}

    @staticmethod
    def _enrich_service_with_volumetrics(
        service: Dict[str, Any], metrics: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Add reproducible arithmetic/defaults used only for calculator sizing."""
        enriched = {**service, "usage_facts": dict(service.get("usage_facts") or {})}
        assumptions = list(service.get("planning_assumptions") or [])

        def metric_values(*needles: str, exclude: tuple[str, ...] = ()) -> List[float]:
            for item in metrics:
                label = str(item.get("metric") or "").casefold()
                if all(needle in label for needle in needles) and not any(
                    needle in label for needle in exclude
                ):
                    return _scaled_numbers(item.get("value"))
            return []

        monthly_values = metric_values("monthly", "conversation")
        if not monthly_values:
            annual_values = metric_values("annual", "conversation")
            monthly_values = [value / 12 for value in annual_values]
        monthly = sorted(monthly_values)[len(monthly_values) // 2] if monthly_values else 0
        turn_values = metric_values("turn") or metric_values("message", "conversation")
        turns = sum(turn_values) / len(turn_values) if turn_values else 1.0
        llm_values = metric_values("llm", "percentage") or metric_values("inference", "percentage")
        llm_ratio = (sum(llm_values) / len(llm_values) / 100) if llm_values else 0.0
        backend_values = metric_values("backend", "percentage")
        backend_ratio = (sum(backend_values) / len(backend_values) / 100) if backend_values else 0.0
        calls_values = (
            metric_values("number", "backend", "calls", exclude=("percentage",))
            or metric_values("backend", "calls", "transactional", exclude=("percentage",))
            or metric_values("backend", "calls", "conversation", exclude=("percentage",))
        )
        calls_per_transaction = sum(calls_values) / len(calls_values) if calls_values else 1.0

        name = _normalise_evidence(service.get("service_name"))
        facts = enriched["usage_facts"]
        if monthly:
            facts["monthly conversations (source-backed)"] = round(monthly)
        if "bedrock" in name and monthly:
            requests = round(monthly * max(llm_ratio, 1.0) * max(turns, 1.0))
            if llm_ratio:
                requests = round(monthly * llm_ratio * max(turns, 1.0))
            facts.update({
                "derived monthly inference requests": requests,
                "planning average input tokens per request": 1000,
                "planning average output tokens per request": 250,
                "planning inference route": "global",
                "planning billing tier": "standard",
            })
            assumptions.append(
                f"{requests:,} monthly inference requests are derived from conversation volume, "
                f"{llm_ratio * 100:.0f}% LLM routing and {turns:g} average turns; "
                "1,000 input and 250 output tokens per request are provisional sizing assumptions"
            )
        elif "lambda" in name and monthly:
            invocations = round(monthly * (1 + backend_ratio * calls_per_transaction))
            facts.update({
                "derived monthly invocations": invocations,
                "planning average duration ms": 500,
                "planning memory MB": 512,
                "planning architecture": "x86_64",
            })
            assumptions.append(
                f"{invocations:,} monthly invocations are derived from conversation and backend-call volumes; "
                "500 ms at 512 MB on x86_64 is a provisional execution profile"
            )
        elif "api gateway" in name and monthly:
            requests = round(monthly * max(backend_ratio, 1.0) * max(calls_per_transaction, 1.0))
            if backend_ratio:
                requests = round(monthly * backend_ratio * max(calls_per_transaction, 1.0))
            facts.update({
                "derived monthly API requests": requests,
                "planning API type": "HTTP API",
            })
            assumptions.append(
                f"{requests:,} monthly API requests are derived from sourced transaction-call percentages; "
                "HTTP API is the provisional calculator profile"
            )
        elif "dynamodb" in name and monthly:
            reads = round(monthly * max(turns, 1.0))
            writes = round(monthly * 2)
            facts.update({
                "derived monthly reads": reads,
                "derived monthly writes": writes,
                "planning capacity mode": "on-demand",
                "planning storage GB": 5,
            })
            assumptions.append(
                f"{reads:,} reads and {writes:,} writes per month are derived from conversation volume; "
                "on-demand capacity and 5 GB initial storage are provisional"
            )
        elif (re.search(r"\bs3\b", name) or "simple storage" in name) and monthly:
            monthly_growth = max(1, round(monthly * 0.000025, 2))
            active_storage = max(1, round(monthly_growth * 12, 2))
            facts.update({
                "planning active storage GB": active_storage,
                "derived monthly growth GB": monthly_growth,
                "planning storage class": "S3 Standard",
            })
            assumptions.append(
                f"{active_storage:g} GB active storage assumes 25 KB of retained content per conversation "
                "across the sourced one-year active-retention period"
            )
        elif "cloudwatch" in name and monthly:
            log_gb = max(1, round(monthly * max(turns, 1.0) * 0.000001, 2))
            facts.update({
                "planning monthly log ingestion GB": log_gb,
                "planning log retention days": 30,
            })
            assumptions.append(
                f"{log_gb:g} GB monthly log ingestion and 30-day hot log retention are provisional"
            )
        enriched["planning_assumptions"] = assumptions
        return enriched

    def _map_fields(self, service: Dict[str, Any], region: str, fields: Any) -> Dict[str, Any]:
        prompt = f"""Map source-backed usage facts to live AWS Pricing Calculator fields. Return JSON only.

SERVICE PLAN:
{json.dumps(service, default=str)}

SELECTED REGION:
{region}

LIVE CALCULATOR FIELD CONTRACT:
{json.dumps(fields, default=str)[:30000]}

Return {{"config":{{"exactFieldId":"valid value"}},"missing_inputs":[{{"field":"label","basis":"known value or blank","reason":"what must be confirmed"}}]}}.

Use only exact field IDs and allowed value shapes from the live contract. Map only facts present in
SERVICE PLAN, including explicitly labelled planning facts derived deterministically from global
volumetrics. Catalogue examples and minimalConfig values explain shape but are not customer sizing
evidence and must not be copied unless the same value is explicitly present in SERVICE PLAN. If any
rate-driving required field cannot be populated, return it in missing_inputs and do not guess.
"""
        result = self.llm.generate(
            prompt,
            task="analysis",
            max_tokens=32768,
            temperature=0.0,
            call_name=f"AWS Pricing Fields - {service['service_name']}",
            fallback_model_id=getattr(self.config, "WRITER_MODEL_ID", None),
        )
        parsed = _json_object(result.text)
        if not parsed:
            raise RuntimeError(f"AWS pricing field mapping returned invalid JSON for {service['service_name']}")
        return parsed

    @staticmethod
    def _select_service_hit(search: Any, name: str) -> Optional[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []
        if isinstance(search, list):
            candidates = [item for item in search if isinstance(item, dict)]
        elif isinstance(search, dict):
            if any(key in search for key in ("key", "serviceCode", "service_code")):
                candidates = [search]
            else:
                for value in search.values():
                    if isinstance(value, list):
                        candidates.extend(item for item in value if isinstance(item, dict))
        wanted = _normalise_evidence(name).replace("amazon ", "").replace("aws ", "")
        for item in candidates:
            label = _normalise_evidence(item.get("name") or item.get("displayName") or item.get("key"))
            if label.replace("amazon ", "").replace("aws ", "") == wanted:
                return item
        return candidates[0] if candidates else None

    @staticmethod
    def _calculator_message(result: Any) -> str:
        if isinstance(result, dict):
            return str(result.get("next_step") or result.get("error") or result.get("status") or "Calculator validation failed")
        return str(result or "Calculator validation failed")

    @staticmethod
    def _assumption_rows(plan: Dict[str, Any], region: str) -> List[Dict[str, str]]:
        rows = [{"input": "AWS region", "basis": region, "status": "Confirmed by user or source"}]
        for service in _as_list(plan.get("services")):
            if not isinstance(service, dict):
                continue
            for label, value in (service.get("usage_facts") or {}).items():
                rows.append({
                    "input": f"{service.get('service_name')} – {label}",
                    "basis": str(value),
                    "status": "Source-backed",
                })
        return rows[:20]

    def _read_cost(self, url: str) -> Dict[str, Any]:
        script = Path(self.config.AWS_PRICING_COST_READER)
        if not script.exists():
            return {"error": "Cost reader is not installed"}
        try:
            completed = subprocess.run(
                [self.config.AWS_PRICING_NODE_BINARY, str(script), url],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.config.AWS_PRICING_COST_TIMEOUT_SECONDS,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                check=False,
            )
            if completed.returncode != 0:
                return {"error": (completed.stderr or "Calculator cost rendering failed").strip()[:500]}
            value = json.loads(completed.stdout)
            return value if isinstance(value, dict) else {"error": "Invalid calculator cost response"}
        except Exception as exc:
            return {"error": str(exc)[:500]}
