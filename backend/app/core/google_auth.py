"""Google Workspace sign-in with one-use, browser-bound OAuth and opaque sessions.

OAuth secrets, PKCE verifiers and Google tokens never enter a browser cookie.
The existing RBAC DynamoDB table stores short-lived challenges and revocable sessions.
"""
import base64
import hashlib
import hmac
import os
import secrets
import time
from urllib.parse import urlencode, urlsplit

import requests
from botocore.exceptions import BotoCoreError, ClientError
from flask import g, jsonify, redirect, request
from google.auth.transport.requests import Request as GoogleRequest
from google.auth.exceptions import TransportError
from google.oauth2 import id_token

from app.core.access_control import AuthServiceUnavailable

SESSION_COOKIE = 'sow_session'
FLOW_COOKIE = 'sow_google_flow'
SESSION_SECONDS = 8 * 60 * 60
FLOW_SECONDS = 600
LEGACY_AUTH_PATHS = {
    '/api/auth/' + name for name in (
        'login', 'signup', 'verify', 'resend-verification', 'forgot-password',
        'reset-password', 'change-password-request',
    )
}


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def frontend_url():
    return os.getenv('FRONTEND_URL', 'http://localhost:3000').rstrip('/')


def frontend_origin():
    parsed = urlsplit(frontend_url())
    return f'{parsed.scheme}://{parsed.netloc}'


def secure_cookies():
    return urlsplit(frontend_url()).scheme == 'https'


def set_cookie(response, name, value, age):
    response.set_cookie(name, value, max_age=age, httponly=True,
                        secure=secure_cookies(), samesite='Lax', path='/api/')


def clear_cookie(response, name):
    response.delete_cookie(name, path='/api/', secure=secure_cookies(),
                           httponly=True, samesite='Lax')


def configuration():
    client_id = os.getenv('GOOGLE_CLIENT_ID', '').strip()
    client_secret = os.getenv('GOOGLE_CLIENT_SECRET', '').strip()
    redirect_uri = os.getenv('GOOGLE_REDIRECT_URI', '').strip()
    domain = os.getenv('GOOGLE_WORKSPACE_DOMAIN', 'shellkode.com').strip().lower()
    # This application is restricted to Shellkode; configuration cannot widen it.
    if not client_id or not client_secret or domain != 'shellkode.com':
        raise ValueError('GOOGLE_NOT_CONFIGURED')
    parsed = urlsplit(redirect_uri)
    if (parsed.path != '/api/auth/google/callback' or parsed.query or parsed.fragment
            or not parsed.netloc or (parsed.scheme != 'https' and not (
                parsed.scheme == 'http' and parsed.hostname in {'localhost', '127.0.0.1'}))):
        raise ValueError('GOOGLE_NOT_CONFIGURED')
    front = urlsplit(frontend_url())
    if front.scheme != 'https' and not (front.scheme == 'http' and front.hostname in {'localhost', '127.0.0.1'}):
        raise ValueError('GOOGLE_NOT_CONFIGURED')
    return client_id, client_secret, redirect_uri, domain


def validate_claims(claims, nonce, client_id, domain):
    """Additional checks after google-auth verifies Google's signature and expiry."""
    email = str(claims.get('email', '')).strip().lower()
    if (claims.get('iss') not in {'accounts.google.com', 'https://accounts.google.com'}
            or claims.get('aud') != client_id
            or claims.get('email_verified') is not True
            or claims.get('hd') != domain
            or email.count('@') != 1 or email.rsplit('@', 1)[-1] != domain
            or not isinstance(claims.get('sub'), str) or not claims['sub']
            or not hmac.compare_digest(str(claims.get('nonce', '')), nonce)
            or float(claims.get('exp', 0)) <= time.time()):
        raise ValueError('GOOGLE_IDENTITY_REJECTED')
    return email


def _key(kind, token):
    return {'PK': f'{kind}#{digest(token)}', 'SK': 'AUTH'}


def authenticate_session(store):
    token = request.cookies.get(SESSION_COOKIE, '')
    if not token:
        return None
    try:
        session = store.table.get_item(Key=_key('SESSION', token), ConsistentRead=True).get('Item')
        if not session or int(session['expires_at']) <= time.time():
            return None
        user = store.get_user(session['email'])
        if not user or user.get('status', 'active') != 'active' or user.get('google_sub') != session['google_sub']:
            return None
        g.auth_session = session
        return store._identity_from_item(user)
    except (BotoCoreError, ClientError) as exc:
        raise AuthServiceUnavailable() from exc


def csrf_valid():
    return (request.headers.get('Origin') == frontend_origin()
            and hmac.compare_digest(request.headers.get('X-CSRF-Token', '').encode(),
                                    g.auth_session['csrf_token'].encode()))


