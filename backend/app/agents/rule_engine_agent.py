"""Requirements rule engine with deterministic preservation and quality gates."""

from __future__ import annotations

import json
import re
from typing import Any, Dict

import boto3

from app.core.sow_quality import as_list, dedupe, is_known, normalize_requirements


class RuleEngineAgent:
    """Validate an LLM analysis without letting the validator invent commitments."""

    def __init__(self, config):
        self.config = config
        self.bedrock = boto3.client(
            service_name="bedrock-runtime",
            region_name=config.BEDROCK_REGION,
            config=config.BOTO_CONFIG,
        )
        self.rules = self._load_rules()

    def _load_rules(self) -> Dict[str, Any]:
        rules_file = self.config.POC_RULES_FILE
        if not rules_file.exists():
            print(f"⚠ Warning: Rules file not found at {rules_file}")
            return {}
        with open(rules_file, "r", encoding="utf-8") as handle:
            rules = json.load(handle)
        print(f"✓ Loaded {len(rules)} rule categories from {rules_file.name}")
        return rules

    def validate_requirements(
        self,
        requirements: Dict[str, Any],
        objective: str,
        mode: str = "POC",
    ) -> Dict[str, Any]:
        """Apply rules, then deterministically restore source-grounded data."""
        baseline = normalize_requirements(requirements, objective, mode)
        if not self.rules:
            return self._post_validate(baseline, baseline, objective, mode)

        prompt = f"""You are the quality and scope-control reviewer for a {mode} Statement of Work.

SOURCE OBJECTIVE:
{objective}

NORMALIZED REQUIREMENTS:
{json.dumps(baseline, indent=2, default=str)}

QUALITY RULES:
{self._format_rules_as_text()}

Return a single JSON object that improves completeness and clarity while following these controls:
1. Preserve every confirmed/user-supplied value exactly. Never remove a source detail.
2. Do not invent dates, prices, data volumes, concurrency, SLAs, compliance frameworks,
   integrations, model versions, customer facts, or acceptance thresholds.
3. Put reasonable design choices in planning_assumptions and material unknowns in
   open_clarifications. A planning assumption is not a commitment.
4. Add testing_approach, architecture_notes, dependencies, out_of_scope,
   risks_and_mitigations, and traceability_notes as useful lists.
5. Make scope testable: each deliverable should have an output and an acceptance method.
6. For POC_TO_PROD, preserve POC evidence separately from proposed production hardening.
7. Keep confirmed_aws_services distinct from proposed_aws_services.
8. Use [] or null when something remains unknown.

Respond with JSON only."""

        candidate: Dict[str, Any] = {}
        try:
            response = self.bedrock.invoke_model(
                modelId=self.config.MODEL_ID,
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": min(getattr(self.config, "MAX_TOKENS", 8192), 8192),
                    "temperature": 0.1,
                    "messages": [{"role": "user", "content": prompt}],
                }),
            )
            body = json.loads(response["body"].read())
            from app.core.nodes import _track_tokens
            _track_tokens(body, "Requirements Validation")
            candidate = json.loads(self._clean_json_response(body["content"][0]["text"]))
        except Exception as exc:
            print(f"⚠ Requirements validation used deterministic fallback: {exc}")

        validated = self._post_validate(candidate, baseline, objective, mode)
        print(f"✓ Requirements validated against {len(self.rules)} rule categories")
        print(f"✓ Source-grounded values restored deterministically")
        return validated

    def _post_validate(
        self,
        candidate: Dict[str, Any],
        baseline: Dict[str, Any],
        objective: str,
        mode: str,
    ) -> Dict[str, Any]:
        candidate = candidate if isinstance(candidate, dict) else {}
        combined = {**baseline, **candidate}

        # Lists are enhanced, not replaced. Baseline order wins.
        for key, value in baseline.items():
            if isinstance(value, list):
                combined[key] = dedupe(value + as_list(candidate.get(key)))
            elif isinstance(value, dict):
                extra = candidate.get(key) if isinstance(candidate.get(key), dict) else {}
                combined[key] = {**value, **extra}

        # These source/extraction fields are immutable after analysis.
        protected = {
            "confirmed_requirements", "confirmed_aws_services", "source_basis",
            "requirements_provenance", "extracted_data_summary", "user_data_extracted",
            "document_volume", "data_volume_description", "poc_evidence",
            "_original_objective",
        }
        for key in protected:
            if key in baseline:
                combined[key] = baseline[key]

        # Explicit values win; unknown baseline values may be supplemented only as proposals.
        for key in (
            "duration_weeks", "timeline", "data_volume_gb", "concurrent_users",
            "mrr_estimate", "ui_required", "industry", "deployment_environment",
            "accuracy_metrics", "data_characteristics",
        ):
            if is_known(baseline.get(key)):
                combined[key] = baseline[key]

        return normalize_requirements(combined, objective, mode)

    def _format_rules_as_text(self) -> str:
        lines = []
        for category, details in self.rules.items():
            if not isinstance(details, dict):
                continue
            rules = details.get("rules")
            if not rules:
                continue
            lines.append(f"{category.replace('_', ' ').title()}:")
            lines.extend(f"- {rule}" for rule in rules)
        # Avoid wasting tokens on examples and decorative separators.
        return "\n".join(lines)

    @staticmethod
    def _clean_json_response(content: str) -> str:
        content = (content or "").strip()
        fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", content, re.I | re.S)
        if fenced:
            return fenced.group(1)
        start, end = content.find("{"), content.rfind("}")
        return content[start:end + 1] if start >= 0 and end > start else "{}"
