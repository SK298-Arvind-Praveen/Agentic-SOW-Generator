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


ASSET_KEY = "architecture_diagram_assets"
LEGACY_ASSET_KEY = "architecture_diagram_asset"
MAX_NODES = 18
MAX_EDGES = 28
MAX_DIAGRAMS = 3
ALLOWED_DIAGRAM_TYPES = {
    "architecture_overview",
    "data_flow",
    "integration_context",
    "deployment_topology",
}
ALLOWED_KINDS = {"actor", "channel", "application", "service", "data", "external"}
KIND_STYLES = {
    "actor": ("#EEF2FF", "#4F46E5"),
    "channel": ("#ECFEFF", "#0891B2"),
    "application": ("#F5F3FF", "#7C3AED"),
    "service": ("#FFF7ED", "#EA580C"),
    "data": ("#ECFDF5", "#059669"),
    "external": ("#F8FAFC", "#64748B"),
}


@dataclass(frozen=True)
class Node:
    id: str
    label: str
    kind: str
    layer: int
    subtitle: str = ""


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

    def as_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "nodes": [node.__dict__ for node in self.nodes],
            "edges": [edge.__dict__ for edge in self.edges],
            "note": self.note,
        }


def _safe_id(value: Any, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", str(value or "")).strip("_")
    return (cleaned or fallback)[:48]


def _clean_label(value: Any, fallback: str = "Component", limit: int = 60) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return (text or fallback)[:limit]


def validate_spec(raw: Dict[str, Any], default_title: str) -> DiagramSpec:
    if not isinstance(raw, dict):
        raise ValueError("Diagram response must be a JSON object")
    raw_nodes = raw.get("nodes")
    raw_edges = raw.get("edges", [])
    if not isinstance(raw_nodes, list) or not 2 <= len(raw_nodes) <= MAX_NODES:
        raise ValueError(f"Diagram must contain between 2 and {MAX_NODES} nodes")
    if not isinstance(raw_edges, list) or len(raw_edges) > MAX_EDGES:
        raise ValueError(f"Diagram cannot contain more than {MAX_EDGES} edges")

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
        nodes.append(Node(
            id=node_id,
            label=_clean_label(item.get("label"), f"Component {index}"),
            kind=kind,
            layer=layer,
            subtitle=_clean_label(item.get("subtitle"), "", 80),
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


def fallback_spec(requirements: Dict[str, Any], metadata: Dict[str, Any]) -> DiagramSpec:
    """Build a conservative source-grounded model without an LLM."""
    company = _clean_label(metadata.get("company_name"), "Customer", 40)
    project = _clean_label(metadata.get("project_title"), "Solution Architecture", 70)
    services = _string_values(requirements.get("aws_services"))[:8]
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
            nodes.append({"id": node_id, "label": service, "kind": "service", "layer": 2})
            edges.append({"source": "solution", "target": node_id})
    else:
        nodes.append({"id": "platform", "label": "AWS Platform Services", "kind": "service", "layer": 2})
        edges.append({"source": "solution", "target": "platform"})
    for index, system in enumerate(integrations, 1):
        node_id = f"external_{index}"
        nodes.append({"id": node_id, "label": system, "kind": "external", "layer": 3})
        edges.append({"source": "solution", "target": node_id, "label": "Integrates"})
    return validate_spec({"title": f"{project} — Proposed Architecture", "nodes": nodes, "edges": edges}, project)


def _geometry(spec: DiagramSpec) -> Tuple[Dict[str, Tuple[int, int, int, int]], int, int]:
    """Lay out a readable, document-friendly graph with at most four columns."""
    node_width, node_height = 280, 104
    x_gap, y_gap, margin = 125, 58, 70
    layers: Dict[int, List[Node]] = {}
    source_layers = sorted({node.layer for node in spec.nodes})
    # Wide six-column diagrams become illegible when Word fits them to a page.
    # Preserve ordering while folding the model's layers into four columns.
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
    # Cap the aspect ratio at 2:1 so labels remain readable in a portrait SOW.
    height = max(680, margin * 2 + 105 + content_height, math.ceil(width / 2))
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


def drawio_xml(spec: DiagramSpec) -> str:
    positions, width, height = _geometry(spec)
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
    for node in spec.nodes:
        x, y, w, h = positions[node.id]
        fill, stroke = KIND_STYLES[node.kind]
        value = node.label + (f"\n{node.subtitle}" if node.subtitle else "")
        style = (
            "rounded=1;whiteSpace=wrap;html=1;arcSize=12;shadow=0;"
            f"fillColor={fill};strokeColor={stroke};strokeWidth=2;fontFamily=Helvetica;"
            "fontSize=14;fontStyle=1;fontColor=#1F2937;verticalAlign=middle;align=center;spacing=8;"
        )
        cell = ET.SubElement(root, "mxCell", {"id": node.id, "value": value, "style": style, "vertex": "1", "parent": "1"})
        ET.SubElement(cell, "mxGeometry", {"x": str(x), "y": str(y), "width": str(w), "height": str(h), "as": "geometry"})
    for index, edge in enumerate(spec.edges, 1):
        style = (
            "edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;jettySize=auto;html=1;"
            "endArrow=block;endFill=1;strokeColor=#64748B;strokeWidth=2;fontSize=11;fontColor=#475569;"
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
    words = str(text or "").split()
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


def render_png(spec: DiagramSpec, config: Any) -> bytes:
    positions, width, height = _geometry(spec)
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

    node_map = {node.id: node for node in spec.nodes}
    label_boxes: List[Tuple[int, int, int, int]] = []
    node_boxes = [(x, y, x + w, y + h) for x, y, w, h in positions.values()]
    for edge in spec.edges:
        sx, sy, sw, sh = positions[edge.source]
        tx, ty, tw, th = positions[edge.target]
        start = (sx + sw, sy + sh // 2)
        end = (tx, ty + th // 2)
        if tx <= sx:
            start = (sx + sw // 2, sy + sh)
            end = (tx + tw // 2, ty)
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
            base_y = min(start[1], end[1]) + abs(start[1] - end[1]) // 2 - label_height - 9
            candidates = [base_y, base_y - 24, base_y + 24]
            placed = None
            for label_y in candidates:
                box = (
                    mid_x - label_width // 2 - 7,
                    label_y - 4,
                    mid_x + label_width // 2 + 7,
                    label_y + label_height + 5,
                )
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

    for node_id, (x, y, w, h) in positions.items():
        node = node_map[node_id]
        fill, stroke = KIND_STYLES[node.kind]
        draw.rounded_rectangle((x, y, x + w, y + h), radius=13, fill=fill, outline=stroke, width=3)
        lines = _wrapped_lines(draw, node.label, label_font, w - 28)
        total_height = len(lines) * 21 + (19 if node.subtitle else 0)
        cursor = y + (h - total_height) // 2
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=label_font)
            draw.text((x + (w - (bbox[2] - bbox[0])) // 2, cursor), line, fill="#1F2937", font=label_font)
            cursor += 21
        if node.subtitle:
            subtitle = _wrapped_lines(draw, node.subtitle, subtitle_font, w - 24, 1)[0]
            bbox = draw.textbbox((0, 0), subtitle, font=subtitle_font)
            draw.text((x + (w - (bbox[2] - bbox[0])) // 2, cursor + 2), subtitle, fill="#64748B", font=subtitle_font)

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
    return base_url + "/?grid=0&pv=0#" + "create=" + urllib.parse.quote(json.dumps(payload, separators=(",", ":")))


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
    ) -> str:
        source = {
            "company": metadata.get("company_name"),
            "project": metadata.get("project_title"),
            "requirements": requirements,
            "architecture_narrative": str(narrative or "")[:9000],
        }
        return f"""You are an AWS solution architect planning a concise set of diagrams for a Statement of Work.
Return JSON only. Create exactly one diagram for each item in ELIGIBLE_TYPES and no others. Use only systems,
services, actors and integrations supported by SOURCE. Do not invent named products. Prefer 5-12 nodes per
diagram and a left-to-right flow. Diagrams must add distinct value; do not repeat the same view.

Schema:
{{
  "diagrams": [{{
    "diagram_type": "architecture_overview|data_flow|integration_context|deployment_topology",
    "title": "short title",
    "placement_heading": "best matching architecture subsection heading",
    "note": "one short qualification",
    "nodes": [{{"id":"stable_id","label":"short label","kind":"actor|channel|application|service|data|external","layer":0,"subtitle":"optional purpose"}}],
    "edges": [{{"source":"node_id","target":"node_id","label":"short protocol or flow"}}]
  }}]
}}

Rules:
- Maximum {MAX_NODES} nodes and {MAX_EDGES} edges.
- Every edge endpoint must be a node id.
- Keep labels under 60 characters and edge labels under 36 characters.
- Show customer/external boundaries through kinds; do not add explanatory paragraphs.
- Use no more than four logical layers. Keep connector labels brief and optional.

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
        overview = fallback_spec(requirements, metadata)
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
        return DiagramSpec(title, overview.nodes, overview.edges, overview.note)

    @staticmethod
    def _placement(diagram_type: str, raw: Dict[str, Any]) -> str:
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
        try:
            result = self.llm.generate(
                self._prompt(requirements, metadata, narrative, eligible_types),
                task="diagram",
                max_tokens=5200,
                temperature=0.05,
                call_name="Architecture Diagram",
                fallback_model_id=getattr(self.config, "WRITER_MODEL_ID", None),
            )
            raw = _extract_json(result.text)
            raw_diagrams = raw.get("diagrams") if isinstance(raw.get("diagrams"), list) else [raw]
            accepted: Dict[str, Tuple[str, str, DiagramSpec]] = {}
            for item in raw_diagrams:
                if not isinstance(item, dict):
                    continue
                diagram_type = str(item.get("diagram_type") or "architecture_overview").strip().lower()
                if diagram_type not in eligible_types or diagram_type in accepted:
                    continue
                accepted[diagram_type] = (
                    diagram_type,
                    self._placement(diagram_type, item),
                    validate_spec(item, title),
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
            print(f"   ⚠ Architecture diagram agent fallback: {exc}")
            return [(
                "architecture_overview",
                self._placement("architecture_overview", {}),
                fallback_spec(requirements, metadata),
            )], True

    def _asset(
        self,
        diagram_type: str,
        placement_heading: str,
        spec: DiagramSpec,
        metadata: Dict[str, Any],
        used_fallback: bool,
    ) -> Dict[str, Any]:
        xml = drawio_xml(spec)
        png = render_png(spec, self.config)
        encoded = base64.b64encode(png).decode("ascii")
        return {
            "type": "drawio_architecture",
            "diagram_type": diagram_type,
            "placement_heading": placement_heading,
            "title": spec.title,
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
        return [
            self._asset(diagram_type, placement, spec, metadata, used_fallback)
            for diagram_type, placement, spec in planned[:MAX_DIAGRAMS]
        ]

    def generate_asset(self, requirements: Dict[str, Any], metadata: Dict[str, Any], narrative: str) -> Dict[str, Any]:
        """Backward-compatible single-diagram API used by older callers."""
        return self.generate_assets(requirements, metadata, narrative)[0]
