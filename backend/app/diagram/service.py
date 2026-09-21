"""Generate a validated architecture model and deterministic draw.io artefacts.

The model is deliberately smaller than draw.io's XML vocabulary.  Bedrock is
allowed to decide *what* belongs in the diagram; layout, XML and PNG generation
are deterministic so malformed model output cannot break document generation.
"""

from __future__ import annotations

import base64
import io
import json
import math
import os
import re
import urllib.parse
import zlib
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple
from xml.etree import ElementTree as ET

import boto3
from PIL import Image, ImageDraw, ImageFont
from lxml import etree as LET

from app.core.bedrock_llm import BedrockLLM
from app.diagram.aws_icons import AwsIconRegistry, IconCandidate


ASSET_KEY = "architecture_diagram_assets"
LEGACY_ASSET_KEY = "architecture_diagram_asset"
MAX_NODES = 24
MAX_EDGES = 40
MAX_DIAGRAMS = 3
ALLOWED_DIAGRAM_TYPES = {
    "architecture_overview",
    "data_flow",
    "integration_context",
    "deployment_topology",
}
ALLOWED_KINDS = {
    "actor", "channel", "application", "service", "data", "external",
    "process", "terminator", "decision", "input_output",
}
ALLOWED_GROUP_KINDS = {"functional", "external", "network", "security", "data"}
ALLOWED_PLACEMENT_ROLES = {
    "external", "entry", "network", "compute", "integration", "data", "security", "operations",
}
ALLOWED_SCOPES = {"external", "regional", "vpc", "az", "managed"}
KIND_STYLES = {
    "actor": ("#EEF2FF", "#4F46E5"),
    "channel": ("#ECFEFF", "#0891B2"),
    "application": ("#F5F3FF", "#7C3AED"),
    "service": ("#FFF7ED", "#EA580C"),
    "data": ("#ECFDF5", "#059669"),
    "external": ("#F8FAFC", "#64748B"),
    "process": ("#F8FAFC", "#475569"),
    "terminator": ("#EEF2FF", "#4F46E5"),
    "decision": ("#FFF7ED", "#EA580C"),
    "input_output": ("#ECFEFF", "#0891B2"),
}


@dataclass(frozen=True)
class Node:
    id: str
    label: str
    kind: str
    layer: int
    subtitle: str = ""
    icon_key: str = ""
    selection: str = "none"
    evidence: str = ""
    group: str = ""
    placement_role: str = ""
    scope: str = ""
    availability_zone: str = ""


@dataclass(frozen=True)
class Group:
    id: str
    label: str
    kind: str = "functional"


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    label: str = ""


@dataclass(frozen=True)
class DiagramSpec:
    title: str
    nodes: Tuple[Node, ...]
    edges: Tuple[Edge, ...]
    note: str = "Proposed logical architecture; validate during discovery."
    groups: Tuple[Group, ...] = ()
    description: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "nodes": [node.__dict__ for node in self.nodes],
            "edges": [edge.__dict__ for edge in self.edges],
            "note": self.note,
            "groups": [group.__dict__ for group in self.groups],
            "description": self.description,
        }


def _safe_id(value: Any, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", str(value or "")).strip("_")
    return (cleaned or fallback)[:48]


def _clean_label(value: Any, fallback: str = "Component", limit: int = 60) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return (text or fallback)[:limit]


_COMPACT_AWS_LABELS = {
    "amazon simple storage service": "Amazon S3",
    "amazon simple queue service": "Amazon SQS",
    "amazon simple notification service": "Amazon SNS",
    "amazon simple email service": "Amazon SES",
    "amazon quick": "Amazon QuickSight",
}


def _compact_aws_label(label: str, icon_key: str) -> str:
    """Use familiar service names so icon captions remain fully visible."""
    if not icon_key:
        return label
    key = re.sub(r"\s+", " ", str(label or "").strip()).casefold()
    return next(
        (compact for long_name, compact in _COMPACT_AWS_LABELS.items() if long_name in key),
        label,
    )


def validate_spec(raw: Dict[str, Any], default_title: str, icon_candidates: Optional[Dict[str, IconCandidate]] = None) -> DiagramSpec:
    if not isinstance(raw, dict):
        raise ValueError("Diagram response must be a JSON object")
    raw_nodes = raw.get("nodes")
    raw_edges = raw.get("edges", [])
    if not isinstance(raw_nodes, list) or not 2 <= len(raw_nodes) <= MAX_NODES:
        raise ValueError(f"Diagram must contain between 2 and {MAX_NODES} nodes")
    if not isinstance(raw_edges, list) or len(raw_edges) > MAX_EDGES:
        raise ValueError(f"Diagram cannot contain more than {MAX_EDGES} edges")

    groups: List[Group] = []
    group_ids: set[str] = set()
    for index, item in enumerate(raw.get("groups", []) if isinstance(raw.get("groups", []), list) else []):
        if not isinstance(item, dict) or len(groups) >= 8:
            continue
        group_id = _safe_id(item.get("id"), f"group_{index + 1}")
        if group_id in group_ids:
            continue
        kind = str(item.get("kind", "functional")).lower()
        groups.append(Group(group_id, _clean_label(item.get("label"), "Architecture Layer", 50),
                            kind if kind in ALLOWED_GROUP_KINDS else "functional"))
        group_ids.add(group_id)

    nodes: List[Node] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_nodes, 1):
        if not isinstance(item, dict):
            raise ValueError("Every diagram node must be an object")
        node_id = _safe_id(item.get("id"), f"node_{index}")
        if node_id in seen:
            raise ValueError(f"Duplicate diagram node id: {node_id}")
        seen.add(node_id)
        kind = str(item.get("kind", "service")).lower()
        if kind not in ALLOWED_KINDS:
            kind = "service"
        try:
            layer = max(0, min(int(item.get("layer", 0)), 5))
        except (TypeError, ValueError):
            layer = 0
        requested_icon_key = str(item.get("icon_key") or "")
        icon_key = requested_icon_key
        provenance = (icon_candidates or {}).get(icon_key)
        if not provenance:
            icon_key = ""
            if requested_icon_key:
                print(
                    f"[DIAGRAM][VALIDATE] Node '{item.get('label', node_id)}' requested "
                    f"unapproved icon '{requested_icon_key}'; removed",
                    flush=True,
                )
        label = _clean_label(item.get("label"), f"Component {index}")
        nodes.append(Node(
            id=node_id,
            label=_compact_aws_label(label, icon_key),
            kind=kind,
            layer=layer,
            subtitle=_clean_label(item.get("subtitle"), "", 80),
            icon_key=icon_key,
            selection=provenance.selection if provenance else "none",
            evidence=provenance.evidence if provenance else "",
            group=_safe_id(item.get("group"), "") if _safe_id(item.get("group"), "") in group_ids else "",
            placement_role=(
                str(item.get("placement_role") or "").casefold()
                if str(item.get("placement_role") or "").casefold() in ALLOWED_PLACEMENT_ROLES else ""
            ),
            scope=(
                str(item.get("scope") or "").casefold()
                if str(item.get("scope") or "").casefold() in ALLOWED_SCOPES else ""
            ),
            availability_zone=(
                "az_b" if str(item.get("availability_zone") or "").casefold() in {"az_b", "b", "2"}
                else "az_a" if str(item.get("availability_zone") or "").casefold() in {"az_a", "a", "1"}
                else ""
            ),
        ))

    edges: List[Edge] = []
    edge_keys: set[Tuple[str, str, str]] = set()
    for item in raw_edges:
        if not isinstance(item, dict):
            continue
        source = _safe_id(item.get("source"), "")
        target = _safe_id(item.get("target"), "")
        if source not in seen or target not in seen or source == target:
            continue
        label = _clean_label(item.get("label"), "", 36)
        key = (source, target, label)
        if key not in edge_keys:
            edge_keys.add(key)
            edges.append(Edge(source, target, label))
    if not edges:
        ordered = sorted(nodes, key=lambda item: (item.layer, item.id))
        edges = [Edge(ordered[index].id, ordered[index + 1].id) for index in range(len(ordered) - 1)]

    return DiagramSpec(
        title=_clean_label(raw.get("title"), default_title, 90),
        nodes=tuple(nodes),
        edges=tuple(edges),
        note=_clean_label(raw.get("note"), "Proposed logical architecture; validate during discovery.", 160),
        groups=tuple(groups),
        description=_clean_label(
            raw.get("description"),
            f"This diagram depicts {raw.get('title') or default_title}.",
            320,
        ),
    )


def _extract_json(text: str) -> Dict[str, Any]:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", str(text or "").strip(), flags=re.I)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Diagram agent did not return JSON")
    value = json.loads(cleaned[start:end + 1])
    if not isinstance(value, dict):
        raise ValueError("Diagram agent JSON was not an object")
    return value


def _string_values(value: Any) -> List[str]:
    if isinstance(value, str):
        return [part.strip() for part in re.split(r"[,;\n]", value) if part.strip()]
    if isinstance(value, dict):
        return [str(key).strip() for key in value if str(key).strip()]
    if isinstance(value, Sequence):
        result: List[str] = []
        for item in value:
            if isinstance(item, dict):
                candidate = item.get("name") or item.get("service") or item.get("title")
                if candidate:
                    result.append(str(candidate).strip())
            elif item:
                result.append(str(item).strip())
        return result
    return []


