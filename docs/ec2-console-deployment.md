# Deploy the SOW portal on EC2 Graviton

This is a console-led, single-instance deployment guide for the current repository.
The commands run in the EC2 terminal, not on your Windows machine. The Linux/ARM
installation has not been executed from this development session. Run the checks
below before making it available to the team.

## 1. Prepare the hostname and access

Ask IT for a hostname such as `sow.shellkode.com`. Substitute your actual hostname
throughout this guide. Google OAuth needs an HTTPS redirect URI outside localhost:
`https://sow.shellkode.com/api/auth/google/callback`.

Keep the existing AWS resources and inference profiles in their configured regions.
In IAM, create an EC2 service role with the app's required access to its existing
S3 bucket, DynamoDB tables/indexes, Bedrock inference profiles and underlying models
(including cross-region inference destinations), Titan embeddings and any configured
knowledge-base retrieval. Grant KMS access only if those resources use a customer key.
Reuse a reviewed application policy; do not attach administrator access to the instance.
Google Search API keys and OAuth secrets remain separate from IAM.

Existing default resources: `agentic-sow-files` (S3), `agentic-sow-v2`, `agentic-poc`,
and `agentic-sow-rbac` (DynamoDB). Check your actual `.env` overrides before setting policy.
Using the same RBAC table retains Arvind's admin role. Model subscriptions/access must
already be enabled; the runtime role does not need permission to buy subscriptions.

## 2. Launch from the AWS console

1. Open EC2 in your chosen region (using `us-east-1` keeps this server near the current backend resources).
2. Choose **Launch instance**, name `shellkode-sow`.
3. Choose **Ubuntu Server 24.04 LTS**, architecture **64-bit Arm**.
4. Start with **m7g.large** (2 vCPU, 8 GiB); use m7g.xlarge if you expect several concurrent generations.
5. Choose a key pair. Create a security group: SSH 22 from your own/VPN IP; HTTPS
   443 from approved users/VPN ranges, or internet if the company approves a public
   authenticated portal. HTTP 80 is needed for the Certbot HTTP challenge below;
   DNS validation is an alternative if the service must remain private.
6. Select a public subnet with an Internet Gateway route; assign a public IP.
7. Allocate **50 GiB gp3**, encrypted. Keep IMDSv2 required.
8. Under **Advanced details → IAM instance profile**, select the app role. Launch.
9. In **Elastic IPs**, allocate and associate an address. Ask IT to create an A
   record for your hostname pointing to it. Do not expose port 9000 or 3000.
10. Connect via SSH with your key, or configure EC2 Instance Connect/Session Manager
    according to your organisation's access policy. Console Instance Connect needs
    its own allowed source range; an SSH rule for your laptop alone does not cover it.

## 3. Install the application

Run as the `ubuntu` user, using sudo only for system installation:

```bash
sudo apt-get update
sudo apt-get install -y git curl xz-utils python3-venv python3-dev build-essential \
  nginx certbot python3-certbot-nginx antiword xvfb xauth fonts-dejavu-core

cd /tmp
curl -fLO https://nodejs.org/dist/v22.23.5/node-v22.23.5-linux-arm64.tar.xz
curl -fLO https://nodejs.org/dist/v22.23.5/SHASUMS256.txt
grep ' node-v22.23.5-linux-arm64.tar.xz$' SHASUMS256.txt | sha256sum -c -
sudo tar -xJf node-v22.23.5-linux-arm64.tar.xz -C /usr/local --strip-components=1

sudo install -d -o ubuntu -g ubuntu /srv/sow
git clone https://github.com/SK298-Arvind-Praveen/Agentic-SOW-Generator.git /srv/sow
cd /srv/sow
python3 -m venv backend/venv
backend/venv/bin/pip install -r backend/config/requirements_clean.txt
backend/venv/bin/pip install gunicorn
npm ci --prefix tools/architecture-layout --omit=dev --ignore-scripts --no-audit --no-fund
npm ci --prefix tools/drawio-renderer --omit=dev --ignore-scripts --no-audit --no-fund
npm ci --prefix tools/aws-pricing-calculator --no-audit --no-fund
cd tools/aws-pricing-calculator
npx playwright install --with-deps chromium
cd /srv/sow
npm ci --prefix frontend
PUBLIC_URL=/ REACT_APP_API_URL=https://sow.shellkode.com npm run build --prefix frontend
sudo install -d /var/www/sow
sudo cp -a frontend/build/. /var/www/sow/
```

For a private repository, use your approved GitHub deploy key/credential method;
do not put a personal token in the clone URL or service environment.

## 4. Install the same diagram renderer

The existing Dockerfile does not install the Desktop renderer. These native
instructions retain `hybrid_drawio` instead of silently changing diagram engines.

```bash
cd /tmp
curl -fLO https://github.com/jgraph/drawio-desktop/releases/download/v32.7.4/drawio-arm64-32.7.4.deb
echo '562fe7e0e108342a60019cb3fbd8500b8ba3a3e532cb34b6ac63e5a7a98e998f  drawio-arm64-32.7.4.deb' | sha256sum -c -
sudo apt-get install -y ./drawio-arm64-32.7.4.deb
sudo tee /usr/local/bin/sow-drawio >/dev/null <<'EOF'
#!/bin/sh
exec /usr/bin/xvfb-run -a /usr/bin/drawio "$@"
EOF
sudo chmod 755 /usr/local/bin/sow-drawio
```

