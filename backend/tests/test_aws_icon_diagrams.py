import io
from pathlib import Path

from PIL import Image

from app.diagram.aws_icons import AwsIconRegistry
from app.diagram.service import DiagramService, _layout, drawio_xml, render_png, validate_spec


class _Config:
    ASSETS_DIR = Path(__file__).resolve().parents[1] / "assets"


def test_registry_resolves_named_and_capability_inferred_services():
    registry = AwsIconRegistry(_Config.ASSETS_DIR)
    candidates = registry.candidates(
        {"aws_services": ["AWS Lambda", "Amazon S3"]},
        "A serverless API must support user authentication and monitoring.",
    )
    by_label = {item.label: item for item in candidates}
    assert by_label["AWS Lambda"].selection == "explicit"
    assert by_label["Amazon Simple Storage Service"].selection == "explicit"
    assert by_label["Amazon CloudWatch"].selection == "inferred"
    assert registry.match("Amazon SES")["label"] == "Amazon Simple Email Service"
    assert registry.match("Contact Lens")["label"] == "Amazon Connect"
    assert registry.match("Amazon QuickSight")["label"] == "Amazon Quick"
    assert registry.match("Amazon S3 for storing email attachments and documents")["label"] == "Amazon Simple Storage Service"
    rendered = registry.png(by_label["AWS Lambda"].key, 64)
    assert rendered is not None
    assert rendered.size == (64, 64)


def test_unapproved_icon_is_removed_and_provenance_is_server_owned():
    registry = AwsIconRegistry(_Config.ASSETS_DIR)
    candidate = registry.candidate("AWS Lambda", "explicit", "aws_services: AWS Lambda")
    raw = {"nodes": [
        {"id": "a", "label": "Lambda", "kind": "service", "layer": 1,
         "icon_key": candidate.key, "selection": "invented", "evidence": "invented"},
        {"id": "b", "label": "Mystery", "kind": "service", "layer": 2,
         "icon_key": "aws.service.fake"},
    ], "edges": [{"source": "a", "target": "b"}]}
    spec = validate_spec(raw, "Test", {candidate.key: candidate})
    assert spec.nodes[0].selection == "explicit"
    assert spec.nodes[0].evidence == "aws_services: AWS Lambda"
    assert spec.nodes[1].icon_key == ""


def test_grouped_icon_layout_is_editable_and_static_render_matches_canvas():
    registry = AwsIconRegistry(_Config.ASSETS_DIR)
    candidates = registry.candidates({"aws_services": ["AWS Lambda", "Amazon S3"]}, "")
    cmap = {item.key: item for item in candidates}
    keys = {item.label: item.key for item in candidates}
    spec = validate_spec({
        "title": "Serverless Architecture",
        "groups": [{"id": "processing", "label": "Processing"}, {"id": "storage", "label": "Storage"}],
        "nodes": [
            {"id": "users", "label": "Users", "kind": "actor", "layer": 0},
            {"id": "lambda", "label": "AWS Lambda", "subtitle": "Business processing", "kind": "service",
             "layer": 1, "group": "processing", "icon_key": keys["AWS Lambda"]},
            {"id": "s3", "label": "Amazon S3", "subtitle": "Document storage", "kind": "service",
             "layer": 2, "group": "storage", "icon_key": keys["Amazon Simple Storage Service"]},
        ], "edges": [{"source": "users", "target": "lambda"}, {"source": "lambda", "target": "s3"}],
    }, "Architecture", cmap)
    xml = drawio_xml(spec, registry)
    assert "data:image/svg+xml;base64," in xml
    assert "AWS Account" in xml and "Regional managed services" in xml
    png = render_png(spec, _Config(), registry)
    image = Image.open(io.BytesIO(png))
    assert image.width >= 900 and image.height >= 680


def test_server_enriches_omitted_llm_icon_keys_and_architecture_groups():
    registry = AwsIconRegistry(_Config.ASSETS_DIR)
    candidates = registry.candidates({"aws_services": ["AWS Lambda", "Amazon S3"]}, "")
    service = DiagramService.__new__(DiagramService)
    service.icon_registry = registry
    enriched = service._enrich_diagram({"nodes": [
        {"id": "lambda", "label": "Amazon Lambda", "kind": "service", "layer": 1},
        {"id": "s3", "label": "Amazon S3", "kind": "service", "layer": 2},
    ]}, "architecture_overview", {item.key: item for item in candidates})
    assert all(node.get("icon_key") for node in enriched["nodes"])
    assert all(node.get("group") for node in enriched["nodes"])
    assert enriched["groups"]


