"""An identity-store outage must never masquerade as bad credentials."""
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

from app.core.access_control import AuthServiceUnavailable, Identity, RBACStore, issue_token


@pytest.mark.parametrize("failure", [
    ClientError({"Error": {"Code": code}}, "GetItem")
    for code in ("ExpiredTokenException", "AccessDeniedException", "ResourceNotFoundException", "ThrottlingException")
] + [EndpointConnectionError(endpoint_url="https://dynamodb.example")])
def test_lookup_failure_is_not_missing_user(failure, monkeypatch):
    monkeypatch.setenv("ENABLE_SAMPLE_USERS", "true")
    store = RBACStore.__new__(RBACStore)
    store.table = MagicMock()
    store.table.get_item.side_effect = failure
    for operation in (lambda: store.get_user("admin@shellkode.com"),
                      lambda: store.authenticate("admin@shellkode.com", "bad-password"),
                      lambda: store.active_identity("admin@shellkode.com")):
        with pytest.raises(AuthServiceUnavailable):
            operation()


def test_missing_user_is_still_missing():
    store = RBACStore.__new__(RBACStore)
    store.table = MagicMock()
    store.table.get_item.return_value = {}
    assert store.get_user("missing@example.com") is None
    assert store.table.get_item.call_args.kwargs["ConsistentRead"] is True


def test_login_outage_returns_503_not_bad_password():
    from app.core import server
    with patch.object(server.rbac_store, "authenticate", side_effect=AuthServiceUnavailable()):
        result = server.app.test_client().post('/api/auth/login', json={"email": "someone@example.com", "password": "test"})
    assert result.status_code == 503
    assert result.json["code"] == "AUTH_SERVICE_UNAVAILABLE"
    assert result.headers["Retry-After"] == "5"


def test_poll_outage_returns_503_and_never_runs_protected_route():
    from app.core import server
    token = issue_token(Identity("someone@example.com", "Someone", "USER", "GenAI"))
    with patch.object(server.rbac_store, "active_identity", side_effect=AuthServiceUnavailable()):
        result = server.app.test_client().get('/api/auth/me', headers={"Authorization": f"Bearer {token}"})
    assert result.status_code == 503


def test_deleted_account_still_revokes_session():
    from app.core import server
    token = issue_token(Identity("someone@example.com", "Someone", "USER", "GenAI"))
    with patch.object(server.rbac_store, "active_identity", return_value=None):
        result = server.app.test_client().get('/api/auth/me', headers={"Authorization": f"Bearer {token}"})
    assert result.status_code == 401


def test_bad_credentials_still_rejected():
    from app.core import server
    with patch.object(server.rbac_store, "authenticate", return_value=None), patch.object(server.rbac_store, "get_user", return_value=None):
        result = server.app.test_client().post('/api/auth/login', json={"email": "missing@example.com", "password": "bad"})
    assert result.status_code == 401