def fallback_spec(requirements: Dict[str, Any], metadata: Dict[str, Any], registry: Optional[AwsIconRegistry] = None,
                  candidates: Sequence[IconCandidate] = ()) -> DiagramSpec:
    """Build a conservative source-grounded model without an LLM."""
    company = _clean_label(metadata.get("company_name"), "Customer", 40)
    project = _clean_label(metadata.get("project_title"), "Solution Architecture", 70)
    services = _string_values(requirements.get("aws_services"))[:14]
    integrations = _string_values(
        requirements.get("integrations")
        or requirements.get("external_systems")
        or requirements.get("data_sources")
    )[:4]
    features = _string_values(requirements.get("key_features"))[:3]

    nodes: List[Dict[str, Any]] = [
        {"id": "users", "label": f"{company} Users", "kind": "actor", "layer": 0},
        {"id": "solution", "label": project, "kind": "application", "layer": 1,
         "subtitle": features[0] if features else "Proposed solution"},
    ]
    edges: List[Dict[str, Any]] = [{"source": "users", "target": "solution", "label": "Uses"}]
    if services:
        for index, service in enumerate(services, 1):
            node_id = f"aws_{index}"
            match = registry.candidate(service, "explicit", f"aws_services: {service}") if registry else None
            nodes.append({"id": node_id, "label": service, "kind": "service", "layer": 2,
                          "icon_key": match.key if match else "", "group": "aws_services"})
            edges.append({"source": "solution", "target": node_id})
    else:
        nodes.append({"id": "platform", "label": "AWS Platform Services", "kind": "service", "layer": 2})
        edges.append({"source": "solution", "target": "platform"})
    for index, system in enumerate(integrations, 1):
        node_id = f"external_{index}"
        nodes.append({"id": node_id, "label": system, "kind": "external", "layer": 3})
        edges.append({"source": "solution", "target": node_id, "label": "Integrates"})
    groups = [{"id": "aws_services", "label": "AWS Cloud", "kind": "functional"}] if services else []
    candidate_map = {item.key: item for item in candidates}
    if registry:
        for service in services:
            match = registry.candidate(service, "explicit", f"aws_services: {service}")
            if match:
                candidate_map[match.key] = match
    return validate_spec({"title": f"{project} — Proposed Architecture", "nodes": nodes, "edges": edges,
                          "groups": groups}, project, candidate_map)


def _chain_order(spec: DiagramSpec) -> List[str]:
    """Return a directed path order when the graph is a simple workflow chain."""
    if len(spec.edges) != len(spec.nodes) - 1:
        return []
    incoming = {node.id: 0 for node in spec.nodes}
    outgoing: Dict[str, List[str]] = {node.id: [] for node in spec.nodes}
    for edge in spec.edges:
        incoming[edge.target] += 1
        outgoing[edge.source].append(edge.target)
    starts = [node_id for node_id, count in incoming.items() if count == 0]
    if len(starts) != 1 or any(count > 1 for count in incoming.values()):
        return []
    if any(len(targets) > 1 for targets in outgoing.values()):
        return []
    order, current, seen = [], starts[0], set()
    while current not in seen:
        order.append(current)
        seen.add(current)
        targets = outgoing[current]
        if not targets:
            break
        current = targets[0]
    return order if len(order) == len(spec.nodes) else []


def _star_hub(spec: DiagramSpec) -> Optional[str]:
    """Identify a genuine hub-and-spoke integration graph."""
    neighbours = {node.id: set() for node in spec.nodes}
    for edge in spec.edges:
        neighbours[edge.source].add(edge.target)
        neighbours[edge.target].add(edge.source)
    hub, peers = max(neighbours.items(), key=lambda item: len(item[1]))
    return hub if len(peers) >= len(spec.nodes) - 1 and len(spec.nodes) >= 5 else None


def _topological_order(spec: DiagramSpec) -> List[str]:
    """Return a stable dependency order, falling back to declared node order."""
    declared = [node.id for node in spec.nodes]
    rank = {node_id: index for index, node_id in enumerate(declared)}
    incoming = {node_id: 0 for node_id in declared}
    outgoing: Dict[str, List[str]] = {node_id: [] for node_id in declared}
    for edge in spec.edges:
        if edge.source in outgoing and edge.target in incoming:
            outgoing[edge.source].append(edge.target)
            incoming[edge.target] += 1
    ready = sorted((node_id for node_id, count in incoming.items() if count == 0), key=rank.get)
    ordered: List[str] = []
    while ready:
        current = ready.pop(0)
        ordered.append(current)
        for target in sorted(outgoing[current], key=rank.get):
            incoming[target] -= 1
            if incoming[target] == 0:
                ready.append(target)
                ready.sort(key=rank.get)
    return ordered if len(ordered) == len(declared) else declared


def _compact_grid(
    order: List[str], node_width: int, node_height: int,
    x_gap: int, y_gap: int, margin: int,
) -> Tuple[Dict[str, Tuple[int, int, int, int]], int, int]:
    """Arrange a flow in a landscape, serpentine reading grid of at most three rows."""
    rows = min(3, max(1, math.ceil(len(order) / 4)))
    columns = math.ceil(len(order) / rows)
    width = margin * 2 + columns * node_width + max(0, columns - 1) * x_gap
    height = max(500, 205 + rows * node_height + max(0, rows - 1) * y_gap)
    positions: Dict[str, Tuple[int, int, int, int]] = {}
    for index, node_id in enumerate(order):
        row, offset = divmod(index, columns)
        column = offset if row % 2 == 0 else columns - 1 - offset
        positions[node_id] = (
            margin + column * (node_width + x_gap),
            130 + row * (node_height + y_gap),
            node_width,
            node_height,
        )
    return positions, width, height


