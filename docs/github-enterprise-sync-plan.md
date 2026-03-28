# GitHub Enterprise Sync — Implementation Plan

**Status:** Draft — Ready for Development  
**Date:** 2026-03-27  
**Constraint Summary:** GitHub App auth only (no PATs). Full rate-limit compliance. Non-destructive upserts. Admin-triggered + scheduled (60–90 day interval). Sync progress visible in the UI via polling. Manual file ingest (audit log exports, Copilot usage exports) supported from the UI.

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)
2. [User Stories & Acceptance Criteria](#2-user-stories--acceptance-criteria)
3. [What We Sync](#3-what-we-sync)
4. [Authentication: GitHub App Model](#4-authentication-github-app-model)
5. [Rate Limit Compliance Strategy](#5-rate-limit-compliance-strategy)
6. [System Architecture](#6-system-architecture)
7. [Data Model Changes](#7-data-model-changes)
8. [New Services: Token Manager & Rate Limiter](#8-new-services-token-manager--rate-limiter)
9. [Celery Task Design](#9-celery-task-design)
10. [API Endpoints](#10-api-endpoints)
11. [Configuration Changes](#11-configuration-changes)
12. [Alembic Migration Plan](#12-alembic-migration-plan)
13. [Security Controls](#13-security-controls)
14. [Conflict Resolution Policy](#14-conflict-resolution-policy)
15. [Scheduler Design](#15-scheduler-design)
16. [Testing Plan](#16-testing-plan)
17. [Phased Rollout](#17-phased-rollout)
18. [Open Questions](#18-open-questions)
19. [Sync Progress UI](#19-sync-progress-ui)
20. [Manual File Ingest](#20-manual-file-ingest)

---

## 1. Problem Statement

Octowatch's detection engine only knows about entities that have appeared in the streaming audit log since deployment. This creates three concrete security gaps:

- **Baseline blindness:** Users, repos, teams, and collaborators that existed before Octowatch went live are invisible to detection rules that compare against "known good" state.
- **Outside collaborator gaps:** The `external_collaborators` table only gets populated when an `outside_collaborator.add` event flows through. Anyone granted access before Octowatch was deployed is a ghost.
- **Drift over time:** Even after initial hydration, events can be missed during ingestion outages, backfill gaps, or configuration changes, causing silent divergence between Octowatch's model and reality.

The **GitHub Enterprise Sync Task** closes these gaps by performing a full snapshot of the enterprise from the GitHub API on first run and periodically thereafter.

---

## 2. User Stories & Acceptance Criteria

### US-01 — GitHub App Credential Configuration

> *As a* sys_admin, *I want to* configure GitHub App credentials so Octowatch can authenticate to GitHub without PATs.

```
Given I set GITHUB_APP_ID, GITHUB_APP_PRIVATE_KEY_PATH, and GITHUB_ENTERPRISE_SLUG
When the application starts
Then it validates the credentials by minting a test JWT
And if validation fails, sync is disabled with a structured error log (app keeps running)
And the private key is never written to DB, logs, or API responses
```

### US-02 — Manual Full Sync Trigger

> *As a* sys_admin, *I want to* trigger a full enterprise sync on demand.

```
Given I am authenticated as sys_admin
When I POST /api/v1/admin/sync/trigger with {"mode": "full"}
Then a sync run is created (status="pending"), a Celery task is queued,
     and I receive 202 with {run_id, status, triggered_by, triggered_at}

Given a sync is already running
When I POST /api/v1/admin/sync/trigger
Then I receive 409 Conflict — no duplicate task dispatched

Given I am NOT a sys_admin
When I POST /api/v1/admin/sync/trigger
Then I receive 403 Forbidden
```

### US-03 — Sync Status Visibility

> *As a* sys_admin, *I want to* see progress and history of sync runs.

```
Given runs exist
When I GET /api/v1/admin/sync/runs
Then I receive a paginated list sorted by started_at desc with
     {run_id, status, triggered_by, started_at, completed_at, progress_pct}

When I GET /api/v1/admin/sync/runs/{run_id}
Then I receive per-entity breakdown: {entity_type, status, records_upserted,
     records_failed, started_at, completed_at}
```

### US-04 — Configurable Schedule

> *As a* sys_admin, *I want to* configure how often automatic syncs run (60–90 days).

```
Given GITHUB_SYNC_INTERVAL_DAYS=60 (default)
When the scheduler heartbeat runs daily at 02:00 UTC
Then it checks whether last completed sync was >= 60 days ago
And dispatches a new sync if so

Given GITHUB_SYNC_INTERVAL_DAYS=50 (invalid)
When the application starts
Then startup validation raises ConfigurationError and exits
```

### US-05 — Cancellation

> *As a* sys_admin, *I want to* cancel a running sync to protect the rate limit budget.

```
Given a sync is running
When I DELETE /api/v1/admin/sync/runs/{run_id}/cancel
Then the run transitions to "cancelling", the task receives a soft shutdown,
     saves its current cursor, then transitions to "cancelled"
And a subsequent trigger resumes from the saved cursor
```

### US-06 — Resumable Sync

> *As a* sys_admin, *I want to* resume a failed/cancelled sync from where it left off.

```
Given a sync run with status="cancelled" or "failed" and saved cursors
When I POST /api/v1/admin/sync/trigger with {"mode": "resume", "run_id": X}
Then only entity/org combinations whose cursor status != "completed" are re-queued
And those with saved cursors resume from their last page, not from page 1
```

### US-07 — Outside Collaborator Baseline

> *As a* security analyst, *I want* the sync to populate `external_collaborators` from the live API so detection rules work from day one.

```
Given outside collaborators exist in GitHub before Octowatch was deployed
When the enterprise sync completes
Then each collaborator appears in external_collaborators with
     is_active=true, role set correctly, data_source="github_api_sync"

Given a collaborator is active in external_collaborators (from past events)
     but has been removed in GitHub
When sync processes that repo
Then the record is updated: is_active=false, removed_at=sync_timestamp
And no record is hard-deleted
```

### US-08 — Automated Scheduler

> *As a* Celery scheduler, *I want to* check daily whether a sync is due and dispatch one if needed.

```
Given beat_schedule includes enterprise-sync-heartbeat running daily
When the heartbeat executes
Then it dispatches a sync if: last_completed_at IS NULL,
     OR last_completed_at + interval_days < now
And it writes a structured log line with the decision outcome
```

### US-09 — Sync Progress in the UI

> *As a* sys_admin, *I want to* see real-time sync progress in the UI without leaving the page.

```
Given a sync run is in status="running"
When I navigate to the Admin > Data Sync page
Then I see a progress bar displaying (completed_entities / total_entities)
And I see a per-entity status table refreshing automatically every 5 seconds
And each entity row shows status, records upserted, and elapsed time
And the page stops auto-refreshing once status transitions to a terminal state
     (completed, failed, cancelled)

Given the last sync completed successfully
When I view the Sync page
Then I see the completion summary: total records, duration, next scheduled sync date
```

### US-10 — Manual Audit Log File Upload

> *As a* sys_admin, *I want to* upload a GitHub audit log export file so I can backfill events without re-configuring an ingestion source.

```
Given I have a GitHub audit log JSON/NDJSON export downloaded from the GitHub UI
When I drag-and-drop or select the file in the Admin > Import Data UI
Then the file is uploaded and a background ingest job is created
And I see a progress bar for the import job that updates as rows are processed
And on completion I see a summary: {rows_ingested, rows_skipped_dedup, errors}

Given I upload a file that is not valid JSON or NDJSON
When the backend validates it
Then I receive a 422 with a descriptive error before any rows are processed

Given the file exceeds the configured size limit (default 500 MB)
When I attempt to upload
Then the UI rejects it client-side with a clear error message before sending
```

### US-11 — Manual Audit Log Git Export Upload

> *As a* sys_admin, *I want to* upload a GitHub audit log git export so git-activity events are backfilled into Octowatch.

```
Given I have a GitHub audit log git export (separate from the main audit log export)
When I upload it via the Import Data UI selecting type="audit_log_git"
Then it is parsed with the git-event schema (different field structure)
And events are ingested into the events table with ingestion_source="manual_git_export"
And deduplication prevents re-inserting events already present
```

### US-12 — Manual Copilot Usage Metrics Upload

> *As a* sys_admin, *I want to* upload a Copilot usage metrics export so usage data is populated in Octowatch.

```
Given I have a Copilot usage metrics NDJSON export
When I upload it via the Import Data UI selecting type="copilot_usage"
Then it is parsed by the existing copilot import logic (from import_copilot_usage.py)
And the processed rows are stored in the appropriate Copilot usage tables
And I see a job status page showing rows processed and any parse errors
```

---

## 3. What We Sync

The table below is ordered by the sync execution sequence (dependency order). Phase 1 is required for MVP; phases 2–4 are iterative enhancements.

### 3.1 Entity Catalog

| # | Entity | GitHub API Endpoint | Security Value | Phase |
|---|--------|---------------------|----------------|-------|
| 1 | Enterprise orgs | `GET /enterprises/{slug}/organizations` | Detect shadow orgs, enumerate scope | 1 |
| 2 | Enterprise members | `GET /enterprises/{slug}/members` | Ghost accounts, churned-employee access | 1 |
| 3 | GitHub App installations (org) | `GET /orgs/{org}/installations` | Third-party supply chain risk | 1 |
| 4 | Org members + roles | `GET /orgs/{org}/members?role=all` | Over-privileged owners | 1 |
| 5 | Outside collaborators | `GET /orgs/{org}/outside_collaborators` | Guest access = #1 lateral movement vector | 1 |
| 6 | SAML credential authorizations | `GET /orgs/{org}/credential-authorizations` | Unlinked PATs/OAuth tokens | 1 |
| 7 | Secret scanning alerts (open) | `GET /repos/{owner}/{repo}/secret-scanning/alerts?state=open` | Active exposed credentials | 1 |
| 8 | Repository inventory | `GET /orgs/{org}/repos` | Visibility, archived/fork status | 1 |
| 9 | Org metadata (2FA, default perm) | `GET /orgs/{org}` | Missing 2FA requirement, permissive defaults | 1 |
| 10 | Teams | `GET /orgs/{org}/teams` | Feeds RBAC modeling | 2 |
| 11 | Team memberships | `GET /orgs/{org}/teams/{slug}/members` | Overprivileged team membership | 2 |
| 12 | Team repositories | `GET /orgs/{org}/teams/{slug}/repos` | Excess repo access via teams | 2 |
| 13 | Direct repo collaborators | `GET /repos/{owner}/{repo}/collaborators?affiliation=direct` | Out-of-band access grants | 2 |
| 14 | Branch protection rules | `GET /repos/{owner}/{repo}/branches/{branch}/protection` | Unprotected default branches | 2 |
| 15 | Dependabot alerts (open) | `GET /repos/{owner}/{repo}/dependabot/alerts?state=open` | Vulnerable dependencies baseline | 2 |
| 16 | Org webhooks | `GET /orgs/{org}/hooks` | Exfiltration via unauthorized webhooks | 3 |
| 17 | Repo webhooks | `GET /repos/{owner}/{repo}/hooks` | Repo-level exfiltration risk | 3 |
| 18 | Code scanning config | `GET /repos/{owner}/{repo}/code-scanning/default-setup` | Security coverage gaps | 3 |
| 19 | Actions permissions (org + repo) | `GET /orgs/{org}/actions/permissions` | External/public Actions supply chain | 3 |
| 20 | Self-hosted runners (org) | `GET /orgs/{org}/actions/runners` | Arbitrary workload execution | 3 |
| 21 | Deploy keys | `GET /repos/{owner}/{repo}/keys` | Persistent SSH credential inventory | 3 |
| 22 | Enterprise IP allow list | GraphQL: `enterpriseAdministration.ipAllowListEntries` | Network access control baseline | 4 |
| 23 | Environments + protection rules | `GET /repos/{owner}/{repo}/environments` | Deployment gate configurations | 4 |
| 24 | Packages | `GET /orgs/{org}/packages` | Supply chain provenance | 4 |

### 3.2 Dependency-Ordered Execution Graph

```
Enterprise
  └─▶ Orgs (enumerate before all per-org work)
        └─▶ Org metadata
        └─▶ Org members
        └─▶ Outside collaborators     ← writes to existing external_collaborators table
        └─▶ SAML credential auths
        └─▶ GitHub App installations
        └─▶ Teams
              └─▶ Team memberships
              └─▶ Team repositories
        └─▶ Repositories              ← must complete before repo-level entities
              └─▶ Direct collaborators
              └─▶ Branch protections
              └─▶ Secret scanning alerts
              └─▶ Dependabot alerts
              └─▶ Webhooks
              └─▶ Code scanning config
              └─▶ Deploy keys
              └─▶ Environments
```

Repositories are the deepest and most numerous entity. A large enterprise can have 10,000+ repos. Repo-level entities are fanned out into per-repo child tasks (see §9).

> **Rate limit note:** For a 10,000-repo enterprise, syncing all Phase 1 repo-level entities (secret scanning alerts + branch protections) requires approximately 20,000 API calls per repo scan pass. At the GHEC installation limit of 15,000 req/hour, a full sync of this scale takes ~1.5 hours. The rate limiter (§5) ensures we stay within budget.

---

## 4. Authentication: GitHub App Model

No Personal Access Tokens are used anywhere in this feature. All GitHub API calls use short-lived installation access tokens derived from the GitHub App.

### 4.1 Token Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│  GitHubAppTokenManager (backend/app/services/github_token_service.py)│
│                                                                     │
│  1. Load RSA private key PEM from disk                              │
│     (path = GITHUB_APP_PRIVATE_KEY_PATH — never the key itself)     │
│                                                                     │
│  2. Mint RS256 JWT:                                                 │
│       iss = GITHUB_APP_ID                                           │
│       iat = now − 60s  (clock skew tolerance)                       │
│       exp = now + 600s (10 min; GitHub maximum)                     │
│                                                                     │
│  3. Check Valkey cache: "github:app:token:{installation_id}"        │
│     HIT  → return cached token (always has ≥5 min remaining TTL)   │
│     MISS → POST /app/installations/{id}/access_tokens               │
│              Authorization: Bearer {jwt}                            │
│            Receive {token, expires_at}  (valid 1 hour)             │
│            Write to Valkey, TTL = expires_at − now − 300s           │
│                                                                     │
│  4. Return token string to caller. Caller never touches key/JWT.    │
└─────────────────────────────────────────────────────────────────────┘
```

### 4.2 Required GitHub App Permissions

The GitHub App must be registered with **read-only** permissions only:

| Resource | Level | Justification |
|----------|-------|---------------|
| Members | Read | Org/enterprise member enumeration |
| Administration | Read | Org settings, branch protection, IP allow list |
| Repository metadata | Read | Repo inventory |
| Secret scanning alerts | Read | Alert baseline |
| Dependabot alerts | Read | Vulnerability baseline |
| Webhooks | Read | Webhook inventory |
| Actions | Read | Actions permissions and runners |
| Environments | Read | Environment protection rules |

> The GitHub App has zero write permissions. All write operations go only to Octowatch's own database.

### 4.3 Multi-Org Support

For enterprises with multiple organizations:

1. Call `GET /app/installations` (authenticated with short-lived App JWT) to enumerate all installations.
2. For each installation where `account.type == "Organization"`, request a scoped token with that org's `installation_id`.
3. Each org token is cached independently in Valkey with its own TTL.
4. The `github_app_configs` table stores one row per (app_id, installation_id) pair with `org_login` set, enabling the sync worker to look up the correct installation ID per org.

---

## 5. Rate Limit Compliance Strategy

GitHub's limits that apply to a GHEC-installed GitHub App:

| Limit Type | Threshold | How We Handle It |
|------------|-----------|------------------|
| Primary rate limit | 15,000 req/hour | Token bucket: 4.17 tokens/sec, burst cap 50 |
| Secondary: concurrency | 100 concurrent | `asyncio.Semaphore(80)` — 20% headroom |
| Secondary: points/min | 900 pts/min (GET=1pt) | Sliding window counter; pause when approaching 900 |
| 429 / 403 response | - | Read `retry-after`, else sleep until `x-ratelimit-reset`, then exponential backoff (1s → 2s → 4s → error) |
| Proactive throttle | remaining < 1,000 | Cap token bucket refill to 1/sec |

### 5.1 GitHubRateLimiter Design

```python
class GitHubRateLimiter:
    # Token bucket: 15,000/hr ≈ 4.17 tokens/sec, max burst 50
    # asyncio.Semaphore(80) for concurrent request cap

    async def acquire(self, cost: int = 1) -> None:
        """Block until tokens available AND semaphore permits."""

    def release(self) -> None:
        """Release semaphore slot after request completes."""

    def update_from_headers(self, headers: httpx.Headers) -> None:
        """Parse x-ratelimit-remaining, x-ratelimit-reset, activate proactive throttle."""

    async def handle_rate_limit_response(self, response: httpx.Response) -> None:
        """Sleep for retry-after / until reset, then add jitter."""
```

Every GitHub API call wraps with:
```python
async with rate_limiter._semaphore:
    await rate_limiter.acquire()
    response = await github_client.get(url, headers=auth_headers)
    rate_limiter.update_from_headers(response.headers)
    if response.status_code in (429, 403):
        await rate_limiter.handle_rate_limit_response(response)
        # retry (handled by Celery task retry with max_retries=3)
```

---

## 6. System Architecture

### 6.1 Component Overview

```
┌──── FastAPI API Server ─────────────────────────────────────────────────┐
│  POST /api/v1/admin/sync/trigger   (sys_admin only)                     │
│  GET  /api/v1/admin/sync/runs      (sys_admin only)                     │
│  GET  /api/v1/admin/sync/config    (sys_admin only)                     │
│  DELETE /api/v1/admin/sync/runs/{id}/cancel                             │
└────────────────────────────┬────────────────────────────────────────────┘
                             │  dispatch
                             ▼
┌──── Valkey (broker) ───────────────────────────────────────────────────┐
│  Queue: github_sync                                                    │
└────────────────────────────┬───────────────────────────────────────────┘
                             │
                             ▼
┌──── Celery Worker (github_sync queue) ───────────────────────────────┐
│  concurrency=4, 1 replica                                            │
│                                                                      │
│  run_enterprise_sync(run_id, scope)      ← orchestrator              │
│    │                                                                 │
│    ├── sync_entity(run_id, "orgs", org=None, installation_id=X)      │
│    ├── sync_entity(run_id, "repositories", org="acme", ...)          │
│    ├── sync_entity(run_id, "repositories", org="widgets", ...)       │
│    └── ... (one task per entity_type × org)                          │
│                                                                      │
│  Services used:                                                      │
│    GitHubAppTokenManager  → Valkey token cache                       │
│    GitHubRateLimiter      → in-process token bucket + semaphore      │
└──────────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌──── TimescaleDB / PostgreSQL ────────────────────────────────────────┐
│  enterprise_sync_runs, enterprise_sync_entity_cursors                │
│  enterprise_orgs, enterprise_members                                 │
│  org_members, org_teams, org_team_members                            │
│  repositories, repo_branch_protections                               │
│  github_app_installations, github_app_configs                        │
│  external_collaborators (existing — upsert from sync)                │
└──────────────────────────────────────────────────────────────────────┘
```

### 6.2 Celery Queue Addition

A dedicated fifth queue isolates GitHub API I/O from latency-sensitive detection paths:

```python
# In celery_app.py — task_routes addition
"app.workers.github_sync.*": {"queue": "github_sync"},
```

### 6.3 New File Layout

```
backend/app/
├── models/
│   └── github_sync.py            # All 11 new ORM models
├── workers/
│   └── github_sync_worker.py     # run_enterprise_sync + sync_entity tasks
├── services/
│   ├── github_token_service.py   # GitHubAppTokenManager
│   └── github_rate_limiter.py    # GitHubRateLimiter
├── routers/
│   └── sync.py                   # /api/v1/admin/sync/* endpoints
└── schemas/
    └── github_sync.py            # Pydantic request/response schemas
```

---

## 7. Data Model Changes

All new models live in `backend/app/models/github_sync.py`. They use the existing `Base` from `app.models.audit_event`. Existing `external_collaborators` gets two additional columns via migration.

### 7.1 GitHub App Config

```python
class GitHubAppConfig(Base):
    """Per-org installation mapping. Private key is NEVER stored here."""
    __tablename__ = "github_app_configs"

    id: Mapped[int]             = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    app_id: Mapped[int]         = mapped_column(Integer, nullable=False)
    installation_id: Mapped[int]= mapped_column(BigInteger, nullable=False)
    enterprise_slug: Mapped[str | None]   # NULL for org-only installations
    org_login: Mapped[str | None]
    enabled: Mapped[bool]       = mapped_column(Boolean, server_default="true")

    # UniqueConstraint("app_id", "installation_id")
    # Index on enterprise_slug, Index on org_login
```

### 7.2 Sync Run Lifecycle

```python
class EnterpriseSyncRun(Base):
    """One row per orchestrated sync run. UUID PK for safe external references."""
    __tablename__ = "enterprise_sync_runs"

    id: Mapped[uuid.UUID]         # server_default=gen_random_uuid()
    created_at: Mapped[datetime]
    status: Mapped[str]           # pending | running | completed | failed | cancelled
    trigger_type: Mapped[str]     # manual | scheduled
    triggered_by: Mapped[str | None]  # github_login
    scope: Mapped[str]            # full | <entity_type>
    started_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]
    error_message: Mapped[str | None]
    entity_counts: Mapped[dict | None]  # JSONB: {"orgs": 3, "repositories": 1804, ...}

    # Index on status, Index on created_at
```

```python
class EnterpriseSyncEntityCursor(Base):
    """Resumable pagination cursor per (run, entity_type, org). Written after every page."""
    __tablename__ = "enterprise_sync_entity_cursors"

    id: Mapped[int]                # BigInteger PK
    created_at: Mapped[datetime]
    run_id: Mapped[uuid.UUID]      # FK → enterprise_sync_runs.id ON DELETE CASCADE
    entity_type: Mapped[str]
    org: Mapped[str | None]        # NULL for enterprise-level entities
    last_cursor: Mapped[str | None]  # opaque GitHub pagination cursor
    items_synced: Mapped[int]      # server_default=0
    status: Mapped[str]            # in_progress | completed | failed

    # UniqueConstraint("run_id", "entity_type", "org")
    # Index on run_id
```

### 7.3 Enterprise-Level Snapshot Tables

```python
class EnterpriseOrg(Base):
    __tablename__ = "enterprise_orgs"
    # Columns: id, created_at, enterprise_slug, org_login, org_id, visibility, plan,
    #          member_count, synced_at
    # UniqueConstraint("enterprise_slug", "org_login")

class EnterpriseMember(Base):
    __tablename__ = "enterprise_members"
    # Columns: id, created_at, enterprise_slug, github_login, github_id,
    #          role (owner|member|billing_manager), synced_at
    # UniqueConstraint("enterprise_slug", "github_login")
```

### 7.4 Org-Level Snapshot Tables

```python
class OrgMember(Base):
    __tablename__ = "org_members"
    # Columns: id, created_at, org, github_login, github_id, role (owner|member), synced_at
    # UniqueConstraint("org", "github_login")

class OrgTeam(Base):
    __tablename__ = "org_teams"
    # Columns: id, created_at, org, team_slug, team_id, name, privacy,
    #          parent_team_slug (Text, NOT a FK to avoid self-ref complications), synced_at
    # UniqueConstraint("org", "team_slug")

class OrgTeamMember(Base):
    __tablename__ = "org_team_members"
    # Columns: id, created_at, org, team_slug, github_login, github_id, role, synced_at
    # UniqueConstraint("org", "team_slug", "github_login")
```

### 7.5 Repository Snapshot Tables

```python
class Repository(Base):
    __tablename__ = "repositories"
    # Columns: id, created_at, org, repo_name, repo_id, visibility (public|private|internal),
    #          default_branch, archived (bool), fork (bool), pushed_at, synced_at
    # UniqueConstraint("org", "repo_name")
    # Index on visibility

class RepoBranchProtection(Base):
    __tablename__ = "repo_branch_protections"
    # Columns: id, created_at, org, repo_name, branch, required_reviews (int),
    #          required_status_checks (JSONB), enforce_admins (bool), synced_at
    # UniqueConstraint("org", "repo_name", "branch")
```

### 7.6 GitHub App Installation Snapshot

```python
class GitHubAppInstallation(Base):
    __tablename__ = "github_app_installations"
    # Columns: id, created_at, app_id, installation_id, target_type (Organization|User),
    #          target_login, permissions (JSONB), synced_at
    # UniqueConstraint("app_id", "installation_id")
    # Index on (target_type, target_login)
```

### 7.7 external_collaborators Table Additions

Two columns added to the existing `external_collaborators` table via migration:

| Column | Type | Default | Purpose |
|--------|------|---------|---------|
| `data_source` | Text | `'audit_event'` | `'audit_event'` or `'github_api_sync'` |
| `last_synced_at` | DateTime(tz=True) | NULL | When this row was last refreshed by the sync task |
| `sync_run_id` | UUID | NULL | FK → enterprise_sync_runs.id (for traceability) |

---

## 8. New Services: Token Manager & Rate Limiter

### 8.1 GitHubAppTokenManager (`backend/app/services/github_token_service.py`)

Key design decisions:
- **Private key never leaves memory.** Loaded from disk at construction. Never stored in DB, Valkey, or any API response.
- **SSRF prevention.** The GitHub API base URL is a hard-coded module constant (`_GITHUB_API_BASE = "https://api.github.com"`). `follow_redirects=False` on all `httpx` calls.
- **Proactive token refresh.** TTL in Valkey = `expires_at − now − 300s` (5-min buffer). Token is always valid for ≥5 minutes when retrieved.

```python
class GitHubAppTokenManager:
    _CACHE_KEY = "github:app:token:{installation_id}"
    _TTL_BUFFER_SECS = 300

    def __init__(self, app_id: int, private_key_pem: str, valkey_client: Redis) -> None: ...

    async def get_installation_token(self, installation_id: int) -> str:
        """Return a cached or freshly minted installation token for the given installation."""

    def _generate_jwt(self) -> str:
        """RS256 JWT: iss=app_id, iat=now−60s, exp=now+600s."""

    async def _exchange_jwt_for_token(self, app_jwt: str, installation_id: int) -> InstallationToken:
        """POST to /app/installations/{id}/access_tokens, return InstallationToken dataclass."""
```

### 8.2 GitHubRateLimiter (`backend/app/services/github_rate_limiter.py`)

Instantiated once per Celery worker process as a module-level singleton. All tasks in that worker share the same token bucket.

```python
class GitHubRateLimiter:
    # Token bucket: rate_per_hour=15_000, max_burst=50
    # asyncio.Semaphore(max_concurrent=80)

    async def acquire(self, cost: int = 1) -> None:
        """Acquire semaphore + cost tokens before making a request."""

    def release(self) -> None:
        """Release semaphore after request completes."""

    def update_from_headers(self, headers) -> None:
        """Parse x-ratelimit-remaining/reset; activate proactive throttle if remaining<1000."""

    async def handle_rate_limit_response(self, response: httpx.Response) -> None:
        """Sleep for retry-after (or until x-ratelimit-reset) + jitter on 429/403."""
```

---

## 9. Celery Task Design

### 9.1 Task Signatures

```python
@celery_app.task(
    name="app.workers.github_sync.run_enterprise_sync",
    bind=True,
    max_retries=0,         # orchestrator never retries; children do
    queue="github_sync",
    soft_time_limit=7200,  # 2 hours
    time_limit=7800,
)
def run_enterprise_sync(self, run_id: str, scope: str = "full") -> dict:
    """
    Orchestrator. Steps:
    1. Mark enterprise_sync_runs.status = "running", started_at = now
    2. Load github_app_configs to get per-org installation IDs
    3. Determine entity × org matrix from scope
    4. apply_async sync_entity for each (entity_type, org) pair
    5. Poll child states until all terminal; set run status = completed|failed
    """


@celery_app.task(
    name="app.workers.github_sync.sync_entity",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    queue="github_sync",
    soft_time_limit=3600,  # 1 hour per entity/org chunk
    acks_late=True,
)
def sync_entity(
    self,
    run_id: str,
    entity_type: str,
    org: str | None,
    installation_id: int,
    cursor: str | None = None,
) -> dict:
    """
    Idempotent child task. Steps:
    1. Read enterprise_sync_entity_cursors for (run_id, entity_type, org) — use saved cursor,
       ignoring the cursor argument if a cursor row already exists
    2. Acquire GitHub installation token via GitHubAppTokenManager
    3. Paginate GitHub API from cursor:
         a. Acquire rate limiter slot
         b. GET page from GitHub
         c. Upsert rows: INSERT ... ON CONFLICT (natural key) DO UPDATE SET ...
         d. Commit
         e. Write cursor to enterprise_sync_entity_cursors (upsert)
         f. Repeat until no next_page
    4. Set cursor row status = "completed"
    5. On failure: set cursor row status = "failed", raise for Celery retry
    """
```

### 9.2 Scheduler Heartbeat Task

```python
@celery_app.task(
    name="app.workers.github_sync.check_sync_schedule",
    queue="github_sync",
)
def check_sync_schedule() -> None:
    """
    Runs daily at 02:00 UTC via Celery Beat.
    1. If GITHUB_SYNC_ENABLED is False, return immediately
    2. Check enterprise_sync_runs for last completed run
    3. If last_completed_at IS NULL or last_completed_at + interval_days < now:
         dispatch run_enterprise_sync(scope="full", trigger_type="scheduled")
    4. If a run is in status=running|pending: log and skip
    """
```

### 9.3 Idempotency & Crash Safety

- After each page, the cursor row is upserted (`ON CONFLICT DO UPDATE`) with the new cursor value.
- At most one page is re-processed on crash restart (since the page was processed but the cursor write may not have committed).
- The upsert on target tables is keyed on the natural unique key (e.g., `(org, github_login)` for `org_members`), so re-inserting data from a re-processed page is a no-op.

---

## 10. API Endpoints

All endpoints are under `/api/v1/admin/sync/` and require `require_role(["sys_admin"])`.

### Summary

| Method | Path | Purpose | Success Code |
|--------|------|---------|--------------|
| `POST` | `/trigger` | Start full sync or resume | 202 |
| `GET` | `/runs` | Paginated run history | 200 |
| `GET` | `/runs/{run_id}` | Run detail with entity breakdown | 200 |
| `DELETE` | `/runs/{run_id}/cancel` | Cancel in-progress run | 202 |
| `GET` | `/config` | View sync configuration | 200 |
| `PUT` | `/config` | Update interval, enabled flag, orgs | 200 |

### POST /trigger

```json
// Request
{"mode": "full"}
// or
{"mode": "resume", "run_id": "550e8400-e29b-41d4-a716..."}

// Response 202
{
  "run_id": "550e8400-...",
  "status": "pending",
  "mode": "full",
  "triggered_by": "octocat",
  "triggered_at": "2026-03-27T14:30:00Z"
}
```

**Error codes:**

| Status | Condition |
|--------|-----------|
| 403 | Not sys_admin |
| 409 | A run is already pending or running |
| 422 | GitHub App not configured (missing env vars) |
| 503 | Celery/Valkey unavailable |

### GET /runs/{run_id}

```json
{
  "run_id": "550e8400-...",
  "status": "completed",
  "trigger_type": "scheduled",
  "triggered_by": null,
  "started_at": "2026-03-27T02:00:05Z",
  "completed_at": "2026-03-27T03:47:12Z",
  "duration_seconds": 6427,
  "total_records_upserted": 147832,
  "entity_statuses": [
    {
      "entity_type": "org_members",
      "org": "acme",
      "status": "completed",
      "records_upserted": 412,
      "started_at": "...",
      "completed_at": "..."
    }
  ]
}
```

### GET /config (never exposes private key path)

```json
{
  "github_app_id": 123456,
  "enterprise_slug": "my-enterprise",
  "sync_enabled": true,
  "sync_interval_days": 60,
  "last_sync_completed_at": "2026-01-25T03:47:12Z",
  "next_sync_due_at": "2026-03-25T02:00:00Z",
  "installations": [
    {"org_login": "acme", "installation_id": 7891234, "enabled": true},
    {"org_login": "widgets", "installation_id": 7891235, "enabled": true}
  ]
}
```

---

## 11. Configuration Changes

New nested settings class added to `backend/app/config.py`:

```python
class GitHubAppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GITHUB_APP_")

    GITHUB_APP_ID: int | None = None
    GITHUB_APP_PRIVATE_KEY_PATH: str | None = None  # path to .pem file on disk
    GITHUB_ENTERPRISE_SLUG: str | None = None        # e.g. "my-enterprise"
    GITHUB_SYNC_INTERVAL_DAYS: int = Field(default=60, ge=60, le=90)
    GITHUB_SYNC_ENABLED: bool = False                # disabled until credentials configured
    GITHUB_SYNC_ORGS: list[str] = []                 # empty = sync all orgs in enterprise

    @field_validator("GITHUB_APP_PRIVATE_KEY_PATH")
    @classmethod
    def validate_key_path(cls, v: str | None) -> str | None:
        """Verify the .pem file exists at startup if path is provided."""
        if v is not None and not os.path.isfile(v):
            raise ValueError(f"GITHUB_APP_PRIVATE_KEY_PATH does not exist: {v}")
        return v

    @field_validator("GITHUB_ENTERPRISE_SLUG")
    @classmethod
    def validate_slug(cls, v: str | None) -> str | None:
        """Only alphanumeric + hyphen — prevents path injection in URL construction."""
        if v is not None and not re.match(r'^[a-zA-Z0-9\-]+$', v):
            raise ValueError("GITHUB_ENTERPRISE_SLUG must be alphanumeric/hyphen only")
        return v
```

**Celery Beat entry** (registered only when `GITHUB_SYNC_ENABLED=True`):

```python
"enterprise-sync-heartbeat": {
    "task": "app.workers.github_sync.check_sync_schedule",
    "schedule": crontab(hour=2, minute=0),   # daily at 02:00 UTC
    "options": {"queue": "github_sync"},
}
```

---

## 12. Alembic Migration Plan

Four sequential migrations. Each is additive — no destructive changes.

### Migration 0004: Sync Run Scaffolding

Tables: `github_app_configs`, `enterprise_sync_runs`, `enterprise_sync_entity_cursors`

Notes:
- `enterprise_sync_runs.id` uses `gen_random_uuid()` (requires `pgcrypto` extension, already enabled from 0001).
- `enterprise_sync_entity_cursors.run_id` has `ON DELETE CASCADE` FK.
- Set `nullable=False` on status columns with appropriate `server_default` values.

### Migration 0005: Enterprise-Level Snapshots

Tables: `enterprise_orgs`, `enterprise_members`, `github_app_installations`

Notes: No inter-table FKs to avoid ordering issues with partial syncs. `github_app_installations` is a snapshot — not the same as `github_app_configs` (which is operator-entered config).

### Migration 0006: Org-Level Snapshots

Tables: `org_members`, `org_teams`, `org_team_members`

Notes:
- `org_teams.parent_team_slug` is `Text`, not a FK, to avoid self-referential cascade complexity and simplify partial loading.
- No FK from `org_team_members` to `org_teams` (snapshot table; avoids insert ordering constraints in fan-out tasks).

### Migration 0007: Repository Snapshots + External Collaborators Update

Tables (new): `repositories`, `repo_branch_protections`

Alterations (existing): `ALTER TABLE external_collaborators`:
```sql
ADD COLUMN data_source TEXT NOT NULL DEFAULT 'audit_event',
ADD COLUMN last_synced_at TIMESTAMPTZ,
ADD COLUMN sync_run_id UUID REFERENCES enterprise_sync_runs(id) ON DELETE SET NULL;
```

Notes:
- No FK between `repositories` and `repo_branch_protections` — avoids insert ordering constraints when fan-out tasks run in parallel.
- The `sync_run_id` FK in `external_collaborators` uses `ON DELETE SET NULL` (non-destructive — orphaned sync reference is acceptable).

---

## 13. Security Controls

### Private Key Handling

| Location | Stored? | Notes |
|----------|---------|-------|
| `.pem` file on disk | ✓ | Operator manages file, restrict to `0600` permissions |
| Environment variable | Path only | `GITHUB_APP_PRIVATE_KEY_PATH` — a path, not the key |
| Database | ✗ | Never |
| Valkey | ✗ | Never |
| API response | ✗ | `GET /config` never returns the path |
| Application logs | ✗ | Key masked in any debug dumps |

### Installation Token Handling

| Location | Stored? | Notes |
|----------|---------|-------|
| Valkey | ✓ (TTL) | Key: `github:app:token:{installation_id}`, TTL = expires_at − 5min |
| Database | ✗ | Never persisted |
| API response | ✗ | Never returned to any client |
| Application logs | ✗ | Never logged (even at DEBUG) |

### Additional Security Controls

- **SSRF prevention:** GitHub API base URL is `_GITHUB_API_BASE = "https://api.github.com"` — a hard-coded constant, never interpolated from user input. All `httpx` calls use `follow_redirects=False`.
- **Enterprise slug injection prevention:** `GITHUB_ENTERPRISE_SLUG` validated at startup against `^[a-zA-Z0-9\-]+$` before being used in URL construction.
- **Installation ID type safety:** `int(installation_id)` cast before URL construction in token manager.
- **Endpoint authorization:** All sync endpoints enforce `require_role(["sys_admin"])` via the existing `deps.py` dependency pattern.
- **Audit trail:** Every manual `POST /trigger`, cancel, and config update writes a row to the existing `audit_trail` table with `action_type`, `triggered_by`, `run_id`.
- **Secret scanning data:** Sync stores alert count and latest alert date only — never the matched secret values themselves.
- **Minimum permissions:** The GitHub App is registered with read-only scopes. No write permissions are requested.

---

## 14. Conflict Resolution Policy

The sync can surface discrepancies between its API snapshot and the event-stream-derived state. The resolution rules are non-destructive:

| Scenario | Policy |
|----------|--------|
| Sync finds a collaborator not in `external_collaborators` | INSERT with `data_source='github_api_sync'` |
| Sync shows collaborator as active; DB shows `is_active=false` (removed per past event) | Update to `is_active=true`, log discrepancy to `audit_trail` |
| Sync shows collaborator as absent; DB shows `is_active=true` (added per past event) | Update to `is_active=false`, `removed_at=sync_timestamp`, set `data_source='github_api_sync'` — never hard-delete |
| Snapshot row exists for an org that no longer exists in the enterprise | Mark `is_active=false` on org-level tables; never hard-delete |
| Branch protection exists in sync snapshot but was removed per audit event | Trust the most recent signal: if the audit event is newer, keep removed; if sync ran after the event, update to current state from API |
| Two concurrent syncs (should be prevented by 409, but as belt-and-suspenders) | Last-write-wins on `synced_at`; `ON CONFLICT DO UPDATE` with `WHERE excluded.synced_at > synced_at` |

**Golden rule:** The sync never hard-deletes any row. All removals are soft-deletes via `is_active=false` or `removed_at` timestamps.

---

## 15. Scheduler Design

The scheduler **avoids modifying the static `beat_schedule`** dictionary based on the interval setting. Instead:

1. A **daily heartbeat task** (`check_sync_schedule`) runs at 02:00 UTC via a fixed Celery Beat entry.
2. The heartbeat queries `enterprise_sync_runs` for the most recent completed run.
3. It computes `last_completed_at + timedelta(days=GITHUB_SYNC_INTERVAL_DAYS)` and compares to `now()`.
4. If a sync is due **and** no run is currently `pending` or `running`, it dispatches `run_enterprise_sync`.

This design means:
- Changing the interval requires only an env-var update and app restart — no Beat schedule modification.
- The 60–90 day constraint is enforced in config validation at startup, not a runtime check.
- If the scheduled sync fails, the heartbeat will attempt again the next day (not wait a full interval).

```
Beat schedule entry (always registered when GITHUB_SYNC_ENABLED=True):
  crontab(hour=2, minute=0)  → check_sync_schedule

check_sync_schedule logic:
  if not settings.GITHUB_APP.GITHUB_SYNC_ENABLED: return
  last_run = SELECT MAX(completed_at) FROM enterprise_sync_runs WHERE status='completed'
  if last_run IS NULL or (now - last_run) >= timedelta(days=interval_days):
      if no run in (pending, running):
          dispatch run_enterprise_sync(scope="full", trigger_type="scheduled")
```

---

## 16. Testing Plan

### Unit Tests

| Test | File | Focus |
|------|------|-------|
| JWT claims | `tests/test_github_token_service.py` | `iss=app_id`, `iat=now−60`, `exp=now+600`, RS256 algorithm |
| Token cache hit | `tests/test_github_token_service.py` | Valkey hit → no GitHub API call (assert `httpx` not called) |
| Token cache miss + refresh | `tests/test_github_token_service.py` | 201 response → token stored in Valkey with correct TTL |
| Token near-expiry refresh | `tests/test_github_token_service.py` | TTL buffer forces refresh before expiry |
| Rate limiter 429 handling | `tests/test_github_rate_limiter.py` | `retry-after: 5` → sleeps 5s ± jitter before retry |
| Rate limiter header parsing | `tests/test_github_rate_limiter.py` | `x-ratelimit-remaining=999` → proactive throttle activates |
| Rate limiter concurrency | `tests/test_github_rate_limiter.py` | Semaphore(80) blocks 81st concurrent request |
| Cursor resumability | `tests/test_github_sync_worker.py` | Simulate crash after page 3; verify task reads cursor and starts at page 4 |
| Idempotency | `tests/test_github_sync_worker.py` | Run sync twice with same mock data; assert row count unchanged after second run |
| Conflict: stale active record | `tests/test_github_sync_worker.py` | Mock API returns no collaborator; DB has `is_active=true` → assert `is_active=false` after sync |

Mock strategy: use `respx` (consistent with existing test patterns) to mock all `httpx` calls to `api.github.com`.

### API Tests

| Test | File | Assertion |
|------|------|-----------|
| Non-sys_admin gets 403 | `tests/test_sync_router.py` | analyst role → `POST /trigger` returns 403 |
| Concurrent trigger rejected | `tests/test_sync_router.py` | Second `POST /trigger` while run is "running" → 409 |
| Manual trigger creates run | `tests/test_sync_router.py` | 202, `run_id` in response, DB row created |
| Cancel transitions state | `tests/test_sync_router.py` | `DELETE /cancel` → status becomes "cancelling" |
| Config hides key path | `tests/test_sync_router.py` | `GET /config` response has no `private_key_path` field |
| 409 on invalid interval | `tests/test_sync_router.py` | `PUT /config {"interval_days": 45}` → 422 |

### Integration Tests

| Test | Focus |
|------|-------|
| Full sync end-to-end (small mock enterprise: 2 orgs, 5 repos each) | `POST /trigger` → task executes → all snapshot tables populated → `GET /runs/{id}` shows completed |
| Resume after cancel | Cancel mid-sync → resume → verify only non-completed entities re-run |
| Scheduled heartbeat dispatch | Backdate `completed_at` by 61 days → run heartbeat → verify new run dispatched |

---

## 17. Phased Rollout

### Phase 1 — MVP (Critical Security Baseline)

**Target:** Get the most security-valuable baseline data into Octowatch ASAP.

Entities: Enterprise orgs, enterprise members, org members, outside collaborators (writes to `external_collaborators`), GitHub App installations, secret scanning alerts, repository inventory, org metadata.

Deliverables:
- GitHub App credential setup (`github_app_configs`, config settings)
- `GitHubAppTokenManager` service
- `GitHubRateLimiter` service
- `run_enterprise_sync` + `sync_entity` tasks for Phase 1 entities
- Migrations 0004–0005 + `external_collaborators` additions
- Admin API: `POST /trigger`, `GET /runs`, `GET /runs/{run_id}`, `GET /config`
- Scheduler heartbeat task

### Phase 2 — Enhanced Baseline

Entities: Teams, team memberships, team repositories, direct repo collaborators, branch protection rules, Dependabot alerts.

Deliverables:
- `sync_entity` handlers for Phase 2 entities
- Migrations 0006–0007 (org/team/repo tables)
- `DELETE /cancel` endpoint + resume mode in `POST /trigger`
- `PUT /config` endpoint

### Phase 3 — Extended Coverage

Entities: Org/repo webhooks, code scanning configs, Actions permissions, self-hosted runners, deploy keys.

Deliverables:
- `sync_entity` handlers for Phase 3 entities
- New snapshot tables (webhooks, runners, deploy keys) via new migration
- Detection rules that reference sync baseline data

### Phase 4 — Full Coverage

Entities: Enterprise IP allow list (GraphQL), environments, packages.

Deliverables:
- GraphQL client wrapper (reusing `GitHubRateLimiter`)
- `sync_entity` handlers for Phase 4 entities
- Automated drift detection: alert when sync reveals state discrepancy with audit events

---

## 18. Open Questions

| # | Question | Decision Needed By | Notes |
|---|----------|--------------------|-------|
| 1 | **Enterprise App vs. Org App?** Should the GitHub App be installed at the enterprise level (one installation covering all orgs) or per-org? | Architecture + GitHub Admin | Enterprise-level installation simplifies the token lookup but requires Enterprise owner to approve. Per-org is more standard. |
| 2 | **Where does the `.pem` file live in production?** Kubernetes Secret mounted as volume file, or a secrets manager (Vault, AWS Secrets Manager)? | Platform / Ops | The `GITHUB_APP_PRIVATE_KEY_PATH` config accepts any path. The mounting strategy is a deployment concern. |
| 3 | **GraphQL for Phase 4?** IP allow list is GraphQL-only. Should we introduce a GraphQL client layer or wait for a REST equivalent? | Engineering | `httpx` can call the GraphQL endpoint; the rate limiter applies equally. |
| 4 | **Repo-level entity scope for large enterprises.** At 10,000+ repos, branch protection + secret scanning alerts = 20,000+ API calls. Should repo-level Phase 1 entities be limited to non-archived, non-forked repos only? | Product | Reasonable default: skip archived repos and forks unless configured otherwise. |
| 5 | **Detection rule integration.** Which existing detection rules should immediately start using the new snapshot tables as baseline? | Security / Detection team | `outside_collaborators` baseline is immediately useful for the existing external collaborator detection. |
| 6 | **Multi-enterprise support.** Future need for a single Octowatch instance monitoring multiple GitHub enterprises? | Product roadmap | Current design only supports one `GITHUB_ENTERPRISE_SLUG`. Multi-enterprise would require partitioning all snapshot tables by enterprise. |
| 7 | **Historical event backfill.** Complement the sync with a one-time audit log backfill (`GET /orgs/{org}/audit-log`) to populate the `events` table for periods before Octowatch was deployed? | Product | Out of scope for this feature but a natural follow-on. |
| 8 | **File upload size limit for manual ingest.** 500 MB default? Some full audit log exports can reach several GB. | Engineering + Ops | Consider streaming parse (NDJSON line-by-line) to avoid loading full file into memory. nginx `client_max_body_size` must match. |
| 9 | **Where is the ingest UI located?** New top-level "Import Data" nav item, or under the existing Integrations page? | Product / UX | Integrations page is the natural home since it already contains ingestion source configuration. |

---

## 19. Sync Progress UI

### 19.1 Approach: Polling via React Query

The frontend uses React Query for all server state. There is no WebSocket or SSE infrastructure. A short-interval polling strategy is the idiomatic approach and consistent with patterns already used elsewhere in the app.

**Polling behavior:**
- When a sync run is in status `pending` or `running`: poll `GET /api/v1/admin/sync/runs/{run_id}` every **5 seconds**.
- When the run transitions to a terminal state (`completed`, `failed`, `cancelled`): React Query's `refetchInterval` callback returns `false`, stopping the poll.
- On page load without an active run: poll `GET /api/v1/admin/sync/runs` once (no interval) to show the most recent run summary and next scheduled sync date.

```typescript
// React Query polling hook
function useSyncRunProgress(runId: string | null) {
  return useQuery({
    queryKey: ['sync-run', runId],
    queryFn: () => api.sync.getRun(runId!),
    enabled: runId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === 'pending' || status === 'running') return 5_000;
      return false;   // stop polling on terminal state
    },
  });
}
```

### 19.2 UI Components

The sync UI lives on a new **Admin > Data Sync** page (or as a section of the existing Integrations page — see Open Question #9). It contains three areas:

**1. Sync Status Header**
- Last sync: relative time (e.g. "12 days ago"), status badge (Completed / Failed)
- Next scheduled sync: absolute date
- "Run Sync Now" button — calls `POST /trigger`, disabled while a run is active
- Cancel button — shown only when status is `running`, calls `DELETE /cancel`

**2. Active Run Progress Panel** (shown only when a run is pending or running)
```
┌─────────────────────────────────────────────────────────────┐
│  Syncing enterprise baseline...                             │
│  ████████████████░░░░░░░░░░░░  9 / 18 entities  (50%)      │
│  Running for 4m 23s · ~4m remaining                        │
│                                                             │
│  Entity                   Org        Status     Records    │
│  ─────────────────────────────────────────────────────────  │
│  ✓ enterprise_orgs        —          Completed  12         │
│  ✓ enterprise_members     —          Completed  412        │
│  ⟳ org_members            acme       Running    1,204       │
│  ● repositories           acme       Pending    —          │
│  ● org_members            widgets    Pending    —          │
└─────────────────────────────────────────────────────────────┘
```

**3. Run History Table** (last 10 runs)
- Columns: Triggered by, Start time, Duration, Status, Records upserted
- Clickable row → expands to show per-entity breakdown

### 19.3 Frontend File Layout

```
frontend/src/
├── pages/
│   └── Integrations/
│       ├── SyncPanel.tsx         # Active run progress + trigger button
│       ├── SyncRunHistory.tsx    # Past run table
│       └── SyncRunDetail.tsx     # Expanded per-entity detail
├── api/
│   └── sync.ts                   # API calls: triggerSync(), getRun(), listRuns(), cancelRun()
├── hooks/
│   └── useSyncRunProgress.ts     # React Query polling hook (see above)
└── types/
    └── sync.ts                   # SyncRun, EntityStatus, SyncConfig TypeScript types
```

### 19.4 TypeScript API Types

```typescript
export type SyncRunStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';

export interface SyncRun {
  readonly run_id: string;
  readonly status: SyncRunStatus;
  readonly trigger_type: 'manual' | 'scheduled';
  readonly triggered_by: string | null;
  readonly started_at: string | null;
  readonly completed_at: string | null;
  readonly duration_seconds: number | null;
  readonly total_records_upserted: number;
  readonly entity_statuses: EntityStatus[];
}

export interface EntityStatus {
  readonly entity_type: string;
  readonly org: string | null;
  readonly status: 'pending' | 'running' | 'completed' | 'failed';
  readonly records_upserted: number;
  readonly started_at: string | null;
  readonly completed_at: string | null;
}

export interface SyncConfig {
  readonly github_app_id: number | null;
  readonly enterprise_slug: string | null;
  readonly sync_enabled: boolean;
  readonly sync_interval_days: number;
  readonly last_sync_completed_at: string | null;
  readonly next_sync_due_at: string | null;
  readonly installations: AppInstallation[];
}
```

---

## 20. Manual File Ingest

This feature allows sys_admins to upload GitHub data export files through the UI and have them ingested into Octowatch's database as a background job — useful for backfilling data that predates Octowatch's deployment or arrived via a manual GitHub export.

### 20.1 Supported File Types

| Type Key | Description | File Format | Backend Handler |
|----------|-------------|-------------|----------------|
| `audit_log` | Standard GitHub audit log export | JSON array or NDJSON | Adapts existing `AbstractIngestWorker` parse logic |
| `audit_log_git` | GitHub audit log git export | NDJSON (different schema) | New parser for git-action events |
| `copilot_usage` | Copilot usage metrics export | NDJSON | Refactored from existing `import_copilot_usage.py` |

### 20.2 Backend: New API Endpoint

**`POST /api/v1/admin/ingest/upload`** — `multipart/form-data`, `sys_admin` only.

Request fields:
- `file`: the upload (binary)
- `type`: one of `audit_log | audit_log_git | copilot_usage`
- `description` (optional): freeform string for the audit trail

Response 202:
```json
{
  "job_id": "uuid",
  "status": "pending",
  "type": "audit_log",
  "filename": "audit-export-2026-01.ndjson",
  "file_size_bytes": 52428800,
  "created_at": "2026-03-27T14:30:00Z"
}
```

**`GET /api/v1/admin/ingest/jobs`** — list past upload jobs (paginated, sys_admin only).

**`GET /api/v1/admin/ingest/jobs/{job_id}`** — job detail with `rows_processed`, `rows_skipped`, `rows_failed`, `error_details`.

### 20.3 File Handling Security

- Files are **streamed directly to a staging path** on the server (or an object store bucket), never loaded fully into the API process memory.
- The file path is a random UUID-keyed path — never derived from the user-supplied filename. The original filename is stored in the job record for display only.
- MIME type and magic bytes are validated server-side (not just client-side) before the job is queued.
- The staging file is deleted after the job completes or fails — not retained.
- **Maximum file size:** configurable via `MANUAL_INGEST_MAX_FILE_MB` (default 500). Enforced at the FastAPI layer before any parsing. The nginx `client_max_body_size` directive must be set to match.
- Uploaded files are validated for structure (valid JSON/NDJSON) before queuing — a 422 is returned immediately for malformed files.

### 20.4 Backend: Celery Task

A new Celery task runs on the existing **`ingestion`** queue (no new queue needed — file I/O is local, not GitHub API-bound):

```python
@celery_app.task(
    name="app.workers.ingestion.process_manual_upload",
    bind=True,
    max_retries=2,
    queue="ingestion",
    soft_time_limit=3600,
)
def process_manual_upload(
    self,
    job_id: str,
    file_path: str,       # staging path, not user-supplied
    ingest_type: str,     # audit_log | audit_log_git | copilot_usage
) -> dict:
    """
    Streams the file line-by-line (NDJSON) or in chunks (JSON array),
    validates each record, upserts via the existing dedup + bulk-insert
    pipeline, updates ManualIngestJob.rows_processed after each batch,
    and deletes the staging file on completion.
    """
```

For `audit_log` type: reuse the existing `AbstractIngestWorker.process_event()` method — the parsed record goes through the same dedup bloom filter and `INSERT ... ON CONFLICT DO NOTHING` pipeline as live S3 events. `ingestion_source` is set to `"manual_upload"` on each inserted row.

For `copilot_usage`: the existing `import_copilot_usage.py` script logic is refactored into a callable function `parse_copilot_usage_ndjson(line) -> CopilotUsageRecord` and called from this task.

### 20.5 Data Model: Manual Ingest Job

New table `manual_ingest_jobs` added in a new migration (0008):

```python
class ManualIngestJob(Base):
    __tablename__ = "manual_ingest_jobs"

    id: Mapped[uuid.UUID]          # gen_random_uuid() PK
    created_at: Mapped[datetime]
    # audit_log | audit_log_git | copilot_usage
    ingest_type: Mapped[str]       = mapped_column(Text, nullable=False)
    # pending | running | completed | failed
    status: Mapped[str]            = mapped_column(Text, nullable=False, server_default="'pending'")
    submitted_by: Mapped[str]      = mapped_column(Text, nullable=False)  # github_login
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)  # display only
    file_size_bytes: Mapped[int]   = mapped_column(BigInteger, nullable=False)
    description: Mapped[str | None]= mapped_column(Text)

    rows_processed: Mapped[int]    = mapped_column(Integer, server_default="0")
    rows_skipped: Mapped[int]      = mapped_column(Integer, server_default="0")
    rows_failed: Mapped[int]       = mapped_column(Integer, server_default="0")
    error_details: Mapped[str | None] = mapped_column(Text)

    started_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]

    # Index on status, Index on created_at, Index on submitted_by
```

### 20.6 Frontend: Import Data UI

Lives as a new section on the Admin > Integrations page (or a sibling "Import Data" tab).

**Upload card per file type:**
```
┌─────────────────────────────────────────────────────────────┐
│  📄 Audit Log Export                                        │
│  Upload a JSON or NDJSON audit log export from GitHub.      │
│                                                             │
│  [ Drag & drop file here, or click to browse ]             │
│                                                             │
│  Max 500 MB · Accepted: .json, .ndjson                     │
│  [ Upload ]                                                 │
└─────────────────────────────────────────────────────────────┘
```

**During upload + processing:**
- File size validated client-side before sending (reject >500 MB immediately in the browser).
- Upload progress bar: standard `XMLHttpRequest`/`fetch` upload progress via `onUploadProgress`.
- After 202 response, poll `GET /api/v1/admin/ingest/jobs/{job_id}` every 3 seconds (React Query) until terminal state — same polling pattern as sync progress.
- Display live `rows_processed` counter.

**Job history table** (below the upload cards):
- Columns: Type, Filename, Submitted by, Started at, Status, Rows ingested
- Last 20 jobs, newest first.

### 20.7 Frontend File Layout

```
frontend/src/
├── pages/
│   └── Integrations/
│       ├── ManualIngestPanel.tsx      # Upload cards for each file type
│       ├── IngestJobProgress.tsx      # Per-job progress display
│       └── IngestJobHistory.tsx       # Past jobs table
├── api/
│   └── ingest.ts                      # uploadFile(), getJob(), listJobs()
├── hooks/
│   └── useIngestJobProgress.ts        # React Query polling (3s interval)
└── types/
    └── ingest.ts                      # ManualIngestJob, IngestType TS types
```

### 20.8 Migration 0008

One new migration adds `manual_ingest_jobs`. No existing tables are modified.

Notes:
- Staging file path is **not** stored in the DB (it is only in memory / passed to the Celery task argument).
- `pgcrypto` `gen_random_uuid()` already available from migration 0001.
