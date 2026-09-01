import base64
import io
import json
import tempfile
import unittest
from pathlib import Path

from docx import Document

from app.diagram.service import (
    ASSET_KEY,
    DiagramService,
    _geometry,
    drawio_xml,
    edit_url,
    fallback_spec,
    update_asset,
    validate_drawio_xml,
    validate_spec,
)
from app.document.document_builder import DocumentBuilder, SectionBuilder


class _Body:
    def __init__(self, value):
        self.value = value

    def read(self):
        return json.dumps(self.value).encode("utf-8")


class _Bedrock:
    def __init__(self, text):
        self.text = text

    def invoke_model(self, **_kwargs):
        return {"body": _Body({"content": [{"text": self.text}], "usage": {}})}


class _Config:
    MODEL_ID = "test-model"

    def __init__(self, output_dir=None):
        backend = Path(__file__).resolve().parents[1]
        self.ASSETS_DIR = backend / "assets"
        self.COVER_PAGE_IMAGE = self.ASSETS_DIR / "coverpage.png"
        self.OUTPUT_DIR = Path(output_dir or tempfile.gettempdir())


class ArchitectureDiagramTests(unittest.TestCase):
    def test_validated_spec_compiles_to_editable_xml_and_png(self):
        response = {
            "title": "CRM Integration Architecture",
            "nodes": [
                {"id": "users", "label": "Advisers", "kind": "actor", "layer": 0},
                {"id": "crm", "label": "CRM Portal", "kind": "application", "layer": 1},
                {"id": "lambda", "label": "AWS Lambda", "kind": "service", "layer": 2},
            ],
            "edges": [
                {"source": "users", "target": "crm", "label": "HTTPS"},
                {"source": "crm", "target": "lambda", "label": "API"},
            ],
        }
        service = DiagramService(_Config(), bedrock=_Bedrock(json.dumps(response)))
        asset = service.generate_asset(
            {"aws_services": ["AWS Lambda"]},
            {"company_name": "Axis Securities", "project_title": "CRM Integration"},
            "The portal invokes AWS Lambda through an API.",
        )
        self.assertFalse(asset["used_fallback"])
        self.assertEqual(asset["type"], "drawio_architecture")
        self.assertIn("<mxfile", asset["drawio_xml"])
        self.assertIn("AWS Lambda", asset["drawio_xml"])
        self.assertTrue(base64.b64decode(asset["image_base64"]).startswith(b"\x89PNG"))
        self.assertTrue(asset["edit_url"].startswith("https://app.diagrams.net/"))

    def test_evidence_gate_plans_multiple_distinct_diagrams_without_exceeding_cap(self):
        diagrams = []
        for diagram_type, title in (
            ("architecture_overview", "CRM Architecture Overview"),
            ("integration_context", "External Integration Context"),
            ("data_flow", "Customer Request Data Flow"),
            ("deployment_topology", "Unrequested Extra Diagram"),
        ):
            diagrams.append({
                "diagram_type": diagram_type,
                "title": title,
                "placement_heading": "End-to-End Data Flow" if diagram_type == "data_flow" else "Integrations",
                "nodes": [
                    {"id": "source", "label": "Source", "kind": "external", "layer": 0},
                    {"id": "solution", "label": "CRM", "kind": "application", "layer": 1},
                    {"id": "target", "label": "Amazon Bedrock", "kind": "service", "layer": 2},
                ],
                "edges": [
                    {"source": "source", "target": "solution", "label": "Request"},
                    {"source": "solution", "target": "target", "label": "Inference"},
                ],
            })
        service = DiagramService(_Config(), bedrock=_Bedrock(json.dumps({"diagrams": diagrams})))
        assets = service.generate_assets(
            {
                "aws_services": ["Amazon Bedrock"],
                "integrations": ["Cisco", "Netcore", "Active Directory", "Core API"],
            },
            {"company_name": "Axis Securities", "project_title": "CRM Integration"},
            "The request workflow includes ingestion, data flow, and a response to the agent.",
        )
        self.assertEqual(len(assets), 3)
        self.assertEqual(
            [asset["diagram_type"] for asset in assets],
            ["architecture_overview", "integration_context", "data_flow"],
        )
        self.assertTrue(all(asset["caption"] == asset["title"] for asset in assets))

    def test_layout_caps_aspect_ratio_and_number_of_columns_for_readability(self):
        raw = {
            "title": "A deliberately long solution architecture title that must remain readable",
            "nodes": [
                {"id": f"node_{index}", "label": f"Component {index}", "kind": "service", "layer": index}
                for index in range(6)
            ],
            "edges": [
                {"source": f"node_{index}", "target": f"node_{index + 1}", "label": "Authenticated request"}
                for index in range(5)
            ],
        }
        spec = validate_spec(raw, "Architecture")
        positions, width, height = _geometry(spec)
        self.assertLessEqual(width / height, 2.0)
        self.assertLessEqual(len({position[0] for position in positions.values()}), 4)

    def test_invalid_agent_output_uses_source_grounded_fallback(self):
        service = DiagramService(_Config(), bedrock=_Bedrock("not json"))
        asset = service.generate_asset(
            {"aws_services": ["Amazon Bedrock", "Amazon DynamoDB"]},
            {"company_name": "Example", "project_title": "Support Assistant"},
            "",
        )
        labels = {node["label"] for node in asset["spec"]["nodes"]}
        self.assertTrue(asset["used_fallback"])
        self.assertIn("Amazon Bedrock", labels)
        self.assertIn("Amazon DynamoDB", labels)

    def test_drawio_edit_round_trip_validates_png_and_xml(self):
        spec = fallback_spec(
            {"aws_services": ["Amazon S3"]},
            {"company_name": "Example", "project_title": "Document Workflow"},
        )
        xml = drawio_xml(spec)
        service = DiagramService(_Config(), bedrock=_Bedrock("{}"))
        image_base64 = service.generate_asset(
            {"aws_services": ["Amazon S3"]},
            {"company_name": "Example", "project_title": "Document Workflow"},
            "",
        )["image_base64"]
        png = "data:image/png;base64," + image_base64
        updated = update_asset(xml, png, {"title": "Existing"})
        self.assertEqual(validate_drawio_xml(updated["drawio_xml"]), xml)
        self.assertTrue(updated["edit_url"].startswith("https://app.diagrams.net/"))
        with self.assertRaises(ValueError):
            update_asset("<html />", png)
        with self.assertRaises(ValueError):
            update_asset("<mxfile><broken></mxfile>", png)

    def test_document_section_embeds_image_and_external_edit_link(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = _Config(temp_dir)
            service = DiagramService(config, bedrock=_Bedrock("invalid"))
            asset = service.generate_asset(
                {"aws_services": ["Amazon Bedrock"]},
                {"company_name": "Example", "project_title": "AI Assistant"},
                "",
            )
            builder = DocumentBuilder(config)
            builder.doc = Document()
            builder._configure_styles()
            builder._add_numbering()
            builder.section_builder = SectionBuilder(builder.doc, config)
            builder._build_section(
                "1. Solution Architecture (AWS)",
                {
                    "architecture_diagram": "The proposed logical design is shown below.",
                    "architecture_diagram_asset": asset,
                },
                {"company_name": "Example", "author_org": "ShellKode"},
                0,
            )
            self.assertEqual(len(builder.doc.inline_shapes), 1)
            self.assertFalse(any(
                paragraph.text.startswith("Figure 1:")
                for paragraph in builder.doc.paragraphs
            ))
            relationship_targets = [rel.target_ref for rel in builder.doc.part.rels.values()]
            self.assertIn(asset["edit_url"], relationship_targets)

    def test_preview_endpoint_persists_an_edited_diagram(self):
        from app.core import server

        preview_id = "PREVIEW_TEST_DIAGRAM"
        service = DiagramService(_Config(), bedrock=_Bedrock("invalid"))
        assets = service.generate_assets(
            {"aws_services": ["Amazon S3"]},
            {"company_name": "Example", "project_title": "Document Workflow"},
            "",
        )
        with server.preview_lock:
            server.preview_storage[preview_id] = {
                "status": "ready",
                "metadata": {"business_unit": "GenAI"},
                "content": {ASSET_KEY: assets},
                "edit_count": 0,
            }
        try:
            server.app.config["TESTING"] = True
            response = server.app.test_client().put(
                f"/api/preview/{preview_id}/architecture-diagram",
                json={
                    "drawio_xml": assets[0]["drawio_xml"],
                    "image_data": "data:image/png;base64," + assets[0]["image_base64"],
                    "diagram_index": 0,
                },
            )
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.get_json()["success"])
            with server.preview_lock:
                self.assertEqual(server.preview_storage[preview_id]["edit_count"], 1)
        finally:
            server.app.config["TESTING"] = False
            with server.preview_lock:
                server.preview_storage.pop(preview_id, None)


if __name__ == "__main__":
    unittest.main()