def _geometry(spec: DiagramSpec) -> Tuple[Dict[str, Tuple[int, int, int, int]], int, int]:
    """Lay out a readable, compact landscape flowchart."""
    node_width, node_height = 245, 112
    x_gap, y_gap, margin = 92, 72, 70
    hub_id = _star_hub(spec)
    if hub_id:
        peers = [node.id for node in spec.nodes if node.id != hub_id]
        columns = min(4, max(2, math.ceil(len(peers) / 2)))
        width = margin * 2 + columns * node_width + max(0, columns - 1) * x_gap
        height = 720
        positions: Dict[str, Tuple[int, int, int, int]] = {
            hub_id: ((width - node_width) // 2, 304, node_width, node_height)
        }
        top = peers[:columns]
        bottom = peers[columns:]
        for row_nodes, y in ((top, 135), (bottom, 535)):
            used_width = len(row_nodes) * node_width + max(0, len(row_nodes) - 1) * x_gap
            start_x = (width - used_width) // 2
            for index, node_id in enumerate(row_nodes):
                positions[node_id] = (start_x + index * (node_width + x_gap), y, node_width, node_height)
        return positions, width, height

    chain = _chain_order(spec)
    if len(chain) >= 5:
        # A long sequence is wrapped as a left-to-right serpentine reading path,
        # preventing a narrow multi-page vertical diagram while retaining order.
        columns = min(4, len(chain))
        rows = math.ceil(len(chain) / columns)
        width = margin * 2 + columns * node_width + (columns - 1) * x_gap
        height = max(
            520,
            210 + rows * node_height + max(0, rows - 1) * y_gap,
            math.ceil(width / 2.0),
        )
        positions = {}
        for index, node_id in enumerate(chain):
            row, offset = divmod(index, columns)
            column = offset if row % 2 == 0 else columns - 1 - offset
            positions[node_id] = (
                margin + column * (node_width + x_gap),
                135 + row * (node_height + y_gap),
                node_width,
                node_height,
            )
        return positions, width, height

    layers: Dict[int, List[Node]] = {}
    source_layers = sorted({node.layer for node in spec.nodes})
    # Flow diagrams prioritize a left-to-right reading order. Four compact
    # columns remain readable on a portrait Word page and avoid tall stacks.
    layer_map = {
        layer: min(3, round(index * 3 / max(1, len(source_layers) - 1)))
        for index, layer in enumerate(source_layers)
    }
    for node in spec.nodes:
        layers.setdefault(layer_map[node.layer], []).append(node)
    ordered_layers = sorted(layers)
    max_rows = max(len(layers[layer]) for layer in ordered_layers)
    width = margin * 2 + len(ordered_layers) * node_width + max(0, len(ordered_layers) - 1) * x_gap
    content_height = max_rows * node_height + max(0, max_rows - 1) * y_gap
    height = max(470, margin * 2 + 105 + content_height, math.ceil(width / 2.0))
    if len(spec.nodes) >= 6 and (max_rows > 3 or height > width * 0.82):
        # Branch-heavy flows can place many peers in one inferred layer. Avoid
        # turning that into a tall stack in Word by using a bounded-row grid.
        return _compact_grid(
            _topological_order(spec), node_width, node_height, x_gap, y_gap, margin
        )
    positions: Dict[str, Tuple[int, int, int, int]] = {}
    for column, layer in enumerate(ordered_layers):
        items = sorted(layers[layer], key=lambda item: item.id)
        content_height = len(items) * node_height + max(0, len(items) - 1) * y_gap
        start_y = 125 + max(0, (height - 165 - content_height) // 2)
        x = margin + column * (node_width + x_gap)
        for row, node in enumerate(items):
            y = start_y + row * (node_height + y_gap)
            positions[node.id] = (x, y, node_width, node_height)
    return positions, width, height


def _architecture_role(node: Node, groups: Dict[str, Group]) -> str:
    """Resolve a semantic placement role without asking the model for coordinates."""
    if node.placement_role:
        return node.placement_role
    text = f"{node.label} {node.subtitle} {groups.get(node.group, Group('', '')).label}".casefold()
    if node.kind in {"actor", "external", "channel"}:
        return "external"
    if any(token in text for token in ("route 53", "route53", "cloudfront", "api gateway", "load balancer", " alb", "dns")):
        return "entry"
    if any(token in text for token in (
        "security", "identity", "cognito", "iam", "kms", "secret", "guardduty", "inspector",
        "certificate", "waf", "shield", "config", "cloudtrail",
    )):
        return "security"
    if any(token in text for token in ("cloudwatch", "x-ray", "monitor", "observab", "logging", "alarm")):
        return "operations"
    if any(token in text for token in (
        "rds", "database", "dynamodb", "s3", "storage", "opensearch", "elasticache", "redshift",
        "aurora", "documentdb", "neptune", "efs", "backup",
    )):
        return "data"
    if any(token in text for token in (
        "lambda", "ec2", "ecs", "fargate", "eks", "compute", "bedrock", "sagemaker", "agentcore",
        "application", "service", "worker", "container",
    )):
        return "compute"
    return "integration"


def _architecture_scope(node: Node, role: str) -> str:
    if node.scope:
        return node.scope
    text = f"{node.label} {node.subtitle}".casefold()
    if role == "external":
        return "external"
    if role in {"security", "operations"}:
        return "regional"
    if role in {"entry", "compute"}:
        return "vpc"
    if any(token in text for token in ("rds", "aurora", "elasticache", "ec2", "ecs", "fargate", "eks")):
        return "vpc"
    return "managed"


def _grid_positions(
    nodes: Sequence[Node], x: int, y: int, width: int, columns: int,
    node_w: int = 138, node_h: int = 116, x_gap: int = 24, y_gap: int = 28,
) -> Tuple[Dict[str, Tuple[int, int, int, int]], int]:
    positions: Dict[str, Tuple[int, int, int, int]] = {}
    if not nodes:
        return positions, 0
    columns = max(1, min(columns, len(nodes)))
    rows = math.ceil(len(nodes) / columns)
    for index, node in enumerate(nodes):
        row, column = divmod(index, columns)
        used = min(columns, len(nodes) - row * columns)
        row_width = used * node_w + max(0, used - 1) * x_gap
        start_x = x + max(0, (width - row_width) // 2)
        positions[node.id] = (start_x + column * (node_w + x_gap), y + row * (node_h + y_gap), node_w, node_h)
    return positions, rows * node_h + max(0, rows - 1) * y_gap


def _aws_architecture_layout(
    spec: DiagramSpec,
) -> Tuple[Dict[str, Tuple[int, int, int, int]], Dict[str, Tuple[int, int, int, int]], int, int]:
    """Lay out an AWS overview as nested infrastructure, not functional swimlanes.

    The model selects components and semantic roles.  Code owns all dimensions,
    containment, symmetry and gutters, which keeps both PNG and draw.io stable.
    """
    group_map = {group.id: group for group in spec.groups}
    buckets: Dict[str, List[Node]] = {role: [] for role in ALLOWED_PLACEMENT_ROLES}
    scopes: Dict[str, str] = {}
    for node in spec.nodes:
        role = _architecture_role(node, group_map)
        buckets[role].append(node)
        scopes[node.id] = _architecture_scope(node, role)

    external = buckets["external"]
    managed = buckets["security"] + buckets["operations"]
    data_vpc = [node for node in buckets["data"] if scopes[node.id] == "vpc"]
    managed += [node for node in buckets["data"] if scopes[node.id] != "vpc"]
    workload = buckets["compute"] + buckets["integration"]
    # Network-boundary controls (firewalls, transit/routing components) share
    # the ingress rail.  Previously they were accepted by validation but never
    # assigned coordinates, causing a KeyError during PNG/draw.io rendering
    # and dropping every diagram in the batch.
    entry = buckets["entry"] + buckets["network"]

    # Fixed-width rails and content-derived vertical sizing produce consistent
    # diagrams from small serverless designs through 20+ component solutions.
    # Keep explicit external-system gutters on both sides of the AWS account.
    # The former 1500px canvas placed the right gutter *inside* the account,
    # which made actors, managed services, and connectors overlap.
    canvas_w = 1800
    cloud_x, cloud_y, cloud_w = 220, 220, 1360
    vpc_x, vpc_y, vpc_w = 300, cloud_y + 110, 900
    managed_x, managed_w = 1230, 300
    entry_pos, entry_h = _grid_positions(
        entry, vpc_x + 30, vpc_y + 64, vpc_w - 60, 4, 150, 120, 28, 32,
    )
    az_y = vpc_y + 106 + max(120, entry_h)
    az_gap = 28
    az_w = (vpc_w - 76 - az_gap) // 2
    workload_by_az: Dict[str, List[Node]] = {"az_a": [], "az_b": []}
    for node in workload:
        requested = node.availability_zone
        target = requested if requested in workload_by_az else min(workload_by_az, key=lambda key: len(workload_by_az[key]))
        workload_by_az[target].append(node)
    workload_pos: Dict[str, Tuple[int, int, int, int]] = {}
    workload_heights: List[int] = []
    for index, zone in enumerate(("az_a", "az_b")):
        zone_x = vpc_x + 24 + index * (az_w + az_gap)
        zone_positions, zone_height = _grid_positions(
            workload_by_az[zone], zone_x + 18, az_y + 104, az_w - 36, 2, 150, 124, 24, 34,
        )
        workload_pos.update(zone_positions)
        workload_heights.append(zone_height)
    workload_h = max(workload_heights or [0])
    data_y = az_y + 132 + max(124, workload_h)
    data_pos, data_h = _grid_positions(
        data_vpc, vpc_x + 42, data_y, vpc_w - 84, 4, 150, 120, 24, 34,
    )
    managed_pos, managed_h = _grid_positions(
        managed, managed_x + 8, vpc_y + 76, managed_w - 16, 2, 134, 120, 14, 34,
    )

    vpc_h = max(560, (data_y - vpc_y) + max(116, data_h) + 42)
    region_h = max(vpc_h + 90, managed_h + 130)
    cloud_h = region_h + 100
    canvas_h = max(800, cloud_y + cloud_h + 55)
    positions: Dict[str, Tuple[int, int, int, int]] = {}
    positions.update(entry_pos)
    positions.update(workload_pos)
    positions.update(data_pos)
    positions.update(managed_pos)

    # The primary actor sits above the account ingress. Other enterprise actors
    # and systems use side rails, making the AWS trust boundary unambiguous.
    top_actor = next((node for node in external if node.kind == "actor"), external[0] if external else None)
    side_external = [node for node in external if node is not top_actor]
    if top_actor:
        positions[top_actor.id] = (cloud_x + (cloud_w - 200) // 2, 90, 200, 120)
    for index, node in enumerate(side_external):
        side = index % 2
        row = index // 2
        x = 10 if side == 0 else canvas_w - 200
        positions[node.id] = (x, cloud_y + 150 + row * 170, 190, 132)

    boxes = {
        "__aws_account": (cloud_x, cloud_y, cloud_w, cloud_h),
        "__region": (cloud_x + 30, cloud_y + 48, cloud_w - 60, region_h),
        "__vpc": (vpc_x, vpc_y, vpc_w, vpc_h),
        "__az_a": (vpc_x + 24, az_y, az_w, vpc_h - (az_y - vpc_y) - 28),
        "__az_b": (vpc_x + 24 + az_w + az_gap, az_y, az_w, vpc_h - (az_y - vpc_y) - 28),
        "__workload": (vpc_x + 30, az_y + 62, vpc_w - 60, max(170, workload_h + 62)),
        "__managed": (managed_x, vpc_y, managed_w, region_h - 62),
    }
    # Functional LLM groups are still retained in the editable node metadata,
    # but are not drawn as another set of boundaries. The standardized AWS
    # Account/Region/VPC/AZ/workload/managed hierarchy already communicates
    # containment; extra frames were the largest source of label and node
    # collisions in complex diagrams.
    print(
        "[DIAGRAM][LAYOUT] AWS hierarchy: "
        f"external={len(external)}, entry={len(entry)}, workload={len(workload)}, "
        f"vpc_data={len(data_vpc)}, managed={len(managed)}, canvas={canvas_w}x{canvas_h}",
        flush=True,
    )
    return positions, boxes, canvas_w, canvas_h


def _layout(spec: DiagramSpec) -> Tuple[Dict[str, Tuple[int, int, int, int]], Dict[str, Tuple[int, int, int, int]], int, int]:
    """Shared collision-free geometry for draw.io and the static DOCX image."""
    if any(node.icon_key for node in spec.nodes):
        return _aws_architecture_layout(spec)
    if not spec.groups:
        positions, width, height = _geometry(spec)
        return positions, {}, width, height
    node_w, node_h, gap, margin = 184, 138, 44, 64
    width, y = 1240, 128
    positions: Dict[str, Tuple[int, int, int, int]] = {}
    boxes: Dict[str, Tuple[int, int, int, int]] = {}
    grouped = {group.id: [node for node in spec.nodes if node.group == group.id] for group in spec.groups}
    rows = [(group, grouped[group.id]) for group in spec.groups if grouped[group.id]]
    ungrouped = [node for node in spec.nodes if not node.group]
    if ungrouped:
        rows.insert(0, (Group("ungrouped", "Users and External Systems", "external"), ungrouped))
    for group, nodes in rows:
        cols = min(5, len(nodes))
        row_count = math.ceil(len(nodes) / cols)
        box_h = 62 + row_count * node_h + max(0, row_count - 1) * 38 + 32
        boxes[group.id] = (margin, y, width - margin * 2, box_h)
        for index, node in enumerate(nodes):
            row, col = divmod(index, cols)
            used_cols = min(cols, len(nodes) - row * cols)
            content_w = used_cols * node_w + max(0, used_cols - 1) * gap
            start_x = (width - content_w) // 2
            positions[node.id] = (start_x + col * (node_w + gap), y + 54 + row * (node_h + 38), node_w, node_h)
        y += box_h + 42
    height = max(680, y + 50, math.ceil(width / 2))
    return positions, boxes, width, height


def drawio_xml(spec: DiagramSpec, registry: Optional[AwsIconRegistry] = None) -> str:
    positions, group_boxes, width, height = _layout(spec)
    mxfile = ET.Element("mxfile", {"host": "app.diagrams.net", "agent": "ShellKode SOW Generator", "version": "1"})
    diagram = ET.SubElement(mxfile, "diagram", {"id": "architecture", "name": "Architecture"})
    model = ET.SubElement(diagram, "mxGraphModel", {
        "dx": str(width), "dy": str(height), "grid": "1", "gridSize": "10", "guides": "1",
        "tooltips": "1", "connect": "1", "arrows": "1", "fold": "1", "page": "1",
        "pageScale": "1", "pageWidth": str(width), "pageHeight": str(height), "math": "0", "shadow": "0",
    })
    root = ET.SubElement(model, "root")
    ET.SubElement(root, "mxCell", {"id": "0"})
    ET.SubElement(root, "mxCell", {"id": "1", "parent": "0"})
    group_map = {group.id: group for group in spec.groups}
    boundary_labels = {
        "__aws_account": "AWS Account", "__region": "AWS Region", "__vpc": "VPC",
        "__az_a": "Availability Zone A · Private subnet", "__az_b": "Availability Zone B · Private subnet",
        "__workload": "Application workload", "__managed": "Regional managed services",
    }
    boundary_styles = {
        "__aws_account": ("#D1326A", "0", "#D1326A"),
        "__region": ("#00A4A6", "1", "#007F82"),
        "__vpc": ("#8B5CF6", "0", "#6D28D9"),
        "__az_a": ("#0EA5E9", "1", "#0284C7"),
        "__az_b": ("#0EA5E9", "1", "#0284C7"),
        "__workload": ("#334155", "1", "#334155"),
        "__managed": ("#94A3B8", "1", "#475569"),
    }
    for group_id, (x, y, w, h) in group_boxes.items():
        group = group_map.get(group_id)
        if group_id in boundary_labels:
            label = boundary_labels[group_id]
            stroke, dashed, font_color = boundary_styles[group_id]
        else:
            label = group.label if group else "Users and External Systems"
            stroke, dashed, font_color = "#F97316", "1", "#EA580C"
        style = (
            "rounded=1;whiteSpace=wrap;html=1;verticalAlign=top;align=left;spacingTop=10;spacingLeft=12;"
            f"fillColor=#FFFFFF;fillOpacity=0;strokeColor={stroke};strokeWidth=2;dashed={dashed};"
            f"fontStyle=1;fontSize=14;fontColor={font_color};"
        )
        cell = ET.SubElement(root, "mxCell", {"id": f"group_{group_id}", "value": label, "style": style, "vertex": "1", "parent": "1"})
        ET.SubElement(cell, "mxGeometry", {"x": str(x), "y": str(y), "width": str(w), "height": str(h), "as": "geometry"})
    for node in spec.nodes:
        x, y, w, h = positions[node.id]
        fill, stroke = KIND_STYLES[node.kind]
        value = node.label + (f"<br><font color=\"#64748B\" style=\"font-size:11px\">{node.subtitle}</font>" if node.subtitle else "")
        icon_uri = registry.svg_data_uri(node.icon_key) if registry and node.icon_key else None
        style = (
            "rounded=1;whiteSpace=wrap;html=1;arcSize=12;shadow=0;"
            f"fillColor={fill};strokeColor={stroke};strokeWidth=2;fontFamily=Helvetica;"
            "fontSize=14;fontStyle=1;fontColor=#1F2937;verticalAlign=middle;align=center;spacing=8;"
        )
        if node.kind == "process":
            style = style.replace("rounded=1", "rounded=0")
        elif node.kind == "terminator":
            style = style.replace("arcSize=12", "arcSize=50")
        elif node.kind == "decision":
            style = style.replace("rounded=1", "shape=rhombus;rounded=0")
        elif node.kind == "input_output":
            style = style.replace("rounded=1", "shape=parallelogram;perimeter=parallelogramPerimeter;rounded=0")
        if icon_uri:
            style = ("shape=label;whiteSpace=wrap;html=1;image=" + icon_uri + ";imageWidth=64;imageHeight=64;"
                     "imageAlign=center;imageVerticalAlign=top;verticalAlign=bottom;align=center;spacingTop=68;"
                     "fillColor=none;strokeColor=none;fontFamily=Helvetica;fontSize=13;fontStyle=1;fontColor=#1F2937;")
        cell = ET.SubElement(root, "mxCell", {"id": node.id, "value": value, "style": style, "vertex": "1", "parent": "1"})
        ET.SubElement(cell, "mxGeometry", {"x": str(x), "y": str(y), "width": str(w), "height": str(h), "as": "geometry"})
    for index, edge in enumerate(spec.edges, 1):
        sx, sy, sw, sh = positions[edge.source]
        tx, ty, tw, th = positions[edge.target]
        if ty >= sy + sh:
            anchors = "exitX=0.5;exitY=1;exitDx=0;exitDy=0;entryX=0.5;entryY=0;entryDx=0;entryDy=0;"
        elif sy >= ty + th:
            anchors = "exitX=0.5;exitY=0;exitDx=0;exitDy=0;entryX=0.5;entryY=1;entryDx=0;entryDy=0;"
        elif tx >= sx:
            anchors = "exitX=1;exitY=0.5;exitDx=0;exitDy=0;entryX=0;entryY=0.5;entryDx=0;entryDy=0;"
        else:
            anchors = "exitX=0;exitY=0.5;exitDx=0;exitDy=0;entryX=1;entryY=0.5;entryDx=0;entryDy=0;"
        style = (
            "edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;jettySize=24;"
            "jumpStyle=arc;jumpSize=7;html=1;"
            "endArrow=block;endFill=1;strokeColor=#64748B;strokeWidth=2;fontSize=11;fontColor=#475569;"
            + anchors
        )
        cell = ET.SubElement(root, "mxCell", {
            "id": f"edge_{index}", "value": edge.label, "style": style, "edge": "1", "parent": "1",
            "source": edge.source, "target": edge.target,
        })
        ET.SubElement(cell, "mxGeometry", {"relative": "1", "as": "geometry"})
    return ET.tostring(mxfile, encoding="unicode")


def _font(config: Any, bold: bool, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    name = "DMSans-Bold.ttf" if bold else "DMSans-Regular.ttf"
    path = config.ASSETS_DIR / "fonts" / name
    try:
        return ImageFont.truetype(str(path), size=size)
    except OSError:
        return ImageFont.load_default()


def _wrapped_lines(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, width: int, max_lines: int = 2) -> List[str]:
    words: List[str] = []
    for word in str(text or "").split():
        if draw.textbbox((0, 0), word, font=font)[2] <= width:
            words.append(word)
            continue
        # Split slash-separated and otherwise unbroken technical labels by
        # measured character width so text can never escape a node boundary.
        chunk = ""
        for character in word:
            candidate = chunk + character
            if chunk and draw.textbbox((0, 0), candidate, font=font)[2] > width:
                words.append(chunk)
                chunk = character
            else:
                chunk = candidate
        if chunk:
            words.append(chunk)
    lines: List[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textbbox((0, 0), candidate, font=font)[2] <= width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
        if len(lines) == max_lines:
            break
    if current and len(lines) < max_lines:
        lines.append(current)
    if len(lines) == max_lines and words and " ".join(lines) != " ".join(words):
        lines[-1] = lines[-1].rstrip("…") + "…"
    return lines


def render_png(spec: DiagramSpec, config: Any, registry: Optional[AwsIconRegistry] = None) -> bytes:
    positions, group_boxes, width, height = _layout(spec)
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    title_font = _font(config, True, 30)
    label_font = _font(config, True, 18)
    subtitle_font = _font(config, False, 14)
    edge_font = _font(config, False, 13)
    title_lines = _wrapped_lines(draw, spec.title, title_font, width - 140, 2)
    for index, line in enumerate(title_lines):
        draw.text((70, 28 + index * 34), line, fill="#3E2A91", font=title_font)
    rule_y = 75 if len(title_lines) == 1 else 105
    draw.line((70, rule_y, width - 70, rule_y), fill="#7B3FF2", width=3)

    group_map = {group.id: group for group in spec.groups}
    boundary_labels = {
        "__aws_account": "AWS Account", "__region": "AWS Region", "__vpc": "VPC",
        "__az_a": "Availability Zone A · Private subnet", "__az_b": "Availability Zone B · Private subnet",
        "__workload": "Application workload", "__managed": "Regional managed services",
    }
    boundary_colours = {
        "__aws_account": "#D1326A", "__region": "#00A4A6", "__vpc": "#8B5CF6",
        "__az_a": "#0EA5E9", "__az_b": "#0EA5E9", "__workload": "#334155", "__managed": "#94A3B8",
    }
    group_font = _font(config, True, 16)
    for group_id, (x, y, w, h) in group_boxes.items():
        group = group_map.get(group_id, Group(group_id, "Users and External Systems", "external"))
        label = boundary_labels.get(group_id, group.label)
        colour = boundary_colours.get(group_id, "#F97316")
        draw.rounded_rectangle((x, y, x + w, y + h), radius=13, outline=colour, width=2)
        draw.text((x + 14, y + 12), label, fill=colour, font=group_font)

    node_map = {node.id: node for node in spec.nodes}
    label_boxes: List[Tuple[int, int, int, int]] = []
    node_boxes = [(x, y, x + w, y + h) for x, y, w, h in positions.values()]
    for edge_index, edge in enumerate(spec.edges):
        sx, sy, sw, sh = positions[edge.source]
        tx, ty, tw, th = positions[edge.target]
        source_icon = bool(node_map[edge.source].icon_key)
        target_icon = bool(node_map[edge.target].icon_key)
        source_cx, target_cx = sx + sw // 2, tx + tw // 2
        if ty >= sy + sh:
            start = (source_cx, sy + sh - 3)
            end = (target_cx, ty + (5 if target_icon else 0))
            lane = ((edge_index % 3) - 1) * 10
            mid_y = (start[1] + end[1]) // 2 + lane
            points = [start, (start[0], mid_y), (end[0], mid_y), end]
        elif sy >= ty + th:
            start = (source_cx, sy + (5 if source_icon else 0))
            end = (target_cx, ty + th - 3)
            lane = ((edge_index % 3) - 1) * 10
            mid_y = (start[1] + end[1]) // 2 + lane
            points = [start, (start[0], mid_y), (end[0], mid_y), end]
        elif tx >= sx + sw:
            start = (source_cx + 34, sy + 37) if source_icon else (sx + sw, sy + sh // 2)
            end = (target_cx - 34, ty + 37) if target_icon else (tx, ty + th // 2)
            mid_x = (start[0] + end[0]) // 2
            points = [start, (mid_x, start[1]), (mid_x, end[1]), end]
        else:
            start = (source_cx - 34, sy + 37) if source_icon else (sx, sy + sh // 2)
            end = (target_cx + 34, ty + 37) if target_icon else (tx + tw, ty + th // 2)
            mid_x = (start[0] + end[0]) // 2
            points = [start, (mid_x, start[1]), (mid_x, end[1]), end]
        draw.line(points, fill="#64748B", width=3, joint="curve")
        angle = math.atan2(end[1] - points[-2][1], end[0] - points[-2][0])
        arrow = []
        for delta in (2.55, -2.55):
            arrow.append((end[0] + 11 * math.cos(angle + delta), end[1] + 11 * math.sin(angle + delta)))
        draw.polygon([end, arrow[0], arrow[1]], fill="#64748B")
        if edge.label:
            label = _clean_label(edge.label, "", 26)
            bbox = draw.textbbox((0, 0), label, font=edge_font)
            label_width, label_height = bbox[2] - bbox[0], bbox[3] - bbox[1]
            segments = list(zip(points, points[1:]))
            segment_start, segment_end = max(
                segments,
                key=lambda segment: abs(segment[1][0] - segment[0][0]) + abs(segment[1][1] - segment[0][1]),
            )
            center_x = (segment_start[0] + segment_end[0]) // 2
            center_y = (segment_start[1] + segment_end[1]) // 2
            horizontal = abs(segment_end[0] - segment_start[0]) >= abs(segment_end[1] - segment_start[1])
            offsets = (-label_height - 10, 8, -label_height - 32) if horizontal else (-label_width - 14, 10, 24)
            placed = None
            for offset in offsets:
                if horizontal:
                    left, top = center_x - label_width // 2 - 7, center_y + offset
                else:
                    left, top = center_x + offset, center_y - label_height // 2 - 4
                left = max(6, min(left, width - label_width - 20))
                top = max(110, min(top, height - label_height - 12))
                box = (left, top, left + label_width + 14, top + label_height + 9)
                intersects = lambda a, b: not (a[2] <= b[0] or a[0] >= b[2] or a[3] <= b[1] or a[1] >= b[3])
                if not any(intersects(box, other) for other in node_boxes + label_boxes):
                    placed = box
                    break
            # Connector labels remain in draw.io even when the static preview
            # has no collision-free position.
            if placed:
                draw.rounded_rectangle(placed, 5, fill="white", outline="#E2E8F0")
                draw.text((placed[0] + 7, placed[1] + 3), label, fill="#475569", font=edge_font)
                label_boxes.append(placed)

    # Redraw boundary captions after connectors so routed lines never obscure
    # AWS Account/Region/VPC/AZ labels.
    for group_id, (x, y, _w, _h) in group_boxes.items():
        group = group_map.get(group_id, Group(group_id, "Users and External Systems", "external"))
        label = boundary_labels.get(group_id, group.label)
        colour = boundary_colours.get(group_id, "#F97316")
        label_bbox = draw.textbbox((0, 0), label, font=group_font)
        label_w = label_bbox[2] - label_bbox[0]
        label_h = label_bbox[3] - label_bbox[1]
        draw.rectangle((x + 8, y + 6, x + 22 + label_w, y + 20 + label_h), fill="white")
        draw.text((x + 14, y + 12), label, fill=colour, font=group_font)

    for node_id, (x, y, w, h) in positions.items():
        node = node_map[node_id]
        fill, stroke = KIND_STYLES[node.kind]
        icon = registry.png(node.icon_key, 64) if registry and node.icon_key else None
        if icon:
            image.paste(icon, (x + (w - 64) // 2, y + 5), icon)
            lines = _wrapped_lines(draw, node.label, label_font, w - 14, 3)
            cursor = y + 73
            for line in lines:
                bbox = draw.textbbox((0, 0), line, font=label_font)
                text_w = bbox[2] - bbox[0]
                text_h = bbox[3] - bbox[1]
                text_x = x + (w - text_w) // 2
                # Mask only the caption glyph area. This keeps the connector
                # visibly attached to the icon while preventing a crossing
                # route from reducing the service name's legibility.
                draw.rectangle(
                    (text_x - 3, cursor - 2, text_x + text_w + 3, cursor + text_h + 3),
                    fill="white",
                )
                draw.text((text_x, cursor), line, fill="#1F2937", font=label_font)
                cursor += 20
            continue
        text_width = w - 28
        if node.kind == "terminator":
            draw.rounded_rectangle((x, y, x + w, y + h), radius=h // 2, fill=fill, outline=stroke, width=3)
            text_width = w - h
        elif node.kind == "decision":
            draw.polygon(
                [(x + w // 2, y), (x + w, y + h // 2), (x + w // 2, y + h), (x, y + h // 2)],
                fill=fill,
                outline=stroke,
            )
            draw.line(
                [(x + w // 2, y), (x + w, y + h // 2), (x + w // 2, y + h),
                 (x, y + h // 2), (x + w // 2, y)],
                fill=stroke,
                width=3,
            )
            text_width = round(w * 0.58)
        elif node.kind == "input_output":
            slant = min(34, w // 6)
            points = [(x + slant, y), (x + w, y), (x + w - slant, y + h), (x, y + h)]
            draw.polygon(points, fill=fill, outline=stroke)
            draw.line(points + [points[0]], fill=stroke, width=3)
            text_width = w - slant * 2 - 16
        elif node.kind == "process":
            draw.rectangle((x, y, x + w, y + h), fill=fill, outline=stroke, width=3)
        else:
            draw.rounded_rectangle((x, y, x + w, y + h), radius=13, fill=fill, outline=stroke, width=3)
        lines = _wrapped_lines(draw, node.label, label_font, text_width)
        subtitle_lines = _wrapped_lines(draw, node.subtitle, subtitle_font, text_width, 2) if node.subtitle else []
        total_height = len(lines) * 21 + len(subtitle_lines) * 17
        cursor = y + (h - total_height) // 2
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=label_font)
            draw.text((x + (w - (bbox[2] - bbox[0])) // 2, cursor), line, fill="#1F2937", font=label_font)
            cursor += 21
        for subtitle in subtitle_lines:
            bbox = draw.textbbox((0, 0), subtitle, font=subtitle_font)
            draw.text((x + (w - (bbox[2] - bbox[0])) // 2, cursor + 2), subtitle, fill="#64748B", font=subtitle_font)
            cursor += 17

    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def edit_url(xml: str, editor_url: Optional[str] = None) -> str:
    encoded_xml = urllib.parse.quote(xml, safe="~()*!.'")
    compressor = zlib.compressobj(level=9, wbits=-15)
    compressed = compressor.compress(encoded_xml.encode("utf-8")) + compressor.flush()
    payload = {
        "type": "xml",
        "compressed": True,
        "data": base64.b64encode(compressed).decode("ascii"),
    }
    base_url = (editor_url or os.environ.get("DRAWIO_EDITOR_URL") or "https://app.diagrams.net").rstrip("/")
    # Word rewrites a URL fragment as the HYPERLINK field's ``\\l`` bookmark
    # switch. The long draw.io ``#create`` payload is not a valid Word
    # bookmark, so updating fields replaces the visible link with
    # "Error! Hyperlink reference not valid." diagrams.net supports the same
    # create payload as a query parameter, which remains an external URL in
    # Word and Google Docs.
    return base_url + "/?grid=0&pv=0&" + "create=" + urllib.parse.quote(json.dumps(payload, separators=(",", ":")))


def validate_drawio_xml(xml: str) -> str:
    if not isinstance(xml, str) or not 20 <= len(xml) <= 2_000_000:
        raise ValueError("Diagram XML is empty or too large")
    if "<!DOCTYPE" in xml.upper() or "<!ENTITY" in xml.upper():
        raise ValueError("Diagram XML cannot contain a document type or entities")
    parser = LET.XMLParser(resolve_entities=False, no_network=True, recover=False, huge_tree=False)
    try:
        root = LET.fromstring(xml.encode("utf-8"), parser=parser)
    except LET.XMLSyntaxError as exc:
        raise ValueError("Diagram XML is malformed") from exc
    root_name = LET.QName(root).localname
    if root_name not in {"mxfile", "mxGraphModel"}:
        raise ValueError("Unsupported diagram XML root")
    if root_name == "mxfile" and not root.xpath(".//*[local-name()='mxGraphModel']"):
        raise ValueError("Diagram XML has no graph model")
    return xml


def update_asset(
    xml: str,
    image_data: str,
    existing: Optional[Dict[str, Any]] = None,
    editor_url: Optional[str] = None,
) -> Dict[str, Any]:
    xml = validate_drawio_xml(xml)
    match = re.fullmatch(r"data:image/png;base64,([A-Za-z0-9+/=\r\n]+)", str(image_data or ""))
    if not match:
        raise ValueError("A PNG export from draw.io is required")
    png = base64.b64decode(match.group(1), validate=True)
    if not png.startswith(b"\x89PNG\r\n\x1a\n") or len(png) > 12_000_000:
        raise ValueError("Invalid or oversized PNG export")
    asset = dict(existing or {})
    asset.update({
        "drawio_xml": xml,
        "image_base64": base64.b64encode(png).decode("ascii"),
        "edit_url": edit_url(xml, editor_url),
    })
    return asset


class DiagramService:
    """Bedrock-backed diagram modeller with a deterministic safe fallback."""

    def __init__(self, config: Any, bedrock: Any = None):
        self.config = config
        self.bedrock = bedrock or boto3.client(
            service_name="bedrock-runtime",
            region_name=config.BEDROCK_REGION,
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            aws_session_token=os.getenv("AWS_SESSION_TOKEN"),
            config=config.BOTO_CONFIG,
        )
        self.llm = BedrockLLM(config, self.bedrock)
        self.icon_registry = AwsIconRegistry(config.ASSETS_DIR)

    @staticmethod
    def _eligible_types(requirements: Dict[str, Any], narrative: str) -> List[str]:
        """Choose a small evidence-backed visual set before the LLM is called."""
        eligible = ["architecture_overview"]
        integrations = _string_values(
            requirements.get("integrations")
            or requirements.get("external_systems")
            or requirements.get("data_sources")
        )
        narrative_text = str(narrative or "").casefold()
        flow_signals = sum(
            token in narrative_text
            for token in ("data flow", "workflow", "ingestion", "migration", "request", "response", "pipeline")
        )
        deployment_signals = sum(
            token in narrative_text
            for token in ("vpc", "subnet", "availability zone", "multi-az", "load balancer", "private endpoint")
        )
        if len(integrations) >= 3:
            eligible.append("integration_context")
        if flow_signals >= 2:
            eligible.append("data_flow")
        if deployment_signals >= 3 and len(eligible) < MAX_DIAGRAMS:
            eligible.append("deployment_topology")
        return eligible[:MAX_DIAGRAMS]

    def _prompt(
        self,
        requirements: Dict[str, Any],
        metadata: Dict[str, Any],
        narrative: str,
        eligible_types: Sequence[str],
        icon_candidates: Sequence[IconCandidate],
    ) -> str:
        source = {
            "company": metadata.get("company_name"),
            "project": metadata.get("project_title"),
            "requirements": requirements,
            "architecture_narrative": str(narrative or "")[:9000],
            "allowed_aws_icons": [item.prompt_dict() for item in icon_candidates],
        }
        return f"""You are an AWS solution architect planning a concise set of diagrams for a Statement of Work.
Return JSON only. Create exactly one diagram for each item in ELIGIBLE_TYPES and no others. Use only systems,
services, actors and integrations supported by SOURCE. Do not invent named products. Diagrams must add distinct
value and must not repeat the same view.

Schema:
{{
  "diagrams": [{{
    "diagram_type": "architecture_overview|data_flow|integration_context|deployment_topology",
    "title": "short title",
    "description": "mandatory 1-2 sentence explanation of what the diagram depicts",
    "placement_heading": "best matching SOW section or subsection heading",
    "note": "one short qualification",
    "groups": [{{"id":"stable_id","label":"Data Ingestion|Processing & ML|Storage|Security|other source-backed layer","kind":"functional|external|network|security|data"}}],
    "nodes": [{{"id":"stable_id","label":"short label","kind":"actor|channel|application|service|data|external|process|terminator|decision|input_output","layer":0,"subtitle":"business purpose","group":"optional group id","icon_key":"allowed key or empty","placement_role":"external|entry|network|compute|integration|data|security|operations","scope":"external|regional|vpc|az|managed","availability_zone":"az_a|az_b|empty"}}],
    "edges": [{{"source":"node_id","target":"node_id","label":"short protocol or flow"}}]
  }}]
}}

Rules:
- Maximum {MAX_NODES} nodes and {MAX_EDGES} edges.
- Every edge endpoint must be a node id.
- Keep labels under 60 characters and edge labels under 36 characters.
- description is mandatory and must say what the reader should understand from the diagram.
- placement_heading may name any matching SOW section/subsection, not only Solution Architecture.
- Keep connector labels brief and optional.
- architecture_overview is the ONLY AWS-icon diagram. It is the complete Solution Architecture view: use 12-22
  source-backed nodes when the evidence permits, 5-8 functional/infrastructure boundaries, relevant actors and
  external systems, and the explicit AWS services needed for ingestion, application/compute, orchestration,
  data/storage, security/identity, observability and delivery. Do not collapse several evidenced responsibilities
  into one generic component. Use all directly relevant explicit AWS service candidates.
- In architecture_overview, AWS service nodes MUST use an icon_key from SOURCE.allowed_aws_icons. Never invent a key.
- For architecture_overview, classify every node semantically. placement_role describes its architectural function,
  scope describes its deployment boundary, and availability_zone is used only for genuinely zonal workloads.
  Actors and enterprise systems use scope=external. Internet entry services use entry. Runtime/application services
  use compute or integration. Databases/object stores use data. Cross-cutting controls use security or operations.
- Request multi-AZ placement only when high availability, private subnets, VPC, load balancing, or production
  resilience is supported by SOURCE. Do not claim a subnet or AZ deployment for globally/regional managed services.
- The renderer owns coordinates. It will place external actors outside the AWS account, nest Account > Region > VPC
  > Availability Zones/private subnets, centre ingress above the workload, distribute zonal compute symmetrically,
  keep managed data/security/observability in a separate regional rail, and route connectors orthogonally.
- Preserve component detail but keep the overview visually sparse: normally use 8-16 meaningful connectors rather
  than connecting every component. Show the principal ingress -> workload -> data paths. Security, monitoring and
  governance services are cross-cutting and should remain visible in their rail without individual connectors unless
  a specific interaction must be explained. Give repeated flows one shared caption instead of repeating text.
- For data_flow, integration_context and deployment_topology, create a compact left-to-right flowchart with
  5-12 nodes. Use terminator only for a real start/end, process for actions, decision only for a genuine branch,
  and input_output for information entering or leaving the flow. Do not force every kind: all-process rectangles
  are correct when the evidence has no start/end, decision, or input/output semantics. Use short Yes/No labels on
  real decision branches. For those diagrams groups MUST be [] and icon_key MUST be "".
- A data_flow may be sequential when the real workflow is sequential, but use branches for source-backed decisions,
  exceptions, human hand-offs and alternate outcomes. Do not invent branching merely for visual variety.
- An integration_context is a context/hub view, not a processing sequence. Put the proposed solution or integration
  layer at the centre and connect each peer channel or enterprise system directly to it. Never chain unrelated peer
  systems (for example CRM -> identity -> analytics) unless the source explicitly says data traverses them in order.
- Do not use layers to request a tall stack. The renderer wraps long flows into a compact landscape reading path.
- An explicit icon is named in the source; an inferred icon is permitted only when its supplied evidence matches the required capability.
- Put the AWS service name in label and its role in subtitle. Keep external systems outside AWS groups.
- Arrange only semantic membership and flow. Rendering and alignment are deterministic.

ELIGIBLE_TYPES:
{json.dumps(list(eligible_types))}

SOURCE:
{json.dumps(source, ensure_ascii=False, default=str)}"""

    def _fallback_for_type(
        self,
        diagram_type: str,
        requirements: Dict[str, Any],
        metadata: Dict[str, Any],
    ) -> DiagramSpec:
        candidates = self.icon_registry.candidates(requirements, "")
        overview = fallback_spec(requirements, metadata, self.icon_registry, candidates)
        if diagram_type == "architecture_overview":
            return overview
        integrations = _string_values(
            requirements.get("integrations")
            or requirements.get("external_systems")
            or requirements.get("data_sources")
        )[:6]
        if diagram_type == "integration_context" and integrations:
            raw_nodes = [
                {"id": "solution", "label": metadata.get("project_title", "Proposed Solution"), "kind": "application", "layer": 1},
            ]
            raw_edges = []
            for index, label in enumerate(integrations, 1):
                raw_nodes.append({"id": f"external_{index}", "label": label, "kind": "external", "layer": 0 if index % 2 else 2})
                raw_edges.append({"source": f"external_{index}", "target": "solution", "label": "Integration"})
            return validate_spec({"title": "Integration Context", "nodes": raw_nodes, "edges": raw_edges}, "Integration Context")
        # Reuse the source-grounded graph with a distinct, qualified title if
        # the model omits an eligible optional view.
        title = "End-to-End Data Flow" if diagram_type == "data_flow" else "Deployment Topology"
        raw = {
            "title": title,
            "description": f"This diagram depicts the {title.casefold()} supported by the supplied requirements.",
            "nodes": [
                {
                    "id": node.id,
                    "label": node.label,
                    "kind": "input_output" if node.kind in {"actor", "channel", "data", "external"} else "process",
                    "layer": node.layer,
                    "subtitle": node.subtitle,
                }
                for node in overview.nodes
            ],
            "edges": [edge.__dict__ for edge in overview.edges],
            "note": overview.note,
        }
        return validate_spec(raw, title)

    def _expand_overview(
        self,
        draft: Dict[str, Any],
        target_nodes: int,
        requirements: Dict[str, Any],
        narrative: str,
        candidates: Sequence[IconCandidate],
    ) -> Dict[str, Any]:
        """Request one evidence-grounded detail pass for an undersized architecture."""
        prompt = f"""You are refining an undersized AWS Solution Architecture diagram.
Return one JSON diagram object only, using the same schema as DRAFT. Preserve correct existing components and
connections, then expand it to at least {target_nodes} and at most 22 nodes. Add distinct, source-backed components
for evidenced ingestion, application/compute, orchestration, integrations, data/storage, security/identity,
observability and delivery responsibilities. Do not add a service merely to reach the count. AWS service nodes may
only use keys from ALLOWED_ICONS. Include 5-8 useful groups and connect every node. This is the only icon diagram.

ALLOWED_ICONS:
{json.dumps([candidate.prompt_dict() for candidate in candidates], ensure_ascii=False)}

REQUIREMENTS:
{json.dumps(requirements, ensure_ascii=False, default=str)}

ARCHITECTURE_NARRATIVE:
{str(narrative or '')[:7000]}

DRAFT:
{json.dumps(draft, ensure_ascii=False, default=str)}"""
        result = self.llm.generate(
            prompt,
            task="diagram",
            max_tokens=8000,
            temperature=0.05,
            call_name="Architecture Detail Pass",
            fallback_model_id=getattr(self.config, "WRITER_MODEL_ID", None),
        )
        raw = _extract_json(result.text)
        if isinstance(raw.get("diagrams"), list) and raw["diagrams"]:
            raw = raw["diagrams"][0]
        raw["diagram_type"] = "architecture_overview"
        return raw

    @staticmethod
    def _group_for_category(category: str) -> Tuple[str, str, str]:
        value = str(category or "").casefold()
        if any(token in value for token in ("machine-learning", "analytics", "artificial-intelligence")):
            return "processing_ai", "Processing, Analytics & AI", "functional"
        if any(token in value for token in ("database", "storage", "backup")):
            return "data_storage", "Data & Storage", "data"
        if any(token in value for token in ("security", "identity", "compliance")):
            return "security_identity", "Security & Identity", "security"
        if any(token in value for token in ("network", "content-delivery")):
            return "network_delivery", "Networking & Delivery", "network"
        if any(token in value for token in ("business-app", "customer-enablement", "contact-center")):
            return "customer_engagement", "Customer Engagement", "functional"
        return "application_processing", "Application & Processing", "functional"

    @staticmethod
    def _simplify_architecture_edges(nodes: List[Dict[str, Any]], edges: Any) -> List[Dict[str, Any]]:
        """Keep architectural complexity while enforcing a readable line budget.

        Cross-cutting services remain visible in their regional rail and do not
        need a connector to every workload. The retained edges express the main
        ingress, processing, integration and persistence paths.
        """
        node_by_id = {
            _safe_id(node.get("id"), ""): node for node in nodes
            if _safe_id(node.get("id"), "")
        }
        if not isinstance(edges, list) or len(edges) <= 1:
            return [dict(edge) for edge in edges if isinstance(edge, dict)] if isinstance(edges, list) else []

        roles: Dict[str, str] = {}
        for node_id, node in node_by_id.items():
            supplied = str(node.get("placement_role") or "").casefold()
            if supplied in ALLOWED_PLACEMENT_ROLES:
                roles[node_id] = supplied
                continue
            kind = str(node.get("kind") or "service").casefold()
            roles[node_id] = _architecture_role(
                Node(node_id, str(node.get("label") or node_id), kind if kind in ALLOWED_KINDS else "service", 0,
                     subtitle=str(node.get("subtitle") or ""), icon_key=str(node.get("icon_key") or "")),
                {},
            )

        transition_score = {
            ("external", "entry"): 10,
            ("external", "integration"): 8,
            ("entry", "compute"): 10,
            ("entry", "integration"): 9,
            ("compute", "compute"): 7,
            ("compute", "integration"): 8,
            ("integration", "compute"): 8,
            ("integration", "data"): 9,
            ("compute", "data"): 10,
            ("data", "compute"): 5,
        }
        cross_cutting = {"security", "operations"}
        important_cross_terms = ("auth", "encrypt", "metric", "log", "audit", "alert", "trace")
        candidates: List[Tuple[int, int, Dict[str, Any]]] = []
        seen_pairs: set[Tuple[str, str]] = set()
        for index, edge in enumerate(edges):
            if not isinstance(edge, dict):
                continue
            source = _safe_id(edge.get("source"), "")
            target = _safe_id(edge.get("target"), "")
            if source not in node_by_id or target not in node_by_id or source == target:
                continue
            pair = (source, target)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            source_role, target_role = roles[source], roles[target]
            label = _clean_label(edge.get("label"), "", 30)
            if ({source_role, target_role} & cross_cutting) and not any(
                token in label.casefold() for token in important_cross_terms
            ):
                continue
            score = transition_score.get((source_role, target_role), 4)
            if label:
                score += 1
            if source_role == "external" or target_role == "external":
                score += 1
            candidates.append((score, index, {"source": source, "target": target, "label": label}))

        # Roughly 0.7 connectors per component is enough to show the principal
        # paths without turning a detailed 18-node design into a wiring diagram.
        budget = min(16, max(6, math.ceil(len(nodes) * 0.7)))
        outgoing: Dict[str, int] = {node_id: 0 for node_id in node_by_id}
        incoming: Dict[str, int] = {node_id: 0 for node_id in node_by_id}
        external_degree: Dict[str, int] = {node_id: 0 for node_id in node_by_id}
        selected: List[Tuple[int, Dict[str, Any]]] = []
        for _score, index, edge in sorted(candidates, key=lambda item: (-item[0], item[1])):
            source, target = edge["source"], edge["target"]
            if outgoing[source] >= 2 or incoming[target] >= 2:
                continue
            if roles[target] == "data" and incoming[target] >= 1:
                continue
            if roles[source] == "external" and external_degree[source] >= 1:
                continue
            if roles[target] == "external" and external_degree[target] >= 1:
                continue
            if roles[source] in cross_cutting and outgoing[source] >= 1:
                continue
            if roles[target] in cross_cutting and incoming[target] >= 1:
                continue
            selected.append((index, edge))
            outgoing[source] += 1
            incoming[target] += 1
            if roles[source] == "external":
                external_degree[source] += 1
            if roles[target] == "external":
                external_degree[target] += 1
            if len(selected) >= budget:
                break

        if not selected:
            for index, edge in enumerate(edges[:budget]):
                if not isinstance(edge, dict):
                    continue
                source = _safe_id(edge.get("source"), "")
                target = _safe_id(edge.get("target"), "")
                if source in node_by_id and target in node_by_id and source != target:
                    selected.append((index, {
                        "source": source, "target": target,
                        "label": _clean_label(edge.get("label"), "", 30),
                    }))

        # Keep at most five distinct captions. Repeated prose beside parallel
        # connectors is visual noise; direction and arrowheads already convey it.
        labelled = 0
        seen_labels: set[str] = set()
        output: List[Dict[str, Any]] = []
        for _index, edge in sorted(selected, key=lambda item: item[0]):
            value = dict(edge)
            normalised = value.get("label", "").casefold()
            if not normalised or normalised in seen_labels or labelled >= 5:
                value["label"] = ""
            else:
                seen_labels.add(normalised)
                labelled += 1
            output.append(value)
        print(
            f"[DIAGRAM][EDGES] architecture connectors reduced {len(edges)} -> {len(output)} "
            f"(labels={labelled}, nodes unchanged={len(nodes)})",
            flush=True,
        )
        return output

    def _enrich_diagram(self, item: Dict[str, Any], diagram_type: str,
                        candidate_map: Dict[str, IconCandidate]) -> Dict[str, Any]:
        """Apply icons/groups deterministically when the LLM omits presentation metadata."""
        enriched = dict(item)
        enriched["diagram_type"] = diagram_type
        nodes = [dict(node) for node in item.get("nodes", []) if isinstance(node, dict)]
        groups = [dict(group) for group in item.get("groups", []) if isinstance(group, dict)]
        existing_groups = {_safe_id(group.get("id"), "") for group in groups}
        if diagram_type != "architecture_overview":
            if diagram_type == "integration_context":
                nodes, item_edges = self._normalise_integration_topology(
                    nodes, item.get("edges", [])
                )
                enriched["edges"] = item_edges
            node_ids = {_safe_id(node.get("id"), "") for node in nodes}
            incoming = {node_id: 0 for node_id in node_ids if node_id}
            outgoing = {node_id: [] for node_id in incoming}
            for edge in enriched.get("edges", item.get("edges", [])):
                if not isinstance(edge, dict):
                    continue
                source = _safe_id(edge.get("source"), "")
                target = _safe_id(edge.get("target"), "")
                if source in outgoing and target in incoming:
                    outgoing[source].append(target)
                    incoming[target] += 1
            queue = [node_id for node_id, count in incoming.items() if count == 0]
            ranks = {node_id: 0 for node_id in queue}
            visited = 0
            while queue:
                source = queue.pop(0)
                visited += 1
                for target in outgoing[source]:
                    ranks[target] = max(ranks.get(target, 0), ranks[source] + 1)
                    incoming[target] -= 1
                    if incoming[target] == 0:
                        queue.append(target)
            for node in nodes:
                node["icon_key"] = ""
                node["group"] = ""
                kind = str(node.get("kind") or "process").casefold()
                if kind in {"application", "service"}:
                    node["kind"] = "process"
                elif kind in {"channel", "data"}:
                    node["kind"] = "input_output"
                if visited == len(incoming):
                    node["layer"] = ranks.get(_safe_id(node.get("id"), ""), 0)
            enriched["nodes"] = nodes
            enriched["groups"] = []
            print(
                f"[DIAGRAM][ENRICH] {diagram_type}: forced conventional flowchart "
                f"({len(nodes)} nodes, no AWS icons, "
                f"horizontal_rank={'yes' if visited == len(incoming) else 'cycle'})",
                flush=True,
            )
            return enriched
        for node in nodes:
            label = str(node.get("label") or "")
            icon_key = str(node.get("icon_key") or "")
            if icon_key and icon_key not in candidate_map:
                print(
                    f"[DIAGRAM][ENRICH] '{label}' returned disallowed key '{icon_key}'",
                    flush=True,
                )
            if icon_key not in candidate_map and str(node.get("kind", "")).casefold() == "service":
                matched = self.icon_registry.match(label)
                if matched and matched.get("key") in candidate_map:
                    icon_key = matched["key"]
                    node["icon_key"] = icon_key
                    print(
                        f"[DIAGRAM][ENRICH] '{label}' -> {icon_key} (label match)",
                        flush=True,
                    )
                elif matched:
                    print(
                        f"[DIAGRAM][ENRICH] '{label}' matched {matched.get('key')} but it was not "
                        "in the source-grounded allowlist",
                        flush=True,
                    )
                else:
                    print(f"[DIAGRAM][ENRICH] '{label}' has no registry match", flush=True)
            provenance = candidate_map.get(icon_key)
            if diagram_type == "architecture_overview" and provenance and not node.get("group"):
                group_id, group_label, group_kind = self._group_for_category(provenance.category)
                node["group"] = group_id
                if group_id not in existing_groups:
                    groups.append({"id": group_id, "label": group_label, "kind": group_kind})
                    existing_groups.add(group_id)
            if provenance:
                category = str(provenance.category or "").casefold()
                if not node.get("placement_role"):
                    label_role = _architecture_role(
                        Node(str(node.get("id") or "node"), label, str(node.get("kind") or "service"), 0),
                        {},
                    )
                    if label_role in {"entry", "data", "security", "operations"}:
                        node["placement_role"] = label_role
                    elif any(token in category for token in ("security", "identity", "compliance")):
                        node["placement_role"] = "security"
                    elif any(token in category for token in ("monitor", "management-governance")):
                        node["placement_role"] = "operations"
                    elif any(token in category for token in ("database", "storage", "backup")):
                        node["placement_role"] = "data"
                    elif any(token in category for token in ("network", "content-delivery")):
                        node["placement_role"] = "entry"
                    else:
                        node["placement_role"] = "compute"
                if not node.get("scope"):
                    label_text = label.casefold()
                    if node["placement_role"] in {"security", "operations"}:
                        node["scope"] = "regional"
                    elif any(token in label_text for token in ("rds", "aurora", "elasticache", "ec2", "ecs", "fargate", "eks")):
                        node["scope"] = "vpc"
                    elif node["placement_role"] in {"entry", "compute"}:
                        node["scope"] = "vpc"
                    else:
                        node["scope"] = "managed"
                print(
                    f"[DIAGRAM][ENRICH] '{label}' uses {icon_key}; group={node.get('group') or '-'}; "
                    f"selection={provenance.selection}; role={node.get('placement_role')}; scope={node.get('scope')}",
                    flush=True,
                )
        enriched["nodes"] = nodes
        if diagram_type == "architecture_overview":
            enriched["groups"] = groups
            enriched["edges"] = self._simplify_architecture_edges(
                nodes, enriched.get("edges", item.get("edges", []))
            )
        return enriched

    @staticmethod
    def _normalise_integration_topology(
        nodes: List[Dict[str, Any]], edges: Any
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Turn a false sequence of peer systems into a compact integration context.

        Enterprise systems are peers around the solution boundary; chaining CRM to
        identity to analytics falsely implies that one system invokes the next.
        Meaningful modelled hubs are retained, while obvious peer chains are
        deterministically converted to hub-and-spoke.
        """
        clean_edges = [dict(edge) for edge in edges if isinstance(edge, dict)] if isinstance(edges, list) else []
        if len(nodes) < 4 or not clean_edges:
            return nodes, clean_edges
        node_ids = {_safe_id(node.get("id"), "") for node in nodes}
        degree = {node_id: 0 for node_id in node_ids if node_id}
        for edge in clean_edges:
            source = _safe_id(edge.get("source"), "")
            target = _safe_id(edge.get("target"), "")
            if source in degree and target in degree:
                degree[source] += 1
                degree[target] += 1
        keywords = ("solution", "platform", "chatbot", "assistant", "application", "orchestr")
        candidates = sorted(
            nodes,
            key=lambda node: (
                any(token in str(node.get("label") or "").casefold() for token in keywords),
                str(node.get("kind") or "").casefold() in {"application", "process", "service"},
                degree.get(_safe_id(node.get("id"), ""), 0),
            ),
            reverse=True,
        )
        hub = _safe_id(candidates[0].get("id"), "") if candidates else ""
        if not hub:
            return nodes, clean_edges
        direct = sum(
            hub in {_safe_id(edge.get("source"), ""), _safe_id(edge.get("target"), "")}
            for edge in clean_edges
        )
        # Keep an already meaningful hub or middleware topology.
        if direct >= max(2, len(nodes) - 2):
            return nodes, clean_edges
        hub_layer = next((int(node.get("layer", 1) or 1) for node in nodes if _safe_id(node.get("id"), "") == hub), 1)
        peers = [node for node in nodes if _safe_id(node.get("id"), "") != hub]
        rebuilt: List[Dict[str, Any]] = []
        for index, node in enumerate(peers):
            peer_id = _safe_id(node.get("id"), "")
            existing = next((
                edge for edge in clean_edges
                if {peer_id, hub} == {
                    _safe_id(edge.get("source"), ""),
                    _safe_id(edge.get("target"), ""),
                }
            ), None)
            if existing:
                rebuilt.append(existing)
            else:
                peer_layer = int(node.get("layer", 0) or 0)
                source, target = (peer_id, hub) if peer_layer <= hub_layer else (hub, peer_id)
                rebuilt.append({"source": source, "target": target, "label": "Integration"})
            node["layer"] = 0 if index < math.ceil(len(peers) / 2) else 2
        for node in nodes:
            if _safe_id(node.get("id"), "") == hub:
                node["layer"] = 1
        print(
            f"[DIAGRAM][TOPOLOGY] integration_context: replaced peer-system chain "
            f"with hub '{hub}' and {len(peers)} integrations",
            flush=True,
        )
        return nodes, rebuilt

    @staticmethod
    def _placement(diagram_type: str, raw: Dict[str, Any]) -> str:
        if diagram_type == "architecture_overview":
            return "Solution Architecture"
        supplied = _clean_label(raw.get("placement_heading"), "", 80)
        defaults = {
            "architecture_overview": "Architecture Overview",
            "integration_context": "Integrations",
            "data_flow": "Data Flow",
            "deployment_topology": "Deployment",
        }
        return supplied or defaults[diagram_type]

    def _generate_specs(self, requirements: Dict[str, Any], metadata: Dict[str, Any], narrative: str) -> Tuple[List[Tuple[str, str, DiagramSpec]], bool]:
        title = f"{metadata.get('project_title', 'Solution')} — Proposed Architecture"
        eligible_types = self._eligible_types(requirements, narrative)
        candidates = self.icon_registry.candidates(requirements, narrative)
        candidate_map = {item.key: item for item in candidates}
        print(
            f"[DIAGRAM][PLAN] eligible={eligible_types}; icon_candidates={len(candidates)}",
            flush=True,
        )
        for candidate in candidates:
            print(
                f"[DIAGRAM][CANDIDATE] {candidate.label} | {candidate.key} | "
                f"{candidate.selection} | {candidate.evidence[:120]}",
                flush=True,
            )
        if not candidates:
            print(
                "[DIAGRAM][CANDIDATE] NONE — no AWS service or capability could be grounded in requirements",
                flush=True,
            )
        try:
            result = self.llm.generate(
                self._prompt(requirements, metadata, narrative, eligible_types, candidates),
                task="diagram",
                max_tokens=10000,
                temperature=0.05,
                call_name="Architecture Diagram",
                fallback_model_id=getattr(self.config, "WRITER_MODEL_ID", None),
            )
            raw = _extract_json(result.text)
            raw_diagrams = raw.get("diagrams") if isinstance(raw.get("diagrams"), list) else [raw]
            print(f"[DIAGRAM][LLM] returned {len(raw_diagrams)} diagram object(s)", flush=True)
            accepted: Dict[str, Tuple[str, str, DiagramSpec]] = {}
            for item in raw_diagrams:
                if not isinstance(item, dict):
                    continue
                diagram_type = str(item.get("diagram_type") or "architecture_overview").strip().lower()
                if diagram_type not in eligible_types or diagram_type in accepted:
                    continue
                raw_nodes = item.get("nodes", []) if isinstance(item.get("nodes"), list) else []
                print(
                    f"[DIAGRAM][LLM] {diagram_type}: nodes={len(raw_nodes)}, "
                    f"groups={len(item.get('groups', [])) if isinstance(item.get('groups'), list) else 0}",
                    flush=True,
                )
                for raw_node in raw_nodes:
                    if isinstance(raw_node, dict):
                        print(
                            f"[DIAGRAM][LLM-NODE] {raw_node.get('label')} | kind={raw_node.get('kind')} | "
                            f"icon={raw_node.get('icon_key') or '-'} | group={raw_node.get('group') or '-'}",
                            flush=True,
                        )
                item = self._enrich_diagram(item, diagram_type, candidate_map)
                validated = validate_spec(item, title, candidate_map)
                if diagram_type == "architecture_overview":
                    service_candidate_count = sum(candidate.key.startswith("aws.service.") for candidate in candidates)
                    target_nodes = min(18, max(12, service_candidate_count + 3))
                    if service_candidate_count >= 6 and len(validated.nodes) < target_nodes:
                        print(
                            f"[DIAGRAM][DETAIL] overview has {len(validated.nodes)} nodes; "
                            f"requesting evidence-backed expansion to {target_nodes}",
                            flush=True,
                        )
                        try:
                            expanded = self._expand_overview(
                                item, target_nodes, requirements, narrative, candidates
                            )
                            expanded = self._enrich_diagram(expanded, diagram_type, candidate_map)
                            expanded_spec = validate_spec(expanded, title, candidate_map)
                            if len(expanded_spec.nodes) > len(validated.nodes):
                                item, validated = expanded, expanded_spec
                                print(
                                    f"[DIAGRAM][DETAIL] accepted expanded overview with "
                                    f"{len(validated.nodes)} nodes",
                                    flush=True,
                                )
                            else:
                                print("[DIAGRAM][DETAIL] expansion added no useful nodes; retained draft", flush=True)
                        except Exception as detail_exc:
                            print(f"[DIAGRAM][DETAIL] expansion skipped: {detail_exc}", flush=True)
                print(
                    f"[DIAGRAM][VALIDATED] {diagram_type}: "
                    f"icons={sum(bool(node.icon_key) for node in validated.nodes)}/{len(validated.nodes)}, "
                    f"groups={len(validated.groups)}, edges={len(validated.edges)}",
                    flush=True,
                )
                accepted[diagram_type] = (
                    diagram_type,
                    self._placement(diagram_type, item),
                    validated,
                )
            # The deterministic eligibility gate, not the LLM, decides how many
            # diagrams are permitted. Fill an omitted eligible view conservatively.
            for diagram_type in eligible_types:
                if diagram_type not in accepted:
                    accepted[diagram_type] = (
                        diagram_type,
                        self._placement(diagram_type, {}),
                        self._fallback_for_type(diagram_type, requirements, metadata),
                    )
            return [accepted[item] for item in eligible_types], False
        except Exception as exc:
            # Keep the architecture section usable when the model returns
            # malformed JSON, an invalid topology, or a transient Bedrock
            # error.  Eligibility and fallback specs are deterministic and
            # remain grounded in the normalized requirements.
            print(
                f"[DIAGRAM][FALLBACK] model diagram unavailable ({exc}); "
                "using deterministic architecture specifications",
                flush=True,
            )
            return [
                (
                    diagram_type,
                    self._placement(diagram_type, {}),
                    self._fallback_for_type(diagram_type, requirements, metadata),
                )
                for diagram_type in eligible_types
            ], True

    def _asset(
        self,
        diagram_type: str,
        placement_heading: str,
        spec: DiagramSpec,
        metadata: Dict[str, Any],
        used_fallback: bool,
    ) -> Dict[str, Any]:
        xml = drawio_xml(spec, self.icon_registry)
        png = render_png(spec, self.config, self.icon_registry)
        icon_nodes = [node for node in spec.nodes if node.icon_key]
        embedded_svg_count = xml.count("data:image/svg+xml;base64,")
        print(
            f"[DIAGRAM][ASSET] {diagram_type}: icon_nodes={len(icon_nodes)}, "
            f"embedded_svgs={embedded_svg_count}, png_bytes={len(png)}, "
            f"canvas_groups={len(spec.groups)}",
            flush=True,
        )
        if icon_nodes and embedded_svg_count != len(icon_nodes):
            print(
                f"[DIAGRAM][ASSET] WARNING: expected {len(icon_nodes)} SVG icon(s), "
                f"embedded {embedded_svg_count}",
                flush=True,
            )
        encoded = base64.b64encode(png).decode("ascii")
        return {
            "type": "drawio_architecture",
            "diagram_type": diagram_type,
            "placement_heading": placement_heading,
            "title": spec.title,
            "description": spec.description,
            "alt_text": f"Logical architecture diagram for {metadata.get('project_title', 'the proposed solution')}",
            "caption": spec.title,
            "note": spec.note,
            "spec": spec.as_dict(),
            "drawio_xml": xml,
            "image_base64": encoded,
            "edit_url": edit_url(xml, getattr(self.config, "DRAWIO_EDITOR_URL", None)),
            "used_fallback": used_fallback,
        }

    def generate_assets(self, requirements: Dict[str, Any], metadata: Dict[str, Any], narrative: str) -> List[Dict[str, Any]]:
        planned, used_fallback = self._generate_specs(requirements, metadata, narrative)
        assets: List[Dict[str, Any]] = []
        errors: List[str] = []
        for diagram_type, placement, spec in planned[:MAX_DIAGRAMS]:
            try:
                assets.append(self._asset(diagram_type, placement, spec, metadata, used_fallback))
                continue
            except Exception as exc:
                errors.append(f"{diagram_type}: {exc}")
                print(
                    f"[DIAGRAM][ASSET] {diagram_type} render failed ({exc}); retrying deterministic fallback",
                    flush=True,
                )
            try:
                fallback = self._fallback_for_type(diagram_type, requirements, metadata)
                assets.append(self._asset(diagram_type, placement, fallback, metadata, True))
            except Exception as fallback_exc:
                errors.append(f"{diagram_type} fallback: {fallback_exc}")
                print(
                    f"[DIAGRAM][ASSET] {diagram_type} fallback render failed ({fallback_exc}); "
                    "continuing with remaining diagrams",
                    flush=True,
                )
        if not assets:
            raise RuntimeError("No architecture diagram asset could be rendered: " + "; ".join(errors))
        return assets

    def generate_asset(self, requirements: Dict[str, Any], metadata: Dict[str, Any], narrative: str) -> Dict[str, Any]:
        """Backward-compatible single-diagram API used by older callers."""
        return self.generate_assets(requirements, metadata, narrative)[0]
