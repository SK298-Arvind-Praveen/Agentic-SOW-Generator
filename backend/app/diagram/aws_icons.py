"""Deterministic retrieval of official AWS architecture icons.

Only a small, evidence-backed candidate set is exposed to the diagram LLM.  The
model may arrange those candidates, but cannot invent an icon path or service.
"""
from __future__ import annotations

import base64
import io
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from PIL import Image


def _norm(value: Any) -> str:
    value = re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold())
    return re.sub(r"\b(?:amazon|aws|service|services)\b", " ", value).strip()


@dataclass(frozen=True)
class IconCandidate:
    key: str
    label: str
    category: str
    path: str
    selection: str
    evidence: str
    score: int = 0

    def prompt_dict(self) -> Dict[str, str]:
        return {"key": self.key, "label": self.label, "category": self.category,
                "selection": self.selection, "evidence": self.evidence}


# Capability inference is deterministic and intentionally conservative.  It is
# used only when the source describes a capability but does not name a service.
CAPABILITY_MAP = {
    "object storage": "Amazon Simple Storage Service",
    "data lake": "Amazon Simple Storage Service",
    "serverless function": "AWS Lambda",
    "api gateway": "Amazon API Gateway",
    "relational database": "Amazon RDS",
    "nosql": "Amazon DynamoDB",
    "foundation model": "Amazon Bedrock",
    "generative ai": "Amazon Bedrock",
    "gen ai": "Amazon Bedrock",
    "genai": "Amazon Bedrock",
    "summarisation": "Amazon Bedrock",
    "summarization": "Amazon Bedrock",
    "sentiment": "Amazon Bedrock",
    "attachments": "Amazon Simple Storage Service",
    "migration": "AWS Step Functions",
    "data migration": "AWS Glue",
    "extract transform": "AWS Glue",
    "integration": "AWS Lambda",
    "api": "Amazon API Gateway",
    "reporting": "Amazon QuickSight",
    "machine learning": "Amazon SageMaker",
    "queue": "Amazon Simple Queue Service",
    "notification": "Amazon Simple Notification Service",
    "event bus": "Amazon EventBridge",
    "monitoring": "Amazon CloudWatch",
    "user authentication": "Amazon Cognito",
    "content delivery": "Amazon CloudFront",
    "web application firewall": "AWS WAF",
    "encryption key": "AWS Key Management Service",
    "container orchestration": "Amazon Elastic Kubernetes Service",
    "workflow orchestration": "AWS Step Functions",
}

SERVICE_SYNONYMS = {
    "s3": "Amazon Simple Storage Service",
    "rds": "Amazon RDS",
    "dynamodb": "Amazon DynamoDB",
    "lambda": "AWS Lambda",
    "api gateway": "Amazon API Gateway",
    "sqs": "Amazon Simple Queue Service",
    "sns": "Amazon Simple Notification Service",
    "ses": "Amazon Simple Email Service",
    "eks": "Amazon Elastic Kubernetes Service",
    "ecs": "Amazon Elastic Container Service",
    "ecr": "Amazon Elastic Container Registry",
    "sagemaker ai": "Amazon SageMaker AI",
    "kms": "AWS Key Management Service",
    "iam": "AWS Identity and Access Management",
    "internet gateway": "Amazon VPC Internet Gateway",
    "nat gateway": "Amazon VPC NAT Gateway",
    "vpc endpoint": "Amazon VPC Endpoints",
    "waf": "AWS WAF",
    "contact lens": "Amazon Connect",
    "connect wisdom": "Amazon Connect",
    "quicksight": "Amazon Quick",
    "quick sight": "Amazon Quick",
    "quick suite": "Amazon Quick",
}

# Available design options, never claims that the BRD names these resources.
DEPLOYMENT_OPTIONS = (
    'Amazon VPC Endpoints', 'Amazon VPC Internet Gateway', 'Amazon VPC NAT Gateway',
    'Elastic Load Balancing Application Load Balancer', 'AWS Secrets Manager',
    'AWS Key Management Service', 'AWS Identity and Access Management',
    'Amazon API Gateway',
)


