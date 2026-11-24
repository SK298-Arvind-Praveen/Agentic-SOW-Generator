import os
import unittest
from unittest.mock import MagicMock, patch
from werkzeug.security import check_password_hash

from app.core.access_control import (
    BUSINESS_UNITS,
    Identity,
    RBACStore,
    SAMPLE_PASSWORD,
    SAMPLE_USERS,
    filter_visible_items,
    issue_token,
    issue_password_reset_token,
    issue_verification_token,
    normalise_business_unit,
    verify_token,
    verify_password_reset_token,
    verify_verification_token,
)
from app.db.dynamodb_handler_optimized import DynamoDBHandlerOptimized


class _FakeDocumentTable:
    def __init__(self, items):
        self.items = items

    def scan(self, **_kwargs):
        return {"Items": self.items}


class _FakeRegistrationTable:
    def __init__(self):
        self.puts = []
        self.deletes = []

    def put_item(self, **kwargs):
        self.puts.append(kwargs)

    def delete_item(self, **kwargs):
        self.deletes.append(kwargs)


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

    def test_signed_token_preserves_multiple_business_unit_roles(self):
        identity = Identity(
            "architect@shellkode.com", "Architect", "GENAI", "GenAI",
            roles=("GENAI", "CLOUD"), business_units=("GenAI", "Cloud"),
        )
        with patch.dict(os.environ, {"AUTH_TOKEN_SECRET": "test-secret"}, clear=False):
            decoded = verify_token(issue_token(identity))
        self.assertEqual(decoded.roles, ("GENAI", "CLOUD"))
        self.assertEqual(decoded.business_units, ("GenAI", "Cloud"))
        self.assertFalse(decoded.is_user)

    def test_email_verification_token_is_separate_and_signed(self):
        with patch.dict(os.environ, {"AUTH_TOKEN_SECRET": "test-secret"}, clear=False):
            token = issue_verification_token("new.user@shellkode.com", "nonce")
            self.assertEqual(verify_verification_token(token), ("new.user@shellkode.com", "nonce"))

    def test_password_reset_token_uses_a_separate_signed_purpose(self):
        with patch.dict(os.environ, {"AUTH_TOKEN_SECRET": "test-secret"}, clear=False):
            token = issue_password_reset_token("new.user@shellkode.com", "reset-nonce")
            self.assertEqual(
                verify_password_reset_token(token),
                ("new.user@shellkode.com", "reset-nonce"),
            )
            with self.assertRaises(Exception):
                verify_verification_token(token)

    def test_password_reset_challenge_is_hashed_and_consumed(self):
        store = object.__new__(RBACStore)
        store.table = _FakeRegistrationTable()
        item = {
            "email": "asha@shellkode.com", "status": "active",
            "email_verified": True, "password_hash": "old-hash",
        }
        with patch.object(store, "get_user", return_value=item):
            email, nonce = store.begin_password_reset("asha@shellkode.com")
            self.assertEqual(email, "asha@shellkode.com")
            self.assertNotEqual(item["password_reset_nonce_hash"], nonce)
            store.reset_password(email, nonce, "new-secret")
        self.assertTrue(check_password_hash(item["password_hash"], "new-secret"))
        self.assertNotIn("password_reset_nonce_hash", item)

    def test_registration_combines_name_and_assigns_user_role(self):
        store = object.__new__(RBACStore)
        store.table = _FakeRegistrationTable()
        user, nonce = store.register_user(
            first_name="Asha", last_name="Rao", email="asha.rao@shellkode.com",
            employee_id=101, business_unit="Cloud", password="secret1",
        )
        self.assertEqual(user["name"], "Asha Rao")
        self.assertEqual(user["role"], "USER")
        self.assertEqual(user["roles"], ["USER"])
        self.assertEqual(user["business_unit"], "Cloud")
        self.assertEqual(user["employee_id"], 101)
        self.assertIsInstance(store.table.puts[1]["Item"]["employee_id"], int)
        self.assertEqual(user["status"], "pending_verification")
        self.assertTrue(nonce)
        self.assertEqual(store.table.puts[1]["Item"]["name"], "Asha Rao")

    def test_legacy_self_signup_bu_role_is_read_as_user(self):
        item = {
            "email": "arvind.p@shellkode.com", "name": "Arvind",
            "role": "GENAI", "roles": ["GENAI"],
            "business_unit": "GenAI", "business_units": ["GenAI"],
            "updated_by": "self-signup",
        }
        identity = RBACStore._identity_from_item(item)
        self.assertTrue(identity.is_user)
        self.assertEqual(identity.role, "USER")
        self.assertEqual(RBACStore._public_user(item)["roles"], ["USER"])

    def test_legacy_self_signup_role_is_persistently_migrated(self):
        store = object.__new__(RBACStore)
        store.table = _FakeRegistrationTable()
        item = {
            "email": "arvind.p@shellkode.com", "role": "GENAI",
            "roles": ["GENAI"], "updated_by": "self-signup",
        }
        store._migrate_self_signup_role(item)
        self.assertEqual(item["role"], "USER")
        self.assertEqual(item["roles"], ["USER"])
        self.assertEqual(store.table.puts[0]["Item"]["role"], "USER")

    def test_registration_requires_shellkode_email(self):
        store = object.__new__(RBACStore)
        store.table = _FakeRegistrationTable()
        with self.assertRaisesRegex(ValueError, "@shellkode.com"):
            store.register_user(
                first_name="Asha", last_name="Rao", email="asha@example.com",
                employee_id=101, business_unit="Cloud", password="secret1",
            )

    def test_legacy_prefixed_employee_id_is_exposed_as_an_integer(self):
        user = RBACStore._public_user({
            "email": "legacy@shellkode.com", "name": "Legacy User",
            "role": "USER", "business_unit": "Cloud", "employee_id": "SK998",
        })
        self.assertEqual(user["employee_id"], 998)

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

    def test_multi_role_user_sees_each_assigned_business_unit(self):
        identity = Identity(
            "architect@shellkode.com", "Architect", "GENAI", "GenAI",
            roles=("GENAI", "CLOUD"), business_units=("GenAI", "Cloud"),
        )
        items = [
            {"document_id": "1", "business_unit": "GenAI"},
            {"document_id": "2", "business_unit": "Cloud"},
            {"document_id": "3", "business_unit": "MLOps"},
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

    def test_tracker_grouping_accepts_multiple_assigned_business_units(self):
        handler = object.__new__(DynamoDBHandlerOptimized)
        handler.table = _FakeDocumentTable([
            {"customer_name": "Client", "project_name": "GenAI Work", "mode": "POC", "version": "v1", "business_unit": "GenAI"},
            {"customer_name": "Client", "project_name": "Cloud Work", "mode": "POC", "version": "v1", "business_unit": "Cloud"},
            {"customer_name": "Client", "project_name": "MLOps Work", "mode": "POC", "version": "v1", "business_unit": "MLOps"},
        ])
        grouped = handler.get_companies_grouped(business_unit=("GenAI", "Cloud"))
        self.assertEqual(grouped["Client"]["document_count"], 2)

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

    def test_user_management_endpoint_is_admin_only(self):
        from app.core import server

        previous_testing = server.app.config.get("TESTING", False)
        server.app.config["TESTING"] = False
        admin = Identity("admin@shellkode.com", "Admin", "ADMIN")
        individual = Identity("ananya.user@shellkode.com", "Ananya", "USER", "GenAI")
        client = server.app.test_client()
        try:
            with patch.object(server, "authenticate_session", return_value=individual):
                response = client.get(
                    "/api/admin/users",
                    headers={"Authorization": f"Bearer {issue_token(individual)}"},
                )
            self.assertEqual(response.status_code, 403)

            with (
                patch.object(server, "authenticate_session", return_value=admin),
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








    def test_user_role_cannot_open_account_apis(self):
        from app.core import server

        previous_testing = server.app.config.get("TESTING", False)
        server.app.config["TESTING"] = False
        individual = Identity("person@shellkode.com", "Person", "USER", "GenAI")
        try:
            with patch.object(server, "authenticate_session", return_value=individual):
                response = server.app.test_client().get(
                    "/api/accounts", headers={"Authorization": f"Bearer {issue_token(individual)}"},
                )
            self.assertEqual(response.status_code, 403)
            self.assertIn("Accounts dashboard", response.get_json()["error"])
        finally:
            server.app.config["TESTING"] = previous_testing

    def test_sow_records_mine_filter_is_role_independent(self):
        from app.core import server

        previous_testing = server.app.config.get("TESTING", False)
        server.app.config["TESTING"] = True
        bypass = patch.dict(server.app.config, {"TEST_AUTH_BYPASS": True})
        bypass.start()
        self.addCleanup(bypass.stop)
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

    def test_sow_deletion_is_admin_only_and_permanent(self):
        from app.core import server

        previous_testing = server.app.config.get("TESTING", False)
        server.app.config["TESTING"] = True
        bypass = patch.dict(server.app.config, {"TEST_AUTH_BYPASS": True})
        bypass.start()
        self.addCleanup(bypass.stop)
        handler = MagicMock()
        handler.get_document_by_id.return_value = {
            "document_id": "doc-1", "timestamp": "2026-09-22T10:00:00", "s3_url": "",
        }
        handler.delete_document.return_value = True
        try:
            with (
                patch.object(server, "_require_admin_response", return_value=None),
                patch.object(server, "DynamoDBHandler", return_value=handler),
                patch.object(server.account_handler, "delete_sow", return_value=True) as unlink,
            ):
                response = server.app.test_client().delete("/api/sows/doc-1")

            self.assertEqual(response.status_code, 200)
            handler.delete_document.assert_called_once_with("doc-1", "2026-09-22T10:00:00")
            unlink.assert_called_once_with("doc-1")
        finally:
            server.app.config["TESTING"] = previous_testing


if __name__ == "__main__":
    unittest.main()


class GoogleOnlyApiTests(unittest.TestCase):
    def test_legacy_routes_are_gone_without_storage_or_email(self):
        from app.core import server
        from app.core.google_auth import LEGACY_AUTH_PATHS
        with patch.object(server.rbac_store, "authenticate") as auth, patch.object(server.rbac_store, "register_user") as register:
            for path in LEGACY_AUTH_PATHS:
                with self.subTest(path=path):
                    result = server.app.test_client().post(path, json={"password": "irrelevant"})
                    self.assertEqual(result.status_code, 410)
            auth.assert_not_called()
            register.assert_not_called()

    def test_testing_alone_and_legacy_bearer_do_not_authenticate(self):
        from app.core import server
        with patch.dict(server.app.config, {"TESTING": True, "TEST_AUTH_BYPASS": False}):
            client = server.app.test_client()
            self.assertEqual(client.get('/api/auth/me').status_code, 401)
            token = issue_token(Identity('admin@shellkode.com', 'Admin', 'ADMIN'))
            self.assertEqual(client.get('/api/auth/me', headers={'Authorization': 'Bearer ' + token}).status_code, 401)

    def test_auth_me_exposes_csrf_but_no_bearer_token(self):
        from flask import g
        from app.core import server
        def session(_store):
            g.auth_session = {'csrf_token': 'csrf'}
            return Identity('a@shellkode.com', 'A', 'USER')
        with patch.object(server, 'authenticate_session', side_effect=session), patch.dict(server.app.config, {'TEST_AUTH_BYPASS': False}):
            response = server.app.test_client().get('/api/auth/me')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['csrf_token'], 'csrf')
        self.assertNotIn('token', response.json)
