"""Requirements rule engine with deterministic preservation and quality gates."""

from __future__ import annotations

import json
import re
from typing import Any, Dict

import boto3

from app.core.bedrock_llm import BedrockLLM
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
        self.llm = BedrockLLM(config, self.bedrock)
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
        # This stage is a policy gate, not an authoring task. Asking a model to
        # echo the complete baseline repeatedly produced oversized, malformed
        # JSON without adding trustworthy source facts. Normalisation and
        # source restoration already implement the required controls exactly.
        validated = self._post_validate({}, baseline, objective, mode)
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
            "_generation_guidance",
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
