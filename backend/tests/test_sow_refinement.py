import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.agents.refinement_agent import SowRefinementAgent
from app.core.sow_section_preferences import infer_selected_section_ids
from app.storage.source_documents import (
    SourceDocumentStore,
    project_source_scope,
    source_text_diff,
)


class _Body(io.BytesIO):
    pass


class _S3:
    def __init__(self):
        self.objects = {}
        self.upload_count = 0

    def list_objects_v2(self, Bucket, Prefix, **_kwargs):
        return {
            "Contents": [{"Key": key} for key in sorted(self.objects) if key.startswith(Prefix)],
            "IsTruncated": False,
        }

    def get_object(self, Bucket, Key):
        return {"Body": _Body(self.objects[Key])}

    def upload_file(self, path, bucket, key, ExtraArgs=None):
        self.upload_count += 1
        self.objects[key] = Path(path).read_bytes()

    def put_object(self, Bucket, Key, Body, **_kwargs):
        self.objects[Key] = Body


class _LLM:
    def generate(self, *_args, **_kwargs):
        return SimpleNamespace(text=json.dumps({
            "refinement_brief": "Move voice to future scope.",
            "affected_sections": ["scope_of_work", "out_of_scope"],
            "preserve_requirements": ["Keep all other modules"],
            "source_change_summary": "Voice timing changed",
        }))


class SowRefinementTests(unittest.TestCase):
    def test_project_id_makes_source_scope_stable_across_authors(self):
        first = project_source_scope({"project_id": "PROJECT-17", "owner_email": "a@example.com"})
        second = project_source_scope({"project_id": "PROJECT-17", "owner_email": "b@example.com"})
        self.assertEqual(first, second)

    def test_small_document_change_returns_diff_not_full_document(self):
        old = "Heading\nRequirement A\nRequirement B\nRequirement C"
        new = "Heading\nRequirement A\nRequirement B amended\nRequirement C"
        context, status = source_text_diff(old, new, "BRD.docx")
        self.assertEqual(status, "changed")
        self.assertIn("+Requirement B amended", context)
        self.assertIn("-Requirement B", context)
        self.assertNotIn("FULL NEW SOURCE DOCUMENT", context)

    def test_exact_reupload_reuses_s3_objects_and_extracted_text(self):
        s3 = _S3()
        store = SourceDocumentStore(client=s3, bucket="test")
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "BRD.txt"
            path.write_text("Project requirement A with enough source content.", encoding="utf-8")
            first = store.ingest("scope", path, "BRD.txt")
            uploads_after_first = s3.upload_count
            second = store.ingest("scope", path, "BRD.txt")
        self.assertFalse(first["reused"])
        self.assertTrue(second["reused"])
        self.assertEqual(second["comparison"], "unchanged")
        self.assertEqual(second["context"], "")
        self.assertEqual(s3.upload_count, uploads_after_first)

    def test_refinement_agent_returns_section_aware_plan(self):
        agent = SowRefinementAgent(config=SimpleNamespace(WRITER_MODEL_ID="writer"), llm=_LLM())
        plan = agent.prepare("Current SOW", "Move voice later", "Voice timing changed")
        self.assertEqual(plan["affected_sections"], ["scope_of_work", "out_of_scope"])

    def test_explicit_deliverable_instruction_becomes_enforceable_constraint(self):
        agent = SowRefinementAgent(config=SimpleNamespace(WRITER_MODEL_ID="writer"), llm=_LLM())
        plan = agent.prepare(
            "Current SOW",
            "Split the scope of work into 2 deliverables - Customer Experience, Agent Operations",
            "",
        )
        self.assertIn("scope_of_work", plan["affected_sections"])
        self.assertEqual(plan["requested_deliverable_count"], 2)
        self.assertEqual(
            plan["requested_deliverable_names"],
            ["Customer Experience", "Agent Operations"],
        )

    def test_legacy_section_recovery_ignores_scope_subsections(self):
        baseline = """1. About ShellKode
2. About Tata Unistore limited
3. Scope of Work
3.7 Testing and Go-Live
4. Solution Architecture - AWS
5. AWS Pricing
6. Success Criteria
7. Contacts and Reporting
8. Terms and Conditions
9. Acceptance and Signatories to Statement of Work
"""
        self.assertEqual(infer_selected_section_ids(baseline, "POC"), [
            "about_shellkode", "about_client", "scope_of_work",
            "architecture_diagram", "aws_pricing", "success_criteria",
            "contacts_reporting", "terms_conditions", "acceptance_signatories",
        ])

    def test_regenerate_endpoint_creates_preview_from_parent_sow(self):
        from app.core import server

        captured = {}
        parent = {
            "document_id": "DOC-1",
            "customer_name": "Customer",
            "project_name": "Project",
            "mode": "POC",
            "s3_url": "s3://agentic-sow-files/POC/base.docx",
            "business_unit": "Cloud",
            "owner_email": "test-admin@shellkode.com",
            "project_id": "PROJECT-1",
            "selected_sow_sections": ["scope_of_work", "success_criteria"],
        }

        class _Store:
            def list_documents(self, _scope):
                return []

        class _Handler:
            def get_next_version(self, *_args):
                return "v4"

        def capture(preview_id, state, _fast):
            captured["preview_id"] = preview_id
            captured["state"] = state

        previous = server.app.config.get("TESTING")
        server.app.config["TESTING"] = True
        try:
            with (
                patch.object(server, "_document_record", return_value=(parent, None)),
                patch.object(server, "_read_s3_document", return_value=("Baseline SOW content " * 10, None)),
                patch.object(server, "SourceDocumentStore", return_value=_Store()),
                patch.object(server, "DynamoDBHandler", return_value=_Handler()),
                patch("app.preview.async_preview.process_preview_async", side_effect=capture),
            ):
                response = server.app.test_client().post(
                    "/api/documents/DOC-1/regenerate",
                    data={"instructions": "Make monitoring more specific", "supporting_doc_count": "0"},
                )
        finally:
            server.app.config["TESTING"] = previous
        self.assertEqual(response.status_code, 202)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        self.assertEqual(captured["state"]["metadata"]["version"], "v4")
        self.assertEqual(
            captured["state"]["selected_sow_sections"],
            ["scope_of_work", "success_criteria"],
        )
        self.assertEqual(captured["state"]["refinement_request"]["instructions"], "Make monitoring more specific")
        self.assertIn("Baseline SOW", captured["state"]["refinement_request"]["baseline_sow"])


if __name__ == "__main__":
    unittest.main()