def test_non_architecture_views_are_forced_to_regular_flowcharts():
    registry = AwsIconRegistry(_Config.ASSETS_DIR)
    candidate = registry.candidate("AWS Lambda", "explicit", "aws_services: Lambda")
    service = DiagramService.__new__(DiagramService)
    service.icon_registry = registry
    raw = {
        "groups": [{"id": "aws", "label": "AWS Cloud"}],
        "nodes": [
            {"id": "start", "label": "Request", "kind": "channel", "group": "aws"},
            {"id": "lambda", "label": "AWS Lambda", "kind": "service", "group": "aws",
             "icon_key": candidate.key},
        ],
        "edges": [{"source": "start", "target": "lambda"}],
    }
    enriched = service._enrich_diagram(raw, "data_flow", {candidate.key: candidate})
    assert enriched["groups"] == []
    assert all(node["icon_key"] == "" and node["group"] == "" for node in enriched["nodes"])
    assert service._placement("architecture_overview", {}) == "Solution Architecture"
    fallback = service._fallback_for_type(
        "data_flow",
        {"aws_services": ["AWS Lambda", "Amazon S3"]},
        {"company_name": "Customer", "project_title": "Project"},
    )
    assert fallback.groups == ()
    assert all(node.icon_key == "" for node in fallback.nodes)


def test_aws_overview_uses_nested_boundaries_and_semantic_placement():
    registry = AwsIconRegistry(_Config.ASSETS_DIR)
    requested = [
        "Amazon API Gateway", "Amazon Elastic Container Service", "Amazon RDS",
        "Amazon S3", "Amazon CloudWatch", "AWS Key Management Service",
    ]
    candidates = [registry.candidate(label, "explicit", f"aws_services: {label}") for label in requested]
    candidates = [candidate for candidate in candidates if candidate]
    cmap = {candidate.key: candidate for candidate in candidates}
    keys = {candidate.label: candidate.key for candidate in candidates}

    def key(fragment):
        return next(value for label, value in keys.items() if fragment.casefold() in label.casefold())

    spec = validate_spec({
        "title": "Resilient application architecture",
        "groups": [{"id": "aws", "label": "AWS services"}],
        "nodes": [
            {"id": "users", "label": "Users", "kind": "actor", "layer": 0,
             "placement_role": "external", "scope": "external"},
            {"id": "api", "label": "Amazon API Gateway", "kind": "service", "layer": 1,
             "group": "aws", "icon_key": key("API Gateway"), "placement_role": "entry", "scope": "vpc"},
            {"id": "ecs_a", "label": "Amazon ECS", "kind": "service", "layer": 2,
             "group": "aws", "icon_key": key("Container Service"), "placement_role": "compute", "scope": "az",
             "availability_zone": "az_a"},
            {"id": "rds", "label": "Amazon RDS", "kind": "service", "layer": 3,
             "group": "aws", "icon_key": key("RDS"), "placement_role": "data", "scope": "vpc"},
            {"id": "s3", "label": "Amazon S3", "kind": "service", "layer": 3,
             "group": "aws", "icon_key": key("Storage Service"), "placement_role": "data", "scope": "managed"},
            {"id": "watch", "label": "Amazon CloudWatch", "kind": "service", "layer": 3,
             "group": "aws", "icon_key": key("CloudWatch"), "placement_role": "operations", "scope": "regional"},
            {"id": "kms", "label": "AWS KMS", "kind": "service", "layer": 3,
             "group": "aws", "icon_key": key("Key Management"), "placement_role": "security", "scope": "regional"},
        ],
        "edges": [
            {"source": "users", "target": "api"}, {"source": "api", "target": "ecs_a"},
            {"source": "ecs_a", "target": "rds"}, {"source": "ecs_a", "target": "s3"},
        ],
    }, "Architecture", cmap)
    positions, boxes, width, height = _layout(spec)
    assert {"__aws_account", "__region", "__vpc", "__az_a", "__az_b", "__workload", "__managed"} <= set(boxes)

    def contains(outer, point):
        ox, oy, ow, oh = outer
        px, py, pw, ph = point
        return ox <= px and oy <= py and px + pw <= ox + ow and py + ph <= oy + oh

    assert contains(boxes["__aws_account"], boxes["__region"])
    assert contains(boxes["__region"], boxes["__vpc"])
    assert contains(boxes["__vpc"], positions["api"])
    assert contains(boxes["__vpc"], positions["ecs_a"])
    assert contains(boxes["__az_a"], positions["ecs_a"])
    assert contains(boxes["__vpc"], positions["rds"])
    assert contains(boxes["__managed"], positions["s3"])
    assert contains(boxes["__managed"], positions["watch"])
    assert contains(boxes["__managed"], positions["kms"])
    assert not contains(boxes["__aws_account"], positions["users"])
    assert width > height

    xml = drawio_xml(spec, registry)
    assert "AWS Account" in xml and "Availability Zone A" in xml and "Regional managed services" in xml
    assert "edgeStyle=orthogonalEdgeStyle" in xml


