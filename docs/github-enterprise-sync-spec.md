# GitHub Enterprise Sync Task — Strategy & Design Specification

**Status:** Draft for Architecture Review  
**Author:** Strategy & Design Agent  
**Date:** 2026-03-27  
**Target Milestone:** Phase 1 Implementation  

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)
2. [User Stories & Acceptance Criteria](#2-user-stories--acceptance-criteria)
3. [Enterprise Data Entities to Sync](#3-enterprise-data-entities-to-sync)
4. [GitHub App Authentication Design](#4-github-app-authentication-design)
5. [API / UX Design — Admin REST Endpoints](#5-api--ux-design--admin-rest-endpoints)
6. [Rate Limit Compliance Strategy](#6-rate-limit-compliance-strategy)
7. [Scheduler Design](#7-scheduler-design)
8. [Sync State Tracking & Resumability](#8-sync-state-tracking--resumability)
9. [Conflict Resolution Policy](#9-conflict-resolution-policy)
10. [New Data Models](#10-new-data-models)
11. [Configuration Schema](#11-configuration-schema)
12. [Phased Rollout & Prioritization](#12-phased-rollout--prioritization)
13. [Non-Functional Requirements](#13-non-functional-requirements)
14. [Open Questions for Architecture Review](#14-open-questions-for-architecture-review)
15. [Handoff Package Summary](#15-handoff-package-summary)

---

## 1. Problem Statement

Octowatch's detection engine relies on event-derived state — it only knows about entities that have appeared in streaming audit log events since the system came online. This means:

- **No baseline knowledge** of users, repos, teams, or collaborators that existed before Octowatch was deployed.
- **Detection blind spots**: rules comparing "current state vs. known good" fire false positives or miss real threats because the "known good" baseline is incomplete.
- **Outside collaborator tracking** in `external_collaborators` is only populated when a `member.added` or `outside_collaborator.add` event is ingested — anyone granted access before ingestion began is invisible.
- **Drift risk**: even after initial hydration, the event stream can miss events (backfill gaps, integration outages), causing state drift over time.

The GitHub Enterprise Sync Task closes this gap by performing a snapshot sync of all current enterprise assets from the GitHub API and writing them into Octowatch's database as a baseline.

---

## 2. User Stories & Acceptance Criteria

### US-01 — GitHub App Credential Configuration

**As a** sys_admin,  
**I want to** configure GitHub App credentials (App ID, private key, installation ID) for my enterprise,  
**so that** Octowatch can authenticate to the GitHub API without using personal access tokens.

**Acceptance Criteria:**

```
Given I am a sys_admin user authenticated to Octowatch
When I add GITHUB_APP_ID, GITHUB_APP_PRIVATE_KEY, GITHUB_APP_INSTALLATION_ID,
     and GITHUB_ENTERPRISE_SLUG to the environment configuration
Then the application validates these credentials at startup by minting a test JWT
     and verifying the installation exists
And if validation fails, the application logs a structured error and disables sync
     functionality rather than crashing
And the private key is never written to database, logs, or API responses

Given the GitHub App installation token has expired (>55 minutes old)
When the next API call is attempted
Then a new installation token is automatically minted before the call proceeds
And no API call is made with an expired token
```

---

### US-02 — Manual Full Sync Trigger

**As a** sys_admin,  
**I want to** trigger a full enterprise sync on demand from the admin API,  
**so that** I can re-baseline the system after suspected drift or a security incident.

**Acceptance Criteria:**

```
Given I am authenticated as a sys_admin
When I POST /api/v1/admin/sync/trigger with body {"mode": "full"}
Then a new EnterpriseSyncRun record is created with status="pending"
And a Celery task is dispatched to the "sync" queue immediately
And the response body contains {run_id, status, triggered_by, triggered_at}
And the response HTTP status is 202 Accepted

Given a sync run is already in status="running"
When I POST /api/v1/admin/sync/trigger
Then the response is 409 Conflict with detail "A sync run is already in progress"
And no new task is dispatched

Given I am NOT a sys_admin (any other role)
When I POST /api/v1/admin/sync/trigger
Then the response is 403 Forbidden
And no task is dispatched

Given the sync task cannot be dispatched (Valkey unavailable)
When I POST /api/v1/admin/sync/trigger
Then the SyncRun record is set to status="failed" immediately
And the response is 503 Service Unavailable with a descriptive error
And the error is written to structured logs with correlation ID
```

---

### US-03 — Sync Status Visibility

**As a** sys_admin,  
**I want to** check the status of running and past sync runs from the admin API,  
**so that** I can monitor progress and diagnose failures.

**Acceptance Criteria:**

```
Given one or more sync runs exist
When I GET /api/v1/admin/sync/runs?limit=10
Then I receive a list of sync runs sorted by started_at descending
And each entry includes: run_id, status, triggered_by, started_at, completed_at,
    progress (completed_entities / total_entities), error_message

Given a specific sync run exists with run_id=42
When I GET /api/v1/admin/sync/runs/42
Then I receive the run details plus a per-entity breakdown
And each entity entry includes: entity_type, status, records_upserted,
    records_failed, started_at, completed_at, error_message

Given a sync run is currently running
When I GET /api/v1/admin/sync/runs/{id}
Then the response shows status="running", reflects the latest
    completed_entities count, and the per-entity statuses show which
    entity types are "running", "completed", or "pending"
```

---

### US-04 — Sync Schedule Configuration

**As a** sys_admin,  
**I want to** configure how often automatic syncs occur (between 60 and 90 days),  
**so that** the baseline refreshes automatically without manual intervention.

**Acceptance Criteria:**

```
Given GITHUB_SYNC_INTERVAL_DAYS=60 (the default)
When the sync coordinator heartbeat runs (daily at 02:00 UTC)
Then it checks whether the last completed sync was >= 60 days ago
And if so, it dispatches a new full sync run with triggered_by="scheduler"

Given I set GITHUB_SYNC_INTERVAL_DAYS=75
When 75 days have elapsed since the last completed sync
Then the scheduler auto-triggers a sync
And a run record is created with triggered_by="scheduler"

Given GITHUB_SYNC_INTERVAL_DAYS=50 is set (invalid: below minimum)
When the application starts
Then startup validation raises a ConfigurationError listing the constraint
And the application exits rather than running with an invalid interval

Given GITHUB_SYNC_INTERVAL_DAYS=95 is set (invalid: above maximum)
When the application starts
Then startup validation raises a ConfigurationError listing the constraint

Given a sync run is already running when the heartbeat fires
When the heartbeat checks whether a sync is due
Then it detects the running sync and does NOT dispatch another one
And it logs "sync_heartbeat.already_running" at debug level
```

---

### US-05 — Cancellation of a Running Sync

**As a** sys_admin,  
**I want to** cancel a sync run that is taking too long or consuming excessive rate limit,  
**so that** I do not exhaust the GitHub API quota during business hours.

**Acceptance Criteria:**

```
Given a sync run is in status="running"
When I POST /api/v1/admin/sync/runs/{id}/cancel
Then the run record is updated to status="cancelling"
And the running Celery task receives a soft shutdown signal (task revoke)
And within 60 seconds the task completes its current paginated API call,
    saves its cursor to EnterpriseSyncEntityStatus, and exits cleanly
And the run record transitions to status="cancelled"
And a subsequent trigger will resume from the saved cursors

Given a sync run is in status="completed" or "failed"
When I POST /api/v1/admin/sync/runs/{id}/cancel
Then the response is 409 Conflict with detail "Run is not in a cancellable state"
```

---

### US-06 — Resume of a Partial Sync

**As a** sys_admin,  
**I want to** resume a cancelled or failed sync from where it left off,  
**so that** I do not have to re-fetch entities that were already successfully synced.

**Acceptance Criteria:**

```
Given a sync run in status="cancelled" or "failed" with saved cursors
When I POST /api/v1/admin/sync/trigger with body {"mode": "resume", "run_id": 42}
Then the existing run record is reactivated (status → "running")
And only entity_types whose status != "completed" are re-queued
And entity_types with saved cursors resume from their last cursor position
And entity_types with status="completed" are not re-fetched

Given no previous incomplete sync run exists
When I POST /api/v1/admin/sync/trigger with body {"mode": "resume", "run_id": 99}
Then the response is 404 Not Found with detail "Sync run not found or not resumable"
```

---

### US-07 — Outside Collaborator Baseline Population

**As a** security analyst,  
**I want** the sync to populate the existing `external_collaborators` table with
all current outside collaborators across all repos in the enterprise,  
**so that** detection rules comparing against known collaborators work correctly
from day one, without waiting for add/remove events to occur.

**Acceptance Criteria:**

```
Given outside collaborators exist in GitHub repos before Octowatch was deployed
When the enterprise sync completes
Then each collaborator appears in external_collaborators with is_active=true,
    role set correctly, and data_source="github_api_sync"

Given an outside collaborator is recorded in external_collaborators with is_active=true
    (from a past audit event), but the sync finds they are no longer present in GitHub
When the sync processes that repo's outside collaborators
Then the record is updated: is_active=false, removed_at=sync_timestamp,
    and a flag conflict_with_event_data=true is set
And an audit trail entry is written noting the discrepancy
And no record is hard-deleted (non-destructive policy)
```

---

### US-08 — Automated Scheduler (non-human actor)

**As a** Celery scheduler,  
**I want to** check daily whether a new sync is due based on the configured interval,  
**so that** the enterprise baseline stays current without requiring manual triggers.

**Acceptance Criteria:**

```
Given beat_schedule includes "enterprise-sync-heartbeat" running daily
When the heartbeat task executes
Then it queries last completed enterprise_sync_run
And if last_completed_at IS NULL (never synced), it dispatches a full sync
And if last_completed_at + interval_days < now, it dispatches a full sync
And if last_completed_at + interval_days >= now, it takes no action
And in all cases it writes a structured log line with the decision outcome
```

---

## 3. Enterprise Data Entities to Sync

The table below lists every GitHub resource Octowatch should sync, its relevant GitHub API endpoint, security justification, and assigned phase.

### 3.1 Entity Catalog

| # | Entity Type | GitHub API Endpoint | Security Value | Phase |
|---|-------------|---------------------|----------------|-------|
| 1 | **Enterprise members** | `GET /enterprises/{slug}/members` | Who belongs to the enterprise at all; detect ghost accounts, churned employee accounts | 1 |
| 2 | **Enterprise organizations** | `GET /enterprises/{slug}/organizations` | Complete list of orgs; detect shadow orgs | 1 |
| 3 | **Org members + roles** | `GET /orgs/{org}/members?role=all` | Who is an owner vs. member; over-privileged owners are high-risk | 1 |
| 4 | **Outside collaborators** | `GET /orgs/{org}/outside_collaborators` | Guest access is the #1 lateral movement vector in GitHub enterprises | 1 |
| 5 | **SAML credential authorizations** | `GET /orgs/{org}/credential-authorizations` | PATs and OAuth tokens granted SAML SSO authorization; unlinked tokens are exfiltration risk | 1 |
| 6 | **GitHub App installations (org-level)** | `GET /orgs/{org}/installations` | Third-party supply chain risk; installations with broad write permissions | 1 |
| 7 | **Secret scanning alerts (open)** | `GET /repos/{owner}/{repo}/secret-scanning/alerts?state=open` | Active exposed credentials; must be baseline for alert deduplication | 1 |
| 8 | **Repository inventory** | `GET /orgs/{org}/repos` | Names, visibility, archived/disabled status, default branch, fork/template status | 1 |
| 9 | **Org metadata** | `GET /orgs/{org}` | Two-factor requirement, default permissions, member privileges | 1 |
| 10 | **Teams** | `GET /orgs/{org}/teams` | Team names, privacy, parent team; feeds RBAC modeling | 2 |
| 11 | **Team memberships** | `GET /orgs/{org}/teams/{slug}/members` | Who is in each team; detect overprivileged team membership | 2 |
| 12 | **Team repositories** | `GET /orgs/{org}/teams/{slug}/repos` | Which repos each team can access and at what permission level | 2 |
| 13 | **Repo collaborators** | `GET /repos/{owner}/{repo}/collaborators?affiliation=direct` | Direct (not team-inherited) repo access grants | 2 |
| 14 | **Branch protection rules** | `GET /repos/{owner}/{repo}/branches/{branch}/protection` | Repos missing protection on default branch are a code integrity risk | 2 |
| 15 | **Dependabot alerts (open)** | `GET /repos/{owner}/{repo}/dependabot/alerts?state=open` | Active vulnerable dependencies baseline | 2 |
| 16 | **Org webhooks** | `GET /orgs/{org}/hooks` | Active webhooks that could exfiltrate event data; detect unauthorized additions | 3 |
| 17 | **Repo webhooks** | `GET /repos/{owner}/{repo}/hooks` | Same exfiltration risk at repo level | 3 |
| 18 | **Code scanning configurations** | `GET /repos/{owner}/{repo}/code-scanning/default-setup` | Which repos lack code scanning; security coverage gap | 3 |
| 19 | **Actions permissions (org)** | `GET /orgs/{org}/actions/permissions` | Whether external Actions/public Actions are allowed; supply chain | 3 |
| 20 | **Actions permissions (repo)** | `GET /repos/{owner}/{repo}/actions/permissions` | Per-repo override of Actions policy | 3 |
| 21 | **Self-hosted runners (org)** | `GET /orgs/{org}/actions/runners` | Self-hosted runners can run arbitrary workloads; need baseline | 3 |
| 22 | **Deploy keys** | `GET /repos/{owner}/{repo}/keys` | Persistent SSH keys with repo access; often overlooked credential | 3 |
| 23 | **Enterprise IP allow list** | `GraphQL: enterpriseAdministration { enterprise { ipAllowListEntries } }` | Network access control baseline | 4 |
| 24 | **Environments + protection rules** | `GET /repos/{owner}/{repo}/environments` | Environment deployment protection gates | 4 |
| 25 | **Org audit log actors (domain)** | `GET /orgs/{org}/audit-log?phrase=action:org` (sampled historical) | Populate actor inventory from historical events without full re-ingestion | 4 |
| 26 | **Packages** | `GET /orgs/{org}/packages` | Published packages from the org; supply chain provenance | 4 |

### 3.2 Entity Relationships & Sync Order

Sync must respect dependency order to avoid FK violations and to maximize value from early data:

```
Enterprise
  └─▶ Organizations (enumerate before syncing per-org entities)
        └─▶ Org Metadata
        └─▶ Org Members
        └─▶ Outside Collaborators         ← populates existing external_collaborators table
        └─▶ SAML Credential Authorizations
        └─▶ GitHub App Installations
        └─▶ Teams
              └─▶ Team Memberships
              └─▶ Team Repositories
        └─▶ Repositories                  ← must exist before repo-level entities
              └─▶ Repo Collaborators
              └─▶ Branch Protection Rules
              └─▶ Secret Scanning Alerts
              └─▶ Dependabot Alerts
              └─▶ Webhooks
              └─▶ Code Scanning Config
              └─▶ Deploy Keys
              └─▶ Environments
```

Repos are the deepest and most numerous entity (a large enterprise may have 10,000+ repos). Repo-level entities are fanned out into per-repo sub-tasks (see Section 7).

---

## 4. GitHub App Authentication Design

### 4.1 Auth Flow

No Personal Access Tokens are used anywhere in this feature. The complete auth sequence per token lifecycle:

```
┌──────────────────────────────────────────────────────────┐
│  GitHubAppTokenManager                                    │
│                                                          │
│  1. Load private key PEM from GITHUB_APP_PRIVATE_KEY env │
│  2. Mint JWT (RS256):                                     │
│       iss = GITHUB_APP_ID                                │
│       iat = now - 60s (clock skew tolerance)             │
│       exp = now + 540s (9 min, safe below 10 min max)    │
│  3. POST /app/installations/{GITHUB_APP_INSTALLATION_ID}  │
│       /access_tokens                                      │
│       Authorization: Bearer {jwt}                        │
│  4. Receive {token, expires_at} — valid 1 hour           │
│  5. Cache token with expires_at                          │
│  6. Before each API call: if expires_at - now < 5 min,   │
│       refresh proactively                                │
└──────────────────────────────────────────────────────────┘
```

### 4.2 Token Scoping

The GitHub App must be registered with the following installation permissions:

| Resource | Permission Level | Justification |
|----------|-----------------|---------------|
| Members | Read | Org/enterprise member enumeration |
| Administration | Read | Org settings, branch protection |
| Repository metadata | Read | Repo inventory |
| Secret scanning alerts | Read | Alert baseline |
| Dependabot alerts | Read | Vulnerability baseline |
| Webhooks | Read | Webhook inventory |
| Actions | Read | Actions permissions |
| Environments | Read | Environment protection rules |

> **Note:** The GitHub App does not need Write permissions for any sync operation. All sync operations are read-only against GitHub. Write operations only go to Octowatch's own database.

### 4.3 Multi-Org Installation

For enterprises with multiple organizations, the sync must iterate across all installations:

1. `GET /app/installations` — list all installations for the GitHub App
2. For each installation with `account.type == "Organization"`: request a scoped installation token for that org's `installation_id`
3. Cache each org token independently (different expiry per org token)
4. Alternatively: configure `GITHUB_APP_INSTALLATION_ID` per org via a JSON map (see Section 11)

### 4.4 Token Storage Security

- Private key is stored exclusively as an environment variable (`GITHUB_APP_PRIVATE_KEY`)
- Never logged (must be in `settings.model_config = SettingsConfigDict(secrets_dir=...)` or masked)
- Installation tokens are held in process memory only (never written to DB, logs, or API responses)
- The token manager exposes only `get_token() -> str` — callers never touch the raw credential

---

## 5. API / UX Design — Admin REST Endpoints

All endpoints mount under the existing `/api/v1/admin` prefix (matching the existing `admin.py` router pattern), and all require `require_role(["sys_admin"])`.

### 5.1 Endpoint Inventory

```
POST   /api/v1/admin/sync/trigger              Trigger a new sync or resume an existing one
GET    /api/v1/admin/sync/runs                 List sync runs (paginated)
GET    /api/v1/admin/sync/runs/{run_id}        Get run detail with per-entity breakdown
POST   /api/v1/admin/sync/runs/{run_id}/cancel Cancel a running sync
GET    /api/v1/admin/sync/config               View current sync configuration
```

### 5.2 Request / Response Schemas

#### `POST /api/v1/admin/sync/trigger`

**Request body:**

```json
{
  "mode": "full" | "resume",
  "run_id": 42           // only required when mode="resume"
}
```

**Response 202:**

```json
{
  "run_id": 107,
  "status": "pending",
  "mode": "full",
  "triggered_by": "octocat",
  "triggered_at": "2026-03-27T14:30:00Z",
  "task_id": "celery-task-uuid-here"
}
```

**Error responses:**

| Status | Condition |
|--------|-----------|
| 400 | Invalid `mode` value or `run_id` missing for resume |
| 403 | Requester lacks `sys_admin` role |
| 404 | `run_id` not found (resume mode) |
| 409 | A sync is already running |
| 422 | GitHub App not configured (missing env vars) |
| 503 | Celery/Valkey unavailable |

---

#### `GET /api/v1/admin/sync/runs`

**Query params:** `limit` (default 20, max 100), `status` (filter), `cursor` (pagination)

**Response 200:**

```json
{
  "items": [
    {
      "run_id": 107,
      "status": "running",
      "mode": "full",
      "triggered_by": "octocat",
      "triggered_at": "2026-03-27T14:30:00Z",
      "started_at": "2026-03-27T14:30:05Z",
      "completed_at": null,
      "total_entities": 18,
      "completed_entities": 5,
      "progress_pct": 27.8,
      "error_message": null
    }
  ],
  "next_cursor": "eyJpZCI6IDEwNn0="
}
```

---

#### `GET /api/v1/admin/sync/runs/{run_id}`

**Response 200:**

```json
{
  "run_id": 107,
  "status": "completed",
  "mode": "full",
  "triggered_by": "scheduler",
  "enterprise_slug": "my-enterprise",
  "started_at": "2026-03-27T02:00:05Z",
  "completed_at": "2026-03-27T03:47:12Z",
  "duration_seconds": 6427,
  "total_entities": 18,
  "completed_entities": 18,
  "total_records_upserted": 147832,
  "total_records_failed": 0,
  "error_message": null,
  "entity_statuses": [
    {
      "entity_type": "orgs",
      "status": "completed",
      "records_upserted": 12,
      "records_failed": 0,
      "started_at": "2026-03-27T02:00:06Z",
      "completed_at": "2026-03-27T02:00:31Z",
      "error_message": null
    },
    {
      "entity_type": "org_members/my-org-1",
      "status": "completed",
      "records_upserted": 843,
      "records_failed": 0,
      "started_at": "2026-03-27T02:00:32Z",
      "completed_at": "2026-03-27T02:04:15Z",
      "error_message": null
    }
  ]
}
```

---

#### `GET /api/v1/admin/sync/config`

**Response 200:**

```json
{
  "github_app_configured": true,
  "github_app_id": 12345,
  "enterprise_slug": "my-enterprise",
  "sync_interval_days": 60,
  "sync_interval_days_min": 60,
  "sync_interval_days_max": 90,
  "last_completed_run": {
    "run_id": 106,
    "completed_at": "2025-12-18T03:47:12Z"
  },
  "next_scheduled_run_at": "2026-02-16T02:00:00Z",
  "scheduler_enabled": true
}
```

Note: `github_app_private_key` is **never** included in any response.

---

### 5.3 Audit Trail for Admin Actions

Every `POST /sync/trigger` and `POST /sync/runs/{id}/cancel` must write a record to an audit trail table capturing: `actor_login`, `action`, `target_run_id`, `source_ip`, `user_agent`, `timestamp`. Reuse the existing `AuditTrail` model if it already captures admin actions; otherwise add a lightweight `SyncAuditEntry` model.

---

## 6. Rate Limit Compliance Strategy

### 6.1 GitHub API Limits in Scope

| Limit | Value | Strategy |
|-------|-------|----------|
| Primary hourly quota | 15,000 req/hr (GitHub App on GHEC org) | Track remaining via `x-ratelimit-remaining` |
| Secondary: concurrency | 100 concurrent requests | `asyncio.Semaphore(80)` — 80% of limit |
| Secondary: point rate | 900 points/min (GET=1pt, POST=5pts) | Token bucket: refill 15pts/second |
| Secondary: CPU trigger | No fixed limit | Back off on 429/403 with `retry-after` |

### 6.2 `GitHubRateLimiter` Design

The sync worker uses a single `GitHubRateLimiter` instance shared across all coroutines within a sync task execution:

```python
# Pseudocode — not implementation
class GitHubRateLimiter:
    semaphore: asyncio.Semaphore(80)       # concurrent request cap
    point_bucket: TokenBucket(15, 900)     # refill 15pts/s, max 900
    
    async def request(session, method, url, **kwargs) -> aiohttp.ClientResponse:
        async with self.semaphore:
            await self.point_bucket.consume(1)   # GET = 1 point
            resp = await session.request(method, url, **kwargs)
            self._update_from_headers(resp.headers)
            if resp.status in (403, 429):
                await self._handle_rate_limit(resp)
                raise RateLimitRetry(...)
            return resp
    
    def _update_from_headers(self, headers):
        remaining = int(headers.get("x-ratelimit-remaining", 9999))
        reset_ts   = int(headers.get("x-ratelimit-reset", 0))
        if remaining < 500:
            # Proactive slow-down: inject sleep so we coast to reset
            self._throttle_until = datetime.utcfromtimestamp(reset_ts)
    
    async def _handle_rate_limit(self, resp):
        retry_after = int(resp.headers.get("retry-after", 60))
        wait = min(retry_after, 300)  # cap at 5 minutes
        logger.warning("rate_limit.backing_off", wait_seconds=wait)
        await asyncio.sleep(wait)
```

### 6.3 Exponential Backoff on Transient Errors

For non-rate-limit errors (5xx, connection errors), use exponential backoff with jitter:

```
wait = min(base * 2^attempt, cap) + random_jitter(0, 1s)
base = 1s, cap = 60s, max_attempts = 5
```

After 5 attempts, record the entity as `status="failed"` in `EnterpriseSyncEntityStatus`, write the error, and continue with the next entity rather than aborting the entire run.

### 6.4 Expected API Call Budget

For a representative large enterprise (12 orgs, 5,000 repos, 3,000 members):

| Entity Type | Estimated Calls | Notes |
|-------------|----------------|-------|
| Enterprise members | ~30 | 100/page |
| Org enumeration | 1 | paginated |
| Per-org metadata | 12 | 1 call/org |
| Org members | ~360 | avg 250 members/org |
| Outside collaborators | ~120 | avg 100/org |
| SAML authorizations | ~360 | avg 250/org |
| App installations | 12 | one call/org | 
| Teams | ~120 | avg 100 teams/org |
| Team members | ~600 | avg 5 calls/team |
| Repositories | ~600 | 30 calls/org for 2,500 per-org repos |
| Repo collaborators | ~5,000 | 1 call/repo |
| Branch protection | ~5,000 | 1 call per default branch |
| Secret scanning alerts | ~5,000 | 1 call/repo (paginated if many) |
| **Total Phase 1+2** | **~12,200** | < 1hr (15k limit) |

> **Conclusion:** A full Phase 1+2 sync fits comfortably within one installation token's quota. Phase 3+4 entities for large enterprises may require 2–3 token refreshes but still finish within 2–4 hours.

---

## 7. Scheduler Design

### 7.1 Celery Beat Integration

The sync scheduling uses two Beat entries added to `celery_app.py`:

```python
# In beat_schedule dict:

"enterprise-sync-heartbeat": {
    "task": "app.workers.sync_worker.sync_heartbeat_task",
    "schedule": crontab(hour=2, minute=0),   # daily at 02:00 UTC
    "options": {"queue": "sync"},
},
```

The heartbeat task is **not** the sync task itself — it is a cheap daily check that queries the database for the last completed sync and decides whether to dispatch the full sync:

```python
# sync_worker.py pseudocode
@celery_app.task(name="app.workers.sync_worker.sync_heartbeat_task", bind=True)
def sync_heartbeat_task(self: Task) -> dict:
    result = asyncio.run(_check_and_dispatch())
    return result

async def _check_and_dispatch() -> dict:
    async with AsyncSessionLocal() as session:
        last_run = await _get_last_completed_run(session)
        interval = timedelta(days=settings.github_app.GITHUB_SYNC_INTERVAL_DAYS)
        
        if last_run is None or last_run.completed_at + interval < datetime.now(UTC):
            # Check no run is currently in progress
            if not await _any_run_in_progress(session):
                run = await _create_sync_run(session, triggered_by="scheduler")
                celery_app.send_task(
                    "app.workers.sync_worker.enterprise_sync_coordinator_task",
                    args=[run.id],
                    queue="sync",
                )
                return {"dispatched": True, "run_id": run.id}
        
        return {"dispatched": False}
```

### 7.2 Configurable Interval Validation

The `GITHUB_SYNC_INTERVAL_DAYS` setting uses a `field_validator` to enforce the 60–90 day range:

```python
@field_validator("GITHUB_SYNC_INTERVAL_DAYS")
@classmethod
def validate_interval(cls, v: int) -> int:
    if not (60 <= v <= 90):
        raise ValueError(
            f"GITHUB_SYNC_INTERVAL_DAYS must be between 60 and 90, got {v}"
        )
    return v
```

### 7.3 Task Architecture

The sync is split into a coordinator + entity worker pattern to stay within Celery's existing 30-minute soft time limit per task:

```
enterprise_sync_coordinator_task(run_id)
    │
    ├─ Mints GitHub App token
    ├─ Fetches org list
    ├─ Creates EnterpriseSyncEntityStatus rows for each entity × org
    └─ Dispatches N tasks:
         ├─ sync_entity_task("enterprise_members", run_id, cursor=None)
         ├─ sync_entity_task("orgs", run_id, cursor=None)
         ├─ sync_entity_task("org_members/my-org-1", run_id, cursor=None)
         ├─ sync_entity_task("org_members/my-org-2", run_id, cursor=None)
         ├─ sync_entity_task("outside_collaborators/my-org-1", run_id, ...)
         └─ ... etc.
         
         After each org-level entity completes:
         ├─ sync_entity_task("repos/my-org-1", run_id, cursor=None)
         └─ After repos complete:
              ├─ sync_entity_task("secret_scanning_alerts/my-org-1", run_id, ...)
              └─ ...
```

The **coordinator task** has `task_soft_time_limit=300` (5 min) since it only orchestrates.  
Each **entity sync task** has `task_soft_time_limit=1800` (30 min) matching the existing global default.  
The task override is set at the `@celery_app.task()` decorator level with `soft_time_limit=`.

A new `"sync"` queue is added to `task_routes` to allow dedicated worker scaling:
```python
"app.workers.sync_worker.*": {"queue": "sync"},
```

### 7.4 Sync Run Completion Tracking

The coordinator either:
- Uses a Celery `chord` (group of entity tasks → completion callback), **or**
- Polls `EnterpriseSyncEntityStatus` rows on a 30-second interval until all entity types reach terminal status

The **polling approach** is recommended over chord because:
1. It survives coordinator worker restart (state is in DB, not Celery headers)
2. New entity types can be added without touching the chord signature
3. Cancellation can be implemented cleanly via a status flag check in the polling loop

---

## 8. Sync State Tracking & Resumability

### 8.1 Data Model Overview

Two new tables track sync state:

**`enterprise_sync_runs`** — one row per sync operation:

| Column | Type | Description |
|--------|------|-------------|
| `id` | BigInteger PK | Run identifier |
| `mode` | Text | `"full"` or `"resume"` |
| `status` | Text | `pending \| running \| cancelling \| cancelled \| completed \| failed \| partial` |
| `triggered_by` | Text | GitHub login or `"scheduler"` |
| `enterprise_slug` | Text | Enterprise slug at time of run |
| `started_at` | TimestampTZ | When coordinator task began |
| `completed_at` | TimestampTZ | NULL until terminal state |
| `total_entities` | Integer | Count of entity sync tasks dispatched |
| `completed_entities` | Integer | Count reaching `completed` terminal state |
| `total_records_upserted` | BigInteger | Aggregate across all entity tasks |
| `total_records_failed` | BigInteger | Records that failed to upsert |
| `error_message` | Text | Last fatal error if status=failed |
| `sync_config_snapshot` | JSONB | Settings values captured at run start |
| `created_at` | TimestampTZ | Row insert time |

**`enterprise_sync_entity_statuses`** — one row per (run × entity_type):

| Column | Type | Description |
|--------|------|-------------|
| `id` | BigInteger PK | |
| `sync_run_id` | FK → sync_runs | Parent run |
| `entity_type` | Text | `"org_members/my-org"`, `"repos/my-org"`, etc. |
| `status` | Text | `pending \| running \| completed \| failed \| skipped` |
| `started_at` | TimestampTZ | |
| `completed_at` | TimestampTZ | |
| `records_upserted` | Integer | |
| `records_failed` | Integer | |
| `next_cursor` | Text | GitHub pagination cursor (URL-safe string) for resumability |
| `error_message` | Text | |

### 8.2 Resumability Protocol

Each entity task writes its `next_cursor` to `EnterpriseSyncEntityStatus` after every successful API page:

```python
# After processing page N of org members:
entity_status.next_cursor = response_headers.get("link-next-cursor")
entity_status.records_upserted += len(page_records)
await session.commit()   # checkpoint after every page
```

On resume, the coordinator queries `entity_statuses` for rows with `status != "completed"`. For each such row, the task is re-dispatched with `cursor=entity_status.next_cursor`. Pages already fetched before the cursor are skipped entirely.

### 8.3 Progress Calculation

```
progress_pct = (completed_entities / total_entities) * 100

# Better metric: records-weighted progress (optional enhancement)
# weight each entity by estimated record count
```

The `GET /admin/sync/runs/{id}` endpoint derives `progress_pct` on read, not stored.

### 8.4 Stale Run Detection

If a sync run has `status="running"` but its most recently updated `entity_status` row has not changed in >2 hours, the run is likely orphaned (worker died). The heartbeat task includes a stale run check:

```python
# In sync_heartbeat_task:
stale_threshold = datetime.now(UTC) - timedelta(hours=2)
stale_run = await _find_stale_running_run(session, stale_threshold)
if stale_run:
    stale_run.status = "failed"
    stale_run.error_message = "Run timed out — worker likely died"
    await session.commit()
    logger.warning("sync.stale_run_detected", run_id=stale_run.id)
```

---

## 9. Conflict Resolution Policy

When synced data conflicts with event-derived data already in the database, the following rules apply. All conflicts are logged rather than silently resolved.

### 9.1 Resolution Matrix

| Conflict Scenario | Resolution | Rationale |
|-------------------|-----------|-----------|
| Sync finds a collaborator `is_active=true`; event data says `removed_at < sync_time` | **Event wins if removal event is recent (< 7 days); Sync wins if removal event is old (> 7 days)** | Recent removal events are likely reliable; stale event-derived removals may have been re-added since |
| Sync finds collaborator NOT present; existing record has `is_active=true` | **Sync wins** — set `is_active=false`, set `removed_at=sync_time` | Sync is a point-in-time truth snapshot; missing from API call means not present |
| Sync finds collaborator present; existing record has `is_active=false` with `removed_at` | **Sync wins** — set `is_active=true`, clear `removed_at` | They were re-added; sync is accurate |
| Sync finds a member `role=member`; event says they were made `owner` | **Take the latest timestamp** — if event is more recent than sync start, event wins; otherwise sync wins | Event timestamp is authoritative for changes that occurred after sync started |
| Sync finds repo `visibility=private`; no conflicting event exists | **Sync wins** (no conflict — this is new information) | Additive data, no conflict |
| Sync finds branch protection rule config differs from event-derived config | **Both preserved** — write sync data to `github_branch_protection_rules`; detection rules can compare both | Branch protection rules do not currently exist in events table; no real conflict |

### 9.2 Conflict Logging

All conflicts write a structured log entry:

```python
logger.warning(
    "sync.conflict_resolved",
    entity_type="external_collaborators",
    record_id=collab.id,
    org=collab.org,
    repo=collab.repo,
    github_login=collab.github_login,
    conflict_type="sync_says_inactive_event_says_active",
    resolution="sync_wins",
    sync_run_id=run_id,
)
```

Additionally, a `data_source` and `last_synced_at` column are added to relevant tables so queries can distinguish event-derived from sync-derived records.

### 9.3 Existing `external_collaborators` Table Augmentation

The existing `ExternalCollaborator` model requires two new columns to support sync:

| New Column | Type | Description |
|------------|------|-------------|
| `data_source` | Text | `"event_stream"` or `"github_api_sync"` |
| `last_synced_at` | TimestampTZ | Timestamp of last sync that touched this record |
| `sync_run_id` | BigInteger (FK, nullable) | Which sync run last updated this record |

These columns are additive (no breaking changes to existing event-derived logic). An Alembic migration handles them.

### 9.4 Non-Destructive Policy

The sync **never** hard-deletes any record. The only state change for "missing from sync" is setting `is_active=false` on the existing record. This preserves audit trail continuity and allows analysts to review discrepancies before trusting the sync.

---

## 10. New Data Models

The following new SQLAlchemy models are required. All use `Base` from `app.models.audit_event`.

### 10.1 `EnterpriseSyncRun`

```python
class EnterpriseSyncRun(Base):
    __tablename__ = "enterprise_sync_runs"
    
    id: BigInteger PK
    mode: Text                # "full" | "resume"
    status: Text              # see 8.1
    triggered_by: Text        # github_login or "scheduler"
    enterprise_slug: Text
    started_at: TimestampTZ | None
    completed_at: TimestampTZ | None
    total_entities: Integer   # set when coordinator starts
    completed_entities: Integer
    total_records_upserted: BigInteger
    total_records_failed: BigInteger
    error_message: Text | None
    sync_config_snapshot: JSONB
    created_at: TimestampTZ

    entity_statuses: relationship → EnterpriseSyncEntityStatus
    
    CheckConstraint("status IN ('pending','running','cancelling','cancelled','completed','failed','partial')")
    Index("idx_sync_runs_status", "status")
    Index("idx_sync_runs_completed", "completed_at DESC NULLS FIRST")
```

### 10.2 `EnterpriseSyncEntityStatus`

```python
class EnterpriseSyncEntityStatus(Base):
    __tablename__ = "enterprise_sync_entity_statuses"
    
    id: BigInteger PK
    sync_run_id: FK → enterprise_sync_runs.id (ON DELETE CASCADE)
    entity_type: Text         # e.g. "org_members/my-org"
    status: Text              # "pending" | "running" | "completed" | "failed" | "skipped"
    started_at: TimestampTZ | None
    completed_at: TimestampTZ | None
    records_upserted: Integer
    records_failed: Integer
    next_cursor: Text | None  # GitHub pagination cursor
    error_message: Text | None
    
    UniqueConstraint("sync_run_id", "entity_type")
    Index("idx_entity_status_run", "sync_run_id", "status")
```

### 10.3 `GithubOrgSnapshot`

```python
class GithubOrgSnapshot(Base):
    __tablename__ = "github_org_snapshots"
    
    id: BigInteger PK
    org: Text (unique)
    github_org_id: BigInteger
    plan_name: Text | None        # "enterprise", "team", etc.
    default_repository_permission: Text | None
    members_can_create_repositories: Boolean | None
    two_factor_requirement_enabled: Boolean | None
    members_allowed_repository_creation_type: Text | None
    raw_data: JSONB               # full API response
    last_synced_at: TimestampTZ
    sync_run_id: BigInteger (FK)
    
    Index("idx_org_snapshot_org", "org")
```

### 10.4 `GithubOrgMembership`

```python
class GithubOrgMembership(Base):
    __tablename__ = "github_org_memberships"
    
    id: BigInteger PK
    org: Text
    github_login: Text
    github_id: BigInteger | None
    role: Text                    # "member" | "owner"
    is_active: Boolean
    first_seen_at: TimestampTZ
    last_synced_at: TimestampTZ
    removed_at: TimestampTZ | None
    data_source: Text             # "event_stream" | "github_api_sync"
    sync_run_id: BigInteger | None
    
    UniqueConstraint("org", "github_login")
    Index("idx_org_membership_org", "org", "is_active")
    Index("idx_org_membership_login", "github_login")
```

### 10.5 `GithubRepoSnapshot`

```python
class GithubRepoSnapshot(Base):
    __tablename__ = "github_repo_snapshots"
    
    id: BigInteger PK
    org: Text
    repo: Text                    # full name: "org/repo"
    github_repo_id: BigInteger
    visibility: Text              # "public" | "private" | "internal"
    default_branch: Text
    archived: Boolean
    disabled: Boolean
    fork: Boolean
    is_template: Boolean
    pushed_at: TimestampTZ | None
    last_synced_at: TimestampTZ
    sync_run_id: BigInteger
    raw_data: JSONB
    
    UniqueConstraint("org", "repo")
    Index("idx_repo_snapshot_org", "org")
    Index("idx_repo_snapshot_visibility", "visibility")
```

### 10.6 `GithubBranchProtectionSnapshot`

```python
class GithubBranchProtectionSnapshot(Base):
    __tablename__ = "github_branch_protection_snapshots"
    
    id: BigInteger PK
    org: Text
    repo: Text
    branch: Text
    required_status_checks_enabled: Boolean
    required_pr_reviews_enabled: Boolean
    required_approving_review_count: Integer | None
    dismiss_stale_reviews: Boolean | None
    require_code_owner_reviews: Boolean | None
    restrictions_enabled: Boolean
    enforce_admins: Boolean | None
    allow_force_pushes: Boolean | None
    allow_deletions: Boolean | None
    last_synced_at: TimestampTZ
    sync_run_id: BigInteger
    raw_data: JSONB
    
    UniqueConstraint("org", "repo", "branch")
    Index("idx_branch_prot_org_repo", "org", "repo")
```

### 10.7 `GithubAppInstallationSnapshot`

```python
class GithubAppInstallationSnapshot(Base):
    __tablename__ = "github_app_installation_snapshots"
    
    id: BigInteger PK
    org: Text
    installation_id: BigInteger   # GitHub installation ID
    app_id: BigInteger
    app_slug: Text
    app_name: Text
    permissions: JSONB            # {"contents": "write", ...}
    events: JSONB                 # ["push", "pull_request", ...]
    created_at_github: TimestampTZ
    suspended_at: TimestampTZ | None
    is_active: Boolean            # false if suspended
    last_synced_at: TimestampTZ
    sync_run_id: BigInteger
    
    UniqueConstraint("org", "installation_id")
    Index("idx_app_install_org", "org", "is_active")
    Index("idx_app_install_app_slug", "app_slug")
```

### 10.8 `GithubSecretScanningAlertSnapshot`

```python
class GithubSecretScanningAlertSnapshot(Base):
    __tablename__ = "github_secret_scanning_alert_snapshots"
    
    id: BigInteger PK
    org: Text
    repo: Text
    alert_number: Integer
    state: Text                   # "open" | "resolved"
    secret_type: Text
    resolution: Text | None
    created_at_github: TimestampTZ
    resolved_at: TimestampTZ | None
    last_synced_at: TimestampTZ
    sync_run_id: BigInteger
    
    UniqueConstraint("org", "repo", "alert_number")
    Index("idx_secret_alert_org_state", "org", "state")
    Index("idx_secret_alert_repo", "repo", "state")
```

> **Additional models** for teams, webhooks, deploy keys, and SAML credential authorizations follow the same pattern. Full model definitions are deferred to the Architecture phase where Alembic migration versions will be authored.

---

## 11. Configuration Schema

A new `GithubAppSettings` class is added to `app/config.py` following the existing grouped `BaseSettings` pattern:

```python
class GithubAppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    GITHUB_APP_ID: int = Field(
        ..., description="GitHub App numeric ID from /settings/apps"
    )
    GITHUB_APP_PRIVATE_KEY: str = Field(
        ...,
        description=(
            "PEM-encoded RS256 private key for the GitHub App. "
            "Multiline: set as base64-encoded string or use a secrets mount. "
            "Never logged or exposed via API."
        ),
    )
    GITHUB_APP_INSTALLATION_ID: int | None = Field(
        None,
        description=(
            "Primary GitHub App installation ID. If omitted, the sync worker "
            "discovers all installations via GET /app/installations."
        ),
    )
    GITHUB_ENTERPRISE_SLUG: str | None = Field(
        None,
        description="GitHub Enterprise slug for /enterprises/{slug} API calls.",
    )
    GITHUB_SYNC_INTERVAL_DAYS: int = Field(
        default=60,
        description="Days between automatic sync runs. Must be 60–90.",
    )
    GITHUB_SYNC_ORGS: list[str] = Field(
        default_factory=list,
        description=(
            "Explicit list of org names to sync. "
            "Empty list = all orgs discovered from the enterprise or installation."
        ),
    )
    GITHUB_SYNC_ENABLED: bool = Field(
        default=True,
        description="Set to false to disable automatic sync scheduling entirely.",
    )
    GITHUB_API_BASE_URL: str = Field(
        default="https://api.github.com",
        description=(
            "Override for GitHub Enterprise Server environments. "
            "Default is the GHEC API endpoint."
        ),
    )

    @field_validator("GITHUB_SYNC_INTERVAL_DAYS")
    @classmethod
    def validate_interval(cls, v: int) -> int:
        if not (60 <= v <= 90):
            raise ValueError(
                f"GITHUB_SYNC_INTERVAL_DAYS must be between 60 and 90 (inclusive), got {v}"
            )
        return v

    @field_validator("GITHUB_APP_PRIVATE_KEY")
    @classmethod
    def validate_private_key(cls, v: str) -> str:
        # Accept base64-encoded or raw PEM; normalize to PEM
        if not v.strip().startswith("-----BEGIN"):
            import base64
            try:
                v = base64.b64decode(v).decode("utf-8")
            except Exception:
                raise ValueError(
                    "GITHUB_APP_PRIVATE_KEY must be a PEM string or base64-encoded PEM"
                )
        if "RSA PRIVATE KEY" not in v and "PRIVATE KEY" not in v:
            raise ValueError(
                "GITHUB_APP_PRIVATE_KEY does not appear to be an RSA private key"
            )
        return v

    @field_validator("GITHUB_API_BASE_URL")
    @classmethod
    def validate_api_url(cls, v: str) -> str:
        parsed = urlparse(v)
        if parsed.scheme not in ("https",):
            raise ValueError("GITHUB_API_BASE_URL must use https://")
        # SSRF protection: reject cloud metadata addresses
        host = (parsed.hostname or "").lower()
        _BLOCKED = ("169.254.169.254", "metadata.google.internal", "169.254.170.2")
        if host in _BLOCKED or host.startswith("169.254."):
            raise ValueError("SSRF protection: GITHUB_API_BASE_URL must not point to metadata IPs")
        return v.rstrip("/")
```

The root `Settings` class adds:
```python
github_app: GithubAppSettings = Field(default_factory=GithubAppSettings)
```

---

## 12. Phased Rollout & Prioritization

### Phase 1 — Critical Baseline (Highest Security Value)

**Target:** Complete in first sprint. Delivers immediate detection value.

| Entity | Security Justification | Effort |
|--------|----------------------|--------|
| Enterprise organizations | Enumerates all orgs — prevents gaps in coverage | S |
| Org metadata (2FA, permissions) | Baseline for "org hardening regressed" detections | S |
| Enterprise & org members | Who belongs → enables ghost account and terminated-employee detections | M |
| Outside collaborators | Populates `external_collaborators` — highest-risk access type | M |
| Repository inventory (visibility, archived) | Enables "private repo made public" baseline comparison | M |
| GitHub App installations | Supply-chain risk; must know what's installed before detecting new installs | M |
| Secret scanning alerts (open) | Active exposed credentials; enables alert-volume anomaly detection | L |

**Phase 1 success criteria:**
- All existing `external_collaborators` detection rules have 100% of current outside collaborators in the DB before first rule evaluation after deployment
- `GET /admin/sync/runs/{id}` shows `status="completed"` with zero `records_failed`
- Sync completes within 4 hours for an enterprise with up to 10,000 repos

---

### Phase 2 — Extended Coverage (High Value)

**Target:** Second sprint. Significantly expands detection capability.

| Entity | Security Justification | Effort |
|--------|----------------------|--------|
| Teams + team memberships | Team-based access grants are the majority of repo permissions in large enterprises | M |
| Team repository permissions | What permissions each team has; detects privilege escalation | M |
| Direct repo collaborators | Non-team grants that often represent exceptions and over-privilege | M |
| Branch protection rules | Repos missing protection on default branch are code-integrity risks | L |
| Dependabot alerts (open) | Vulnerable dependency baseline for anomaly detection | M |

---

### Phase 3 — Security Posture Hardening

**Target:** Third sprint. Adds exfiltration and supply-chain coverage.

| Entity | Security Justification | Effort |
|--------|----------------------|--------|
| Org + repo webhooks | Exfiltration vector; detect unauthorized webhook additions | M |
| Code scanning configurations | Identifies repos with no code scanning — security coverage gaps | M |
| Actions permissions (org + repo) | Public Actions allowed policies; supply-chain risk | M |
| Self-hosted runners | Run arbitrary workloads; inventory is a security requirement | S |
| Deploy keys | Long-lived SSH keys with repo access often overlooked in offboarding | M |
| SAML credential authorizations | PATs/tokens with SAML SSO authorize; unlinked tokens are exfiltration risk | M |

---

### Phase 4 — Completeness & Compliance

**Target:** Delivered when Phase 3 is stable. Compliance-driven features.

| Entity | Security Justification | Effort |
|--------|----------------------|--------|
| Enterprise IP allow list (GraphQL) | Network access control baseline | M |
| Environments + protection rules | Deployment gate integrity | S |
| Packages | Supply-chain provenance | S |
| GraphQL enhancements | Enterprise-level SAML identity provider configuration | L |

---

## 13. Non-Functional Requirements

### Performance

| Metric | Requirement |
|--------|-------------|
| Phase 1+2 full sync duration | ≤4 hours for enterprises with ≤10,000 repos |
| Phase 1+2 full sync duration | ≤8 hours for enterprises with ≤50,000 repos |
| Manual trigger API response latency (task dispatch) | ≤2 seconds p95 |
| `GET /admin/sync/runs/{id}` response latency | ≤500ms p95 |
| Rate limit headroom maintained | `x-ratelimit-remaining` stays above 500 at all times |

### Reliability

| Metric | Requirement |
|--------|-------------|
| Partial failure tolerance | Any single entity type failing must NOT abort the overall sync run |
| Crash recovery | After worker restart, resuming from cursor must not re-process already-synced pages |
| Token refresh | Zero API calls made with an expired installation token |
| Idempotency | Running sync twice within 24 hours produces identical DB state (upsert semantics) |

### Observability

| Requirement |
|-------------|
| Every sync run, entity sync start/complete/fail, rate limit backoff, and conflict resolution must produce a structured log line (structlog) with `run_id`, `entity_type`, and correlation context |
| `GET /admin/sync/runs/{id}` provides sufficient detail to diagnose any failure without requiring log access |
| A Prometheus counter `octowatch_sync_records_upserted_total{entity_type}` increments per upserted record |
| A Prometheus gauge `octowatch_sync_last_completed_timestamp` set at run completion (feeds SLA alerting) |

### Security

| Requirement |
|-------------|
| GitHub App private key never appears in logs, API responses, or `sync_config_snapshot` JSONB |
| Installation tokens never persist to database, file system, or structured logs |
| All sync API endpoints (`/admin/sync/*`) require `sys_admin` role |
| SSRF validation on `GITHUB_API_BASE_URL` (implemented in `field_validator`) |
| Sync does not write data to GitHub — all writes are to Octowatch's own database only |

### Scalability

| Requirement |
|-------------|
| Sync worker must bind to dedicated `"sync"` queue to avoid competing with ingestion/detection queues |
| Number of concurrent GitHub API requests capped at 80 (via semaphore) regardless of entity parallelism |
| Sync architecture must support adding new entity types by adding a new task + entity_type constant — no coordinator changes required |

---

## 14. Open Questions for Architecture Review

1. **Multi-installation vs. single installation:** Should one GitHub App installation cover the entire enterprise (requires org-level installation in each org), or should there be one enterprise-level installation? The answer affects token acquisition strategy and scoping.

2. **GraphQL vs. REST for enterprise-level data:** IP allow list and SAML identity provider configuration have no REST equivalents — they require GraphQL. Should Phase 1 include GraphQL support, or is it deferred to Phase 4?

3. **External collaborators table strategy:** Should sync populate the existing `external_collaborators` table (with new columns), or create a separate `github_outside_collaborator_snapshots` table and feed `external_collaborators` via a reconciliation step? The first approach keeps detection queries simpler; the second preserves cleaner separation of concerns.

4. **Alembic migration sequencing:** Eight new tables (plus column additions to `external_collaborators`) require ordering. Architecture should confirm whether these can be consolidated into a single migration or need to be sequenced to accommodate zero-downtime deployment.

5. **Celery Beat persistence:** The current beat schedule is in-memory (defined in `celery_app.py`). Adding two new beat entries requires a code deploy to change the schedule. Is this acceptable, or should we move to a DB-backed beat scheduler (e.g., `celery-redbeat`) to allow runtime schedule changes?

6. **Sync queue worker scaling:** How many `sync` queue workers are appropriate? Because the sync is rate-limited by GitHub API quotas rather than worker throughput, one worker is likely sufficient, but this should be validated against the load estimate in Section 6.4.

---

## 15. Handoff Package Summary

### User Stories
Eight user stories (US-01 through US-08) covering: credential configuration, manual trigger, status visibility, schedule configuration, cancellation, resumability, outside collaborator baseline, and automated scheduling. All follow INVEST criteria with Given-When-Then acceptance criteria.

### Design Specifications
- REST API: 5 new endpoints under `/api/v1/admin/sync/`, all guarded by `require_role(["sys_admin"])`, consistent with existing admin router patterns
- No frontend changes required for Phase 1
- All response schemas defined above

### Non-Functional Requirements
- Sync duration: ≤4 hours for ≤10,000 repos
- Rate limit: always maintains ≥500 request headroom
- Reliability: resumable from cursor after any failure
- Security: no credentials in logs or responses

### Work Breakdown Summary

**Phase 1 Tasks (estimated ≤3 days each):**

| Task | Owner | Size |
|------|-------|------|
| GithubAppSettings config class + validators + startup validation | Backend | 1d |
| `GitHubAppTokenManager` (JWT mint, token cache, auto-refresh) | Backend | 2d |
| `GitHubRateLimiter` (semaphore, token bucket, header inspection, backoff) | Backend | 2d |
| Alembic migration: `enterprise_sync_runs` + `enterprise_sync_entity_statuses` | Backend | 1d |
| Alembic migration: `github_org_snapshots`, `github_org_memberships`, `github_repo_snapshots` | Backend | 1d |
| Alembic migration: add `data_source`, `last_synced_at`, `sync_run_id` to `external_collaborators` | Backend | 1d |
| `sync_worker.py`: coordinator task + heartbeat task | Backend | 3d |
| `sync_worker.py`: entity tasks for orgs, org members, outside collaborators, repos | Backend | 3d |
| `sync_worker.py`: entity tasks for GitHub App installations, secret scanning alerts | Backend | 2d |
| Admin router: sync trigger, status, config, cancel endpoints | Backend | 2d |
| Admin router: Pydantic schemas for sync request/response | Backend | 1d |
| Add `"sync"` queue to `celery_app.py` + beat schedule entry | Backend | 1d |
| Unit tests: token manager, rate limiter, conflict resolution logic | Backend | 2d |
| Integration tests: sync trigger API, state machine transitions | Backend | 2d |

**Total Phase 1 estimated effort:** ~24 developer-days (4–5 week sprint for 1 backend engineer with parallel testing)

### Success Metrics

- `external_collaborators` table completeness: 100% of current GitHub outside collaborators present within 4 hours of first sync completion
- False positive rate on outside-collaborator detection rules: reduction of ≥60% compared to pre-sync baseline
- Sync reliability: ≥99% of entity sync tasks complete successfully in the first 30 days
- Rate limit violations: zero 429 responses attributable to sync tasks

### Constraints & Dependencies

- **Dependency:** A GitHub App must be registered and installed in each org before this feature can be deployed. This is a pre-deployment human action that requires GitHub Enterprise Admin access.
- **Constraint:** The GitHub App *private key* must be supplied as an environment variable or secrets mount. It cannot be uploaded through the Octowatch UI (no API endpoint for key configuration is in scope).
- **Dependency:** Phase 2 and Phase 3 tasks depend entirely on Phase 1 infrastructure (token manager, rate limiter, state tracking) being stable.
- **Technical constraint:** `asyncio.run()` pattern used in existing Celery workers is compatible with the proposed async sync implementation. No architectural deviation from existing worker pattern required.
