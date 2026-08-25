import unittest

from app.core import server


class PreviewMarkdownEditTests(unittest.TestCase):
    preview_id = "PREVIEW_MARKDOWN_EDIT_TEST"

    def setUp(self):
        self.client = server.app.test_client()
        with server.preview_lock:
            server.preview_storage[self.preview_id] = {
                "preview_id": self.preview_id,
                "status": "ready",
                "progress": 100,
                "mode": "POC",
                "metadata": {"company_name": "Example Customer"},
                "content": {
                    "cover_page": "Managed cover",
                    "toc_structure": "1. About Shellkode",
                    "about_shellkode": "Original profile",
                    "aws_pricing": "Original pricing",
                    "generation_quality_summary": "Internal notes",
                    server.ARCHITECTURE_ASSETS_KEY: [{"title": "Architecture"}],
                },
                "edit_count": 0,
            }

    def tearDown(self):
        with server.preview_lock:
            server.preview_storage.pop(self.preview_id, None)

    def test_direct_markdown_edit_updates_body_and_preserves_managed_content(self):
        response = self.client.put(
            f"/api/preview/{self.preview_id}/content",
            json={
                "content": {
                    "about_shellkode": "### Profile\n\nUpdated **reviewer** content.",
                    "aws_pricing": "| Item | Basis |\n|---|---|\n| Storage | Confirmed |",
                }
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["edited_sections"], ["about_shellkode", "aws_pricing"])
        self.assertEqual(payload["content"]["cover_page"], "Managed cover")
        self.assertEqual(payload["content"]["toc_structure"], "1. About Shellkode")
        self.assertEqual(payload["content"]["generation_quality_summary"], "Internal notes")
        self.assertEqual(
            payload["content"][server.ARCHITECTURE_ASSETS_KEY],
            [{"title": "Architecture"}],
        )
        self.assertEqual(payload["edit_count"], 1)

    def test_direct_markdown_edit_rejects_system_managed_and_unknown_keys(self):
        for key in ("toc_structure", "not_a_generated_section"):
            with self.subTest(key=key):
                response = self.client.put(
                    f"/api/preview/{self.preview_id}/content",
                    json={"content": {key: "Changed"}},
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn("Unknown or system-managed", response.get_json()["error"])


if __name__ == "__main__":
    unittest.main()

