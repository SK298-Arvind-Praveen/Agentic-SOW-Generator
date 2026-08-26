import os
import unittest
from unittest.mock import patch

from app.core.access_control import (
    BUSINESS_UNITS,
    Identity,
    RBACStore,
    SAMPLE_PASSWORD,
    filter_visible_items,
    issue_token,
    normalise_business_unit,
    verify_token,
)


class AccessControlTests(unittest.TestCase):
    def test_business_unit_normalisation_is_strict(self):
        self.assertEqual(normalise_business_unit("data-engineering"), "Data Engineering")
        self.assertEqual(len(BUSINESS_UNITS), 5)
        with self.assertRaises(ValueError):
            normalise_business_unit("Sales")

    def test_signed_token_preserves_role_and_business_unit(self):
        identity = Identity("genai@shellkode.com", "GenAI User", "BU", "GenAI")
        with patch.dict(os.environ, {"AUTH_TOKEN_SECRET": "test-secret"}, clear=False):
            decoded = verify_token(issue_token(identity))
        self.assertEqual(decoded, identity)
        self.assertFalse(decoded.is_admin)

    def test_bu_scope_excludes_other_and_unassigned_records(self):
        identity = Identity("cloud@shellkode.com", "Cloud User", "BU", "Cloud")
        items = [
            {"document_id": "1", "business_unit": "Cloud"},
            {"document_id": "2", "business_unit": "GenAI"},
            {"document_id": "3"},
        ]
        self.assertEqual(
            [item["document_id"] for item in filter_visible_items(items, identity)],
            ["1"],
        )

    def test_admin_can_filter_or_view_all_business_units(self):
        admin = Identity("admin@shellkode.com", "Admin", "ADMIN")
        items = [
            {"document_id": "1", "business_unit": "Cloud"},
            {"document_id": "2", "business_unit": "GenAI"},
            {"document_id": "3"},
        ]
        self.assertEqual(len(filter_visible_items(items, admin)), 3)
        self.assertEqual(
            [item["document_id"] for item in filter_visible_items(items, admin, "GenAI")],
            ["2"],
        )

    @patch.object(RBACStore, "get_user", return_value=None)
    def test_sample_user_fallback_supports_admin_and_each_bu(self, _get_user):
        with patch.dict(os.environ, {"ENABLE_SAMPLE_USERS": "true"}, clear=False):
            store = RBACStore()
            self.assertTrue(store.authenticate("admin@shellkode.com", SAMPLE_PASSWORD).is_admin)
            self.assertEqual(store.authenticate("mlops@shellkode.com", SAMPLE_PASSWORD).business_unit, "MLOps")

    def test_api_requires_and_accepts_a_signed_session(self):
        from app.core import server

        previous_testing = server.app.config.get("TESTING", False)
        server.app.config["TESTING"] = False
        identity = Identity("cloud@shellkode.com", "Cloud User", "CLOUD", "Cloud")
        try:
            client = server.app.test_client()
            self.assertEqual(client.get("/api/auth/me").status_code, 401)
            with patch.object(server.rbac_store, "authenticate", return_value=identity):
                login = client.post("/api/auth/login", json={"email": identity.email, "password": "password"})
            self.assertEqual(login.status_code, 200)
            token = login.get_json()["token"]
            me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
            self.assertEqual(me.status_code, 200)
            self.assertEqual(me.get_json()["user"]["business_unit"], "Cloud")
        finally:
            server.app.config["TESTING"] = previous_testing


if __name__ == "__main__":
    unittest.main()