## 5. Configure the backend and Google

Create `/srv/sow/backend/config/.env` using your working settings and secret values.
Do not commit it. Keep the model-selection settings and inference profile ARNs.
Remove `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` and any
local AWS profile override: the instance role supplies rotating credentials.

Set these deployment-specific values:

```dotenv
AWS_REGION=us-east-1
BEDROCK_REGION=us-east-1
FRONTEND_URL=https://sow.shellkode.com
GOOGLE_REDIRECT_URI=https://sow.shellkode.com/api/auth/google/callback
GOOGLE_WORKSPACE_DOMAIN=shellkode.com
GOOGLE_CLIENT_ID=<existing client ID>
GOOGLE_CLIENT_SECRET=<existing secret>
ARCHITECTURE_DIAGRAM_ENGINE=hybrid_drawio
DRAWIO_DESKTOP_BINARY=/usr/local/bin/sow-drawio
```

Replace Windows-specific executable paths with Linux paths or remove those overrides.
Retain Google Search configuration for company research and any other integrations
you actually use. Secure the file with `chmod 600 /srv/sow/backend/config/.env`.

In **Google Cloud Console → Google Auth Platform → Clients** (or APIs & Services →
Credentials), edit the web OAuth client. Add the exact redirect URI above. If
origins are configured, add `https://sow.shellkode.com`. Keep localhost entries
for development. Use an Internal audience for the Shellkode Workspace organisation.

## 6. Run a single backend worker

Create `/etc/systemd/system/sow-backend.service`:

```ini
[Unit]
Description=ShellKode SOW backend
After=network-online.target
Wants=network-online.target

[Service]
User=ubuntu
Group=ubuntu
WorkingDirectory=/srv/sow/backend
Environment=PATH=/srv/sow/backend/venv/bin:/usr/local/bin:/usr/bin:/bin
Environment=HOME=/home/ubuntu
Environment=PYTHONUNBUFFERED=1
ExecStart=/srv/sow/backend/venv/bin/gunicorn --workers 1 --threads 8 --timeout 1800 --graceful-timeout 1800 --bind 127.0.0.1:9000 --access-logfile - --error-logfile - app.core.server:app
Restart=on-failure
RestartSec=5
TimeoutStopSec=1830

[Install]
WantedBy=multi-user.target
```

The app reads its `.env` itself. **Keep one worker and one instance initially**:
previews and background tasks are held in process memory. Multiple workers/servers
would need shared task storage/queues first. Restart only when generations and
needed unsaved previews have finished.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now sow-backend
curl -f http://127.0.0.1:9000/health
sudo journalctl -u sow-backend -n 80 --no-pager
```

## 7. Serve the frontend and API through HTTPS

Create `/etc/nginx/sites-available/sow` (replace the hostname):

```nginx
server {
    listen 80;
    server_name sow.shellkode.com;
    root /var/www/sow;
    index index.html;
    client_max_body_size 100m;

    location /api/ {
        proxy_pass http://127.0.0.1:9000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 1800s;
        proxy_send_timeout 1800s;
        proxy_buffering off;
    }
    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/sow /etc/nginx/sites-enabled/sow
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d sow.shellkode.com --redirect
sudo certbot renew --dry-run
```

Frontend/API share one HTTPS origin; Google session cookies are automatically
Secure when FRONTEND_URL uses HTTPS. Do not put the Google secret in a frontend env file.

## 8. Validate before team use

1. As ubuntu, run `cd /srv/sow/backend && venv/bin/python scripts/smoke_drawio.py`.
   Inspect the PNG in `backend/output/drawio-local-test/nested` and confirm the
   renderer audit reports Desktop export without a fallback.
2. Visit the HTTPS hostname, sign in using a Shellkode Google account, and confirm
   Arvind sees admin controls. Outside-domain accounts must be rejected.
3. Generate a small BRD through the normal UI, including diagram, service table,
   timeline and pricing. Confirm the calculator link, history and DOCX download.
4. Check `sudo journalctl -u sow-backend -f` for timing and errors. Confirm model
   invocation uses the instance role, not copied expiring session credentials.
5. Confirm certificate renewal and instance monitoring. Restrict inbound access
   as agreed with IT; keep the backend port private.

This gives an initial deployment, not multi-instance high availability. Provisioning,
DNS, Google console changes, ARM dependency installation and live EC2 testing remain
actions to perform on the target instance.

References: [AWS IAM instance role](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/attach-iam-role.html),
[M7g specifications](https://aws.amazon.com/ec2/instance-types/m7g/),
[Google web-server OAuth](https://developers.google.com/identity/protocols/oauth2/web-server),
[draw.io ARM64 release](https://github.com/jgraph/drawio-desktop/releases/tag/v32.7.4),
[Node downloads](https://nodejs.org/en/download).
