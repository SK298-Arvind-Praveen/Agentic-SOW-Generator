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


def test_session_outage_returns_503_not_invalid_session():
    from app.core import server
    with patch.object(server, "authenticate_session", side_effect=AuthServiceUnavailable()):
        result = server.app.test_client().get('/api/auth/me')
    assert result.status_code == 503
    assert result.json["code"] == "AUTH_SERVICE_UNAVAILABLE"
    assert result.headers["Retry-After"] == "5"


def test_poll_outage_returns_503_and_never_runs_protected_route():
    from app.core import server
    token = issue_token(Identity("someone@example.com", "Someone", "USER", "GenAI"))
    with patch.object(server, "authenticate_session", side_effect=AuthServiceUnavailable()):
        result = server.app.test_client().get('/api/auth/me', headers={"Authorization": f"Bearer {token}"})
    assert result.status_code == 503


def test_deleted_account_still_revokes_session():
    from app.core import server
    token = issue_token(Identity("someone@example.com", "Someone", "USER", "GenAI"))
    with patch.object(server, "authenticate_session", return_value=None):
        result = server.app.test_client().get('/api/auth/me', headers={"Authorization": f"Bearer {token}"})
    assert result.status_code == 401


def test_bad_credentials_still_rejected():
    from app.core import server
    with patch.object(server.rbac_store, "authenticate", return_value=None), patch.object(server.rbac_store, "get_user", return_value=None):
        result = server.app.test_client().post('/api/auth/login', json={"email": "missing@example.com", "password": "bad"})
    assert result.status_code == 410


@pytest.mark.parametrize('path,endpoint', [('/api/finalize','finalize_document'),('/api/proxy-download','proxy_download')])
def test_auth_outage_happens_before_document_work_and_retry_rechecks_account(path, endpoint):
    from app.core import server
    identity = Identity('someone@example.com','Someone','USER','GenAI')
    token = issue_token(identity)
    protected = MagicMock(return_value=({'success':True},200))
    with patch.object(server,'authenticate_session',side_effect=[AuthServiceUnavailable(), identity]) as auth, \
            patch.object(server, 'csrf_valid', return_value=True), \
            patch.dict(server.app.view_functions,{endpoint:protected}):
        client = server.app.test_client()
        first = client.post(path,json={'preview_id':'p1'},headers={'Authorization':f'Bearer {token}'})
        assert first.status_code == 503 and first.json['retryable'] is True
        protected.assert_not_called()
        second = client.post(path,json={'preview_id':'p1'},headers={'Authorization':f'Bearer {token}'})
        assert second.status_code == 200
        assert auth.call_count == 2
        protected.assert_called_once()


def test_credential_outage_is_not_retried_or_logged_with_secrets(caplog):
    store = RBACStore.__new__(RBACStore)
    store.table = MagicMock()
    store.table.get_item.side_effect = ClientError({'Error':{'Code':'ExpiredTokenException','Message':'PRIVATE_CREDENTIAL'},
        'ResponseMetadata':{'RequestId':'aws-request-123','RetryAttempts':0}},'GetItem')
    with pytest.raises(AuthServiceUnavailable) as failure:
        store.get_user('private-email@example.com')
    assert failure.value.retryable is False
    assert 'ExpiredTokenException' in caplog.text and 'aws-request-123' in caplog.text
    assert 'PRIVATE_CREDENTIAL' not in caplog.text and 'private-email@example.com' not in caplog.text


def test_identity_store_uses_bounded_standard_retries():
    with patch('app.core.access_control.boto3.resource') as resource:
        RBACStore()
    config = resource.call_args.kwargs['config']
    assert config.connect_timeout == 5 and config.read_timeout == 8
    assert config.retries == {'mode':'standard','total_max_attempts':2}
