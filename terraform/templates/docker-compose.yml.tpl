version: "3.9"

# ---------------------------------------------------------------------------
# Shared environment variables consumed by api, workers, and beat.
# Referenced below via <<: *app-env to avoid repetition.
# See docs/security-and-deployment.md Section 2 for full variable reference.
# ---------------------------------------------------------------------------
x-app-env: &app-env
  DATABASE_URL: $${DATABASE_URL}
  VALKEY_URL: $${VALKEY_URL}
  SECRET_KEY: $${SECRET_KEY}
  ENCRYPTION_KEY: $${ENCRYPTION_KEY:-}
  GITHUB_CLIENT_ID: $${GITHUB_CLIENT_ID}
  GITHUB_CLIENT_SECRET: $${GITHUB_CLIENT_SECRET}
  GITHUB_RULES_REPO: $${GITHUB_RULES_REPO}
  GITHUB_RULES_TOKEN: $${GITHUB_RULES_TOKEN}
  GITHUB_RULES_BRANCH: $${GITHUB_RULES_BRANCH:-main}
  LOG_LEVEL: $${LOG_LEVEL:-INFO}
  GEOIP_DB_PATH: $${GEOIP_DB_PATH:-/app/data/GeoLite2-City.mmdb}
  APP_BASE_URL: $${APP_BASE_URL:-https://localhost}

networks:
  # Segmented networks — least-privilege connectivity between services.
  # frontend: nginx <-> frontend SPA container
  # backend:  nginx <-> api; workers & beat coordinate via api
  # data:     api/workers/beat <-> db, valkey
  frontend:
    driver: bridge
  backend:
    driver: bridge
  data:
    driver: bridge

# ---------------------------------------------------------------------------
# Volumes: bind-mounted to /mnt/octowatch-data on the Azure data disk.
# The data disk is formatted as ext4 and mounted by cloud-init at boot.
# ---------------------------------------------------------------------------
volumes:
  pg_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /mnt/octowatch-data/pg_data
  valkey_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /mnt/octowatch-data/valkey_data

services:

  # ---------------------------------------------------------------------------
  # PostgreSQL 16 + TimescaleDB 2.14
  # events table is a TimescaleDB hypertable (weekly chunks).
  # ---------------------------------------------------------------------------
  db:
    image: timescale/timescaledb:2.25.1-pg16
    environment:
      POSTGRES_USER: $${POSTGRES_USER}
      POSTGRES_PASSWORD: $${POSTGRES_PASSWORD}
      POSTGRES_DB: $${POSTGRES_DB}
    volumes:
      - pg_data:/var/lib/postgresql/data
    networks:
      - data
    # No ports exposed to host; application connects via internal network.
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $$$${POSTGRES_USER} -d $$$${POSTGRES_DB}"]
      interval: 10s
      timeout: 5s
      retries: 6
      start_period: 30s
    restart: unless-stopped

  # ---------------------------------------------------------------------------
  # Valkey 7.2 (BSD-3 Redis-compatible)
  # Used as: Celery broker, JWT session store, dedup bloom filter,
  #          RBAC team cache, Celery task queues.
  # ---------------------------------------------------------------------------
  valkey:
    image: valkey/valkey:9.0.3-alpine
    command:
      - valkey-server
      - --requirepass
      - $${VALKEY_PASSWORD}
      - --appendonly
      - "yes"
    volumes:
      - valkey_data:/data
    networks:
      - data
    # No ports exposed to host.
    healthcheck:
      test: ["CMD", "valkey-cli", "-a", "$${VALKEY_PASSWORD}", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 10s
    restart: unless-stopped

  # ---------------------------------------------------------------------------
  # migrate - runs Alembic schema migrations before the API starts.
  # Uses condition: service_completed_successfully so the api service waits
  # until this exits 0. On failure (exit non-zero), Compose logs the error
  # and the api service does not start.
  # restart: on-failure retries up to 3 times if db is temporarily unavailable.
  # ---------------------------------------------------------------------------
  migrate:
    image: ghcr.io/${ghcr_owner}/octowatch-api:${ghcr_image_tag}
    command: ["alembic", "upgrade", "head"]
    environment:
      DATABASE_URL: $${DATABASE_URL}
    networks:
      - data
    depends_on:
      db:
        condition: service_healthy
    restart: on-failure

  # ---------------------------------------------------------------------------
  # api - FastAPI 0.111 application server (uvicorn)
  # All secrets injected via environment. No hardcoded credentials.
  # For horizontal scaling, run: docker compose up --scale api=3
  # Update nginx upstream block to list all api instances if scaling manually.
  # ---------------------------------------------------------------------------
  api:
    image: ghcr.io/${ghcr_owner}/octowatch-api:${ghcr_image_tag}
    command: ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
    environment:
      <<: *app-env
      # Ingestion mode
      INGESTION_MODE: $${INGESTION_MODE:-hec}
      # SAML - optional; leave blank to disable SAML auth
      SAML_SP_CERT: $${SAML_SP_CERT:-}
      SAML_SP_KEY: $${SAML_SP_KEY:-}
      SAML_IDP_METADATA_URL: $${SAML_IDP_METADATA_URL:-}
      # MaxMind GeoIP license (used at startup to fetch mmdb if not present)
      MAXMIND_LICENSE_KEY: $${MAXMIND_LICENSE_KEY:-}
      # Query engine limits
      DETECTION_CONFIDENCE_THRESHOLD: $${DETECTION_CONFIDENCE_THRESHOLD:-0.7}
      QUERY_MAX_ROWS: $${QUERY_MAX_ROWS:-100000}
      QUERY_TIMEOUT_SECONDS: $${QUERY_TIMEOUT_SECONDS:-30}
      # GitHub App - Enterprise Sync config (optional - app starts without these)
      GITHUB_APP_ID: $${GITHUB_APP_ID:-}
      GITHUB_APP_PRIVATE_KEY_PATH: $${GITHUB_APP_PRIVATE_KEY_PATH:+/app/secrets/github-app-key.pem}
      GITHUB_ENTERPRISE_SLUG: $${GITHUB_ENTERPRISE_SLUG:-}
      GITHUB_SYNC_ENABLED: $${GITHUB_SYNC_ENABLED:-false}
      GITHUB_SYNC_INTERVAL_DAYS: $${GITHUB_SYNC_INTERVAL_DAYS:-60}
      GITHUB_SYNC_ORGS: $${GITHUB_SYNC_ORGS:-}
    volumes:
      - $${GITHUB_APP_PRIVATE_KEY_PATH:-/dev/null}:/app/secrets/github-app-key.pem:ro
    networks:
      - backend
      - data
    # No ports exposed to host; nginx proxies /api/ -> api:8000
    depends_on:
      db:
        condition: service_healthy
      valkey:
        condition: service_healthy
      migrate:
        condition: service_completed_successfully
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    restart: unless-stopped

  # ---------------------------------------------------------------------------
  # worker-ingestion - Celery worker for ingestion queue
  # Concurrency: 4 (one thread per concurrent source; bounded to avoid OOM
  # from parallel gzip decompression of large audit log files).
  # ---------------------------------------------------------------------------
  worker-ingestion:
    image: ghcr.io/${ghcr_owner}/octowatch-worker:${ghcr_image_tag}
    command: ["celery", "-A", "app.celery_app", "worker", "-Q", "ingestion", "-c", "4", "--loglevel", "$${LOG_LEVEL:-INFO}"]
    environment:
      <<: *app-env
      INGESTION_MODE: $${INGESTION_MODE:-hec}
      # AWS S3 credentials - only required when INGESTION_MODE=s3
      AWS_ACCESS_KEY_ID: $${AWS_ACCESS_KEY_ID:-}
      AWS_SECRET_ACCESS_KEY: $${AWS_SECRET_ACCESS_KEY:-}
      AWS_DEFAULT_REGION: $${AWS_DEFAULT_REGION:-}
      S3_AUDIT_BUCKET: $${S3_AUDIT_BUCKET:-}
      # Azure Blob credentials - only required when INGESTION_MODE=azure_blob
      AZURE_STORAGE_CONNECTION_STRING: $${AZURE_STORAGE_CONNECTION_STRING:-}
      AZURE_AUDIT_CONTAINER: $${AZURE_AUDIT_CONTAINER:-}
      MAXMIND_LICENSE_KEY: $${MAXMIND_LICENSE_KEY:-}
    networks:
      - backend
      - data
    depends_on:
      db:
        condition: service_healthy
      valkey:
        condition: service_healthy
    restart: unless-stopped

  # ---------------------------------------------------------------------------
  # worker-detection - Celery worker for detection queue
  # Concurrency: 8 (detection rule evaluation is CPU-bound; 8 processes
  # saturates a 4-core host while leaving headroom for other services).
  # Includes all IdP enrichment, notification, and ticketing credentials.
  # ---------------------------------------------------------------------------
  worker-detection:
    image: ghcr.io/${ghcr_owner}/octowatch-worker:${ghcr_image_tag}
    command: ["celery", "-A", "app.celery_app", "worker", "-Q", "detection", "-c", "8", "--loglevel", "$${LOG_LEVEL:-INFO}"]
    environment:
      <<: *app-env
      DETECTION_CONFIDENCE_THRESHOLD: $${DETECTION_CONFIDENCE_THRESHOLD:-0.7}
      # IdP enrichment - Okta
      OKTA_ORG_URL: $${OKTA_ORG_URL:-}
      OKTA_API_TOKEN: $${OKTA_API_TOKEN:-}
      # IdP enrichment - Azure AD / Entra
      AZURE_AD_TENANT_ID: $${AZURE_AD_TENANT_ID:-}
      AZURE_AD_CLIENT_ID: $${AZURE_AD_CLIENT_ID:-}
      AZURE_AD_CLIENT_SECRET: $${AZURE_AD_CLIENT_SECRET:-}
      # IdP enrichment - Google Workspace
      GOOGLE_WORKSPACE_DOMAIN: $${GOOGLE_WORKSPACE_DOMAIN:-}
      GOOGLE_SERVICE_ACCOUNT_JSON: $${GOOGLE_SERVICE_ACCOUNT_JSON:-}
      # Notifications
      SLACK_BOT_TOKEN: $${SLACK_BOT_TOKEN:-}
      SMTP_HOST: $${SMTP_HOST:-}
      SMTP_PORT: $${SMTP_PORT:-587}
      SMTP_USERNAME: $${SMTP_USERNAME:-}
      SMTP_PASSWORD: $${SMTP_PASSWORD:-}
      SMTP_FROM_ADDRESS: $${SMTP_FROM_ADDRESS:-}
      # Ticketing
      JIRA_URL: $${JIRA_URL:-}
      JIRA_USERNAME: $${JIRA_USERNAME:-}
      JIRA_API_TOKEN: $${JIRA_API_TOKEN:-}
    networks:
      - backend
      - data
    depends_on:
      db:
        condition: service_healthy
      valkey:
        condition: service_healthy
    restart: unless-stopped

  # ---------------------------------------------------------------------------
  # worker-notification - Celery worker for notification queue
  # Concurrency: 2 (low volume; notifications are dispatched per-detection
  # after the detection pipeline completes).
  # ---------------------------------------------------------------------------
  worker-notification:
    image: ghcr.io/${ghcr_owner}/octowatch-worker:${ghcr_image_tag}
    command: ["celery", "-A", "app.celery_app", "worker", "-Q", "notification", "-c", "2", "--loglevel", "$${LOG_LEVEL:-INFO}"]
    environment:
      <<: *app-env
      SLACK_BOT_TOKEN: $${SLACK_BOT_TOKEN:-}
      SMTP_HOST: $${SMTP_HOST:-}
      SMTP_PORT: $${SMTP_PORT:-587}
      SMTP_USERNAME: $${SMTP_USERNAME:-}
      SMTP_PASSWORD: $${SMTP_PASSWORD:-}
      SMTP_FROM_ADDRESS: $${SMTP_FROM_ADDRESS:-}
    networks:
      - backend
      - data
    depends_on:
      db:
        condition: service_healthy
      valkey:
        condition: service_healthy
    restart: unless-stopped

  # ---------------------------------------------------------------------------
  # worker-baseline - Celery worker for behavioral baseline queue
  # Concurrency: 2 (baseline recomputation is I/O-bound and runs hourly;
  # low concurrency prevents it from competing with detection workers).
  # ---------------------------------------------------------------------------
  worker-baseline:
    image: ghcr.io/${ghcr_owner}/octowatch-worker:${ghcr_image_tag}
    command: ["celery", "-A", "app.celery_app", "worker", "-Q", "baseline", "-c", "2", "--loglevel", "$${LOG_LEVEL:-INFO}"]
    environment:
      <<: *app-env
    networks:
      - backend
      - data
    depends_on:
      db:
        condition: service_healthy
      valkey:
        condition: service_healthy
    restart: unless-stopped

  # ---------------------------------------------------------------------------
  # worker-sync - Celery worker for GitHub Enterprise Sync queue
  # Concurrency: 4 (GitHub API rate limits constrain throughput more than
  # local resources; 4 workers allow parallel sync of independent orgs).
  # ---------------------------------------------------------------------------
  worker-sync:
    image: ghcr.io/${ghcr_owner}/octowatch-worker:${ghcr_image_tag}
    command: ["celery", "-A", "app.celery_app", "worker", "-Q", "github_sync", "--pool=solo", "--loglevel", "$${LOG_LEVEL:-INFO}"]
    environment:
      <<: *app-env
      INGESTION_MODE: $${INGESTION_MODE:-hec}
      GITHUB_APP_ID: $${GITHUB_APP_ID:-}
      GITHUB_APP_PRIVATE_KEY_PATH: $${GITHUB_APP_PRIVATE_KEY_PATH:+/app/secrets/github-app-key.pem}
      GITHUB_ENTERPRISE_SLUG: $${GITHUB_ENTERPRISE_SLUG:-}
      GITHUB_SYNC_ENABLED: $${GITHUB_SYNC_ENABLED:-false}
      GITHUB_SYNC_INTERVAL_DAYS: $${GITHUB_SYNC_INTERVAL_DAYS:-60}
      GITHUB_SYNC_ORGS: $${GITHUB_SYNC_ORGS:-}
    volumes:
      - $${GITHUB_APP_PRIVATE_KEY_PATH:-/dev/null}:/app/secrets/github-app-key.pem:ro
    networks:
      - backend
      - data
    depends_on:
      db:
        condition: service_healthy
      valkey:
        condition: service_healthy
    restart: unless-stopped

  # ---------------------------------------------------------------------------
  # beat - Celery Beat scheduler
  # CRITICAL: Only ONE beat instance must ever run. Running multiple causes
  # duplicate task scheduling (double ingestion, double baseline recomputation).
  # PersistentScheduler stores the schedule state in /tmp/celerybeat-schedule.
  # ---------------------------------------------------------------------------
  beat:
    image: ghcr.io/${ghcr_owner}/octowatch-worker:${ghcr_image_tag}
    command: ["celery", "-A", "app.celery_app", "beat", "--scheduler", "celery.beat:PersistentScheduler", "--loglevel", "$${LOG_LEVEL:-INFO}"]
    environment:
      <<: *app-env
    networks:
      - backend
      - data
    depends_on:
      valkey:
        condition: service_healthy
    restart: unless-stopped

  # ---------------------------------------------------------------------------
  # frontend - React 18 + Vite production build served by a static HTTP server
  # Not exposed directly; nginx proxies / -> frontend:3001
  # ---------------------------------------------------------------------------
  frontend:
    image: ghcr.io/${ghcr_owner}/octowatch-frontend:${ghcr_image_tag}
    networks:
      - frontend
    depends_on:
      - api
    restart: unless-stopped

  # ---------------------------------------------------------------------------
  # nginx 1.28 - TLS termination and reverse proxy
  # Proxies: /api/  -> api:8000
  #          /      -> frontend:3001
  # HTTP -> HTTPS redirect enforced. HSTS header applied.
  # TLS certificates are mounted from /opt/octowatch/ssl on the host.
  # ---------------------------------------------------------------------------
  nginx:
    image: nginx:1.28-alpine
    ports:
      # Both ports exposed to host - nginx is the only external entry point
      - "80:80"
      - "443:443"
    volumes:
      # nginx config - read from absolute host path (managed by cloud-init)
      - /opt/octowatch/nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      # TLS certs - populated by cloud-init (self-signed or Let's Encrypt)
      - /opt/octowatch/ssl:/etc/nginx/ssl:ro
      # ACME challenge root for Let's Encrypt HTTP-01 validation
      - /opt/octowatch/certbot-webroot:/var/www/certbot:ro
    networks:
      - frontend
      - backend
      - data
    depends_on:
      api:
        condition: service_healthy
      frontend:
        condition: service_started
    restart: unless-stopped