def register_google_auth(app, get_store):
    def failure(code):
        response = redirect(frontend_url() + '/#/login?' + urlencode({'error': code}))
        clear_cookie(response, FLOW_COOKIE)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Referrer-Policy'] = 'no-referrer'
        return response

    @app.get('/api/auth/google/start')
    def google_start():
        try:
            client_id, _, redirect_uri, domain = configuration()
            state, binding, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(4))
            get_store().table.put_item(Item={
                **_key('OAUTH', state), 'binding': digest(binding), 'nonce': nonce,
                'verifier': verifier, 'expires_at': int(time.time()) + FLOW_SECONDS,
            })
            challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
            response = redirect('https://accounts.google.com/o/oauth2/v2/auth?' + urlencode({
                'client_id': client_id, 'redirect_uri': redirect_uri, 'response_type': 'code',
                'scope': 'openid email profile', 'state': state, 'nonce': nonce, 'hd': domain,
                'code_challenge': challenge, 'code_challenge_method': 'S256', 'prompt': 'select_account',
            }))
            set_cookie(response, FLOW_COOKIE, binding, FLOW_SECONDS)
            response.headers['Cache-Control'] = 'no-store'
            return response
        except ValueError:
            return failure('GOOGLE_NOT_CONFIGURED')
        except (BotoCoreError, ClientError, AuthServiceUnavailable):
            return failure('AUTH_SERVICE_UNAVAILABLE')

    @app.get('/api/auth/google/callback')
    def google_callback():
        try:
            client_id, client_secret, redirect_uri, domain = configuration()
        except ValueError:
            return failure('GOOGLE_NOT_CONFIGURED')
        try:
            state, binding = request.args.get('state', ''), request.cookies.get(FLOW_COOKIE, '')
            if not state or not binding:
                return failure('GOOGLE_STATE_INVALID')
            store = get_store()
            # Atomic consume: expired, missing, mismatched and replayed challenges fail closed.
            try:
                flow = store.table.delete_item(
                    Key=_key('OAUTH', state), ReturnValues='ALL_OLD',
                    ConditionExpression='binding = :binding AND expires_at > :now',
                    ExpressionAttributeValues={':binding': digest(binding), ':now': int(time.time())},
                ).get('Attributes')
            except ClientError as exc:
                if exc.response['Error']['Code'] == 'ConditionalCheckFailedException':
                    return failure('GOOGLE_STATE_INVALID')
                raise
            if not flow:
                return failure('GOOGLE_STATE_INVALID')
            if request.args.get('error'):
                return failure('GOOGLE_CANCELLED')
            code = request.args.get('code', '')
            if not code:
                return failure('GOOGLE_STATE_INVALID')
            token_response = requests.post('https://oauth2.googleapis.com/token', data={
                'code': code, 'client_id': client_id, 'client_secret': client_secret,
                'redirect_uri': redirect_uri, 'grant_type': 'authorization_code',
                'code_verifier': flow['verifier'],
            }, timeout=15)
            token_response.raise_for_status()
            claims = id_token.verify_oauth2_token(token_response.json()['id_token'], GoogleRequest(), client_id)
            email = validate_claims(claims, flow['nonce'], client_id, domain)
            store.google_identity(email, claims['sub'], str(claims.get('name') or email))
            session_token = secrets.token_urlsafe(48)
            store.table.put_item(Item={
                **_key('SESSION', session_token), 'email': email, 'google_sub': claims['sub'],
                'csrf_token': secrets.token_urlsafe(32), 'expires_at': int(time.time()) + SESSION_SECONDS,
            })
            # Revoke any previous browser session on successful sign-in.
            previous = request.cookies.get(SESSION_COOKIE)
            if previous:
                store.table.delete_item(Key=_key('SESSION', previous))
            response = redirect(frontend_url() + '/#/')
            set_cookie(response, SESSION_COOKIE, session_token, SESSION_SECONDS)
            clear_cookie(response, FLOW_COOKIE)
            response.headers['Cache-Control'] = 'no-store'
            response.headers['Referrer-Policy'] = 'no-referrer'
            return response
        except (BotoCoreError, ClientError, AuthServiceUnavailable):
            return failure('AUTH_SERVICE_UNAVAILABLE')
        except requests.HTTPError as exc:
            if exc.response is not None and 400 <= exc.response.status_code < 500:
                return failure('GOOGLE_IDENTITY_REJECTED')
            return failure('AUTH_SERVICE_UNAVAILABLE')
        except (requests.RequestException, TransportError):
            return failure('AUTH_SERVICE_UNAVAILABLE')
        except Exception:
            # Never log callback codes, token responses, secrets, or raw Google errors.
            return failure('GOOGLE_IDENTITY_REJECTED')

    @app.post('/api/auth/logout')
    def google_logout():
        try:
            token = request.cookies.get(SESSION_COOKIE)
            if token:
                get_store().table.delete_item(Key=_key('SESSION', token))
        except (BotoCoreError, ClientError) as exc:
            raise AuthServiceUnavailable() from exc
        response = jsonify({'success': True})
        clear_cookie(response, SESSION_COOKIE)
        return response