def test_architecture_enrichment_assigns_server_owned_role_and_scope():
    registry = AwsIconRegistry(_Config.ASSETS_DIR)
    candidates = registry.candidates(
        {"aws_services": ["Amazon RDS", "Amazon CloudWatch", "AWS Lambda"]}, ""
    )
    service = DiagramService.__new__(DiagramService)
    service.icon_registry = registry
    raw = {"nodes": [
        {"id": "rds", "label": "Amazon RDS", "kind": "service"},
        {"id": "watch", "label": "Amazon CloudWatch", "kind": "service"},
        {"id": "lambda", "label": "AWS Lambda", "kind": "service"},
    ]}
    enriched = service._enrich_diagram(raw, "architecture_overview", {item.key: item for item in candidates})
    by_id = {node["id"]: node for node in enriched["nodes"]}
    assert by_id["rds"]["placement_role"] == "data" and by_id["rds"]["scope"] == "vpc"
    assert by_id["watch"]["placement_role"] == "operations" and by_id["watch"]["scope"] == "regional"
    assert by_id["lambda"]["placement_role"] == "compute" and by_id["lambda"]["scope"] == "vpc"


def test_architecture_edges_are_reduced_without_removing_components():
    nodes = [
        {"id": "customer", "label": "Customer", "kind": "actor", "placement_role": "external"},
        {"id": "api", "label": "API Gateway", "kind": "service", "placement_role": "entry"},
        {"id": "app", "label": "Application", "kind": "service", "placement_role": "compute"},
        {"id": "worker", "label": "Worker", "kind": "service", "placement_role": "compute"},
        {"id": "db", "label": "Database", "kind": "service", "placement_role": "data"},
        {"id": "s3", "label": "Object Storage", "kind": "service", "placement_role": "data"},
        {"id": "watch", "label": "CloudWatch", "kind": "service", "placement_role": "operations"},
        {"id": "kms", "label": "KMS", "kind": "service", "placement_role": "security"},
    ]
    edges = [
        {"source": "customer", "target": "api", "label": "Initiates conversation"},
        {"source": "customer", "target": "app", "label": "Initiates conversation"},
        {"source": "api", "target": "app", "label": "Request"},
        {"source": "api", "target": "worker", "label": "Request"},
        {"source": "app", "target": "worker", "label": "Task"},
        {"source": "app", "target": "db", "label": "Stores data"},
        {"source": "worker", "target": "db", "label": "Stores data"},
        {"source": "worker", "target": "s3", "label": "Stores data"},
        {"source": "app", "target": "watch", "label": "Sends metrics"},
        {"source": "worker", "target": "watch", "label": "Sends metrics"},
        {"source": "app", "target": "kms", "label": "Encrypts"},
        {"source": "worker", "target": "kms", "label": "Encrypts"},
    ]
    reduced = DiagramService._simplify_architecture_edges(nodes, edges)
    assert len(nodes) == 8
    assert len(reduced) <= 6
    assert sum("customer" in (edge["source"], edge["target"]) for edge in reduced) <= 1
    labels = [edge["label"].casefold() for edge in reduced if edge.get("label")]
    assert len(labels) == len(set(labels))
    assert sum("watch" in (edge["source"], edge["target"]) for edge in reduced) <= 1
    assert sum("kms" in (edge["source"], edge["target"]) for edge in reduced) <= 1
