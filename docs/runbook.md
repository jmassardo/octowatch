# Audit Log Analyzer — Operations Runbook

**Version**: 1.0  
**Date**: 2026-03-25  
**Audience**: On-call engineers, platform team  
**Related docs**: [docs/architecture.md](architecture.md), [docs/security-and-deployment.md](security-and-deployment.md)

---

## Table of Contents

1. [Docker Compose: First-time Setup](#1-docker-compose-first-time-setup)
2. [Kubernetes/Helm: First-time Install](#2-kuberneteshelm-first-time-install)
3. [Common Operational Tasks](#3-common-operational-tasks)
   - [Check Worker Queue Depth](#31-check-worker-queue-depth)
   - [Manually Trigger Ingestion](#32-manually-trigger-ingestion-for-a-specific-prefix)
   - [Disable a Detection Rule](#33-disable-a-detection-rule)
   - [Rotate the SECRET_KEY](#34-rotate-the-secret_key)
   - [Roll Back a Helm Release](#35-roll-back-a-helm-release)
   - [Backup and Restore TimescaleDB](#36-backup-and-restore-timescaledb)
4. [Observability](#4-observability)
5. [Incident Response](#5-incident-response)
6. [SLOs and Error Budgets](#6-slos-and-error-budgets)

---

## 1. Docker Compose: First-time Setup

### Prerequisites

- Docker Engine 24+ with Docker Compose v2
- `openssl` available on the host
- TLS certificate/key pair (self-signed OK for dev; use Let's Encrypt for production)

### Step 1 — Copy and configure environment

```bash
cd /path/to/audit-log-analyzer

# Copy the example env file
cp backend/.env.example .env   # create this file if it doesn't exist

# Edit the file and fill in all required secrets
# Required variables (no defaults):
#   SECRET_KEY            — JWT signing key
#   POSTGRES_USER         — PostgreSQL admin username
#   POSTGRES_PASSWORD     — PostgreSQL admin password
#   POSTGRES_DB           — PostgreSQL database name
#   DATABASE_URL          — Full asyncpg URL: postgresql+asyncpg://user:pass@db:5432/dbname
#   VALKEY_URL            — redis://:password@valkey:6379/0
#   VALKEY_PASSWORD       — Valkey auth password
#   MINIO_ROOT_USER       — MinIO root user
#   MINIO_ROOT_PASSWORD   — MinIO root password
#   MINIO_AUDIT_BUCKET    — Name of the audit log bucket (e.g. audit-logs)
#   MINIO_INGEST_USER     — Read-only MinIO service account username
#   MINIO_INGEST_PASSWORD — Read-only MinIO service account password
#   GITHUB_CLIENT_ID      — GitHub OAuth App Client ID
#   GITHUB_CLIENT_SECRET  — GitHub OAuth App Client Secret
#   GITHUB_RULES_REPO     — GitHub repo for detection rule YAML files (optional, e.g. my-org/audit-rules)
#   GITHUB_RULES_TOKEN    — GitHub PAT with contents:write on GITHUB_RULES_REPO (optional)
$EDITOR .env
```

### Step 2 — Generate TLS certificates (development only)

```bash
mkdir -p nginx/ssl
openssl req -x509 -nodes -newkey rsa:4096 -days 365 \
  -keyout nginx/ssl/key.pem \
  -out nginx/ssl/cert.pem \
  -subj "/CN=localhost"
```

> **Production**: Replace with a valid certificate from Let's Encrypt or your PKI.

### Step 2b — Download GeoIP database (required for impossible travel detection)

The GeoLite2-City database must be downloaded manually from MaxMind. A free account is required.

```bash
# 1. Sign up at https://www.maxmind.com/en/geolite2/signup
# 2. Generate a license key at: Account > Manage License Keys
# 3. Download the database:
mkdir -p backend/data
curl -sSL "https://download.maxmind.com/geoip/databases/GeoLite2-City/download?suffix=tar.gz" \
  -u "YOUR_ACCOUNT_ID:YOUR_LICENSE_KEY" \
  | tar -xz --strip-components=1 -C backend/data/ "*.mmdb"
```

Set `GEOIP_DB_PATH=/app/data/GeoLite2-City.mmdb` in your `.env` and mount the file into the container via a volume. Example addition to your `.env`:
```
GEOIP_DB_PATH=/app/data/GeoLite2-City.mmdb
MAXMIND_LICENSE_KEY=YOUR_LICENSE_KEY
```

> **Note**: If `GEOIP_DB_PATH` is missing or the file does not exist, GeoIP enrichment and impossible travel detection are **silently disabled** — other detection rules still run normally.

### Step 3 — Start infrastructure services and wait for health checks

```bash
docker compose up -d db valkey minio
echo "Waiting for services to be healthy..."
sleep 15

# Verify all three are healthy
docker compose ps db valkey minio
```

### Step 4 — Run database migrations

```bash
docker compose run --rm migrate
# Expected output: INFO  [alembic.runtime.migration] Running upgrade ... -> ..., ...
```

### Step 5 — Start all services

```bash
docker compose up -d
```

### Step 6 — Verify health

```bash
# Wait for nginx and api to start
sleep 10

# Liveness check
curl -sk https://localhost/health | jq .
# Expected: {"status": "ok", "version": "..."}

# Readiness check (returns 503 until DB+Valkey are ready)
curl -sk https://localhost/ready | jq .
# Expected: {"status": "ready", "dependencies": {...}}

# Check all containers are running
docker compose ps
```

### Step 6 — Access MinIO console (optional)

The MinIO console is bound to localhost only (127.0.0.1:9001). Open in browser: http://localhost:9001

---

## 2. Kubernetes/Helm: First-time Install

### Prerequisites

- `kubectl` configured for your cluster
- `helm` v3.14+
- Cluster has a working `nginx` ingress controller and `cert-manager` (optional)

### Step 1 — Add Helm repositories

```bash
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo add minio   https://charts.min.io/
helm repo update
```

### Step 2 — Create namespace

```bash
kubectl create namespace audit-log
```

### Step 3 — Create secrets

> **Production recommendation**: Use [External Secrets Operator](https://external-secrets.io) (pulling from AWS Secrets Manager / Vault) or [Sealed Secrets](https://github.com/bitnami-labs/sealed-secrets) for GitOps workflows. The `kubectl create secret` approach below is suitable for initial setup only.

```bash
SECRET_KEY=$(openssl rand -hex 32)
POSTGRES_PASSWORD=$(openssl rand -hex 16)
VALKEY_PASSWORD=$(openssl rand -hex 16)
MINIO_ROOT_PASSWORD=$(openssl rand -hex 16)
MINIO_INGEST_PASSWORD=$(openssl rand -hex 16)

# Application secrets
kubectl create secret generic audit-log-analyzer-secrets \
  --namespace audit-log \
  --from-literal=secret-key="${SECRET_KEY}" \
  --from-literal=database-url="postgresql+asyncpg://app_rw:${POSTGRES_PASSWORD}@release-postgresql:5432/auditlogs" \
  --from-literal=valkey-url="redis://:${VALKEY_PASSWORD}@release-valkey-master:6379/0" \
  --from-literal=github-client-id="YOUR_GITHUB_CLIENT_ID" \
  --from-literal=github-client-secret="YOUR_GITHUB_CLIENT_SECRET" \
  --from-literal=github-rules-token="" \
  --from-literal=minio-root-user="minioadmin" \
  --from-literal=minio-root-password="${MINIO_ROOT_PASSWORD}" \
  --from-literal=minio-ingest-user="ingest" \
  --from-literal=minio-ingest-password="${MINIO_INGEST_PASSWORD}"

# Database password secret (consumed by Bitnami PostgreSQL subchart)
kubectl create secret generic audit-log-analyzer-db-secret \
  --namespace audit-log \
  --from-literal=postgres-password="${POSTGRES_PASSWORD}" \
  --from-literal=app-password="${POSTGRES_PASSWORD}"

# Valkey password secret (consumed by Bitnami Valkey subchart)
kubectl create secret generic audit-log-analyzer-valkey-secret \
  --namespace audit-log \
  --from-literal=valkey-password="${VALKEY_PASSWORD}"
```

### Step 4 — Install the chart

```bash
# Update chart dependencies
helm dependency update helm/

# Dry-run first
helm install audit-log ./helm \
  --namespace audit-log \
  --values helm/values.yaml \
  --set global.image.tag=v0.1.0 \
  --dry-run --debug 2>&1 | head -80

# Install for real
helm install audit-log ./helm \
  --namespace audit-log \
  --values helm/values.yaml \
  --set global.image.tag=v0.1.0
```

### Step 5 — Verify deployment

```bash
# Watch pods come up
kubectl get pods -n audit-log -w

# Verify all deployments are ready
kubectl get deployments -n audit-log

# Check the migration job completed successfully
kubectl get jobs -n audit-log

# Check health via ingress (if configured)
curl https://your-domain.example.com/health

# Check readiness
curl https://your-domain.example.com/ready
```

---

## 3. Common Operational Tasks

### 3.1 Check Worker Queue Depth

**Docker Compose:**

```bash
# Using valkey-cli (via Docker)
docker compose exec valkey valkey-cli -a "${VALKEY_PASSWORD}" \
  LLEN celery

# Check specific queue depth
for queue in ingestion detection baseline; do
  depth=$(docker compose exec -T valkey valkey-cli -a "${VALKEY_PASSWORD}" LLEN "${queue}")
  echo "Queue '${queue}': ${depth} tasks"
done

# Using Celery Flower (start ad-hoc)
docker compose run --rm -p 5555:5555 \
  -e DATABASE_URL="${DATABASE_URL}" \
  -e VALKEY_URL="${VALKEY_URL}" \
  worker-detection \
  celery -A app.celery_app flower --port=5555
# Then open http://localhost:5555
```

**Kubernetes:**

```bash
# Port-forward to Valkey
kubectl port-forward -n audit-log svc/release-valkey-master 6379:6379 &

# Check queue depths (requires valkey-cli installed locally)
for queue in ingestion detection baseline; do
  depth=$(valkey-cli -a "${VALKEY_PASSWORD}" LLEN "${queue}" 2>/dev/null || echo "N/A")
  echo "Queue '${queue}': ${depth} tasks"
done

kill %1  # stop port-forward
```

> **Alert threshold**: Page if any queue exceeds 1,000 tasks for more than 5 minutes.

---

### 3.2 Manually Trigger Ingestion for a Specific S3 Prefix

Use this to reprocess a time range or failed batch.

**Docker Compose:**

```bash
docker compose exec api python -c "
from app.celery_app import celery_app
from app.workers.ingestion.minio_worker import ingest_prefix

# Trigger ingestion for a specific date prefix
result = celery_app.send_task(
    'app.workers.ingestion.minio_worker.ingest_prefix',
    kwargs={'prefix': '2026/03/25/', 'bucket': 'audit-logs'},
    queue='ingestion'
)
print(f'Task ID: {result.id}')
"
```

**Kubernetes:**

```bash
kubectl exec -n audit-log \
  deploy/audit-log-analyzer-worker-ingestion \
  -- python -c "
from app.celery_app import celery_app
result = celery_app.send_task(
    'app.workers.ingestion.minio_worker.ingest_prefix',
    kwargs={'prefix': '2026/03/25/', 'bucket': 'audit-logs'},
    queue='ingestion'
)
print(f'Task ID: {result.id}')
"
```

---

### 3.3 Disable a Detection Rule

Detection rules are stored as JSON in Gitea and cached in Valkey. To disable a rule without deleting it:

**Via API (recommended):**

```bash
# Authenticate first to get a JWT
TOKEN=$(curl -s -X POST https://your-domain/auth/login \
  -H "Content-Type: application/json" \
  -d '{"code":"..."}' | jq -r .access_token)

# List rules to find the rule ID
curl -s https://your-domain/api/rules \
  -H "Authorization: Bearer ${TOKEN}" | jq '.[] | {id, name, enabled}'

# Disable rule by ID
curl -s -X PATCH https://your-domain/api/rules/{rule_id} \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

**Requires `rule_admin` or `sys_admin` role.**

---

### 3.4 Rotate the SECRET_KEY

`SECRET_KEY` is used for JWT signing. Rotating it invalidates all active sessions.

1. **Generate a new key:**
   ```bash
   NEW_KEY=$(openssl rand -hex 32)
   echo "New SECRET_KEY: ${NEW_KEY}"
   ```

2. **Update the secret (Docker Compose):**
   ```bash
   # Edit .env and update SECRET_KEY=<new value>
   $EDITOR .env
   ```

3. **Update the secret (Kubernetes):**
   ```bash
   kubectl patch secret audit-log-analyzer-secrets -n audit-log \
     --type=merge \
     -p "{\"stringData\":{\"secret-key\":\"${NEW_KEY}\"}}"
   ```

4. **Perform a rolling restart of all services that use the key:**

   **Docker Compose:**
   ```bash
   docker compose restart api worker-ingestion worker-detection worker-baseline beat
   ```

   **Kubernetes:**
   ```bash
   for deploy in api worker-ingestion worker-detection worker-baseline beat; do
     kubectl rollout restart deploy/audit-log-analyzer-${deploy} -n audit-log
   done
   # Wait for all rollouts to complete
   kubectl rollout status deploy -n audit-log --timeout=5m
   ```

5. **Verify:** All users will need to re-authenticate. Check the health endpoint returns 200:
   ```bash
   curl -f https://your-domain/health
   ```

---

### 3.5 Roll Back a Helm Release

```bash
# View release history
helm history audit-log -n audit-log

# Roll back to the previous revision
helm rollback audit-log -n audit-log

# Roll back to a specific revision number
helm rollback audit-log 3 -n audit-log

# Verify the rollback
kubectl get pods -n audit-log -w
curl -f https://your-domain/health
```

> **Note**: Helm rollback does NOT revert database migrations. If the rolled-back version is incompatible with the current schema, additional steps may be required. Always test rollback procedures in staging.

---

### 3.6 Backup and Restore TimescaleDB

#### Backup

```bash
# Docker Compose: pg_dump with compression
docker compose exec db pg_dump \
  -U "${POSTGRES_USER}" \
  -d "${POSTGRES_DB}" \
  --format=custom \
  --compress=9 \
  --file=/tmp/backup-$(date +%Y%m%d-%H%M%S).dump

# Copy backup out of container
docker compose cp db:/tmp/backup-*.dump ./backups/

# Kubernetes: port-forward and dump
kubectl port-forward -n audit-log svc/release-postgresql 5432:5432 &
pg_dump \
  --host=localhost \
  --username=app_rw \
  --dbname=auditlogs \
  --format=custom \
  --compress=9 \
  --file=backup-$(date +%Y%m%d-%H%M%S).dump
kill %1
```

> **TimescaleDB note**: Include `--load-via-partition-root` flag when restoring to TimescaleDB hypertables. For continuous aggregates, drop and recreate them after restore.

#### Restore

```bash
# Docker Compose: stop API first to prevent writes during restore
docker compose stop api worker-ingestion worker-detection worker-baseline beat

docker compose exec -T db pg_restore \
  --host=localhost \
  --username="${POSTGRES_USER}" \
  --dbname="${POSTGRES_DB}" \
  --no-owner \
  --no-privileges \
  --verbose \
  /tmp/backup-YYYYMMDD-HHMMSS.dump

docker compose start api worker-ingestion worker-detection worker-baseline beat
```

---

## 4. Observability

### Log Locations

| Environment | Service | Command |
|-------------|---------|---------|
| Docker Compose | API | `docker compose logs -f api` |
| Docker Compose | Workers | `docker compose logs -f worker-ingestion worker-detection worker-baseline` |
| Docker Compose | Beat | `docker compose logs -f beat` |
| Docker Compose | All | `docker compose logs -f --tail=100` |
| Kubernetes | API | `kubectl logs -f -n audit-log deploy/audit-log-analyzer-api` |
| Kubernetes | Detection worker | `kubectl logs -f -n audit-log deploy/audit-log-analyzer-worker-detection` |
| Kubernetes | Beat | `kubectl logs -f -n audit-log deploy/audit-log-analyzer-beat` |

All services emit structured JSON logs via `structlog`. Key fields:
- `event` — log message
- `level` — DEBUG/INFO/WARNING/ERROR
- `timestamp` — ISO 8601
- `request_id` — UUID tied to HTTP request (API only)
- `task_id` — Celery task UUID (workers only)

### Health Check URLs

| Endpoint | Method | Expected | Purpose |
|----------|--------|----------|---------|
| `/health` | GET | `200 {"status": "ok"}` | Liveness — always 200 if process is alive |
| `/ready`  | GET | `200 {"status": "ready"}` or `503` | Readiness — 503 if DB/Valkey/Gitea unreachable |

### Key Metrics to Alert On

| Metric | Threshold | Action |
|--------|-----------|--------|
| Celery queue depth (any queue) | > 1,000 tasks for > 5 min | Scale up the relevant worker |
| API p99 latency | > 2,000 ms | Investigate slow queries; scale API replicas |
| API 5xx error rate | > 1% over 5 min | Check logs; escalate to SEV2 |
| DB connection pool exhaustion | `pool_timeout` errors in logs | Increase `SQLALCHEMY_POOL_SIZE` or add connection pooler |
| Disk usage (TimescaleDB) | > 80% | Enable TimescaleDB compression; add storage |
| Detection worker memory | > 1.8 GiB per pod | Check for memory leak; restart pod |
| MinIO storage usage | > 80% | Archive or delete old `.json.gz` files |

### Valkey (Session / Dedup) Health

```bash
# Docker Compose
docker compose exec valkey valkey-cli -a "${VALKEY_PASSWORD}" INFO server | grep uptime
docker compose exec valkey valkey-cli -a "${VALKEY_PASSWORD}" INFO memory | grep used_memory_human

# Kubernetes
kubectl exec -n audit-log deploy/release-valkey-master -- \
  valkey-cli -a "${VALKEY_PASSWORD}" INFO memory
```

---

## 5. Incident Response

### Severity Classification

| Level | Condition | Response Time | Escalation |
|-------|-----------|---------------|------------|
| SEV1 | Complete service outage (all `/health` checks failing) | < 15 min | Immediate exec notification |
| SEV2 | Major feature unavailable (ingestion stopped, no detections firing) | < 30 min | Team lead notification |
| SEV3 | Degraded performance (high latency, queues backing up) | < 2 hours | Next standup |
| SEV4 | Minor issues (single worker restart needed, cosmetic bugs) | < 1 business day | Standard ticket |

### Rollback Decision Criteria

Initiate rollback if **any** of the following are true:
- API error rate > 5% sustained for > 2 minutes
- `/ready` returns 503 after deployment
- Database migration failed or left schema in inconsistent state
- Security incident or credential exposure detected

### Recovery Steps (Kubernetes)

```bash
# 1. Roll back Helm release
helm rollback audit-log -n audit-log

# 2. Verify pods are rolling back
kubectl get pods -n audit-log -w

# 3. Verify health after rollback
kubectl exec -n audit-log deploy/audit-log-analyzer-api -- \
  curl -sf http://localhost:8000/health

# 4. Check error rates have dropped
kubectl logs -n audit-log deploy/audit-log-analyzer-api --since=5m | \
  grep -c '"level":"error"'
```

---

## 6. SLOs and Error Budgets

| SLI | SLO Target | Measurement |
|-----|-----------|-------------|
| API availability | 99.9% (43.8 min downtime/month) | `successful_requests / total_requests` over a rolling 30-day window |
| API p95 latency | < 500 ms | Measured at the nginx access log level |
| API p99 latency | < 2,000 ms | Measured at the nginx access log level |
| Ingestion lag | < 5 min end-to-end | Time from MinIO PUT event to event stored in DB |
| Detection freshness | < 2 min | Time from event ingest to detection rule evaluation |

### Error Budget Policy

- **0–25% consumed**: Normal operations; continue shipping features
- **25–75% consumed**: Review change velocity; prioritize reliability work
- **75–100% consumed**: Freeze non-critical deployments; reliability work takes priority
- **Budget exhausted**: All deployments require explicit sign-off from on-call lead

Track monthly error budget status during the weekly incident review meeting.