class AwsIconRegistry:
    def __init__(self, assets_dir: Path):
        self.root = Path(assets_dir) / "aws-icons"
        manifest = json.loads((self.root / "manifest.json").read_text(encoding="utf-8"))
        raw_entries = manifest.get("icons", manifest) if isinstance(manifest, dict) else manifest
        self.entries = [item for item in raw_entries if item.get("kind") in {"service", "resource"}]
        self.by_key = {item["key"]: item for item in self.entries}
        # Boundary glyphs are renderable, but never offered as workload services.
        self.group_by_key = {item['key']: item for item in raw_entries if item.get('kind') == 'group'}

    @staticmethod
    def _aliases(item: Dict[str, Any]) -> Iterable[str]:
        yield item.get("label", "")
        yield item.get("key", "").replace(".", " ")
        for alias in item.get("aliases", []):
            yield alias

    def match(self, query: str) -> Optional[Dict[str, Any]]:
        # The leading service owns its icon; a parenthetical implementation
        # detail must not turn "AWS Batch (GPU, EC2 G6)" into an EC2 icon.
        needle = _norm(re.split(r'\s*\(', str(query), maxsplit=1)[0])
        if not needle:
            return None
        # Resolve well-known acronyms even when followed by a purpose phrase,
        # e.g. "Amazon S3 for storing attachments". Previously the trailing
        # word "documents" outscored S3 and selected a generic Documents icon.
        for synonym, canonical in sorted(SERVICE_SYNONYMS.items(), key=lambda pair: len(pair[0]), reverse=True):
            if re.search(rf"\b{re.escape(synonym)}\b", needle):
                needle = _norm(canonical)
                break
        best, best_score = None, 0
        needle_tokens = set(needle.split())
        for item in self.entries:
            for alias in self._aliases(item):
                candidate = _norm(alias)
                if not candidate:
                    continue
                tokens = set(candidate.split())
                score = 100 if needle == candidate else 0
                if len(needle) >= 3 and (
                    re.search(rf"\b{re.escape(needle)}\b", candidate)
                    or re.search(rf"\b{re.escape(candidate)}\b", needle)
                ):
                    score = max(score, 86)
                if needle_tokens and tokens:
                    score = max(score, round(75 * len(needle_tokens & tokens) / len(needle_tokens | tokens)))
                if score > best_score:
                    best, best_score = item, score
        return best if best_score >= 48 else None

    def candidate(self, query: str, selection: str, evidence: str) -> Optional[IconCandidate]:
        item = self.match(query)
        if not item:
            return None
        return IconCandidate(item["key"], item["label"], item.get("category", "Other"),
                             item["path"], selection, evidence, 100 if selection == "explicit" else 70)

    def candidates(self, requirements: Dict[str, Any], narrative: str, limit: int = 40) -> List[IconCandidate]:
        found: Dict[str, IconCandidate] = {}
        from app.diagram.knowledge import _positive_text
        fields = ("aws_services", "services", "technology_stack", "architecture_components")
        for field in fields:
            value = requirements.get(field)
            items = value if isinstance(value, list) else re.split(r"[,;\n]", str(value or ""))
            for raw in items:
                if isinstance(raw, dict):
                    raw = raw.get("name") or raw.get("service") or raw.get("title") or ""
                candidate = self.candidate(str(raw), "explicit", f"{field}: {raw}")
                if candidate and candidate.key.startswith('aws.service.') and not (
                    re.search(r'\b(?:amazon|aws)\b', str(raw), re.I)
                    or any(re.search(rf'\b{re.escape(s)}\b', str(raw), re.I) for s in SERVICE_SYNONYMS)
                ):
                    candidate = None
                if candidate and not _positive_text(str(raw)):
                    candidate = None
                if candidate:
                    found[candidate.key] = candidate

        source = _positive_text(requirements) + ' ' + _positive_text(narrative)
        # Named services anywhere in the extracted source count as explicit.
        for item in self.entries:
            aliases = [a.casefold() for a in self._aliases(item) if
                       not item['key'].startswith('aws.service.') or re.search(r'\b(?:amazon|aws)\b', a, re.I)]
            label = next((a for a in aliases if len(a) >= 4 and re.search(rf"\b{re.escape(a)}\b", source)), None)
            if label and item["key"] not in found:
                found[item["key"]] = IconCandidate(item["key"], item["label"], item.get("category", "Other"),
                                                     item["path"], "explicit", f"source names {item['label']}", 95)
        normalized_source = _norm(source)
        for synonym, canonical in SERVICE_SYNONYMS.items():
            if re.search(rf"\b{re.escape(synonym)}\b", normalized_source):
                candidate = self.candidate(canonical, "explicit", f"source names {synonym}")
                if candidate:
                    found[candidate.key] = candidate
        for signal, service in CAPABILITY_MAP.items():
            if signal in normalized_source:
                candidate = self.candidate(service, "inferred", f"capability: {signal}")
                if candidate and candidate.key not in found:
                    found[candidate.key] = candidate
        for label in DEPLOYMENT_OPTIONS:
            candidate = self.candidate(label, 'inferred', 'Optional supporting infrastructure; select only for a justified deployment need')
            if candidate and candidate.key not in found:
                found[candidate.key] = candidate
        if requirements.get('architecture_evidence_policy'):
            confirmed_keys = {c.key for name in requirements.get('confirmed_aws_services', [])
                              if (c := self.candidate(str(name), 'explicit', 'Confirmed source evidence'))}
            # Icon availability is not evidence of a customer's product choice.
            found = {key: (value if key in confirmed_keys else IconCandidate(
                value.key, value.label, value.category, value.path, 'inferred',
                'Implementation option; not a confirmed client mandate. ' + value.evidence, 70))
                for key, value in found.items()}
        return sorted(found.values(), key=lambda c: (-c.score, c.category, c.label))[:limit]

    def svg_data_uri(self, key: str) -> Optional[str]:
        item = self.by_key.get(key) or self.group_by_key.get(key)
        if not item:
            print(f"[DIAGRAM][SVG] Unknown icon key: {key}", flush=True)
            return None
        path = self.root / item["path"]
        if not path.is_file():
            print(f"[DIAGRAM][SVG] Missing asset for {key}: {path}", flush=True)
            return None
        data = path.read_bytes()
        return "data:image/svg+xml;base64," + base64.b64encode(data).decode("ascii")

    def png(self, key: str, size: int = 64) -> Optional[Image.Image]:
        item = self.by_key.get(key) or self.group_by_key.get(key)
        if not item:
            return None
        try:
            # resvg-py ships a self-contained Windows wheel. CairoSVG requires
            # a separate native Cairo/GTK runtime and silently produced box-only
            # diagrams on clean Windows machines.
            from resvg_py import svg_to_bytes
            data = svg_to_bytes(svg_path=str(self.root / item["path"]), width=size, height=size)
            return Image.open(io.BytesIO(data)).convert("RGBA")
        except Exception as exc:
            print(f"[DIAGRAM][PNG] Failed to render {key}: {type(exc).__name__}: {exc}", flush=True)
            return None
