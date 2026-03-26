# Audit Log Analyzer — System Architecture

**Version**: 1.0  
**Date**: 2026-03-25  
**Status**: Approved for Development  

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Component Breakdown](#2-component-breakdown) _(18 components, including embedded MinIO)_
3. [Database Schema](#3-database-schema)
4. [Technology Stack Table](#4-technology-stack-table)
5. [Technical Risks](#5-technical-risks)

---

## 1. System Overview

### 1.1 Component Diagram

```
                ┌─────────────────────────────────────────────────────────────┐
                │             GITHUB ENTERPRISE CLOUD                         │
                │  (Audit Log Streaming must be pre-configured by operator.   │
                │   See: https://docs.github.com/en/enterprise-cloud/admin/   │
                │   monitoring-activity-in-your-enterprise/streaming-the-     │
                │   audit-log-for-your-enterprise)                            │
                └──────────────────────┬──────────────────────────────────────┘
                                       │  Streams YYYY/MM/DD/HH/MM/<uuid>.json.gz
                          ┌────────────┴────────────┬─────────────────────────┐
                          │                         │                         │
               ┌──────────▼──────────┐   ┌──────────▼──────────────┐  ┌───────▼──────────────┐
               │    AWS S3 Bucket    │   │  Azure Blob Container   │  │  MinIO (Embedded)    │
               │    (read-only)      │   │      (read-only)        │  │  S3-compatible,      │
               │                     │   │                         │  │  self-hosted.        │
               └──────────┬──────────┘   └──────────┬──────────────┘  │  GitHub streams      │
                          │                          │                 │  directly here via   │
                          │                          │                 │  S3 protocol.        │
                          │                          │                 │  Bucket event →      │
                          │                          │                 │  Valkey pub/sub      │
                          │                          │                 │  (no poll needed)    │
                          │                          │                 └──────────┬───────────┘
                          └─────────────────┬────────┘                           │
                                            └──────────────────┬─────────────────┘
                                                               │ list objects + stream-download
                                                               │ (or push-notify for MinIO mode)
                    ┌────────────────────▼────────────────────┐
                    │           INGESTION WORKERS              │
                    │   Celery Beat (scheduler, 1–15 min)      │
                    │   Celery Workers (parallel per source)   │
                    │  ─────────────────────────────────────  │
                    │  1. Claim cursor (FOR UPDATE SKIP LOCKED)│
                    │  2. List prefixes newer than last_prefix │
                    │  3. Stream-download + decompress .gz     │
                    │  4. Check dedup (Valkey bloom → PG)      │
                    │  5. Normalize raw JSON → EventSchema     │
                    │  6. GeoIP enrich via MaxMind mmdb        │
                    │  7. Bulk INSERT events (ON CONFLICT SKIP)│
                    │  8. Commit cursor + dedup in same txn    │
                    │  9. Enqueue detection batch task         │
                    └──┬──────────────┬──────────────┬─────────┘
                       │              │              │
          ┌────────────▼──┐  ┌────────▼────┐  ┌────▼──────────────────┐
          │  EVENT STORE  │  │ CURSOR STORE │  │  RAW PAYLOAD STORE    │
          │ PostgreSQL 16 │  │ PostgreSQL   │  │  PostgreSQL           │
          │ + TimescaleDB │  │ ingestion_   │  │  event_raw_payloads   │
          │ events        │  │ cursors      │  │  (one row per event,  │
          │ (hypertable,  │  │              │  │   full raw JSON;      │
          │  weekly chunks│  └─────────────┘  │   .gz files stay in   │
          │  + compression│                   │   S3/Blob unchanged)  │
          └───────┬───────┘                   └───────────────────────┘
                  │
        ┌─────────┴──────────────────────────────────────────────┐
        │                                                        │
        ▼                                                        ▼
┌──────────────────────────┐             ┌───────────────────────────────┐
│    DETECTION ENGINE      │             │    BEHAVIORAL BASELINE ENGINE │
│    Celery Workers        │             │    Celery Beat (hourly)       │
│  ──────────────────────  │             │  ─────────────────────────── │
│  • Load enabled rules    │             │  • Rolling 30-day window      │
│  • Evaluate rule DSL     │             │  • Compute mean/stddev/p95/   │
│    (threshold, pattern,  │             │    p99 per actor + org        │
│     sequence, statistical│             │  • Writes behavioral_baselines│
│  • Impossible travel     │             │  • Optional: enabled in admin │
│  • Off-hours anomaly     │             └───────────────────────────────┘
│  • Check suppressions    │
│  • Write detections      │             ┌───────────────────────────────┐
│  • Enqueue notifications │             │    ENRICHMENT SERVICE         │
│  • Auto-create tickets   │             │    Celery Background (async)  │
└──────────┬───────────────┘             │  ─────────────────────────── │
           │                             │  • Okta / Entra / G-Workspace │
           ▼                             │    actor metadata sync (hourly│
  ┌──────────────────────┐               │  • GitHub REST API            │
  │   detections table   │               │    (on-demand, per-investig.  │
  │   + detection_       │               │     only, never bulk)         │
  │   suppressions       │               │  • Writes idp_actor_          │
  └──────────┬───────────┘               │    enrichments                │
             │                           └───────────────────────────────┘
             ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                            API LAYER                                     │
│                     FastAPI 0.111 (async)                                │
│  ──────────────────────────────────────────────────────────────────────  │
│  • Auth: GitHub OAuth (Authlib) + SAML 2.0 (python3-saml) → JWT        │
│  • Session: JWT signed HS256, stored as key ref in Valkey (15-min TTL) │
│  • RBAC: team→role lookup, org+repo scope enforced on every query       │
│  • Rate limiting: slowapi (per-user, per-endpoint)                      │
│  • Audit trail: FastAPI middleware writes every mutation to audit_trail  │
│  • OpenAPI 3.1 spec + Swagger UI at /docs                               │
└─────────────────────────────┬────────────────────────────────────────────┘
                              │
               ┌──────────────┴───────────────────────────────┐
               │                                              │
               ▼                                              ▼
┌──────────────────────────────────┐         ┌───────────────────────────┐
│         WEB FRONTEND             │         │   EXTERNAL CONSUMERS      │
│  React 18 + TypeScript + Vite    │         │  • Programmatic REST API  │
│  TailwindCSS + Apache ECharts    │         │    (JWT auth required)    │
│  TanStack Query + QueryBuilder   │         │  • Read-only PostgreSQL   │
│  ────────────────────────────── │         │    connection (BI tools)  │
│  /dashboard   Metrics + ECharts  │         └───────────────────────────┘
│  /detections  Lifecycle viewer   │
│  /query       SQL + Visual QB    │
│  /rules       WYSIWYG editor     │
│  /admin       System config      │
└──────────────────────────────────┘

                   Supporting async services (Celery workers)
        ┌──────────────────────┐  ┌──────────────────────┐  ┌───────────────────┐
        │  NOTIFICATION SVC    │  │  TICKETING INTEG.    │  │    RULE STORE     │
        │  slack-sdk           │  │  Jira REST API       │  │  PostgreSQL +     │
        │  aiosmtplib          │  │  GitHub Issues API   │  │    RULE STORE     │
        │  Jinja2 templates    │  │  atlassian-python-   │  │  PostgreSQL +     │
        │                      │  │  api + PyGithub      │  │  GitHub repo sync │
        └──────────────────────┘  └──────────────────────┘  └───────────────────┘

                    ┌────────────────────────────────────┐
                    │      VALKEY 7.2 (State Store)       │
                    │  • Celery broker + result backend   │
                    │  • JWT session key-value store      │
                    │  • Dedup bloom filter (24h TTL)     │
                    │  • RBAC team membership cache (5m)  │
                    └────────────────────────────────────┘
```

### 1.2 Data Flow Narrative

**Poll / Push** — Three ingestion modes are supported, selected per-source via `ingestion_cursors.source_type`:

- **`s3`** — Celery Beat fires `ingestion.poll_sources` every 1–15 minutes. Worker lists all S3 object keys with a prefix lexicographically greater than `last_prefix` using `ListObjectsV2 StartAfter`.
- **`azure_blob`** — Same polling model; uses `list_blobs(name_starts_with=last_prefix)`.
- **`minio`** — Embedded MinIO service runs inside the Docker Compose / Helm stack. GitHub streams directly to MinIO (S3-compatible endpoint). MinIO bucket notifications publish to a Valkey channel (`minio:events`) on each new `.json.gz` PUT. Worker subscribes via Valkey pub/sub; new-file notifications trigger immediate processing without waiting for the Celery Beat tick.

For all modes, each Ingestion Worker acquires a source lock using `SELECT id FROM ingestion_cursors WHERE status = 'active' AND source_type = $1 FOR UPDATE SKIP LOCKED LIMIT 1`. Multiple workers can run in parallel, each processing a different source.

**Parse** — The worker lists all object keys under prefixes lexicographically greater than `last_prefix` (using S3 `ListObjectsV2` with `StartAfter` or Azure Blob `list_blobs` with `name_starts_with`). Each `.json.gz` is streamed, decompressed via Python `gzip.GzipFile`, and each newline-delimited JSON record is parsed.

**Dedup** — Each parsed record's `_document_id` is checked against a Valkey SET (24-hour TTL, O(1)). On a cache miss, the `event_dedup` table is queried. Records with a known `document_id` are silently discarded. This handles GitHub's at-least-once delivery guarantee without relying on GitHub to deduplicate for us.

**Normalize** — Each raw record is validated against `EventSchema` (Pydantic v2). Standard fields (`actor`, `actor_id`, `org`, `org_id`, `repo`, `action`, `created_at`, `source_ip`, `user_agent`) are mapped to typed columns. All remaining fields are preserved in `data JSONB`. The `namespace` column is derived as `split_part(action, '.', 1)` (stored, generated column).

**Store** — Normalized events are bulk-inserted into the `events` TimescaleDB hypertable via multi-row `INSERT ... ON CONFLICT (document_id) DO NOTHING`. The raw JSON is stored in `event_raw_payloads`. `event_dedup` rows and the `ingestion_cursors.last_prefix` are committed atomically in the same transaction. On failure, the cursor does not advance and the batch is retried from the same position.

**Detect** — After batch commit, the worker enqueues a `detection.evaluate_batch` Celery task with the list of new event IDs. Detection workers fetch those events, evaluate all enabled `rule_definitions` using the JSON-DSL interpreter, check `detection_suppressions`, and write matching `detections`. Severity is resolved against `severity_configs`. Auto-ticket and notification tasks are enqueued if configured.

**Serve** — FastAPI serves all reads from PostgreSQL through scoped SQLAlchemy queries. Every API request undergoes JWT validation, RBAC scope resolution, and appends a row to `audit_trail`. The React frontend exclusively communicates via the REST API.

---

## 2. Component Breakdown

### 2.1 Ingestion Worker

| Attribute | Detail |
|-----------|--------|
| **Responsibility** | Read new `.json.gz` objects from S3, Azure Blob, or embedded MinIO; decompress; dedup; normalize; GeoIP-enrich; bulk-write events; advance cursor atomically |
| **Technology** | Python 3.12, Celery 5.4 (BSD-3), boto3 1.34 (Apache 2.0), azure-storage-blob 12.19 (MIT), geoip2 4.8 (Apache 2.0) |
| **Key Interfaces** | `ingestion_cursors` R/W; `events` W; `event_raw_payloads` W; `event_dedup` R/W; Valkey dedup SET; Valkey `minio:events` pub/sub (MinIO mode); Celery detection queue W |
| **Scalability** | One worker per concurrent source; row-level advisory lock via `FOR UPDATE SKIP LOCKED`; backfill parallelized by splitting prefix date ranges across multiple workers |

**Ingestion modes:**

| Mode | `source_type` | Trigger mechanism | GitHub streams to |
|------|--------------|-------------------|------------------|
| AWS S3 | `s3` | Celery Beat poll (1–15 min) | External AWS S3 bucket |
| Azure Blob | `azure_blob` | Celery Beat poll (1–15 min) | External Azure Blob container |
| Embedded MinIO | `minio` | Valkey pub/sub push (near-instant) | MinIO service inside this stack |

> **MinIO mode requirement:** The MinIO service needs a TLS-terminated, publicly accessible endpoint so GitHub can validate SSL when streaming. Operators expose this via an ingress, reverse proxy (nginx/Caddy), or a tunnel (Cloudflare Tunnel). For private/air-gapped environments, fall back to S3 or Azure Blob.

### 2.2 Event Store

| Attribute | Detail |
|-----------|--------|
| **Responsibility** | Persistent, queryable, compressed time-series store for all normalized audit log events |
| **Technology** | PostgreSQL 16 (PostgreSQL License), TimescaleDB 2.14 OSS (Apache 2.0) |
| **Key Interfaces** | Written by Ingestion Worker; queried by Detection Engine, Reporting Engine, Query Engine, API Layer |
| **Scalability** | Weekly hypertable chunks; automatic columnar compression at 7-day age (~90% space reduction); continuous aggregates for pre-computed metrics; retention policy enforced by TimescaleDB job, configurable via admin portal |

### 2.3 Detection Engine

| Attribute | Detail |
|-----------|--------|
| **Responsibility** | Evaluate enabled detection rules against new event batches; apply suppression logic; write detections; trigger notifications and ticketing |
| **Technology** | Python 3.12, Celery 5.4 (BSD-3), custom JSON-DSL rule interpreter (zero `eval()`), pandas 2.2 (BSD-3) for sliding-window aggregation |
| **Key Interfaces** | Reads `events`, `rule_definitions`, `detection_suppressions`, `behavioral_baselines`, `idp_actor_enrichments`; writes `detections`; enqueues `notification.send` and `ticketing.create_ticket` tasks |
| **Scalability** | Stateless workers; horizontal scaling; batches of 500 events; per-rule deduplication window prevents duplicate open detections |

**Rule logic types:** `threshold` (count in time window > N), `pattern` (single-event field match), `sequence` (ordered events from same actor within window), `statistical` (deviation > N stddev from `behavioral_baselines`).

### 2.4 Behavioral Baseline Engine

| Attribute | Detail |
|-----------|--------|
| **Responsibility** | Compute rolling per-actor and per-org activity baselines (mean, stddev, p95, p99) consumed by statistical detection rules |
| **Technology** | Python 3.12, Celery Beat (hourly), pandas 2.2 (BSD-3), SQLAlchemy 2.0 (MIT) |
| **Key Interfaces** | Reads `events` (30-day rolling window); writes `behavioral_baselines`; read by Detection Engine |
| **Scalability** | Incremental hourly compute; disabled by default — enabled in admin portal when operators are ready for statistical detection |

### 2.5 GeoIP Service

| Attribute | Detail |
|-----------|--------|
| **Responsibility** | Resolve `source_ip` to country, city, lat/lon, and proxy/hosting/VPN flags inline during ingestion |
| **Technology** | MaxMind GeoLite2 City mmdb (CC BY-SA 4.0), geoip2 Python library 4.8 (Apache 2.0) |
| **Key Interfaces** | Called synchronously by Ingestion Worker during normalization; each worker loads the mmdb file (~95 MB) into process memory at startup |
| **Scalability** | Pure in-process; zero network latency; mmdb refreshed weekly via GeoIP Update cron job (container sidecar or k8s CronJob) |

### 2.6 Enrichment Service

| Attribute | Detail |
|-----------|--------|
| **Responsibility** | Sync actor metadata from IdP providers; execute on-demand GitHub REST API lookups during investigations |
| **Technology** | httpx 0.27 (BSD-3), okta-sdk-python 2.x (Apache 2.0), msal 1.x (MIT), google-auth 2.x (Apache 2.0) |
| **Key Interfaces** | Background Celery task reads distinct actors from `events`; writes `idp_actor_enrichments`; on-demand REST call triggered by API Layer endpoint, result returned inline and not cached permanently |
| **Scalability** | Non-blocking; enrichment failures never block ingestion or detection; IdP calls are rate-limited with exponential backoff |

### 2.7 Query Engine

| Attribute | Detail |
|-----------|--------|
| **Responsibility** | Safely execute user-authored SQL queries against the event store with mandatory org/repo scope enforcement |
| **Technology** | PostgreSQL 16 (read-only role `readonly_query_user`), SQLAlchemy 2.0, pglast 6.x (BSD) for SQL AST parsing and validation |
| **Key Interfaces** | Receives query text from API Layer after SQL validation; executes via read-only connection pool; returns paginated JSON |
| **Scalability** | Separate connection pool (max 20); 30-second execution timeout; 100,000-row result cap; per-user rate limit (10 concurrent queries) |

**Security model:** User SQL is parsed by pglast to an AST before execution. Only `SELECT` statements on `events`, `detections`, `behavioral_baselines`, and continuous aggregate views are permitted. The mandatory org/repo `WHERE` predicate is injected by the engine before execution. DDL, DML, `COPY`, function calls, and cross-schema references are rejected at parse time.

### 2.8 Reporting Engine

| Attribute | Detail |
|-----------|--------|
| **Responsibility** | Compute and serve pre-built business metric dashboards; support drill-down from metric to contributing raw events |
| **Technology** | Python 3.12, FastAPI (inline), SQLAlchemy 2.0, TimescaleDB continuous aggregates |
| **Key Interfaces** | Reads `events_hourly`, `events_daily_actor`, `detections_daily` continuous aggregate views; reads `detections` for drill-down |
| **Scalability** | Continuous aggregates updated incrementally in TimescaleDB background; API queries hit materialized views only |

**Pre-built metrics (v1):** MAU/WAU by org, license seat utilization, repo creation/deletion rate, Actions run volume + success/failure rate, Copilot seat utilization, codespace hours, PAT counts by expiry tier, webhook and GitHub App counts.

**Continuous aggregates:**
- `events_hourly` — `(org, namespace, action, bucket_hour)` → event count
- `events_daily_actor` — `(actor, org, namespace, bucket_day)` → event count
- `detections_daily` — `(severity, status, bucket_day)` → detection count

### 2.9 API Layer

| Attribute | Detail |
|-----------|--------|
| **Responsibility** | REST API serving all frontend and external consumers; JWT auth; RBAC enforcement; audit trail; rate limiting |
| **Technology** | FastAPI 0.111 (MIT), Pydantic 2.7 (MIT), Authlib 1.3 (BSD-3), python3-saml 1.16 (MIT), slowapi 0.1.9 (MIT), PyJWT 2.8 (MIT) |
| **Key Interfaces** | All React frontend + external REST consumers; enforces scope on all DB reads; writes `audit_trail` on every mutation |
| **Scalability** | Stateless; horizontally scalable behind any HTTP load balancer; JWT verification is signature-only (no DB call on hot path) |

**Auth flow:**
1. **GitHub OAuth**: User redirected to `github.com/login/oauth/authorize` → callback at `/auth/github/callback` → exchange code for access token (Authlib) → fetch `/user` and `/user/teams` → issue HS256 JWT → store session metadata in Valkey with 15-minute TTL.
2. **SAML 2.0**: SP-initiated or IdP-initiated → validate assertion via python3-saml (strict mode, signature required) → extract NameID → map to GitHub login via `user_role_assignments.saml_subject` → issue JWT.
3. **Every request**: `Authorization: Bearer <jwt>` → verify HS256 signature → check Valkey session key exists → resolve RBAC from `user_role_assignments` → inject `scoped_orgs[]` / `scoped_repos[]` into request context.

### 2.10 Web Frontend

| Attribute | Detail |
|-----------|--------|
| **Responsibility** | Browser SPA: metric dashboards, detection lifecycle viewer, self-service query builder, WYSIWYG rule editor, admin portal |
| **Technology** | React 18.3 (MIT), TypeScript 5.4, Vite 5.4 (MIT), TailwindCSS 3.4 (MIT), TanStack Query v5 (MIT), Apache ECharts 5.5 (Apache 2.0), @react-querybuilder/react-querybuilder 7.x (MIT), Monaco Editor 0.49 (MIT) |
| **Key Interfaces** | REST API Layer exclusively; no direct database access; all JSONB rendered through React's default HTML escaping |
| **Scalability** | Static asset bundle; served by nginx container; CDN-cacheable (content-hash filenames); no SSR required |

**Key routes:**

| Route | Purpose |
|-------|---------|
| `/dashboard` | Metric tiles powered by ECharts; click-through drill-down to raw events |
| `/detections` | Filterable table; lifecycle actions (investigate / resolve / false-positive); Jira/GitHub Issues creation |
| `/query` | Visual query builder (@react-querybuilder) + Monaco SQL editor; paginated results table; CSV/JSON export |
| `/rules` | Rule list; WYSIWYG rule config editor; version history diff view |
| `/admin` | Ingestion sources, severity configs, IdP, ticketing, notifications, retention, RBAC assignments |

### 2.11 Rule Store

| Attribute | Detail |
|-----------|--------|
| **Responsibility** | Version-controlled storage of detection rule definitions; WYSIWYG editor; full git history accessible in UI |
| **Technology** | PostgreSQL `rule_definitions` + `rule_versions` tables; PyGithub 2.3 to commit rule YAML files to a configured GitHub repository (`GITHUB_RULES_REPO`) |
| **Key Interfaces** | CRUD via API Layer (`/rules/*` endpoints); read by Detection Engine at task start; every rule save triggers a non-fatal async commit to the GitHub repo (DB is source of truth) |
| **Scalability** | Low write frequency; GitHub API calls are synchronous but non-blocking (failure logs a warning, rule mutation still succeeds in DB) |

**Rule lifecycle:** `draft → active → deprecated`. Changes create a new `rule_versions` row and increment `rule_definitions.version`. Deprecated rules are never deleted. Rule engine always reads the highest `version` where `enabled = true`.

### 2.12 Ticketing Integration

| Attribute | Detail |
|-----------|--------|
| **Responsibility** | Create and update tickets in Jira or GitHub Issues from detection events; bidirectional status sync |
| **Technology** | atlassian-python-api 3.41 (Apache 2.0), PyGithub 2.3 (LGPL-3.0) |
| **Key Interfaces** | Triggered by Detection Engine (auto-create, if `ticketing_configs.auto_create = true` and severity in `auto_create_severity`) or API Layer (manual trigger); reads `ticketing_configs`; writes `tickets` |
| **Scalability** | Async Celery tasks; exponential backoff with max 5 retries; bidirectional sync cron every 15 minutes to pull status updates |

### 2.13 Notification Service

| Attribute | Detail |
|-----------|--------|
| **Responsibility** | Send Slack messages and SMTP email on detection creation and status change events |
| **Technology** | slack-sdk 3.30 (MIT), aiosmtplib 3.0 (MIT), Jinja2 3.1 (BSD-3) for message templates |
| **Key Interfaces** | Triggered via Celery task queue by Detection Engine (on new detection) and API Layer (on status change if configured); reads `notification_configs` and `detections` |
| **Scalability** | Async workers; per-detection deduplication (suppress repeat notifications within configurable cooldown window) |

### 2.14 Auth / RBAC

| Attribute | Detail |
|-----------|--------|
| **Responsibility** | Authenticate via GitHub OAuth + SAML 2.0; resolve GitHub team memberships to application roles; enforce org/repo scoped data isolation on every request |
| **Technology** | Authlib 1.3 (BSD-3), python3-saml 1.16 (MIT), PyJWT 2.8 (MIT), Valkey 7.2 (BSD-3) |
| **Key Interfaces** | FastAPI `Depends()` middleware; reads `user_role_assignments` + `rbac_roles`; team memberships cached in Valkey (5-minute TTL) |
| **Scalability** | JWT validation is stateless (signature + Valkey key-exists check); team cache avoids GitHub API calls on hot path |

**Role definitions:**

| Role | Permissions |
|------|-------------|
| `analyst` | `events:read`, `detections:read`, `detections:update`, `queries:run`, `reports:read` |
| `report_admin` | All analyst + `reports:manage`, `queries:manage`, `exports:create` |
| `rule_author` | All analyst + `rules:read`, `rules:write`, `rules:enable_disable` |
| `sys_admin` | All permissions including `admin:*`, `audit_trail:read`, `rbac:manage` |

**Scope isolation:** Every database query is augmented by the RBAC middleware with a mandatory `WHERE org = ANY(:scoped_orgs) AND (repo IS NULL OR repo = ANY(:scoped_repos))` predicate. The `readonly_query_user` database role has `GRANT SELECT` only on `events`, `detections`, and continuous aggregate views — it cannot read `audit_trail`, `ticketing_configs`, or `notification_configs`.

### 2.15 Audit Trail

| Attribute | Detail |
|-----------|--------|
| **Responsibility** | Immutable, append-only log of every user action within the application |
| **Technology** | PostgreSQL `audit_trail` TimescaleDB hypertable (monthly chunks + compression) |
| **Key Interfaces** | Written by FastAPI middleware on every API request (success, denied, and error outcomes recorded); readable only by `sys_admin` role |
| **Scalability** | Monthly compression; independently configurable retention (default 2 years); partition structure isolates from events retention |

### 2.16 Admin Portal

| Attribute | Detail |
|-----------|--------|
| **Responsibility** | System-wide configuration UI: ingestion sources, retention policies, severity configs, IdP setup, ticketing config, notification config, RBAC assignments |
| **Technology** | React frontend pages under `/admin`; FastAPI `/admin/*` endpoints (all require `sys_admin` JWT) |
| **Key Interfaces** | Reads/writes `ingestion_cursors`, `severity_configs`, `ticketing_configs`, `notification_configs`, `user_role_assignments`; triggers ingestion worker reconnect on source config changes |
| **Scalability** | Low-frequency administration operations; no special scaling requirements |

### 2.17 Cursor / State Store

| Attribute | Detail |
|-----------|--------|
| **Responsibility** | Celery message broker, result backend, JWT session cache, dedup bloom filter, RBAC team cache |
| **Technology** | **Valkey 7.2** (BSD-3-Clause; Linux Foundation fork of Redis 7.2; fully API-compatible) |
| **Key Interfaces** | Celery (broker + result backend via `valkey://`); API Layer (JWT session key-value); Ingestion Worker (dedup SET, 24h TTL); Auth/RBAC (GitHub team cache, 5m TTL) |
| **Scalability** | Single-node for most deployments; Valkey Cluster mode for large-scale; persistence via AOF |

> **Why Valkey, not Redis:** Redis 7.x uses the RSAL (Redis Source Available License), which restricts use cases in competing products. Valkey is its BSD-3-licensed, Linux Foundation-maintained community fork, API-compatible at the protocol level. The `redis-py` client and Celery both work with Valkey without code changes — just update the connection URL.

### 2.18 Embedded Object Store (MinIO)

| Attribute | Detail |
|-----------|--------|
| **Responsibility** | S3-compatible object storage that receives GitHub audit log streams directly, eliminating the need for an external AWS or Azure account in simple deployments |
| **Technology** | **MinIO** RELEASE.2024-06 (AGPL-3.0); `mc` CLI for bucket configuration; `boto3` client (same as S3 mode — no code changes) |
| **Key Interfaces** | GitHub streams `.json.gz` files via S3 `PutObject`; MinIO bucket notification webhook publishes to Valkey channel `minio:events` on each new file; Ingestion Worker subscribes to that channel and triggers immediate processing |
| **Scalability** | Single-node for most deployments (MinIO standalone); MinIO Distributed mode available for large deployments; volume-backed for persistence |

**Setup flow (operator):**

1. Deploy the stack (MinIO starts with access key + secret key from env vars).
2. Expose MinIO's S3 port (9000) via TLS-terminated reverse proxy or Kubernetes ingress — GitHub requires HTTPS with a valid certificate.
3. In the Admin Portal under **Ingestion Sources → Add MinIO source**, obtain the generated access key and the public endpoint URL.
4. In the GitHub Enterprise admin, configure Audit Log Streaming → Amazon S3, using the MinIO endpoint URL, access key, and secret key, and bucket name `audit-logs`.
5. MinIO automatically fires bucket notifications → Valkey → Ingestion Worker begins processing within seconds of each file upload.

**Bucket notification configuration** (applied by the stack at startup via `mc event add`):

```
mc event add minio/audit-logs arn:minio:sqs::1:valkey \
  --event put \
  --suffix .json.gz
```

**When MinIO is NOT the right choice:**
- The analyzer host cannot be exposed to the public internet (use S3 or Azure Blob instead).
- The enterprise already has an existing streaming destination configured (use the matching source type).
- Air-gapped / highly regulated environments that restrict running additional services (use S3 or Azure Blob with existing bucket).

---

## 3. Database Schema

### Prerequisites

```sql
-- Required extensions
CREATE EXTENSION IF NOT EXISTS timescaledb;   -- Apache 2.0 OSS edition
CREATE EXTENSION IF NOT EXISTS pg_trgm;        -- trigram indexes for text search
CREATE EXTENSION IF NOT EXISTS btree_gin;      -- GIN on scalar types
CREATE EXTENSION IF NOT EXISTS pgcrypto;       -- gen_random_uuid() for idempotency keys
```

---

### 3.1 `events`

Core normalized event store. TimescaleDB hypertable partitioned by `created_at`.

> **Dedup note:** A globally unique index on `document_id` alone cannot span hypertable partitions in TimescaleDB. Deduplication is enforced at two levels: (1) the `event_dedup` lookup table (see §3.2) checked before insert, and (2) `INSERT ... ON CONFLICT (document_id) DO NOTHING` using the per-chunk unique index.

```sql
CREATE TABLE events (
    id               BIGSERIAL        NOT NULL,
    -- Dedup key (GitHub _document_id field)
    document_id      TEXT             NOT NULL,
    -- Temporal fields
    created_at       TIMESTAMPTZ      NOT NULL,   -- GitHub @timestamp
    ingested_at      TIMESTAMPTZ      NOT NULL DEFAULT NOW(),
    -- Action
    action           TEXT             NOT NULL,   -- e.g. "repo.create"
    namespace        TEXT             NOT NULL GENERATED ALWAYS AS (
                                          split_part(action, '.', 1)
                                      ) STORED,
    -- Actor
    actor            TEXT,
    actor_id         BIGINT,
    actor_is_bot     BOOLEAN          NOT NULL DEFAULT FALSE,
    -- Org/repo scope
    org              TEXT,
    org_id           BIGINT,
    repo             TEXT,            -- full_name: org/repo
    repo_id          BIGINT,
    business         TEXT,
    business_id      BIGINT,
    -- Network
    source_ip        INET,
    user_agent       TEXT,
    -- GeoIP (enriched by MaxMind at ingest time)
    geo_country_code CHAR(2),
    geo_city         TEXT,
    geo_latitude     DOUBLE PRECISION,
    geo_longitude    DOUBLE PRECISION,
    geo_is_proxy     BOOLEAN,         -- MaxMind proxy/VPN/hosting flag
    -- Full normalized payload
    data             JSONB            NOT NULL,
    -- Ingestion metadata
    ingestion_source TEXT             NOT NULL
                     CHECK (ingestion_source IN ('s3', 'azure_blob')),
    source_file_path TEXT             NOT NULL,   -- S3 key or blob path
    PRIMARY KEY (id, created_at)     -- partition key must appear in PK
);

-- Convert to hypertable: weekly chunks balance chunk count vs. query performance
SELECT create_hypertable(
    'events',
    'created_at',
    chunk_time_interval => INTERVAL '1 week',
    if_not_exists => TRUE
);

-- Compress chunks older than 7 days (columnar, ~90% compression typical)
ALTER TABLE events SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'org, namespace',
    timescaledb.compress_orderby   = 'created_at DESC'
);
SELECT add_compression_policy('events', INTERVAL '7 days');

-- Retention policy: default 1 year, managed via admin portal
-- Uncomment after admin portal sets configured_retention_interval:
-- SELECT add_retention_policy('events', INTERVAL '1 year');

-- Indexes
-- Per-chunk dedup: TimescaleDB creates this on each chunk
-- Global dedup enforced via event_dedup table (see 3.2)
CREATE INDEX idx_events_actor         ON events (actor, created_at DESC);
CREATE INDEX idx_events_org           ON events (org, created_at DESC);
CREATE INDEX idx_events_repo          ON events (repo, created_at DESC)
    WHERE repo IS NOT NULL;
CREATE INDEX idx_events_namespace     ON events (namespace, created_at DESC);
CREATE INDEX idx_events_action        ON events (action, created_at DESC);
CREATE INDEX idx_events_source_ip     ON events (source_ip, created_at DESC)
    WHERE source_ip IS NOT NULL;
CREATE INDEX idx_events_actor_is_bot  ON events (actor_is_bot, created_at DESC)
    WHERE actor_is_bot = TRUE;
CREATE INDEX idx_events_data_gin      ON events USING GIN (data jsonb_path_ops);

-- Continuous aggregates for reporting engine
CREATE MATERIALIZED VIEW events_hourly
WITH (timescaledb.continuous) AS
    SELECT
        time_bucket('1 hour', created_at) AS bucket_hour,
        org,
        namespace,
        action,
        COUNT(*)                           AS event_count
    FROM events
    GROUP BY 1, 2, 3, 4
WITH NO DATA;

SELECT add_continuous_aggregate_policy('events_hourly',
    start_offset => INTERVAL '3 hours',
    end_offset   => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour');

CREATE MATERIALIZED VIEW events_daily_actor
WITH (timescaledb.continuous) AS
    SELECT
        time_bucket('1 day', created_at)  AS bucket_day,
        actor,
        org,
        namespace,
        COUNT(*)                           AS event_count
    FROM events
    WHERE actor IS NOT NULL
    GROUP BY 1, 2, 3, 4
WITH NO DATA;

SELECT add_continuous_aggregate_policy('events_daily_actor',
    start_offset => INTERVAL '2 days',
    end_offset   => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour');
```

---

### 3.2 `event_dedup`

Global deduplication lookup table — checked before every insert into `events`.

```sql
CREATE TABLE event_dedup (
    document_id  TEXT        PRIMARY KEY,
    event_id     BIGINT      NOT NULL,    -- references events.id (not FK — cross-chunk)
    created_at   TIMESTAMPTZ NOT NULL,    -- mirrors events.created_at for range pruning
    ingested_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Prune old dedup records on a schedule matching events retention
-- (run via Celery Beat, configurable)
-- DELETE FROM event_dedup WHERE created_at < NOW() - INTERVAL '1 year';
```

---

### 3.3 `event_raw_payloads`

Stores the complete unmodified JSON for each event. The original `.json.gz` files remain untouched in S3/Azure Blob.

```sql
CREATE TABLE event_raw_payloads (
    id           BIGSERIAL   PRIMARY KEY,
    document_id  TEXT        NOT NULL UNIQUE,
    source_file  TEXT        NOT NULL,   -- S3 key or blob path of the source .json.gz
    raw_json     JSONB       NOT NULL,   -- full, unmodified JSON record from GitHub
    event_id     BIGINT,                 -- set after events insert (may be NULL if deduped)
    ingested_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_raw_payloads_event_id ON event_raw_payloads (event_id)
    WHERE event_id IS NOT NULL;
```

---

### 3.4 `ingestion_cursors`

Tracks the last successfully-processed object prefix per source. Used for resumable polling.

```sql
CREATE TABLE ingestion_cursors (
    id                SERIAL      PRIMARY KEY,
    source_type       TEXT        NOT NULL
                      CHECK (source_type IN ('s3', 'azure_blob', 'minio')),
    source_name       TEXT        NOT NULL,  -- S3 bucket name or Azure container name
    -- Connection config (no credentials stored — use env vars)
    source_region     TEXT,                  -- AWS region (S3 only)
    source_prefix     TEXT        NOT NULL DEFAULT '',  -- optional key prefix filter
    -- Cursor state
    last_prefix       TEXT        NOT NULL DEFAULT '',  -- last processed YYYY/MM/DD/HH/MM
    last_file         TEXT,                  -- last file processed within last_prefix
    last_event_count  BIGINT      NOT NULL DEFAULT 0,
    last_processed_at TIMESTAMPTZ,
    -- Worker state
    status            TEXT        NOT NULL DEFAULT 'active'
                      CHECK (status IN ('active', 'paused', 'error', 'backfilling')),
    error_message     TEXT,
    error_count       INT         NOT NULL DEFAULT 0,
    -- Poll interval
    poll_interval_sec INT         NOT NULL DEFAULT 300, -- 5 minutes default
    -- Metadata
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source_type, source_name)
);
```

---

### 3.5 `detections`

One row per detected threat finding.

```sql
CREATE TABLE detections (
    id              BIGSERIAL    PRIMARY KEY,
    -- Rule reference
    rule_id         BIGINT       NOT NULL REFERENCES rule_definitions(id),
    rule_version    INT          NOT NULL,
    -- Timing
    triggered_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    window_start    TIMESTAMPTZ,           -- observation window start (for sliding rules)
    window_end      TIMESTAMPTZ,           -- observation window end
    -- Classification
    severity        TEXT         NOT NULL
                    CHECK (severity IN ('critical', 'high', 'medium', 'low', 'info')),
    confidence      TEXT         NOT NULL
                    CHECK (confidence IN ('high', 'medium', 'low')),
    -- Lifecycle
    status          TEXT         NOT NULL DEFAULT 'open'
                    CHECK (status IN ('open', 'investigating', 'resolved', 'false_positive')),
    assigned_to     TEXT,
    -- Description
    title           TEXT         NOT NULL,
    description     TEXT         NOT NULL,
    -- Scope (denormalized for fast filtering without joining events)
    actor           TEXT,
    org             TEXT,
    repo            TEXT,
    source_ip       INET,
    -- Evidence
    event_ids       BIGINT[]     NOT NULL DEFAULT '{}',  -- contributing event IDs
    context_data    JSONB        NOT NULL DEFAULT '{}',  -- rule-specific structured context
    -- Resolution
    resolved_at     TIMESTAMPTZ,
    resolved_by     TEXT,
    resolution_note TEXT,
    -- Relations
    suppressed_by   BIGINT       REFERENCES detection_suppressions(id),
    -- Metadata
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_detections_status    ON detections (status, triggered_at DESC);
CREATE INDEX idx_detections_actor     ON detections (actor, triggered_at DESC)
    WHERE actor IS NOT NULL;
CREATE INDEX idx_detections_org       ON detections (org, triggered_at DESC)
    WHERE org IS NOT NULL;
CREATE INDEX idx_detections_severity  ON detections (severity, status, triggered_at DESC);
CREATE INDEX idx_detections_rule      ON detections (rule_id, triggered_at DESC);

-- Continuous aggregate for dashboard
CREATE MATERIALIZED VIEW detections_daily
WITH (timescaledb.continuous) AS
    SELECT
        time_bucket('1 day', triggered_at) AS bucket_day,
        severity,
        status,
        COUNT(*)                            AS detection_count
    FROM detections
    GROUP BY 1, 2, 3
WITH NO DATA;
```

> **Note:** `detections` is not a hypertable because detection count is orders of magnitude lower than events, and the full lifecycle history on each row requires mutable rows (TimescaleDB compressed chunks are immutable). A standard PostgreSQL table with range partitioning can be added later if needed.

---

### 3.6 `detection_suppressions`

Analyst-authored suppression rules that prevent detections from being written (or mark existing ones as suppressed) for known-benign patterns.

```sql
CREATE TABLE detection_suppressions (
    id              BIGSERIAL    PRIMARY KEY,
    rule_id         BIGINT       REFERENCES rule_definitions(id),  -- NULL = all rules
    -- Scope (at least one of these must be non-NULL — see constraint below)
    suppress_actor  TEXT,        -- NULL = any actor
    suppress_org    TEXT,        -- NULL = any org
    suppress_repo   TEXT,        -- NULL = any repo
    -- Justification
    reason          TEXT         NOT NULL,
    created_by      TEXT         NOT NULL,
    -- Validity window
    expires_at      TIMESTAMPTZ,  -- NULL = permanent
    active          BOOLEAN      NOT NULL DEFAULT TRUE,
    -- Metadata
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_suppression_has_scope CHECK (
        suppress_actor IS NOT NULL
        OR suppress_org IS NOT NULL
        OR suppress_repo IS NOT NULL
        OR rule_id IS NOT NULL
    )
);

CREATE INDEX idx_suppressions_active ON detection_suppressions (active, expires_at)
    WHERE active = TRUE;
CREATE INDEX idx_suppressions_actor  ON detection_suppressions (suppress_actor)
    WHERE suppress_actor IS NOT NULL AND active = TRUE;
CREATE INDEX idx_suppressions_org    ON detection_suppressions (suppress_org)
    WHERE suppress_org IS NOT NULL AND active = TRUE;
```

---

### 3.7 `severity_configs`

Per-action-pattern tunable severity overrides. Operators set these via the admin portal.

```sql
CREATE TABLE severity_configs (
    id               SERIAL      PRIMARY KEY,
    -- Pattern: exact action ("repo.create"), namespace wildcard ("repo.*"),
    -- or global fallback ("*"). More-specific patterns take precedence.
    action_pattern   TEXT        NOT NULL UNIQUE,
    default_severity TEXT        NOT NULL
                     CHECK (default_severity IN ('critical', 'high', 'medium', 'low', 'info')),
    -- Operator override: when set, supersedes both the rule default and detection engine default
    custom_severity  TEXT
                     CHECK (custom_severity IN ('critical', 'high', 'medium', 'low', 'info')),
    notes            TEXT,
    updated_by       TEXT,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Seed with well-known high-sensitivity actions
INSERT INTO severity_configs (action_pattern, default_severity, notes) VALUES
    ('protected_branch.policy_override',   'critical', 'Branch protection bypass'),
    ('business.recovery_code_used',        'critical', 'Enterprise SSO bypass'),
    ('org.recovery_code_used',             'critical', 'Org SSO bypass'),
    ('secret_scanning_alert.reopen',       'high',     'Dismissed secret scanning alert reopened'),
    ('repo.destroy',                       'high',     'Repository deleted'),
    ('repo.transfer',                      'high',     'Repository transferred'),
    ('org.remove_member',                  'medium',   'Member removed from org'),
    ('personal_access_token.access',       'low',      'PAT API access event'),
    ('*',                                  'info',     'Default fallback severity');
```

---

### 3.8 `behavioral_baselines`

Rolling statistical baselines computed by the Behavioral Baseline Engine.

```sql
CREATE TABLE behavioral_baselines (
    id             BIGSERIAL         PRIMARY KEY,
    -- What is being baselined
    baseline_type  TEXT              NOT NULL,
    -- Values: 'actor_hourly', 'actor_daily', 'org_daily', 'actor_namespace_daily'
    scope_key      TEXT              NOT NULL,   -- actor username or org name
    metric_name    TEXT              NOT NULL,
    -- e.g. 'clone_count', 'push_count', 'unique_repo_count', 'unique_ip_count'
    -- Observation window
    window_start   TIMESTAMPTZ       NOT NULL,
    window_end     TIMESTAMPTZ       NOT NULL,
    -- Statistics
    mean           DOUBLE PRECISION  NOT NULL,
    stddev         DOUBLE PRECISION  NOT NULL DEFAULT 0,
    p95            DOUBLE PRECISION  NOT NULL,
    p99            DOUBLE PRECISION  NOT NULL,
    sample_count   INT               NOT NULL,
    -- Metadata
    computed_at    TIMESTAMPTZ       NOT NULL DEFAULT NOW(),
    UNIQUE (baseline_type, scope_key, metric_name, window_start)
);

CREATE INDEX idx_baselines_lookup ON behavioral_baselines
    (baseline_type, scope_key, metric_name, window_end DESC);
```

---

### 3.9 `audit_trail`

Immutable application-level audit log. Records every user action.

```sql
CREATE TABLE audit_trail (
    id             BIGSERIAL    NOT NULL,
    timestamp      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    -- Who
    user_login     TEXT         NOT NULL,
    user_github_id BIGINT,
    ip_address     INET,
    user_agent     TEXT,
    -- What
    action_type    TEXT         NOT NULL,
    -- e.g. 'query.run', 'detection.update_status', 'rule.update',
    --      'suppression.create', 'admin.update_retention'
    resource_type  TEXT,        -- 'detection', 'rule', 'query', 'suppression', etc.
    resource_id    TEXT,        -- string representation of resource PK
    -- Sanitized parameters (no secrets, no raw SQL with data values)
    parameters     JSONB,
    -- Outcome
    outcome        TEXT         NOT NULL
                   CHECK (outcome IN ('success', 'denied', 'error')),
    error_detail   TEXT,
    PRIMARY KEY (id, timestamp)
);

SELECT create_hypertable(
    'audit_trail',
    'timestamp',
    chunk_time_interval => INTERVAL '1 month',
    if_not_exists => TRUE
);

ALTER TABLE audit_trail SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'user_login',
    timescaledb.compress_orderby   = 'timestamp DESC'
);
SELECT add_compression_policy('audit_trail', INTERVAL '30 days');

CREATE INDEX idx_audit_trail_user   ON audit_trail (user_login, timestamp DESC);
CREATE INDEX idx_audit_trail_action ON audit_trail (action_type, timestamp DESC);
CREATE INDEX idx_audit_trail_resource ON audit_trail (resource_type, resource_id, timestamp DESC)
    WHERE resource_type IS NOT NULL;
```

---

### 3.10 `rbac_roles` and `user_role_assignments`

```sql
CREATE TABLE rbac_roles (
    id           SERIAL      PRIMARY KEY,
    name         TEXT        NOT NULL UNIQUE
                 CHECK (name IN ('analyst', 'report_admin', 'rule_author', 'sys_admin')),
    display_name TEXT        NOT NULL,
    description  TEXT,
    -- Canonical list of permission strings granted by this role
    permissions  JSONB       NOT NULL DEFAULT '[]',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO rbac_roles (name, display_name, description, permissions) VALUES
    ('analyst',
     'Analyst',
     'View and triage detections, run custom queries, view reports',
     '["events:read","detections:read","detections:update","reports:read","queries:run"]'),
    ('report_admin',
     'Report Admin',
     'All Analyst permissions plus manage report exports and query templates',
     '["events:read","detections:read","detections:update","reports:read","reports:manage","queries:run","queries:manage","exports:create"]'),
    ('rule_author',
     'Rule Author',
     'All Analyst permissions plus create and modify detection rules',
     '["events:read","detections:read","detections:update","reports:read","queries:run","rules:read","rules:write","rules:enable_disable","suppressions:manage"]'),
    ('sys_admin',
     'System Admin',
     'Full administrative access including system configuration and RBAC management',
     '["*"]');

-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE user_role_assignments (
    id               BIGSERIAL    PRIMARY KEY,
    -- Identity (GitHub login is the canonical identifier)
    github_login     TEXT         NOT NULL,
    github_team_id   BIGINT,      -- if team-based, references a GitHub team
    github_team_slug TEXT,        -- human-readable team slug for display
    saml_subject     TEXT,        -- NameID from SAML assertion (alternative identity)
    -- Role
    role_id          INT          NOT NULL REFERENCES rbac_roles(id),
    -- Scope: 'global' grants access to all orgs/repos visible in the event store.
    -- 'org' restricts to the named org. 'repo' restricts to the named repo.
    scope_type       TEXT         NOT NULL
                     CHECK (scope_type IN ('global', 'org', 'repo')),
    scope_value      TEXT,        -- org name or repo full_name; NULL when scope_type='global'
    -- Validity
    granted_by       TEXT         NOT NULL,
    granted_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    expires_at       TIMESTAMPTZ, -- NULL = no expiry
    active           BOOLEAN      NOT NULL DEFAULT TRUE,
    CONSTRAINT chk_scope_value CHECK (
        (scope_type = 'global' AND scope_value IS NULL)
        OR (scope_type IN ('org', 'repo') AND scope_value IS NOT NULL)
    ),
    UNIQUE (github_login, role_id, scope_type, COALESCE(scope_value, ''))
);

CREATE INDEX idx_role_assign_login  ON user_role_assignments (github_login, active);
CREATE INDEX idx_role_assign_team   ON user_role_assignments (github_team_id, active)
    WHERE github_team_id IS NOT NULL;
CREATE INDEX idx_role_assign_scope  ON user_role_assignments (scope_type, scope_value, active);
```

---

### 3.11 `rule_definitions` and `rule_versions`

```sql
CREATE TABLE rule_definitions (
    id                BIGSERIAL    PRIMARY KEY,
    name              TEXT         NOT NULL,
    slug              TEXT         NOT NULL UNIQUE,  -- URL-safe identifier
    description       TEXT,
    -- Categorization
    category          TEXT         NOT NULL,
    -- Values: 'exfiltration', 'account_compromise', 'privilege_escalation',
    --   'secret_leakage', 'supply_chain', 'branch_protection_bypass',
    --   'pat_abuse', 'impossible_travel', 'off_hours_anomaly', 'other'
    -- Defaults (overridden by severity_configs)
    default_severity   TEXT        NOT NULL
                       CHECK (default_severity IN ('critical', 'high', 'medium', 'low', 'info')),
    default_confidence TEXT        NOT NULL
                       CHECK (default_confidence IN ('high', 'medium', 'low')),
    -- Rule implementation
    logic_type         TEXT        NOT NULL
                       CHECK (logic_type IN ('threshold', 'pattern', 'sequence', 'statistical')),
    -- JSON config interpreted by the Detection Engine's DSL.
    -- Schema varies by logic_type (see docs/rule-dsl-reference.md).
    logic_config       JSONB       NOT NULL,
    -- Lifecycle
    enabled            BOOLEAN     NOT NULL DEFAULT TRUE,
    status             TEXT        NOT NULL DEFAULT 'active'
                       CHECK (status IN ('draft', 'active', 'deprecated')),
    -- Versioning
    version            INT         NOT NULL DEFAULT 1,
    git_commit_sha     TEXT,       -- GitHub commit SHA of last save
    -- Authorship
    created_by         TEXT        NOT NULL,
    updated_by         TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_rules_enabled   ON rule_definitions (enabled, status)
    WHERE enabled = TRUE AND status = 'active';
CREATE INDEX idx_rules_category  ON rule_definitions (category);

-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE rule_versions (
    id             BIGSERIAL    PRIMARY KEY,
    rule_id        BIGINT       NOT NULL REFERENCES rule_definitions(id) ON DELETE CASCADE,
    version        INT          NOT NULL,
    logic_config   JSONB        NOT NULL,  -- snapshot of config at this version
    change_summary TEXT,
    changed_by     TEXT         NOT NULL,
    git_commit_sha TEXT,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (rule_id, version)
);
```

---

### 3.12 `idp_actor_enrichments`

Actor metadata synchronized from IdP providers.

```sql
CREATE TABLE idp_actor_enrichments (
    id                BIGSERIAL    PRIMARY KEY,
    github_login      TEXT         NOT NULL,
    idp_provider      TEXT         NOT NULL
                      CHECK (idp_provider IN ('okta', 'entra', 'google_workspace')),
    -- IdP-sourced fields
    idp_user_id       TEXT,
    email             TEXT,
    display_name      TEXT,
    department        TEXT,
    title             TEXT,
    employment_status TEXT
                      CHECK (employment_status IN ('active', 'inactive', 'unknown')),
    manager_login     TEXT,        -- GitHub login of manager (if known)
    location          TEXT,
    timezone          TEXT,        -- IANA timezone, e.g. "America/New_York"
    -- Full raw attributes for future extensibility
    raw_attributes    JSONB        NOT NULL DEFAULT '{}',
    -- Sync metadata
    last_synced_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    sync_error        TEXT,        -- last sync error, NULL if last sync succeeded
    UNIQUE (github_login, idp_provider)
);

CREATE INDEX idx_idp_enrichments_login ON idp_actor_enrichments (github_login);
```

---

### 3.13 `ticketing_configs` and `tickets`

```sql
CREATE TABLE ticketing_configs (
    id                     SERIAL      PRIMARY KEY,
    provider               TEXT        NOT NULL
                           CHECK (provider IN ('jira', 'github_issues')),
    display_name           TEXT        NOT NULL,
    -- Jira: full base URL (e.g. https://company.atlassian.net)
    -- GitHub Issues: owner/repo (e.g. security-team/findings)
    target                 TEXT        NOT NULL,
    project_key            TEXT,       -- Jira project key (e.g. "SEC")
    default_issue_type     TEXT        NOT NULL DEFAULT 'Bug',
    -- Maps severity strings to provider priority/label values
    -- e.g. {"critical": "Highest", "high": "High", ...}
    severity_priority_map  JSONB       NOT NULL DEFAULT '{}',
    -- Auto-creation rules
    auto_create            BOOLEAN     NOT NULL DEFAULT FALSE,
    auto_create_severities TEXT[]      NOT NULL DEFAULT ARRAY['critical', 'high'],
    -- Credential stored in environment variable (never in DB)
    -- The value here is the env var NAME, not the secret itself.
    credential_env_var     TEXT        NOT NULL,
    -- State
    enabled                BOOLEAN     NOT NULL DEFAULT TRUE,
    created_by             TEXT        NOT NULL,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE tickets (
    id                  BIGSERIAL    PRIMARY KEY,
    ticketing_config_id INT          NOT NULL REFERENCES ticketing_configs(id),
    detection_id        BIGINT       NOT NULL REFERENCES detections(id),
    -- External system identifiers
    external_id         TEXT         NOT NULL,  -- Jira key (SEC-123) or GH issue number
    external_url        TEXT         NOT NULL,
    -- Mirrored status from external system
    external_status     TEXT,
    -- Authorship
    created_by          TEXT         NOT NULL,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    last_synced_at      TIMESTAMPTZ,
    UNIQUE (ticketing_config_id, detection_id)
);

CREATE INDEX idx_tickets_detection_id ON tickets (detection_id);
```

---

### 3.14 `notification_configs`

Admin-configured notification channels.

```sql
CREATE TABLE notification_configs (
    id                     SERIAL      PRIMARY KEY,
    channel_type           TEXT        NOT NULL
                           CHECK (channel_type IN ('slack', 'email')),
    display_name           TEXT        NOT NULL,
    -- Slack: webhook URL or channel ID (stored in env var referenced below)
    -- Email: comma-separated SMTP recipient addresses
    target                 TEXT        NOT NULL,
    -- Credential env var name (for Slack token or SMTP password)
    credential_env_var     TEXT,
    -- Which severity levels trigger this channel
    notify_severities      TEXT[]      NOT NULL DEFAULT ARRAY['critical', 'high'],
    -- Cooldown: suppress repeat notifications for same detection within N seconds
    cooldown_seconds       INT         NOT NULL DEFAULT 3600,
    enabled                BOOLEAN     NOT NULL DEFAULT TRUE,
    created_by             TEXT        NOT NULL,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

## 4. Technology Stack Table

| Component | Technology | Version | License | Justification |
|-----------|------------|---------|---------|---------------|
| Python Runtime | CPython | 3.12 | PSF-2.0 | Long-term support; async `asyncio` performance improvements over 3.11 |
| Web Framework | FastAPI | 0.111 | MIT | Native async, Pydantic v2 integration, OpenAPI 3.1 auto-generation |
| Data Validation | Pydantic | 2.7 | MIT | 5–50× faster than v1; Python dataclass-compatible; JSON schema output |
| ORM | SQLAlchemy | 2.0 | MIT | Async-first 2.x API; supports `asyncpg`; established in stack |
| Async PG driver | asyncpg | 0.29 | Apache-2.0 | Fastest Python PostgreSQL driver; native binary protocol |
| DB Migrations | Alembic | 1.13 | MIT | Standard SQLAlchemy migration tool; auto-generated from models |
| Task Queue | Celery | 5.4 | BSD-3-Clause | Mature; supports Valkey broker; beat scheduler for periodic tasks |
| State Store / Broker | Valkey | 7.2 | BSD-3-Clause | Linux Foundation Redis 7.2 fork; fully API-compatible; avoids RSAL |
| Python Valkey client | redis-py | 5.0 | MIT | API-compatible with Valkey; used by both app code and Celery |
| Primary Database | PostgreSQL | 16 | PostgreSQL License | ACID, JSONB, partitioning, row-level security, pgcrypto |
| Time-Series Extension | TimescaleDB OSS | 2.14 | Apache-2.0 | Automatic chunking, compression, continuous aggregates, retention policies |
| S3 Client | boto3 | 1.34 | Apache-2.0 | Official AWS SDK; streaming object reads; also used as MinIO client (same S3 protocol) |
| Azure Blob Client | azure-storage-blob | 12.19 | MIT | Official Azure SDK; streaming blob reads |
| Embedded Object Store | MinIO | RELEASE.2024-06 | AGPL-3.0 | S3-compatible self-hosted object store; GitHub streams directly here; push notifications via bucket events → Valkey pub/sub; eliminates need for external cloud storage in simple deployments |
| HTTP Client | httpx | 0.27 | BSD-3-Clause | Async-first; used by enrichment and ticketing services |
| GeoIP Lookup | MaxMind GeoLite2 + geoip2 | DB 2024, lib 4.8 | CC BY-SA 4.0 / Apache-2.0 | Industry-standard IP geolocation; includes proxy/VPN detection; free tier |
| OAuth 2.0 | Authlib | 1.3 | BSD-3-Clause | Full OAuth 2.0 / OIDC client; GitHub OAuth integration |
| SAML 2.0 | python3-saml | 1.16 | MIT | Battle-tested SAML SP implementation; strict mode by default |
| JWT | PyJWT | 2.8 | MIT | Lightweight HS256 JWT sign/verify |
| Rate Limiting | slowapi | 0.1.9 | MIT | FastAPI-native rate limiting via decorators |
| SQL AST Validation | pglast | 6.x | GPL-3.0 | Parse user SQL to AST for whitelist validation before execution |
| Data Processing | pandas | 2.2 | BSD-3-Clause | Used by Behavioral Baseline Engine for rolling window stats |
| Jinja2 Templates | Jinja2 | 3.1 | BSD-3-Clause | Notification message templates |
| Jira API | atlassian-python-api | 3.41 | Apache-2.0 | Jira REST API wrapper |
| GitHub API | PyGithub | 2.3 | LGPL-3.0 | GitHub Issues creation and status sync |
| Okta SDK | okta-sdk-python | 2.x | Apache-2.0 | IdP enrichment: Okta user metadata |
| Microsoft Entra | msal | 1.x | MIT | IdP enrichment: Entra ID user metadata |
| Google Workspace | google-auth + google-api-python | 2.x | Apache-2.0 | IdP enrichment: Google Workspace user metadata |
| Git Backend | GitHub | API | N/A | Remote GitHub repository for rule YAML version history; requires `GITHUB_RULES_REPO` + `GITHUB_RULES_TOKEN` |
| GitPython | GitPython | 3.1 | BSD-3-Clause | API→Git commit sync for rule saves |
| Slack Notifications | slack-sdk | 3.30 | MIT | Official Slack SDK; supports Webhook and Web API |
| SMTP Notifications | aiosmtplib | 3.0 | MIT | Async SMTP client; TLS support |
| Frontend Framework | React | 18.3 | MIT | Established in stack; large ecosystem |
| Frontend Language | TypeScript | 5.4 | Apache-2.0 | Type safety; established in stack |
| Frontend Build | Vite | 5.4 | MIT | Fast HMR; established in stack |
| CSS Framework | TailwindCSS | 3.4 | MIT | Established in stack; utility-first |
| Data Fetching | TanStack Query | 5.x | MIT | Server state management; caching; background refetch |
| Charts | Apache ECharts | 5.5 | Apache-2.0 | Rich chart types; performant with large datasets |
| Query Builder UI | @react-querybuilder | 7.x | MIT | Visual SQL / filter builder; exports to SQL |
| Code Editor | Monaco Editor | 0.49 | MIT | VS Code's editor engine; SQL syntax highlighting |
| Frontend Test | Vitest | 1.x | MIT | Established in stack |
| E2E Testing | Playwright | 1.44 | Apache-2.0 | Established in stack |
| Backend Test | pytest + pytest-asyncio | 8.x | MIT | Standard Python test runner |
| Linting (Python) | ruff | 0.4 | MIT | Single-tool linter + formatter; fast |
| Type Checking (Python) | mypy | 1.10 | MIT | Static type checking |
| Security Scanning | bandit | 1.7 | Apache-2.0 | Python security linter; run in CI |
| Dependency Audit | pip-audit | 2.7 | Apache-2.0 | PyPA vulnerability scanner; run in CI |
| Container Runtime | Docker | 27.x | Apache-2.0 | Container packaging |
| Orchestration | Kubernetes | 1.30 | Apache-2.0 | Production orchestration |
| Helm | Helm | 3.15 | Apache-2.0 | Kubernetes packaging |
| Static Server | nginx | 1.26 | BSD-2-Clause | Serves React SPA; reverse proxy to FastAPI |

> **Note on MinIO AGPL-3.0:** MinIO is licensed under AGPL-3.0. Because this project is already open-source (and MinIO runs as a separate service process, not linked into the application), the AGPL copyleft obligation is satisfied by the project's own open-source license. Operators who require a non-AGPL embedded store may substitute any S3-compatible alternative (e.g., SeaweedFS — Apache 2.0) by updating the MinIO service definition; the ingestion worker uses standard `boto3` and requires no code changes.

> **Note on pglast GPL-3.0:** pglast is used only server-side for SQL validation at the API layer boundary. As a web application, the GPL-3.0 license requires the application itself to be open-source — which is already the case. If a commercial fork is created later, replace pglast with sqlglot (MIT) and implement a custom AST validation pass.

---

## 5. Technical Risks

### Risk 1: TimescaleDB Hypertable Deduplication Constraint

**Description:** TimescaleDB hypertables cannot have a globally unique index on a column that does not include the partitioning column (`created_at`). A naive `UNIQUE (document_id)` constraint will fail on partition boundaries.

**Probability:** Certain (architectural constraint, not hypothetical).

**Impact:** Without mitigation, re-processed files produce duplicate events, corrupting detection counts and metrics.

**Mitigation:**
- Implement the two-layer dedup strategy: Valkey SET (24h TTL, O(1) hot path) → `event_dedup` lookup table (authoritative, PostgreSQL index).
- All inserts use `ON CONFLICT (document_id) DO NOTHING` scoped to the relevant weekly chunk.
- Transaction atomically commits event insert + `event_dedup` insert + cursor advance. If the transaction fails, no cursor advance occurs and the batch is retried safely.
- Add integration test in CI that re-processes the same `.json.gz` file and asserts event count remains unchanged.

---

### Risk 2: Impossible-Travel False Positives from Shared Infrastructure

**Description:** GitHub Actions runners, corporate NAT gateways, CDN edge nodes, and VPNs all share IP addresses across many users. The impossible-travel rule comparing consecutive source IPs for the same actor will fire constantly in these environments.

**Probability:** High for any enterprise using GitHub Actions or a corporate proxy.

**Impact:** Immediate analyst alert fatigue, loss of trust in the detection system, pressure to disable the rule entirely.

**Mitigation:**
- Ship the rule with `default_confidence = 'low'` and a prominent UI note explaining the VPN/NAT caveat.
- Add an admin-portal field for "trusted CIDR ranges" stored in `severity_configs.logic_config`; impossible-travel detections originating entirely within trusted CIDRs are suppressed automatically.
- Require a velocity threshold (≥ 2 impossible travel events within 1 hour) before escalating confidence to `medium`.
- Document the limitation in the rule description and link to tuning guidance.

---

### Risk 3: S3 / Azure Blob Listing Performance During Backfill

**Description:** A 1-year backfill for a large enterprise could enumerate 500,000+ object keys. S3 `ListObjectsV2` returns a maximum of 1,000 keys per API call, and Azure Blob `list_blobs` pages similarly. Listing alone could take hours.

**Probability:** High for any enterprise that enables the analyzer months or years after streaming was configured.

**Impact:** Initial data load blocks useful analysis; long-running list operations may timeout or consume all ingestion worker capacity.

**Mitigation:**
- Implement prefix-range partitioning for backfill: split the date range across multiple `ingestion_cursors` rows (one row per month), each processed by a separate worker in parallel.
- Use `StartAfter` (S3) / `name_starts_with` combined with marker (Azure) to page efficiently within each prefix.
- Expose a "Start Backfill" action in the admin portal that pre-seeds cursor rows for a specified date range.
- Rate-limit the listing loop to avoid S3/Azure throttling (default: 100ms sleep between list pages).

---

### Risk 4: SAML XML Signature Wrapping and XXE Vulnerabilities

**Description:** SAML 2.0 parsing is notoriously vulnerable to XML Signature Wrapping (XSW) attacks (where an attacker inserts a second valid XML element to confuse the signature validator) and XML External Entity (XXE) injection.

**Probability:** Low in normal operation, but high if a malicious or misconfigured IdP is pointed at the system.

**Impact:** Authentication bypass — an attacker could authenticate as any user including `sys_admin`.

**Mitigation:**
- Use python3-saml exclusively; never implement custom XML parsing for SAML assertions.
- Enable `strict=True` in python3-saml's `OneLogin_Saml2_Auth` constructor — this rejects unsigned responses.
- Pin and validate the IdP's X.509 certificate in `idp_actor_enrichments.raw_attributes`; reject certificate changes without admin confirmation.
- Disable `load_defusedxml` fallbacks; use defusedxml library directly to parse all XML inputs, preventing XXE.
- Add CI test asserting that a forged unsigned SAML assertion is rejected.

---

### Risk 5: Self-Service Query Engine SQL Injection and Data Exfiltration

**Description:** The self-service query interface allows users to write arbitrary SQL. A malicious or compromised analyst account could craft queries to bypass org/repo scope isolation or exfiltrate `audit_trail` and `ticketing_configs` data.

**Probability:** Medium — scope bypass requires knowledge of PostgreSQL internals, but is well-documented.

**Impact:** Complete data isolation failure; unauthorized access to other organizations' event data.

**Mitigation:**
- All user SQL is parsed to an AST by pglast before execution. The validator enforces: (a) only `SELECT` statements, (b) only explicitly whitelisted tables/views (`events`, `detections`, and continuous aggregate views), (c) no schema-qualified names (`information_schema`, `pg_catalog`), (d) no function calls outside an allowed list, (e) no `COPY`, `\copy`, or set-returning functions.
- Queries execute under `readonly_query_user` PostgreSQL role, which has `GRANT SELECT` only on the allowed tables and no access to `audit_trail`, system catalogs, or config tables.
- The mandatory scope predicate (`WHERE org = ANY(:orgs)`) is injected as a CTE wrapper by the engine, not appended — the user cannot override it.
- Query execution timeout: 30 seconds. Result row cap: 100,000 rows.

---

### Risk 6: Rule Author Privilege through Arbitrary Logic Execution

**Description:** Rule definitions contain `logic_config JSONB` interpreted by the Detection Engine. If the interpreter uses Python `eval()`, `exec()`, or dynamic import, a malicious rule author could execute arbitrary code on the detection workers.

**Probability:** Low if the DSL is implemented correctly, but catastrophic if it is not.

**Impact:** Full remote code execution on the backend, credential exfiltration via environment variables, lateral movement to PostgreSQL and Valkey.

**Mitigation:**
- The Detection Engine DSL interpreter is a bounded JSON evaluator — it evaluates comparisons, threshold counts, and field references expressed as JSON objects. It never calls `eval()`, `exec()`, `compile()`, or `importlib`.
- Rule `logic_config` JSON schemas are validated against a strict JSON Schema before saving (`rule_definitions.logic_config` has a `CHECK` constraint via a PostgreSQL function that calls `jsonschema_validate()`).
- All rule changes are recorded in `rule_versions` and `audit_trail` with the author's login.
- Detection workers run with a non-root OS user and no file system write access outside the mmdb directory.

---

### Risk 7: Ingestion Cursor Gap or Duplication on Worker Crash

**Description:** If an ingestion worker crashes after inserting events but before committing the cursor update, the batch will be re-processed on restart. If it crashes after the cursor advances but before events are inserted, those events are silently skipped.

**Probability:** Medium — worker crashes are normal in containerized environments (OOM kill, node eviction).

**Impact:** Duplicate detections from re-processed events (mitigated by dedup), or — worse — silent event loss if cursor advances without insert.

**Mitigation:**
- Cursor advance and event insert are wrapped in a single PostgreSQL transaction. The cursor never advances unless events are committed.
- `INSERT ... ON CONFLICT (document_id) DO NOTHING` makes the event insert idempotent. Re-running the same batch after a crash produces zero duplicate rows.
- The `event_dedup` table insert is also within the same transaction.
- Worker startup performs a consistency check: if a cursor row has `last_processed_at` older than 2× `poll_interval_sec`, the worker resets the cursor to the last committed prefix, not a cached in-memory value.
- Dead workers release their `FOR UPDATE` lock automatically when the PostgreSQL connection is closed.

---

### Risk 8: IdP Enrichment Token Expiry Silently Breaking Actor Context

**Description:** IdP API tokens (Okta, Entra, Google Workspace) expire or are revoked. If the enrichment sync fails silently, the `idp_actor_enrichments` table becomes stale and detection rules relying on `employment_status = 'active'` produce incorrect results.

**Probability:** High over the lifetime of a deployment — token rotation is routine.

**Impact:** Detection rules that reference IdP employment status become unreliable; `inactive` employees appear as `active`; false negatives for insider threat rules.

**Mitigation:**
- Enrichment sync failures update `idp_actor_enrichments.sync_error` with the error message and timestamp.
- A Celery Beat health check task (`enrichment.health_check`) runs every 30 minutes and writes an `alert` to the API Layer if any IdP connection has not synced successfully within 2× its configured sync interval.
- The admin portal displays IdP sync health prominently on the dashboard with last-synced timestamps.
- Detection rules that depend on IdP data include a `requires_idp_sync` flag in `logic_config`; if the required provider's last sync is stale (configurable threshold), the rule emits `confidence = 'low'` detections rather than `high`.
- Document in the operator guide that IdP tokens should be service account tokens with long-lived expiry or rotated via automation.

---

### Risk 9: Event Volume Spike Overwhelming Detection Workers

**Description:** A security incident (e.g., mass repo cloning during a breach) or an automated process (CI/CD pipeline running thousands of Actions jobs) can generate a spike of hundreds of thousands of events in minutes. The detection worker queue depth can fall behind, causing detection latency to grow and detection task results to expire in Valkey.

**Probability:** Medium — spike events are a defining characteristic of the threat scenarios we detect.

**Impact:** Detections are delayed (defeating the 1–15 minute near-real-time SLA) or, if Valkey result TTL is shorter than queue depth, task results are lost.

**Mitigation:**
- Detection tasks are enqueued with a dedicated `detection` Celery queue with its own worker pool, isolated from ingestion and notification workers.
- Celery task result backend TTL is set to 1 hour (configurable). Detection tasks are fire-and-forget (no caller awaits the result); results are written directly to PostgreSQL, making Valkey TTL irrelevant to correctness.
- Worker autoscaling is supported in Kubernetes via KEDA (Kubernetes Event-Driven Autoscaling) scaling on Valkey queue depth — document and provide a KEDA `ScaledObject` in the Helm chart.
- Rate-limit detection per rule: if a single rule fires more than 50 detections within a 5-minute window for the same actor, subsequent matches are batched into a single "high-volume detection" record to prevent detection table bloat.

---

### Risk 10: MaxMind GeoLite2 License Compliance

**Description:** MaxMind GeoLite2 databases require a free account registration and prohibit redistribution of the database file in raw form. Bundling the mmdb file in the container image violates the terms of service.

**Probability:** Certain if the database is baked into the Docker image.

**Impact:** Compliance violation; potential legal exposure for users of the open-source distribution; MaxMind account suspension.

**Mitigation:**
- The mmdb file is **never** bundled in the container image.
- The Docker and Helm deployments include a GeoIP Update sidecar container (or init container) that downloads the database at startup using the operator's `MAXMIND_ACCOUNT_ID` and `MAXMIND_LICENSE_KEY` environment variables.
- The `geoip-updater` is the official MaxMind-compatible `maxmind/geoipupdate` Docker image (Apache-2.0).
- If no MaxMind credentials are configured, the GeoIP fields (`geo_*`) are stored as NULL; GeoIP-dependent detection rules (`impossible_travel`, `geo_anomaly`) emit `confidence = 'low'` with a warning in the detection description.
- Document the MaxMind free license registration process in `DEPLOYMENT.md`.

---

*End of Architecture Document*
