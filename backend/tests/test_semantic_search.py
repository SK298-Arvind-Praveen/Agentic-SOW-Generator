import io
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.search.semantic_search import (
    BedrockSemanticEmbedder,
    SEMANTIC_INDEX_VERSION,
    build_semantic_search_text,
    latest_versions,
    semantic_search_records,
)


class SemanticSearchTests(unittest.TestCase):
    @patch("app.search.semantic_search.boto3.client")
    def test_embedder_invokes_the_configured_titan_profile(self, client_factory):
        runtime = client_factory.return_value
        runtime.invoke_model.return_value = {
            "body": io.BytesIO(json.dumps({"embedding": [0.25, 0.75]}).encode("utf-8"))
        }
        profile = (
            "arn:aws:bedrock:us-east-1:106611079163:"
            "application-inference-profile/ve7wpqurv75w"
        )
        embedder = BedrockSemanticEmbedder(SimpleNamespace(
            SEMANTIC_SEARCH_EMBEDDING_MODEL_ID=profile,
            BEDROCK_REGION="us-east-1",
            BOTO_CONFIG=None,
        ))

        self.assertEqual(embedder.embed("customer support"), [0.25, 0.75])
        self.assertEqual(runtime.invoke_model.call_args.kwargs["modelId"], profile)
        request_body = json.loads(runtime.invoke_model.call_args.kwargs["body"])
        self.assertEqual(request_body["dimensions"], 256)
        self.assertTrue(request_body["normalize"])

    def test_latest_versions_keeps_highest_version_per_sow_and_mode(self):
        records = [
            {"document_id": "a1", "project_name": "CRM", "customer_name": "Acme", "mode": "POC", "owner_email": "a@x.com", "version": "v1"},
            {"document_id": "a3", "project_name": "CRM", "customer_name": "Acme", "mode": "POC", "owner_email": "a@x.com", "version": "v3"},
            {"document_id": "a2", "project_name": "CRM", "customer_name": "Acme", "mode": "POC", "owner_email": "a@x.com", "version": "v2"},
            {"document_id": "prod", "project_name": "CRM", "customer_name": "Acme", "mode": "PROD", "owner_email": "a@x.com", "version": "v1"},
        ]
        latest = latest_versions(records)
        self.assertEqual({item["document_id"] for item in latest}, {"a3", "prod"})

    def test_results_are_thresholded_and_sorted_by_closeness(self):
        vectors = {
            "query": [1.0, 0.0],
            "close": [0.9, 0.1],
            "borderline": [0.5, 0.8660254],
            "far": [0.0, 1.0],
        }
        records = [
            {"document_id": "far", "project_name": "Far", "semantic_search_text": "far"},
            {"document_id": "border", "project_name": "Border", "semantic_search_text": "borderline"},
            {"document_id": "close", "project_name": "Close", "semantic_search_text": "close"},
        ]
        results = semantic_search_records(records, "query", lambda text: vectors[text], threshold=0.5)
        self.assertEqual([item["document_id"] for item in results], ["close", "border"])
        self.assertGreater(results[0]["similarity_score"], results[1]["similarity_score"])
        self.assertAlmostEqual(results[1]["similarity_score"], 70.59, places=2)

    def test_persisted_vectors_avoid_one_embedding_call_per_record(self):
        calls = []

        def embed(text):
            calls.append(text)
            return [1.0, 0.0]

        records = [{
            "document_id": f"doc-{index}",
            "project_name": f"Project {index}",
            "semantic_search_text": f"stored SOW {index}",
            "semantic_search_embedding": [0.9, 0.1],
            "semantic_embedding_model_id": "titan-profile",
            "semantic_index_version": SEMANTIC_INDEX_VERSION,
        } for index in range(100)]

        results = semantic_search_records(
            records, "query", embed, threshold=0.5, model_id="titan-profile"
        )

        self.assertEqual(len(results), 100)
        self.assertEqual(calls, ["query"])

    def test_exact_project_name_is_never_lost_to_embedding_threshold(self):
        records = [{
            "document_id": "tata",
            "project_name": "Tata CLiQ Agentic Customer Support Platform",
            "semantic_search_text": "customer support platform",
            "semantic_search_embedding": [0.0, 1.0],
            "semantic_embedding_model_id": "titan-profile",
            "semantic_index_version": SEMANTIC_INDEX_VERSION,
        }]
        results = semantic_search_records(
            records, "tata", lambda _text: [1.0, 0.0],
            threshold=0.5, model_id="titan-profile",
        )
        self.assertEqual(results[0]["document_id"], "tata")
        self.assertEqual(results[0]["similarity_score"], 100.0)

    def test_exact_subsection_phrase_is_ranked_even_with_low_semantic_cosine(self):
        records = [{
            "document_id": "omnichannel",
            "project_name": "Support Platform",
            "semantic_search_text": "Deliverable 2\nOmnichannel Delivery\nConfigure customer channels.",
            "semantic_search_embedding": [0.0, 1.0],
            "semantic_embedding_model_id": "titan-profile",
            "semantic_index_version": SEMANTIC_INDEX_VERSION,
        }]
        results = semantic_search_records(
            records, "omnichannel delivery", lambda _text: [1.0, 0.0],
            threshold=0.5, model_id="titan-profile",
        )
        self.assertEqual(results[0]["similarity_score"], 98.0)

    def test_search_text_keeps_late_headings_in_verbose_documents(self):
        text = build_semantic_search_text({
            "early_context": "background " * 10000,
            "scope_of_work": {
                "deliverable_2": {"omnichannel_delivery": "Configure customer channels."}
            },
        }, {"company_name": "Tata CLiQ", "project_title": "Support Platform"})
        self.assertIn("omnichannel delivery", text.casefold())

    def test_search_text_omits_diagram_payloads(self):
        text = build_semantic_search_text(
            {"project_overview": "Customer support automation", "architecture_assets": "data:image/png;base64,secret"},
            {"company_name": "Acme", "project_title": "Support Platform"},
        )
        self.assertIn("Customer support automation", text)
        self.assertNotIn("base64", text)


if __name__ == "__main__":
    unittest.main()
