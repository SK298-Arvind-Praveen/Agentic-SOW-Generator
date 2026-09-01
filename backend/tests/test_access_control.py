import os
import unittest
from unittest.mock import MagicMock, patch

from app.core.access_control import (
    BUSINESS_UNITS,
    Identity,
    RBACStore,
    SAMPLE_PASSWORD,
    SAMPLE_USERS,
    filter_visible_items,
    issue_token,
    normalise_business_unit,
    verify_token,
)
from app.db.dynamodb_handler_optimized import DynamoDBHandlerOptimized


class _FakeDocumentTable:
    def __init__(self, items):
        self.items = items

    def scan(self, **_kwargs):
        return {"Items": self.items}


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

    def test_individual_user_only_sees_records_they_own(self):
        identity = Identity("ananya.user@shellkode.com", "Ananya Rao", "USER", "GenAI")
        items = [
            {"document_id": "1", "business_unit": "GenAI", "owner_email": identity.email},
            {"document_id": "2", "business_unit": "GenAI", "owner_email": "someone@shellkode.com"},
            {"document_id": "3", "business_unit": "Cloud", "owner_email": identity.email},
            {"document_id": "4", "business_unit": "GenAI"},
        ]
        self.assertEqual(
            [item["document_id"] for item in filter_visible_items(items, identity)],
            ["1", "3"],
        )

    def test_bu_head_sees_every_owned_record_in_their_business_unit(self):
        identity = Identity("genai@shellkode.com", "GenAI Head", "GENAI", "GenAI")
        items = [
            {"document_id": "1", "business_unit": "GenAI", "owner_email": "a@shellkode.com"},
            {"document_id": "2", "business_unit": "GenAI", "owner_email": "b@shellkode.com"},
            {"document_id": "3", "business_unit": "Cloud", "owner_email": "c@shellkode.com"},
        ]
        self.assertEqual(
            [item["document_id"] for item in filter_visible_items(items, identity)],
            ["1", "2"],
        )

    def test_tracker_grouping_filters_individual_users_by_owner_email(self):
        handler = object.__new__(DynamoDBHandlerOptimized)
        handler.table = _FakeDocumentTable([
            {
                "customer_name": "Shared Client",
                "project_name": "Ananya Project",
                "mode": "POC",
                "version": "v1",
                "owner_email": "ananya.user@shellkode.com",
            },
            {
                "customer_name": "Shared Client",
                "project_name": "Rohan Project",
                "mode": "POC",
                "version": "v1",
                "owner_email": "rohan.user@shellkode.com",
            },
            {
                "customer_name": "Legacy Client",
                "project_name": "Unowned Project",
                "mode": "PROD",
                "version": "v1",
            },
        ])

        grouped = handler.get_companies_grouped(owner_email="ANANYA.USER@SHELLKODE.COM")

        self.assertEqual(list(grouped), ["Shared Client"])
        self.assertEqual(grouped["Shared Client"]["document_count"], 1)
        self.assertEqual(list(grouped["Shared Client"]["projects"]), ["Ananya Project"])

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
            self.assertTrue(store.authenticate("ananya.user@shellkode.com", SAMPLE_PASSWORD).is_user)
            self.assertEqual(len(SAMPLE_USERS), 9)

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
            with patch.object(server.rbac_store, "active_identity", return_value=identity):
                me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
            self.assertEqual(me.status_code, 200)
            self.assertEqual(me.get_json()["user"]["business_unit"], "Cloud")
        finally:
            server.app.config["TESTING"] = previous_testing

    def test_user_management_endpoint_is_admin_only(self):
        from app.core import server

        previous_testing = server.app.config.get("TESTING", False)
        server.app.config["TESTING"] = False
        admin = Identity("admin@shellkode.com", "Admin", "ADMIN")
        individual = Identity("ananya.user@shellkode.com", "Ananya", "USER", "GenAI")
        client = server.app.test_client()
        try:
            with patch.object(server.rbac_store, "active_identity", return_value=individual):
                response = client.get(
                    "/api/admin/users",
                    headers={"Authorization": f"Bearer {issue_token(individual)}"},
                )
            self.assertEqual(response.status_code, 403)

            with (
                patch.object(server.rbac_store, "active_identity", return_value=admin),
                patch.object(server.rbac_store, "list_users", return_value=[admin.public_dict()]),
            ):
                response = client.get(
                    "/api/admin/users",
                    headers={"Authorization": f"Bearer {issue_token(admin)}"},
                )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.get_json()["users"]), 1)
        finally:
            server.app.config["TESTING"] = previous_testing

    def test_sow_records_mine_filter_is_role_independent(self):
        from app.core import server

        previous_testing = server.app.config.get("TESTING", False)
        server.app.config["TESTING"] = True
        handler = MagicMock()
        handler.list_all_documents.return_value = [
            {
                "document_id": "mine",
                "owner_email": "test-admin@shellkode.com",
                "project_name": "My SOW",
            },
            {
                "document_id": "other",
                "owner_email": "someone@shellkode.com",
                "project_name": "Someone Else's SOW",
            },
        ]
        try:
            with (
                patch.object(server, "DynamoDBHandler", return_value=handler),
                patch.object(server, "merge_with_active_tasks", side_effect=lambda items, **_kwargs: items),
            ):
                response = server.app.test_client().get("/api/history?mine=true&limit=1000")

            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            self.assertEqual([item["document_id"] for item in payload["documents"]], ["mine"])
        finally:
            server.app.config["TESTING"] = previous_testing


if __name__ == "__main__":
    unittest.main()
