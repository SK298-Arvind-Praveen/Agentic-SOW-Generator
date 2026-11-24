"""Offline security regressions: no Google calls or AWS writes."""
import os
import time
import unittest
import requests
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlsplit

from botocore.exceptions import ClientError
from flask import Flask, g, jsonify

from app.core.access_control import RBACStore
from app.core.google_auth import (
    FLOW_COOKIE, SESSION_COOKIE, _key, authenticate_session, csrf_valid,
    register_google_auth, validate_claims,
)


class MemoryTable:
    def __init__(self):
        self.items = {}

    def put_item(self, Item, **kwargs):
        self.items[(Item['PK'], Item['SK'])] = dict(Item)

    def get_item(self, Key, **kwargs):
        return {'Item': self.items.get((Key['PK'], Key['SK']))}

    def delete_item(self, Key, **kwargs):
        key = (Key['PK'], Key['SK'])
        item = self.items.get(key)
        if kwargs.get('ConditionExpression'):
            values = kwargs['ExpressionAttributeValues']
            if not item or item['binding'] != values[':binding'] or item['expires_at'] <= values[':now']:
                raise ClientError({'Error': {'Code': 'ConditionalCheckFailedException'}}, 'DeleteItem')
        return {'Attributes': self.items.pop(key, None)}


class GoogleAuthTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            'GOOGLE_CLIENT_ID': 'test-client', 'GOOGLE_CLIENT_SECRET': 'server-secret',
            'GOOGLE_REDIRECT_URI': 'http://localhost:9000/api/auth/google/callback',
            'GOOGLE_WORKSPACE_DOMAIN': 'shellkode.com', 'FRONTEND_URL': 'http://localhost:3000',
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.store = MagicMock()
        self.store.table = MemoryTable()
        self.store.get_user.return_value = {'email': 'a@shellkode.com', 'name': 'A', 'status': 'active',
                                            'google_sub': 'subject', 'role': 'USER', 'roles': ['USER']}
        self.store._identity_from_item.side_effect = RBACStore._identity_from_item
        self.app = Flask(__name__)
        self.app.testing = True
        register_google_auth(self.app, lambda: self.store)

        @self.app.before_request
        def protect():
            if '/google/' in __import__('flask').request.path:
                return None
            g.current_identity = authenticate_session(self.store)
            if not g.current_identity:
                return jsonify(error='unauthenticated'), 401
            if __import__('flask').request.method == 'POST' and not csrf_valid():
                return jsonify(error='csrf'), 403

        @self.app.get('/api/me')
        def me():
            return jsonify(user=g.current_identity.public_dict(), csrf_token=g.auth_session['csrf_token'])

        self.client = self.app.test_client()

    def claims(self, nonce='nonce'):
        return {'iss': 'https://accounts.google.com', 'aud': 'test-client', 'sub': 'subject',
                'email': 'a@shellkode.com', 'email_verified': True, 'hd': 'shellkode.com',
                'nonce': nonce, 'exp': time.time() + 3600}

    def start(self):
        response = self.client.get('/api/auth/google/start')
        query = parse_qs(urlsplit(response.location).query)
        self.assertEqual(query['code_challenge_method'], ['S256'])
        self.assertNotIn('server-secret', response.location)
        self.assertIn('HttpOnly', response.headers['Set-Cookie'])
        return query['state'][0], query['nonce'][0]

    def login(self):
        state, nonce = self.start()
        with patch('app.core.google_auth.requests.post') as post, patch('app.core.google_auth.id_token.verify_oauth2_token', return_value=self.claims(nonce)) as verify:
            post.return_value.json.return_value = {'id_token': 'verified-google-token'}
            response = self.client.get('/api/auth/google/callback?state=' + state + '&code=code')
            verify.assert_called_once()
            self.assertTrue(post.call_args.kwargs['data']['code_verifier'])
        self.assertEqual(response.location, 'http://localhost:3000/#/')
        self.assertNotIn('verified-google-token', str(response.headers))
        return state

    def test_claims_reject_wrong_domain_unverified_issuer_audience_nonce_expiry(self):
        for field, value in [('hd', 'other.com'), ('email', 'a@other.com'), ('email_verified', False),
                             ('iss', 'evil'), ('aud', 'wrong-client'), ('nonce', 'other'), ('exp', 0), ('sub', '')]:
            with self.subTest(field=field):
                claims = self.claims()
                claims[field] = value
                with self.assertRaises(ValueError):
                    validate_claims(claims, 'nonce', 'test-client', 'shellkode.com')

    def test_wrong_browser_and_replay_are_rejected_before_token_exchange(self):
        state, _ = self.start()
        other = self.app.test_client()
        other.set_cookie(FLOW_COOKIE, 'wrong', path='/api/')
        with patch('app.core.google_auth.requests.post') as post:
            response = other.get('/api/auth/google/callback?state=' + state + '&code=x')
            self.assertIn('GOOGLE_STATE_INVALID', response.location)
            post.assert_not_called()
        used = self.login()
        with patch('app.core.google_auth.requests.post') as post:
            response = self.client.get('/api/auth/google/callback?state=' + used + '&code=x')
            self.assertIn('GOOGLE_STATE_INVALID', response.location)
            post.assert_not_called()

    def test_expired_flow_is_rejected(self):
        state, _ = self.start()
        key = _key('OAUTH', state)
        self.store.table.items[(key['PK'], key['SK'])]['expires_at'] = 0
        self.assertIn('GOOGLE_STATE_INVALID', self.client.get('/api/auth/google/callback?state=' + state).location)

    def test_google_verification_failure_creates_no_session(self):
        state, _ = self.start()
        with patch('app.core.google_auth.requests.post'), patch('app.core.google_auth.id_token.verify_oauth2_token', side_effect=ValueError('bad signature')):
            response = self.client.get('/api/auth/google/callback?state=' + state + '&code=x')
        self.assertIn('GOOGLE_IDENTITY_REJECTED', response.location)
        self.store.google_identity.assert_not_called()
        self.assertFalse(any(key[0].startswith('SESSION#') for key in self.store.table.items))

    def test_google_transport_outage_is_reported_as_service_unavailable(self):
        state, _ = self.start()
        with patch('app.core.google_auth.requests.post', side_effect=requests.Timeout()):
            response = self.client.get('/api/auth/google/callback?state=' + state + '&code=x')
        self.assertIn('AUTH_SERVICE_UNAVAILABLE', response.location)
        self.store.google_identity.assert_not_called()

    def test_session_csrf_logout_revocation_and_current_roles(self):
        self.login()
        me = self.client.get('/api/me').get_json()
        self.assertEqual(me['user']['role'], 'USER')
        self.store.get_user.return_value['role'] = 'ADMIN'
        self.store.get_user.return_value['roles'] = ['ADMIN']
        self.assertEqual(self.client.get('/api/me').get_json()['user']['role'], 'ADMIN')
        self.assertEqual(self.client.post('/api/auth/logout').status_code, 403)
        self.assertEqual(self.client.post('/api/auth/logout', headers={'Origin': 'https://evil.example', 'X-CSRF-Token': me['csrf_token']}).status_code, 403)
        cookie = self.client.get_cookie(SESSION_COOKIE, path='/api/').value
        response = self.client.post('/api/auth/logout', headers={'Origin': 'http://localhost:3000', 'X-CSRF-Token': me['csrf_token']})
        self.assertEqual(response.status_code, 200)
        self.client.set_cookie(SESSION_COOKIE, cookie, path='/api/')
        self.assertEqual(self.client.get('/api/me').status_code, 401)

    def test_inactive_or_unlinked_identity_revokes_existing_session(self):
        self.login()
        self.store.get_user.return_value['status'] = 'inactive'
        self.assertEqual(self.client.get('/api/me').status_code, 401)
        self.store.get_user.return_value.update(status='active', google_sub='different')
        self.assertEqual(self.client.get('/api/me').status_code, 401)

    def test_expired_session_and_bearer_tokens_rejected(self):
        self.assertEqual(self.client.get('/api/me', headers={'Authorization': 'Bearer anything'}).status_code, 401)
        self.login()
        cookie = self.client.get_cookie(SESSION_COOKIE, path='/api/').value
        key = _key('SESSION', cookie)
        self.store.table.items[(key['PK'], key['SK'])]['expires_at'] = 0
        self.assertEqual(self.client.get('/api/me').status_code, 401)

    def test_new_google_user_is_user_and_existing_roles_preserved(self):
        store = RBACStore.__new__(RBACStore)
        store.table = MagicMock()
        new = {'email': 'new@shellkode.com', 'name': 'New', 'google_sub': 'sub', 'role': 'USER'}
        store.get_user = MagicMock(side_effect=[None, new])
        self.assertEqual(store.google_identity('new@shellkode.com', 'sub', 'New').role, 'USER')
        profile = store.table.put_item.call_args.kwargs['Item']
        self.assertEqual(profile['roles'], ['USER'])
        self.assertNotIn('password_hash', profile)
        existing = dict(new, role='ADMIN', roles=['ADMIN'])
        store.get_user = MagicMock(return_value=existing)
        self.assertTrue(store.google_identity('new@shellkode.com', 'sub', 'New').is_admin)
        self.assertNotIn('role', store.table.update_item.call_args.kwargs['UpdateExpression'])

    def test_google_link_rejects_inactive_or_changed_subject(self):
        store = RBACStore.__new__(RBACStore)
        store.table = MagicMock()
        for user in [{'status': 'inactive'}, {'status': 'pending_verification'}, {'status': 'active', 'google_sub': 'other'}]:
            store.get_user = MagicMock(return_value=user)
            with self.assertRaises(ValueError):
                store.google_identity('a@shellkode.com', 'sub', 'A')
        store.table.put_item.assert_not_called()

    def test_sample_identity_never_bypasses_store(self):
        store = RBACStore.__new__(RBACStore)
        store.get_user = MagicMock(return_value=None)
        with patch.dict(os.environ, {'ENABLE_SAMPLE_USERS': 'true'}):
            self.assertIsNone(store.active_identity('admin@shellkode.com'))


if __name__ == '__main__':
    unittest.main()
