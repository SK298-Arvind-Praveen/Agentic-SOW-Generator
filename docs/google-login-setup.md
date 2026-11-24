# Local Google Workspace login

Deployment is not required. Automated tests use mocked Google responses; the real
Google round trip still requires the configuration below.

## IT configuration

Use an OAuth client of type **Web application**, with an **Internal** consent
audience in the Shellkode Google Workspace organisation. Permit the application
for Shellkode users if Workspace app controls require it.

Register this exact **Authorised redirect URI**, with no trailing slash:

`http://localhost:9000/api/auth/google/callback`

The website is `http://localhost:3000`. A JavaScript origin is not needed for this
server-side redirect flow. Only `openid email profile` scopes are requested.
Provide the client ID and secret securely to the local developer.

## Local configuration

Add or update these values in the ignored `backend/config/.env`:

```dotenv
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=http://localhost:9000/api/auth/google/callback
GOOGLE_WORKSPACE_DOMAIN=shellkode.com
FRONTEND_URL=http://localhost:3000
```

Keep the secret in the backend only, never frontend variables, chat or Git.
No new application signing secret is required: sessions use opaque random tokens
stored as hashes in DynamoDB. Keep existing AWS/RBAC configuration and valid AWS
credentials. The RBAC table requires GetItem, PutItem, UpdateItem and DeleteItem,
plus existing administration permissions. Optional TTL on `expires_at` cleans up
expired records; code enforces expiry even without TTL.

From `backend`, install requirements if needed and restart:

```powershell
.\venv\Scripts\python.exe -m pip install -r config/requirements_clean.txt
.\venv\Scripts\python.exe app/core/server.py
```

Stop the previous backend terminal with Ctrl+C before starting another on port 9000.
From `frontend`, run `npm start`. If an API override is configured, set
`REACT_APP_API_URL=http://localhost:9000`. Open `http://localhost:3000`.
Use localhost consistently, not a mixture of localhost and 127.0.0.1.

## Test manually

1. Click **Sign in with Google** and choose a Shellkode account.
2. Refresh: you should stay signed in. Sign out: protected APIs must stop working.
   Signing out of this app does not sign out of Google globally.
3. Every new verified shellkode.com Workspace user receives USER access. Existing
   active users retain roles and business units. New users never become admins
   automatically; use an existing active administrator to assign roles. Existing
   disabled or pending-verification accounts require admin activation.
4. Personal Gmail and other-domain accounts must be rejected. Cancellation should
   return a clear message with the option to retry.

Sessions expire after eight hours and use HttpOnly cookies. Unsafe API requests
require a CSRF token and the configured frontend Origin. Old password endpoints
return 410. Old signup/reset screens redirect to Google login. Old bearer tokens
and sample credentials do not grant access.

## Troubleshooting

- `redirect_uri_mismatch`: register the callback exactly on the configured client ID.
- Sign-in not configured: check the five env values and restart the backend.
- Sign-in temporarily unavailable: check Google connectivity, AWS credential expiry,
  RBAC DynamoDB permissions and backend logs. Do not share secrets or tokens.
- Account rejected: check Workspace membership, verified email and local active status.

Google documents localhost redirects and web client setup:
https://developers.google.com/identity/protocols/oauth2/web-server
