# OctoWatch — Deployment Guide

OctoWatch is a security analytics platform for GitHub Enterprise audit logs. It
ships as three Docker images published to the GitHub Container Registry (GHCR).
You pull these images and deploy them on your own infrastructure — either as a
Docker Compose stack on a single server or via the included Helm chart on
Kubernetes.

This guide covers both paths end-to-end: quick-start, production hardening,
updates, backups, TLS, networking, and troubleshooting.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Container Images](#2-container-images)
3. [Quick Start (Docker Compose)](#3-quick-start-docker-compose)
4. [Production Deployment (Docker Compose)](#4-production-deployment-docker-compose)
5. [Kubernetes Deployment (Helm)](#5-kubernetes-deployment-helm)
6. [Updating the Application](#6-updating-the-application)
7. [Data Persistence & Backup](#7-data-persistence--backup)
8. [Environment Variables Reference](#8-environment-variables-reference)
9. [TLS / HTTPS](#9-tls--https)
10. [Network Architecture](#10-network-architecture)
11. [Troubleshooting](#11-troubleshooting)
12. [Zero-Downtime Upgrades](#12-zero-downtime-upgrades)
13. [High Availability Configuration](#13-high-availability-configuration)

---

## 1. Prerequisites

| Requirement | Minimum | Notes |
|---|---|---|
| Docker Engine | 24+ | With Docker Compose v2 (`docker compose`) |
| CPU | 4 vCPU | 8 vCPU recommended for production |
| RAM | 8 GB | 16 GB recommended for production |
| Disk | 100 GB | SSD strongly recommended; TimescaleDB is I/O heavy |
| Python | 3.10+ | Only needed on the deploy host to run `scripts/gen_env.py` |
| Domain name | — | Required for production TLS; optional for local dev |

**GitHub OAuth App** — required for user authentication:

1. Go to **GitHub → Settings → Developer Settings → OAuth Apps → New OAuth App**.
2. Set the **Authorization callback URL** to `https://<your-domain>/api/auth/github/callback`.
3. Note the **Client ID** and generate a **Client Secret**.

**GitHub App** (optional) — required only for GitHub Enterprise audit log sync:

1. Create a GitHub App in your Enterprise with these permissions:
   - `members: read`, `administration: read`, `secret_scanning_alerts: read`
2. Install it on the organizations you want to sync.
3. Note the **App ID** and download the **private key** `.pem` file.

---

## 2. Container Images

All images are published to GHCR by the
[Publish workflow](../.github/workflows/deploy.yml) after every successful CI
run on `main`, on version tags (`v*`), or via manual dispatch.

| Image | Description |
|---|---|
| `ghcr.io/<owner>/octowatch-api` | FastAPI backend + Alembic migration runner |
| `ghcr.io/<owner>/octowatch-worker` | Celery workers (ingestion, detection, baseline, sync) and beat scheduler |
| `ghcr.io/<owner>/octowatch-frontend` | React SPA served by nginx |

Replace `<owner>` with the GitHub user or organization that owns the repository
(e.g. `ghcr.io/acme-corp/octowatch-api`).

### Tagging strategy

| Tag | When applied | Example |
|---|---|---|
| `<commit-sha>` | Every publish | `a1b2c3d4e5f6` |
| `latest` | Every publish from `main` | `latest` |
| `<version>` | On version tag push (`v*`) | `1.2.3` |
| `<major>.<minor>` | On version tag push (`v*`) | `1.2` |

**Pin to a SHA or version tag in production** — never rely on `latest` for
repeatable deployments.

### Pulling images

```bash
# Latest
docker pull ghcr.io/<owner>/octowatch-api:latest
docker pull ghcr.io/<owner>/octowatch-worker:latest
docker pull ghcr.io/<owner>/octowatch-frontend:latest

# Specific version
docker pull ghcr.io/<owner>/octowatch-api:1.2.3
docker pull ghcr.io/<owner>/octowatch-worker:1.2.3
docker pull ghcr.io/<owner>/octowatch-frontend:1.2.3
```

If the repository is private, authenticate first:

```bash
echo "$GITHUB_TOKEN" | docker login ghcr.io -u <github-username> --password-stdin
```

---

## 3. Quick Start (Docker Compose)

This gets OctoWatch running locally for development and evaluation.

### Step 1 — Clone the repository

```bash
git clone https://github.com/<owner>/octowatch.git
cd octowatch
```

### Step 2 — Generate environment file

```bash
python scripts/gen_env.py
```

This creates a `.env` in the repository root with random secrets for
`SECRET_KEY`, `POSTGRES_PASSWORD`, `VALKEY_PASSWORD`, and `HEC_TOKEN`.

### Step 3 — Set GitHub OAuth credentials

Open `.env` and replace the placeholder values:

```dotenv
GITHUB_CLIENT_ID=your-oauth-client-id
GITHUB_CLIENT_SECRET=your-oauth-client-secret
APP_BASE_URL=https://localhost
```

If you want specific GitHub users to be granted admin access on first login, set:

```dotenv
INITIAL_ADMIN_LOGINS=octocat,hubot
```

### Step 4 — Generate self-signed TLS certificates

The bundled nginx expects TLS certificates at `nginx/ssl/`:

```bash
cd nginx/ssl
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout key.pem -out cert.pem \
  -subj "/CN=localhost"
cd ../..
```

### Step 5 — Build local images

```bash
docker compose build
```

### Step 6 — Start the stack

```bash
docker compose up -d
```

Docker Compose will start all services in dependency order. The `migrate`
service runs Alembic migrations before the API starts.

### Step 7 — Verify

```bash
# Check all containers are healthy
docker compose ps

# Test the health endpoint
curl -k https://localhost/health
```

Open **https://localhost** in your browser (accept the self-signed certificate
warning) and sign in with GitHub.

---

## 4. Production Deployment (Docker Compose)

For production, you pull pre-built images from GHCR instead of building locally,
use proper TLS, and set strong secrets.

### 4.1 Create a production compose override

Create a `docker-compose.prod.yml` that overrides image references to point at
GHCR and replaces nginx with Caddy for automatic TLS:

```yaml
# docker-compose.prod.yml — production overrides
services:
  migrate:
    image: ghcr.io/<owner>/octowatch-api:1.2.3

  api:
    image: ghcr.io/<owner>/octowatch-api:1.2.3

  worker-ingestion:
    image: ghcr.io/<owner>/octowatch-worker:1.2.3

  worker-detection:
    image: ghcr.io/<owner>/octowatch-worker:1.2.3

  worker-baseline:
    image: ghcr.io/<owner>/octowatch-worker:1.2.3

  worker-sync:
    image: ghcr.io/<owner>/octowatch-worker:1.2.3

  beat:
    image: ghcr.io/<owner>/octowatch-worker:1.2.3

  frontend:
    image: ghcr.io/<owner>/octowatch-frontend:1.2.3

  # Replace the dev nginx with Caddy for automatic Let's Encrypt TLS
  nginx:
    image: caddy:2-alpine
    ports:
      - "80:80"
      - "443:443"
      - "443:443/udp"   # HTTP/3
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config

volumes:
  caddy_data:
  caddy_config:
```

See [§9 — TLS / HTTPS](#9-tls--https) for the `Caddyfile` example.

### 4.2 Set strong secrets

Generate cryptographically secure secrets — **do not reuse dev defaults**:

```bash
# 64 hex chars (256 bits) — suitable for SECRET_KEY, ENCRYPTION_KEY
openssl rand -hex 32

# Generate all secrets at once
echo "SECRET_KEY=$(openssl rand -hex 32)"
echo "ENCRYPTION_KEY=$(openssl rand -hex 32)"
echo "POSTGRES_PASSWORD=$(openssl rand -hex 16)"
echo "VALKEY_PASSWORD=$(openssl rand -hex 16)"
echo "HEC_TOKEN=$(openssl rand -hex 32)"
```

Update `.env` with these values and ensure `DATABASE_URL` and `VALKEY_URL`
contain the matching passwords.

### 4.3 Configure the public URL

Set `APP_BASE_URL` to your actual domain (must match the OAuth callback URL):

```dotenv
APP_BASE_URL=https://octowatch.example.com
```

### 4.4 Mount data volumes to a dedicated disk

Bind-mount named volumes to a dedicated data disk to isolate I/O and simplify
backups. Add to `docker-compose.prod.yml`:

```yaml
volumes:
  pg_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /mnt/data/octowatch/postgres
  valkey_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /mnt/data/octowatch/valkey
```

Create the directories before starting the stack:

```bash
sudo mkdir -p /mnt/data/octowatch/{postgres,valkey}
```

### 4.5 Start the production stack

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### 4.6 Set up auto-restart with systemd

Create `/etc/systemd/system/octowatch.service`:

```ini
[Unit]
Description=OctoWatch
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/octowatch
ExecStart=/usr/bin/docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
ExecStop=/usr/bin/docker compose -f docker-compose.yml -f docker-compose.prod.yml down
TimeoutStartSec=120

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now octowatch
```

---

## 5. Kubernetes Deployment (Helm)

The `helm/` directory contains a full Helm chart with templates for all
OctoWatch services, plus Bitnami subcharts for PostgreSQL and Valkey.

### 5.1 Prerequisites

- Kubernetes 1.27+
- Helm 3.12+
- An ingress controller (e.g. ingress-nginx)
- cert-manager (recommended for automatic TLS)

### 5.2 Create your values file

Copy the defaults and customize:

```bash
cp helm/values.yaml my-values.yaml
```

At a minimum, update these settings:

```yaml
global:
  image:
    registry: ghcr.io/<owner>
    tag: "1.2.3"    # Pin to a specific version

ingress:
  host: octowatch.example.com
  tls:
    enabled: true
    secretName: octowatch-tls
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
```

The chart image repositories default to `octowatch-{api,worker,frontend}`.
If you are using the published GHCR images, override them:

```yaml
api:
  image:
    repository: octowatch-api

worker:
  image:
    repository: octowatch-worker

frontend:
  image:
    repository: octowatch-frontend
```

### 5.3 Create secrets

The chart expects these Kubernetes Secrets to exist before install:

```bash
# Database credentials
kubectl create secret generic octowatch-db-secret \
  --from-literal=postgres-password="$(openssl rand -hex 16)" \
  --from-literal=app-password="$(openssl rand -hex 16)"

# Valkey password
kubectl create secret generic octowatch-valkey-secret \
  --from-literal=valkey-password="$(openssl rand -hex 16)"

# Application secrets
kubectl create secret generic octowatch-app-secret \
  --from-literal=secret-key="$(openssl rand -hex 32)" \
  --from-literal=encryption-key="$(openssl rand -hex 32)" \
  --from-literal=github-client-id="your-client-id" \
  --from-literal=github-client-secret="your-client-secret"
```

### 5.4 Install

```bash
helm dependency update ./helm
helm install octowatch ./helm -f my-values.yaml
```

### 5.5 Verify

```bash
kubectl get pods -l app.kubernetes.io/instance=octowatch
kubectl logs -l app.kubernetes.io/component=api --tail=50
```

The Helm chart includes a `job-migrate` that runs Alembic migrations
automatically before the API deployment starts.

---

## 6. Configuring GitHub Audit Log Stream → HEC

OctoWatch's default ingestion mode (`INGESTION_MODE=hec`) uses a Splunk
HEC-compatible receiver to accept events directly from GitHub Enterprise
Cloud's audit log streaming feature — no intermediate object storage required.

### 6.1 Prerequisites

- OctoWatch is publicly accessible over HTTPS (required by GitHub for streaming)
- `HEC_TOKEN` is set to a strong random secret in your `.env`:
  ```bash
  echo "HEC_TOKEN=$(openssl rand -hex 32)"
  ```

### 6.2 Configure the audit log stream in GitHub Enterprise Cloud

1. Go to your GitHub organization or enterprise settings.
2. Navigate to **Audit log** → **Streams** (or **Log streaming** in enterprise settings).
3. Click **Add new stream** or **Configure stream**.
4. Set the stream **destination type** to **Splunk** (or **Custom HTTPS endpoint**
   if that appears instead).
5. Set the **Endpoint URL**:
   ```
   https://<your-octowatch-host>/services/collector
   ```
6. Set the **Token** field to the value of your `HEC_TOKEN`.
   GitHub will send `Authorization: Splunk <token>` with each request.
7. Leave other fields at their defaults (JSON format).
8. Click **Save** and verify GitHub shows the stream as **Active**.

### 6.3 Verify events are flowing

```bash
# Watch API logs for incoming HEC events
docker compose logs api --tail=50 -f | grep "hec\."

# Or test manually with a sample event
curl -sk -X POST https://<your-host>/services/collector \
  -H "Authorization: Splunk ${HEC_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"event": {"action": "org.add_member", "actor": "test-user", "org": "acme-corp"}}'
# Expected: {"text": "Success", "code": 0}
```

### 6.4 Switching to S3 or Azure Blob (optional)

If you prefer poll-based ingestion, set `INGESTION_MODE=s3` or
`INGESTION_MODE=azure_blob` in your `.env`. See the
[Object Storage (S3)](#object-storage-s3--when-ingestion_modes3) and
[Object Storage (Azure)](#object-storage-azure--when-ingestion_modeazure_blob) sections
below for the additional required environment variables.

---

## 7. Updating the Application

### Your data is safe

All persistent data lives in Docker volumes (or Kubernetes PersistentVolumeClaims).
Container image updates **never** touch these volumes:

| Volume | Contents |
|---|---|
| `pg_data` | TimescaleDB — all events, rules, users, detections |
| `valkey_data` | Valkey AOF — Celery results, dedup keys, sessions |

Updating containers is like swapping the engine on a car — the chassis (your
data) stays exactly where it is.

### Docker Compose update process

```bash
cd /opt/octowatch

# 1. Pull the latest images (or a specific tag)
docker compose -f docker-compose.yml -f docker-compose.prod.yml pull

# 2. Recreate only the containers whose images changed
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# 3. Clean up old image layers to reclaim disk space
docker image prune -f
```

That's it. Docker Compose detects which images changed and only restarts those
containers. Infrastructure services (TimescaleDB, Valkey) are unaffected
unless you explicitly update their image tags.

### Database migrations run automatically

The `migrate` service runs `alembic upgrade head` on every startup. It
executes before the API container starts (via `depends_on` with
`condition: service_completed_successfully`). You never need to run migrations
manually.

### Rollback

If an update causes issues, pin your override file to the previous working
image tag:

```yaml
# docker-compose.prod.yml — roll back to a known good version
services:
  api:
    image: ghcr.io/<owner>/octowatch-api:abc123def456
  # ... same SHA for worker and frontend
```

Then redeploy:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

> **Note:** Alembic migrations are forward-only by default. If a new release
> introduced a migration that you need to undo, you must run
> `alembic downgrade <previous-revision>` manually inside the API container
> before rolling back the image.

### Automated updates

#### Option A — Cron-based deploy script

Create `/opt/octowatch/deploy.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
cd /opt/octowatch

echo "[$(date -Iseconds)] Starting OctoWatch update..."

docker compose -f docker-compose.yml -f docker-compose.prod.yml pull --quiet
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
docker image prune -f --filter "until=72h"

echo "[$(date -Iseconds)] Update complete."
```

Schedule it with cron (e.g. daily at 03:00 UTC):

```bash
chmod +x /opt/octowatch/deploy.sh
echo "0 3 * * * /opt/octowatch/deploy.sh >> /var/log/octowatch-deploy.log 2>&1" \
  | sudo tee /etc/cron.d/octowatch-deploy
```

#### Option B — Webhook-based deployment

Set up a lightweight webhook listener (e.g.
[adnanh/webhook](https://github.com/adnanh/webhook)) that triggers the deploy
script when GHCR pushes a new image. Add a repository dispatch or
`workflow_dispatch` step in your CI pipeline to hit the webhook after a
successful publish.

### Helm update process

```bash
# Update to a new version
helm upgrade octowatch ./helm -f my-values.yaml --set global.image.tag=1.3.0

# Rollback to previous release
helm rollback octowatch 1
```

The Helm chart's `job-migrate` runs automatically on every `helm upgrade`,
applying any pending Alembic migrations before the new API pods start.

---

## 7. Data Persistence & Backup

### Volume inventory

| Volume | Service | Contents | Critical? |
|---|---|---|---|
| `pg_data` | TimescaleDB | Events, detections, rules, users, baselines | **Yes** — primary data store |
| `valkey_data` | Valkey | Celery task results, dedup keys, sessions | No — ephemeral cache; rebuilt on restart |

### Backup strategy

#### TimescaleDB (critical)

Use `pg_dump` for logical backups. Run from the host or a sidecar container:

```bash
# Full database dump (compressed)
docker compose exec db pg_dump \
  -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" \
  --format=custom \
  --compress=9 \
  -f /tmp/octowatch-backup.dump

# Copy the dump to the host
docker compose cp db:/tmp/octowatch-backup.dump ./backups/

# Or one-liner piped to host filesystem
docker compose exec db pg_dump \
  -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -Z9 \
  > "./backups/octowatch-$(date +%Y%m%d-%H%M%S).dump"
```

For large databases, consider TimescaleDB's native
[continuous aggregates and compression](https://docs.timescale.com/self-hosted/latest/backup-and-restore/)
plus filesystem-level snapshots (LVM, ZFS, or cloud disk snapshots).

**Schedule daily backups** with cron:

```bash
0 2 * * * docker compose -f /opt/octowatch/docker-compose.yml exec -T db \
  pg_dump -U appuser -d audit_logs -Fc -Z9 \
  > "/mnt/backups/octowatch-$(date +\%Y\%m\%d).dump" 2>&1
```

#### Valkey (not critical)

Valkey data is an ephemeral cache. It is automatically rebuilt from the database
and Celery task state on restart. Backups are not required, but Valkey's AOF
persistence (`--appendonly yes`) ensures dedup keys survive container restarts
and prevents duplicate event ingestion.

### Restore procedure

#### Restore TimescaleDB

```bash
# Stop the application (keep only the database running)
docker compose stop api worker-ingestion worker-detection worker-baseline worker-sync beat

# Restore from dump
docker compose exec -T db pg_restore \
  -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" \
  --clean --if-exists \
  < ./backups/octowatch-20250101.dump

# Restart the stack (migrations run automatically on startup)
docker compose up -d
```

---

## 8. Environment Variables Reference Set them in a `.env` file
(Docker Compose reads it automatically) or as Kubernetes Secrets / ConfigMaps.

### Core

| Variable | Required | Default | Description |
|---|---|---|---|
| `SECRET_KEY` | **Yes** | — | HS256 JWT signing key. Minimum 32 characters. Generate with `openssl rand -hex 32`. |
| `ENCRYPTION_KEY` | No | Falls back to `SECRET_KEY` | Separate key for encrypting sensitive data at rest. |
| `APP_BASE_URL` | **Yes** | — | Public URL of the app (e.g. `https://octowatch.example.com`). Used for OAuth callbacks and SAML ACS. |
| `LOG_LEVEL` | No | `INFO` | Logging verbosity: `DEBUG`, `INFO`, `WARNING`, `ERROR`. |
| `ENVIRONMENT` | No | `development` | Deployment environment label. |
| `INGESTION_MODE` | No | `hec` | Ingestion backend: `hec`, `webhook`, `s3`, or `azure_blob`. |
| `INITIAL_ADMIN_LOGINS` | No | `""` | Comma-separated GitHub usernames granted admin on first login. |
| `DETECTION_CONFIDENCE_THRESHOLD` | No | `0.7` | Minimum confidence score (0.0–1.0) for a detection to be persisted. |
| `QUERY_MAX_ROWS` | No | `100000` | Max rows returned by the self-service query engine. |
| `QUERY_TIMEOUT_SECONDS` | No | `30` | Server-side timeout for self-service SQL queries. |

### Database

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | **Yes** | — | PostgreSQL connection string. Must start with `postgresql+asyncpg://` or `postgresql://`. |
| `POSTGRES_USER` | **Yes** | — | PostgreSQL user (used by the `db` container). |
| `POSTGRES_PASSWORD` | **Yes** | — | PostgreSQL password. |
| `POSTGRES_DB` | **Yes** | — | PostgreSQL database name. |

### Cache

| Variable | Required | Default | Description |
|---|---|---|---|
| `VALKEY_URL` | **Yes** | — | Valkey/Redis connection string. Must start with `redis://`, `rediss://`, or `unix://`. |
| `VALKEY_PASSWORD` | **Yes** | — | Valkey authentication password (used by the `valkey` container). |

### HEC Ingestion — when `INGESTION_MODE=hec` (default)

| Variable | Required | Default | Description |
|---|---|---|---|
| `HEC_TOKEN` | No | `""` | Shared secret for HEC authentication. Set in GitHub's audit log stream config as `Authorization: Splunk <token>`. Strongly recommended in production. |

### Object Storage (S3) — when `INGESTION_MODE=s3`

| Variable | Required | Default | Description |
|---|---|---|---|
| `AWS_ACCESS_KEY_ID` | Conditional | `""` | AWS access key. Required when `INGESTION_MODE=s3`. |
| `AWS_SECRET_ACCESS_KEY` | Conditional | `""` | AWS secret key. |
| `AWS_DEFAULT_REGION` | Conditional | `""` | AWS region (e.g. `us-east-1`). |
| `S3_AUDIT_BUCKET` | Conditional | `""` | S3 bucket containing GitHub audit logs. |

### Object Storage (Azure) — when `INGESTION_MODE=azure_blob`

| Variable | Required | Default | Description |
|---|---|---|---|
| `AZURE_STORAGE_CONNECTION_STRING` | Conditional | `""` | Azure Blob Storage connection string. |
| `AZURE_AUDIT_CONTAINER` | Conditional | `""` | Azure Blob container name. |

### GitHub OAuth

| Variable | Required | Default | Description |
|---|---|---|---|
| `GITHUB_CLIENT_ID` | **Yes** | — | OAuth App Client ID. |
| `GITHUB_CLIENT_SECRET` | **Yes** | — | OAuth App Client Secret. |

### GitHub App / Enterprise Sync

| Variable | Required | Default | Description |
|---|---|---|---|
| `GITHUB_APP_ID` | No | `""` | GitHub App ID for Enterprise sync. |
| `GITHUB_APP_PRIVATE_KEY_PATH` | No | `""` | Path to the `.pem` private key file (mounted as a volume). |
| `GITHUB_APP_PRIVATE_KEY_PEM` | No | `""` | Inline PEM private key (alternative to file path). |
| `GITHUB_ENTERPRISE_SLUG` | No | `""` | Enterprise slug (e.g. `acme-corp`). |
| `GITHUB_SYNC_ENABLED` | No | `false` | Enable periodic Enterprise audit log sync. |
| `GITHUB_SYNC_INTERVAL_DAYS` | No | `60` | Sync lookback window in days (60–90). |
| `GITHUB_SYNC_ORGS` | No | `""` | Comma-separated list of organization slugs to sync. |

### GitHub-Backed Detection Rules

| Variable | Required | Default | Description |
|---|---|---|---|
| `GITHUB_RULES_REPO` | No | `""` | Repository for externally managed detection rules (e.g. `org/rules`). |
| `GITHUB_RULES_TOKEN` | No | `""` | PAT for accessing the rules repository. |
| `GITHUB_RULES_BRANCH` | No | `main` | Branch to read/commit rule YAML files. |

### GeoIP Enrichment

| Variable | Required | Default | Description |
|---|---|---|---|
| `GEOIP_DB_PATH` | No | `/app/data/GeoLite2-City.mmdb` | Path to MaxMind GeoLite2 database file. |
| `MAXMIND_LICENSE_KEY` | No | `""` | MaxMind license key for automatic database downloads. |

### SAML / SSO

| Variable | Required | Default | Description |
|---|---|---|---|
| `SAML_IDP_METADATA_URL` | No | `""` | SAML IdP metadata URL for SSO. |
| `SAML_SP_CERT` | No | `""` | SAML Service Provider certificate (PEM). |
| `SAML_SP_KEY` | No | `""` | SAML Service Provider private key (PEM). |

### IdP Integrations (Identity Correlation)

| Variable | Required | Default | Description |
|---|---|---|---|
| `OKTA_ORG_URL` | No | `""` | Okta organization URL (must end in `.okta.com`). |
| `OKTA_API_TOKEN` | No | `""` | Okta API token for user lookups. |
| `AZURE_AD_TENANT_ID` | No | `""` | Microsoft Entra ID (Azure AD) tenant ID. |
| `AZURE_AD_CLIENT_ID` | No | `""` | Entra ID application (client) ID. |
| `AZURE_AD_CLIENT_SECRET` | No | `""` | Entra ID client secret. |
| `GOOGLE_WORKSPACE_DOMAIN` | No | `""` | Google Workspace domain for user lookups. |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | No | `""` | Google service account credentials (JSON string). |

### Notifications

| Variable | Required | Default | Description |
|---|---|---|---|
| `SLACK_BOT_TOKEN` | No | `""` | Slack Bot User OAuth Token for detection alerts. |
| `SMTP_HOST` | No | `""` | SMTP server hostname. |
| `SMTP_PORT` | No | `587` | SMTP server port. |
| `SMTP_USERNAME` | No | `""` | SMTP authentication username. |
| `SMTP_PASSWORD` | No | `""` | SMTP authentication password. |
| `SMTP_FROM_ADDRESS` | No | `""` | Sender email address. |
| `SMTP_USE_TLS` | No | `true` | Use STARTTLS for SMTP connections. |
| `JIRA_URL` | No | `""` | Jira instance URL (HTTPS only). |
| `JIRA_USERNAME` | No | `""` | Jira username or email. |
| `JIRA_API_TOKEN` | No | `""` | Jira API token. |

---

## 9. TLS / HTTPS

### Local development — self-signed certificates

The included `nginx` service uses self-signed certificates for local
development. Generate them as shown in [§3 Quick Start](#step-4--generate-self-signed-tls-certificates).

Your browser will show a certificate warning — this is expected.

### Production — Caddy with automatic Let's Encrypt

For production, replace nginx with [Caddy](https://caddyserver.com/), which
obtains and renews TLS certificates automatically via Let's Encrypt.

Create a `Caddyfile` in the repository root:

```caddyfile
octowatch.example.com {
    # Frontend SPA
    handle /* {
        reverse_proxy frontend:3001
    }

    # API and auth routes
    handle /api/* {
        reverse_proxy api:8000
    }
    handle /auth/* {
        reverse_proxy api:8000
    }

    # Health and readiness probes
    handle /health {
        reverse_proxy api:8000
    }
    handle /ready {
        reverse_proxy api:8000
    }

    # HEC endpoint for GitHub audit log streaming
    handle /services/* {
        reverse_proxy api:8000
    }

    # Security headers
    header {
        X-Frame-Options "DENY"
        X-Content-Type-Options "nosniff"
        Referrer-Policy "strict-origin-when-cross-origin"
        Strict-Transport-Security "max-age=63072000; includeSubDomains; preload"
        Permissions-Policy "camera=(), microphone=(), geolocation=(), payment=()"
    }
}
```

Then use the `docker-compose.prod.yml` override from [§4](#41-create-a-production-compose-override)
which replaces the nginx service with Caddy.

> **Important:** Ensure port 80 and 443 are open on your server — Caddy needs
> both for the ACME HTTP-01 challenge.

### Kubernetes — cert-manager + ingress

The Helm chart's `ingress.yaml` is pre-configured for cert-manager with
`letsencrypt-prod`. Set the `ingress.host` and `ingress.tls.secretName` in
your values file and cert-manager handles the rest.

---

## 10. Network Architecture

OctoWatch uses three-tier network segmentation to isolate traffic by function.
Each Docker network is a bridge network; only services that need to communicate
share a network.

```
                    ┌─────────────────────────────────────────┐
                    │            Internet / Users              │
                    └──────────────────┬──────────────────────┘
                                       │ :80 / :443
                               ┌───────┴───────┐
                               │  nginx/Caddy   │
                               └───┬───────┬───┘
                                   │       │
              ┌────────────────────┘       └────────────────────┐
              │  frontend network                               │  backend network
              │                                                 │
       ┌──────┴──────┐                                   ┌──────┴──────┐
       │  frontend   │                                   │     api     │
       │  (React)    │                                   │  (FastAPI)  │
       └─────────────┘                                   └──────┬──────┘
                                                                │
                                              ┌─────────────────┼─────────────────┐
                                              │                 │                 │
                                     ┌────────┴──┐    ┌────────┴──┐    ┌────────┴──┐
                                     │  worker-  │    │  worker-  │    │  worker-  │
                                     │ ingestion │    │ detection │    │ baseline  │
                                     └────────┬──┘    └────────┬──┘    └────────┬──┘
                                              │                │                │
                                     ┌────────┴──┐    ┌────────┴──────────────┘
                                     │  worker-  │    │
                                     │   sync    │    │  data network
                                     └────────┬──┘    │
                                              │       │
                           ┌──────────────────┼────────────────────────────┐
                           │                  │                           │
                    ┌──────┴──────┐    ┌──────┴───┐                      │
                    │ TimescaleDB │    │  Valkey   │                      │
                    │   (pg16)    │    │  (cache)  │                      │
                    └─────────────┘    └──────────┘                      │
                                                                         │
                                                           ┌─────────────┴┐
                                                           │     beat     │
                                                           │ (scheduler)  │
                                                           └──────────────┘
```

| Network | Services | Purpose |
|---|---|---|
| `frontend` | nginx/Caddy, frontend, api | Browser-facing traffic: serves the SPA and proxies API calls |
| `backend` | api, all workers, beat | Internal application traffic: API dispatches tasks to Celery workers |
| `data` | api, all workers, beat, db, valkey, nginx | Data-plane traffic: database queries, cache operations |

**Key design decisions:**

- The `frontend` container (static React SPA) has **no access** to the data
  network — it cannot reach the database or cache directly.
- Workers communicate with the database and Valkey on the `data` network but
  are not exposed to external traffic.
- nginx/Caddy sits on all three networks because it reverse-proxies to both the
  frontend (on `frontend`) and the API (on `backend`).

---

## 11. Troubleshooting

### Container won't start

```bash
# Check container status and exit codes
docker compose ps -a

# View logs for a specific service
docker compose logs api --tail=100
docker compose logs worker-ingestion --tail=100

# Follow logs in real time
docker compose logs -f api
```

**Common causes:**
- Missing or invalid environment variables — the app validates all config at
  startup and fails fast with a descriptive error.
- `SECRET_KEY` too short — must be at least 32 characters.
- Invalid `DATABASE_URL` — must start with `postgresql+asyncpg://` or `postgresql://`.
- Invalid `VALKEY_URL` — must start with `redis://`, `rediss://`, or `unix://`.

### Database connection refused

The `api` service has `depends_on: db: condition: service_healthy`. If the
database health check hasn't passed yet, the API container waits. Check:

```bash
# Is the database healthy?
docker compose ps db

# Check database logs
docker compose logs db --tail=50

# Test connectivity manually
docker compose exec db pg_isready -U appuser -d audit_logs
```

### Migrations fail

```bash
# Check migration logs
docker compose logs migrate --tail=100

# Run migrations manually for debugging
docker compose run --rm migrate alembic upgrade head
```

### GitHub OAuth callback error

If you see "redirect_uri mismatch" or similar OAuth errors:

1. Verify `APP_BASE_URL` matches the URL your browser uses to access OctoWatch.
2. Verify the OAuth App's **Authorization callback URL** is set to
   `<APP_BASE_URL>/api/auth/github/callback`.
3. Ensure there are no trailing slashes in `APP_BASE_URL`.

### Workers not processing tasks

```bash
# Check worker logs
docker compose logs worker-ingestion --tail=50
docker compose logs worker-detection --tail=50

# Verify Valkey connectivity (Celery broker)
docker compose exec valkey valkey-cli -a "$VALKEY_PASSWORD" ping
# Expected: PONG

# Check Celery queue depths
docker compose exec api celery -A app.celery_app inspect active
```

### HEC not receiving events

```bash
# Test connectivity with a minimal HEC event
curl -sk -X POST https://localhost/services/collector \
  -H "Authorization: Splunk ${HEC_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"event": {"action": "test.event", "actor": "octowatch-test", "org": "test-org"}}'
# Expected: {"text": "Success", "code": 0}

# Check HEC health endpoint
curl -sk https://localhost/services/collector/health
# Expected: {"text": "HEC is healthy", "code": 17}

# Check API logs for auth failures
docker compose logs api --tail=50 | grep "hec\."
```

### "Invalid date" or timezone errors

Ensure TimescaleDB is running in UTC (the default). Do not set `TZ` or
`PGTZ` environment variables on the `db` container.

```bash
docker compose exec db psql -U appuser -d audit_logs -c "SHOW timezone;"
# Expected: UTC
```

### High memory usage

- **TimescaleDB:** Enable compression on hypertables for ~90% storage reduction.
  See the [TimescaleDB compression docs](https://docs.timescale.com/use-timescale/latest/compression/).
- **Workers:** Reduce `-c` (concurrency) flags in the worker commands if
  workers are OOM-killed. The defaults are tuned for a 4-vCPU / 8-GB server.

### Viewing health and readiness

```bash
# Liveness probe (is the API process alive?)
curl -sf http://localhost:8000/health

# Readiness probe (are database and cache connected?)
curl -sf http://localhost:8000/ready
```

Both endpoints are available through the reverse proxy at `/health` and `/ready`.

---

## 12. Zero-Downtime Upgrades

OctoWatch is designed for zero-downtime upgrades when deployed on Kubernetes
with the included Helm chart. The upgrade sequence ensures no requests are
dropped and no tasks are lost.

### Upgrade Sequence

When you run `helm upgrade`, the following happens in order:

1. **Migration Job** (`pre-upgrade` hook, weight `-5`): Alembic runs
   `upgrade head` against the database. All migrations are designed to be
   backwards-compatible — they add columns/tables but never drop or rename
   columns used by the current version.

2. **Rolling Update — API pods**: New pods start alongside old pods. The
   deployment uses `maxSurge: 1, maxUnavailable: 0`, so at least the current
   replica count is always available. A `preStop` hook adds a 5-second delay
   to allow the Ingress controller to drain connections.

3. **Rolling Update — Worker pods**: Workers have a 300-second
   `terminationGracePeriodSeconds`. On SIGTERM, Celery stops accepting new
   tasks but finishes in-progress ones. `task_acks_late: true` and
   `task_reject_on_worker_lost: true` in the Celery config ensure that any
   task not completed before shutdown is automatically re-queued.

### Performing an Upgrade

```bash
# 1. Review what will change
helm diff upgrade audit-log ./helm -n audit-log \
  --set global.image.tag=v1.2.0

# 2. Upgrade (migration runs first, then rolling update)
helm upgrade audit-log ./helm -n audit-log \
  --set global.image.tag=v1.2.0 \
  --wait --timeout 10m

# 3. Verify
kubectl rollout status deploy/octowatch-api -n audit-log
curl -sf https://your-domain/health
curl -sf https://your-domain/ready
```

### Writing Backwards-Compatible Migrations

To ensure zero-downtime, all Alembic migrations must follow these rules:

| ✅ Safe Operations | ❌ Unsafe Operations |
|---|---|
| `ADD COLUMN ... DEFAULT ...` | `DROP COLUMN` (still read by old code) |
| `CREATE TABLE` | `RENAME TABLE` or `RENAME COLUMN` |
| `CREATE INDEX CONCURRENTLY` | `CREATE INDEX` (locks table) |
| `ADD CONSTRAINT ... NOT VALID` | `ALTER COLUMN TYPE` |
| `ALTER TABLE ... VALIDATE CONSTRAINT` (separate migration) | `DROP TABLE` (still read by old code) |

**Two-phase column removal pattern:**

1. **v1.2.0**: Deploy new code that stops reading/writing the column.
2. **v1.3.0**: Add migration to `DROP COLUMN`.

This ensures old pods (v1.1.x) that are still running during the v1.2.0
rollout don't fail.

### Rollback Procedure

```bash
# 1. Roll back Helm release to previous revision
helm rollback audit-log -n audit-log

# 2. Wait for rollout
kubectl rollout status deploy -n audit-log --timeout 5m

# 3. If the rolled-back version needs a schema downgrade:
kubectl exec -n audit-log deploy/octowatch-api -- \
  alembic downgrade <target-revision>

# 4. Verify health
curl -sf https://your-domain/health
```

> **Important**: `helm rollback` does NOT automatically downgrade the database
> schema. If the new version added a migration, and the old version is
> incompatible with the new schema, you must run `alembic downgrade` manually.
> Always test rollback procedures in a staging environment first.

### Worker Task Safety on Restart

The Celery configuration ensures task safety during upgrades:

- **`task_acks_late: true`**: Tasks are acknowledged only after completion,
  not when received. If a worker is killed mid-task, the broker re-delivers
  the message.
- **`task_reject_on_worker_lost: true`**: If the worker process dies
  unexpectedly, the task is rejected and returned to the queue.
- **`terminationGracePeriodSeconds: 300`**: Workers have 5 minutes to finish
  in-progress tasks before Kubernetes sends SIGKILL.
- **`--without-heartbeat`**: Reduces unnecessary traffic during shutdown.

---

## 13. High Availability Configuration

This section describes how to configure OctoWatch for high availability (HA)
in a Kubernetes environment.

### Architecture Overview

```
                    ┌─────────────────────────────────────┐
                    │           Ingress (nginx)            │
                    │    TLS termination, load balancing   │
                    └─────────────┬───────────────────────┘
                                  │
                    ┌─────────────▼───────────────────────┐
                    │       API Deployment (3+ replicas)   │
                    │  HPA: 2–10 replicas by CPU/memory   │
                    │  PDB: minAvailable=1                │
                    └──────┬──────────────┬───────────────┘
                           │              │
              ┌────────────▼──┐    ┌──────▼─────────┐
              │  TimescaleDB  │    │     Valkey      │
              │   (Primary)   │    │  (Sentinel HA)  │
              │   + Replica   │    │                 │
              └───────────────┘    └─────────────────┘
```

### API Layer — Stateless, Horizontally Scalable

The API is fully stateless — all session state is stored in Valkey, all
persistent data in TimescaleDB. This means you can scale the API to any number
of replicas.

**Recommended production configuration:**

```yaml
# values.yaml
api:
  replicaCount: 3   # Minimum 3 replicas for HA
```

The HPA (`hpa-api.yaml`) automatically scales between 2 and 10 replicas based
on CPU (70%) and memory (80%) utilization. The PDB (`pdb-api.yaml`) ensures at
least 1 pod is always available during voluntary disruptions (node maintenance,
upgrades).

**Ingress notes:**
- Sticky sessions are **NOT required** — the API is stateless.
- The Ingress controller handles TLS termination and distributes traffic
  across all ready API pods.
- If using nginx-ingress, the default round-robin load balancing is optimal.

### TimescaleDB — High Availability with Patroni

For production HA, deploy TimescaleDB with Patroni for automatic failover:

1. **Use the TimescaleDB Operator** or the
   [Patroni Helm chart](https://github.com/zalando/patroni) instead of the
   Bitnami PostgreSQL subchart:

   ```yaml
   # values.yaml — disable the built-in PostgreSQL
   postgresql:
     enabled: false
   ```

2. **Configure Patroni** with at least 1 primary + 2 replicas for quorum-based
   failover:

   ```yaml
   patroni:
     replicaCount: 3
     synchronous_mode: true  # Synchronous replication for zero data loss
   ```

3. **Connection string**: Point `DATABASE_URL` to the Patroni service, which
   automatically routes to the current primary:

   ```
   postgresql+asyncpg://app_rw:password@patroni-master:5432/auditlogs?sslmode=require
   ```

**Failover procedure:**

| Step | Action | Command |
|------|--------|---------|
| 1 | Detect primary failure | Patroni auto-detects via health checks |
| 2 | Automatic failover | Patroni promotes a replica (< 30s) |
| 3 | Verify | `patronictl list` shows new primary |
| 4 | OctoWatch reconnects | Automatic via Patroni service DNS |
| 5 | Post-failover | Check `alembic current` on new primary |

> **Backup note**: Point your backup CronJob at the **replica** to avoid
> impacting primary performance.

### Valkey — High Availability with Sentinel

For production HA, deploy Valkey in Sentinel mode:

```yaml
# values.yaml
valkey:
  enabled: true
  architecture: replication    # 1 master + N replicas
  sentinel:
    enabled: true
    quorum: 2
  replica:
    replicaCount: 2
```

Update `VALKEY_URL` to use the Sentinel-aware connection string:

```
redis+sentinel://:password@valkey-sentinel:26379/0/mymaster
```

Celery and the API both support Sentinel-based failover natively via the
`redis` Python library.

### Celery Beat — Exactly-One Constraint

> ⚠ **CRITICAL**: Celery Beat must run as **exactly one instance**. Running
> multiple Beat instances causes duplicate task scheduling.

The Helm chart enforces this by hardcoding `replicas: 1` for the Beat
deployment (the `replicaCount` value is intentionally not exposed).

**Additional safeguards:**

1. **No HPA for Beat**: The Beat deployment does not have a
   HorizontalPodAutoscaler.

2. **Resource limits**: Beat is lightweight — it only schedules tasks, not
   execute them:
   ```yaml
   beat:
     resources:
       requests: { cpu: "50m", memory: "128Mi" }
       limits:   { cpu: "200m", memory: "256Mi" }
   ```

3. **Leader election** (optional, for maximum safety): If you need Beat HA
   (automatic failover if the Beat pod dies), consider using
   [django-celery-beat](https://github.com/celery/django-celery-beat) with a
   database-backed scheduler or [redbeat](https://github.com/sibson/redbeat)
   which uses Valkey-based locking:

   ```bash
   celery -A app.celery_app beat --scheduler=redbeat.RedBeatScheduler
   ```

   This ensures only one Beat instance is active even if multiple pods are
   running.

### Celery Workers — Independent Scaling

Each worker queue is deployed as a separate Kubernetes Deployment, allowing
independent scaling:

| Queue | Default Replicas | Concurrency | Scaling Guide |
|-------|-----------------|-------------|---------------|
| `ingestion` | 1 | 4 | Scale when ingestion lag > 5 min |
| `detection` | 2 | 8 | Scale when detection queue > 500 |
| `baseline` | 1 | 2 | Single replica is fine (idempotent) |
| `notification` | 1 | 4 | Scale if notification delivery is slow |

Workers are stateless and can be scaled freely. The `task_acks_late` setting
ensures no task is lost during scaling events.

### Health Check Summary

| Component | Liveness | Readiness | Notes |
|-----------|----------|-----------|-------|
| API | `GET /health` → 200 | `GET /ready` → 200 (DB+Valkey) | Both on port 8000 |
| Workers | Process alive check | N/A (no HTTP) | Celery handles restarts |
| Beat | Process alive check | N/A | Single replica |
| TimescaleDB | `pg_isready` | Replication lag check | Via Patroni |
| Valkey | `PING` → `PONG` | Sentinel quorum check | Via Sentinel |

### Recommended Production Topology

| Component | Replicas | Anti-Affinity | Notes |
|-----------|----------|---------------|-------|
| API | 3+ (HPA: 2–10) | Spread across nodes | Stateless |
| Ingestion worker | 2 | Spread across nodes | Scale with event volume |
| Detection worker | 2 | Spread across nodes | CPU-bound |
| Baseline worker | 1 | — | I/O-bound, idempotent |
| Beat | 1 | — | Exactly-one constraint |
| TimescaleDB | 3 (Patroni) | Spread across AZs | Synchronous replication |
| Valkey | 3 (Sentinel) | Spread across AZs | Sentinel quorum = 2 |
