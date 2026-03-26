# API & Detection Engine Design

**Version**: 1.0  
**Date**: 2026-03-25  
**Status**: Approved for Development  
**Depends on**: [docs/architecture.md](architecture.md)

---

## Table of Contents

1. [REST API Surface](#1-rest-api-surface)
   - [1.1 Global Conventions](#11-global-conventions)
   - [1.2 Auth](#12-auth)
   - [1.3 Events](#13-events)
   - [1.4 Detections](#14-detections)
   - [1.5 Reports](#15-reports)
   - [1.6 Query](#16-query)
   - [1.7 Rules](#17-rules)
   - [1.8 Admin](#18-admin)
   - [1.9 Integrations](#19-integrations)
   - [1.10 Audit Trail](#110-audit-trail)
2. [Detection Engine Design](#2-detection-engine-design)
   - [2a. Detection Rule YAML Schema](#2a-detection-rule-yaml-schema)
   - [2b. Example Rules — All 9 Threat Categories](#2b-example-rules--all-9-threat-categories)
   - [2c. Evaluation Pipeline](#2c-evaluation-pipeline)
   - [2d. Confidence Scoring](#2d-confidence-scoring)
   - [2e. Behavioral Baseline Algorithm](#2e-behavioral-baseline-algorithm)
   - [2f. Impossible Travel Algorithm](#2f-impossible-travel-algorithm)
   - [2g. Suppression Evaluation Order](#2g-suppression-evaluation-order)

---

## 1. REST API Surface

### 1.1 Global Conventions

**Base path:** `/api/v1`

**Authentication:** All endpoints except `/auth/*` require `Authorization: Bearer <jwt>`. JWT is HS256-signed, 15-minute TTL, with a Valkey session key-exists check on every request.

**Scope auto-injection (critical security property):** Every endpoint that reads `events` or `detections` **never** trusts client-supplied `org` or `repo` filter parameters to expand the caller's data access. The RBAC middleware resolves `scoped_orgs[]` and `scoped_repos[]` from `user_role_assignments` at request time and injects a mandatory `WHERE org = ANY(:scoped_orgs) AND (repo IS NULL OR repo = ANY(:scoped_repos))` predicate into the database query. Client-supplied `org`/`repo` filters are applied as an additional restriction **on top of** the RBAC scope — they can only narrow it, never widen it.

**Pagination:** All list responses support `?page=1&page_size=50` (max 500). Response envelope includes `total`, `page`, `page_size`, `has_next`.

**Error format:**
```json
{ "error": "string", "detail": "string", "request_id": "uuid" }
```

**Rate limiting:** Enforced per user per endpoint via `slowapi`. Default: 60 req/min for reads, 10 req/min for writes.

**Audit trail:** FastAPI middleware appends one row to `audit_trail` for every request — including denied (`403`) and error (`5xx`) outcomes. The `parameters` JSONB column stores sanitized request context (no raw SQL values, no secrets).

---

### 1.2 Auth

| Method | Path | Auth Required | Description |
|--------|------|---------------|-------------|
| `GET`  | `/auth/github` | None | Initiate GitHub OAuth flow — redirects to `github.com/login/oauth/authorize` |
| `GET`  | `/auth/github/callback` | None | GitHub OAuth callback; exchanges code for token, issues JWT, sets Valkey session |
| `POST` | `/auth/saml/acs` | None | SAML 2.0 Assertion Consumer Service; validates assertion (strict mode, signature required), maps NameID to `user_role_assignments.saml_subject`, issues JWT |
| `GET`  | `/auth/saml/metadata` | None | Returns SP SAML metadata XML for IdP registration |
| `POST` | `/auth/logout` | Any authenticated | Deletes Valkey session key; JWT is invalidated immediately |
| `GET`  | `/auth/me` | Any authenticated | Returns caller's resolved identity, roles, and effective org/repo scope |

**`GET /auth/me` — Response fields:**
```json
{
  "github_login": "string",
  "github_id": 123456,
  "roles": ["analyst"],
  "scoped_orgs": ["my-org"],
  "scoped_repos": [],
  "scope_type": "org",
  "session_expires_at": "2026-03-25T12:15:00Z"
}
```

---

### 1.3 Events

All queries auto-inject the caller's RBAC scope. The `org` and `repo` params below are optional additional narrowing filters.

| Method | Path | Role Required | Description |
|--------|------|---------------|-------------|
| `GET`  | `/events` | `analyst` | List events with filtering; RBAC scope auto-injected |
| `GET`  | `/events/{id}` | `analyst` | Get a single normalized event by ID |
| `GET`  | `/events/{id}/raw` | `analyst` | Get the unmodified raw JSON payload for an event |

**`GET /events` — Key query parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `org` | `string` | Restrict to this org (must be within caller's RBAC scope) |
| `repo` | `string` | Restrict to this repo full-name |
| `actor` | `string` | Filter by actor login |
| `action` | `string` | Filter by exact action (e.g., `repo.create`) or namespace prefix (e.g., `repo.*`) |
| `namespace` | `string` | Filter by computed namespace column |
| `source_ip` | `string` | Filter by source IP (exact or CIDR) |
| `since` | `ISO8601` | Start of time range (inclusive) |
| `until` | `ISO8601` | End of time range (exclusive) |
| `actor_is_bot` | `boolean` | Filter bot/human events |
| `geo_country_code` | `string` | 2-letter ISO country code |
| `sort` | `string` | `created_at_desc` (default) or `created_at_asc` |

**`GET /events` — Key response fields per item:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | `bigint` | Internal event ID |
| `document_id` | `string` | GitHub `_document_id` (dedup key) |
| `created_at` | `ISO8601` | GitHub event timestamp |
| `action` | `string` | Full action string (e.g., `protected_branch.policy_override`) |
| `namespace` | `string` | Derived namespace (first segment of action) |
| `actor` | `string` | Actor GitHub login |
| `actor_is_bot` | `boolean` | Whether actor is a bot/app |
| `org` | `string` | Organization name |
| `repo` | `string` | Repository full name (`org/repo`) |
| `source_ip` | `string` | Source IP address |
| `geo_country_code` | `string` | MaxMind-resolved country |
| `geo_city` | `string` | MaxMind-resolved city |
| `geo_is_proxy` | `boolean` | MaxMind proxy/VPN/hosting flag |
| `data` | `object` | Full normalized JSONB payload (all event-specific fields) |
| `ingestion_source` | `string` | `s3` or `azure_blob` |

---

### 1.4 Detections

| Method | Path | Role Required | Description |
|--------|------|---------------|-------------|
| `GET`    | `/detections` | `analyst` | List detections with filtering; RBAC scope auto-injected |
| `GET`    | `/detections/{id}` | `analyst` | Get full detection detail including contributing event IDs and context data |
| `PATCH`  | `/detections/{id}/status` | `analyst` | Lifecycle transition: `open → investigating → resolved` or `open → false_positive`; see valid transitions below |
| `PATCH`  | `/detections/{id}/assign` | `analyst` | Assign detection to a user login |
| `GET`    | `/detections/{id}/events` | `analyst` | Return the contributing raw events for this detection (drills through `event_ids[]`) |
| `POST`   | `/detections/{id}/ticket` | `analyst` | Manually trigger ticket creation in configured Jira or GitHub Issues integration |
| `GET`    | `/detections/summary` | `analyst` | Aggregate counts by severity and status; used by dashboard tiles |

**`PATCH /detections/{id}/status` — Request body:**
```json
{
  "status": "investigating | resolved | false_positive",
  "resolution_note": "optional human-readable justification"
}
```

**Valid lifecycle transitions:**

```
open  ──────────────────────► investigating ──► resolved
 │                                               │
 └──────────────────────────────────────────────► false_positive
```
Any backward transition (e.g., `resolved → open`) is rejected with `422 Unprocessable Entity`.

**`GET /detections` — Key query parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `status` | `string` | `open`, `investigating`, `resolved`, `false_positive` (comma-separated for multi) |
| `severity` | `string` | `critical`, `high`, `medium`, `low`, `info` (comma-separated) |
| `rule_id` | `bigint` | Filter by rule |
| `actor` | `string` | Filter by actor |
| `org` | `string` | Must be within caller's RBAC scope |
| `repo` | `string` | Must be within caller's RBAC scope |
| `since` | `ISO8601` | `triggered_at` range start |
| `until` | `ISO8601` | `triggered_at` range end |
| `assigned_to` | `string` | Filter by assignee login |

**`GET /detections/{id}` — Key response fields:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | `bigint` | Detection ID |
| `rule_id` | `bigint` | Rule that triggered this |
| `rule_name` | `string` | Denormalized rule name |
| `rule_version` | `int` | Rule version at time of detection |
| `severity` | `string` | Resolved severity (after `severity_configs` override) |
| `confidence` | `string` | `high`, `medium`, `low` |
| `confidence_score` | `float` | Raw 0.0–1.0 score (see §2d) |
| `status` | `string` | Current lifecycle status |
| `title` | `string` | Human-readable detection title |
| `description` | `string` | Detailed description with contributing context |
| `actor` | `string` | Primary actor |
| `org` | `string` | Organization |
| `repo` | `string` | Repository (if scoped) |
| `source_ip` | `string` | Primary source IP |
| `window_start` | `ISO8601` | Observation window start |
| `window_end` | `ISO8601` | Observation window end |
| `event_ids` | `bigint[]` | Contributing event IDs |
| `context_data` | `object` | Rule-specific structured context (e.g., event count, threshold, top IPs) |
| `triggered_at` | `ISO8601` | When detection was created |
| `assigned_to` | `string` | Assigned analyst login |
| `resolved_at` | `ISO8601` | When resolved (if applicable) |
| `resolution_note` | `string` | Resolution justification |
| `tickets` | `object[]` | Associated tickets (jira/github-issues) |

---

### 1.5 Reports

All report endpoints require `reports:read` permission (`analyst` role). Endpoints requiring `reports:manage` are noted. RBAC scope is auto-injected; the optional `org` parameter narrows within the caller's permitted orgs.

All report endpoints accept common query parameters:

| Parameter | Type | Description |
|-----------|------|-------------|
| `org` | `string` | Narrow to this org (must be in RBAC scope) |
| `granularity` | `string` | `daily`, `weekly`, or `monthly` (default: `daily`) |
| `window` | `string` | `30d`, `60d`, `90d` (default: `30d`) |

All report responses include:

| Field | Type | Description |
|-------|------|-------------|
| `org` | `string` | Org filter applied (or `null` for all in scope) |
| `granularity` | `string` | Granularity used |
| `window` | `string` | Window used |
| `generated_at` | `ISO8601` | Server-side generation timestamp |
| `data` | `object[]` | Timeseries buckets (see per-endpoint schema below) |

---

#### `GET /reports/mau` — Monthly/Weekly Active Users

Role: `analyst`

**Response `data[]` fields:**

| Field | Type | Description |
|-------|------|-------------|
| `bucket` | `ISO8601` | Start of time bucket |
| `unique_actor_count` | `int` | Count of distinct human actors with at least one event |
| `unique_bot_actor_count` | `int` | Count of distinct bot actors |
| `new_actor_count` | `int` | Actors seen for the first time in this bucket |

---

#### `GET /reports/seat-utilization` — License Seat Utilization

Role: `analyst`

**Response `data[]` fields:**

| Field | Type | Description |
|-------|------|-------------|
| `bucket` | `ISO8601` | Start of time bucket |
| `active_seat_count` | `int` | Unique actors with any event in bucket |
| `provisioned_seat_count` | `int` | Observed maximum unique actor count in window (proxy for provisioned seats) |
| `utilization_pct` | `float` | `active / provisioned * 100` |

---

#### `GET /reports/repo-creation-rate` — Repository Creation and Deletion Rate

Role: `analyst`

**Response `data[]` fields:**

| Field | Type | Description |
|-------|------|-------------|
| `bucket` | `ISO8601` | Start of time bucket |
| `repos_created` | `int` | `repo.create` event count |
| `repos_deleted` | `int` | `repo.destroy` event count |
| `repos_transferred` | `int` | `repo.transfer` event count |
| `repos_made_public` | `int` | `repo.access` events where visibility changed to public |

---

#### `GET /reports/actions-volume` — GitHub Actions Workflow Run Volume

Role: `analyst`

**Response `data[]` fields:**

| Field | Type | Description |
|-------|------|-------------|
| `bucket` | `ISO8601` | Start of time bucket |
| `workflow_runs_total` | `int` | Total `workflows.*` events |
| `workflow_runs_succeeded` | `int` | Runs with `conclusion=success` in `data` |
| `workflow_runs_failed` | `int` | Runs with `conclusion=failure` in `data` |
| `success_rate_pct` | `float` | `succeeded / total * 100` |
| `unique_workflows` | `int` | Distinct workflow file paths |

---

#### `GET /reports/copilot-seats` — Copilot Seat Utilization

Role: `analyst`

**Response `data[]` fields:**

| Field | Type | Description |
|-------|------|-------------|
| `bucket` | `ISO8601` | Start of time bucket |
| `seats_assigned` | `int` | Cumulative `copilot.seat_assignment_created` events |
| `seats_revoked` | `int` | `copilot.seat_assignment_cancelled` events |
| `seats_net` | `int` | `assigned - revoked` (rolling net) |
| `policy_change_count` | `int` | `copilot.policy_disabled` or `copilot.policy_enabled` events |

---

#### `GET /reports/codespace-hours` — Codespace Usage Hours

Role: `analyst`

**Response `data[]` fields:**

| Field | Type | Description |
|-------|------|-------------|
| `bucket` | `ISO8601` | Start of time bucket |
| `codespace_create_count` | `int` | `codespaces.create` events |
| `codespace_delete_count` | `int` | `codespaces.destroy` events |
| `unique_actors` | `int` | Distinct actors using codespaces |
| `unique_repos` | `int` | Distinct repos with codespace activity |

> Note: Actual runtime hours are not available in the audit log stream; this report tracks creation/deletion activity as a utilization proxy.

---

#### `GET /reports/pat-counts` — Personal Access Token Counts

Role: `analyst`

**Response `data[]` fields:**

| Field | Type | Description |
|-------|------|-------------|
| `bucket` | `ISO8601` | Start of time bucket |
| `pats_created` | `int` | `personal_access_token.create` events |
| `pats_deleted` | `int` | `personal_access_token.destroy` events |
| `pats_expired` | `int` | `personal_access_token.expired` events |
| `fine_grained_pats` | `int` | Events where `data.token_type = 'fine_grained'` |
| `classic_pats` | `int` | Events where `data.token_type = 'classic'` |
| `high_access_pats` | `int` | PATs with `data.scopes` containing `repo` or `admin` |

---

#### `GET /reports/webhook-counts` — Webhook and GitHub App Counts

Role: `analyst`

**Response `data[]` fields:**

| Field | Type | Description |
|-------|------|-------------|
| `bucket` | `ISO8601` | Start of time bucket |
| `webhooks_created` | `int` | `hook.create` events |
| `webhooks_deleted` | `int` | `hook.destroy` events |
| `app_installs` | `int` | `integration_installation.create` events |
| `app_uninstalls` | `int` | `integration_installation.destroy` events |
| `unique_webhook_targets` | `int` | Distinct `data.config.url` domains |

---

#### `GET /reports/export/{report_type}` — Export Report Data

Role: `report_admin` (requires `exports:create`)

**Query parameters (in addition to common params):**

| Parameter | Type | Description |
|-----------|------|-------------|
| `format` | `string` | `csv` or `json` (default: `json`) |

Returns the same data as the corresponding report endpoint as a downloadable file.

---

### 1.6 Query

Role: `analyst` (`queries:run`). Template management requires `queries:manage` (`report_admin`).

| Method | Path | Role Required | Description |
|--------|------|---------------|-------------|
| `POST`  | `/query/run` | `analyst` | Execute a validated SELECT query; scope injected as CTE |
| `GET`   | `/query/templates` | `analyst` | List saved query templates |
| `POST`  | `/query/templates` | `report_admin` | Save a new query template |
| `GET`   | `/query/templates/{id}` | `analyst` | Get a single template |
| `PUT`   | `/query/templates/{id}` | `report_admin` | Update a template |
| `DELETE`| `/query/templates/{id}` | `report_admin` | Delete a template |

**`POST /query/run` — Request body:**
```json
{
  "sql": "SELECT actor, COUNT(*) AS cnt FROM events WHERE action = 'repo.create' GROUP BY actor ORDER BY cnt DESC LIMIT 20",
  "org": "optional-narrowing-org",
  "format": "json | csv"
}
```

**Security model for `POST /query/run`:**

1. The submitted SQL is parsed by `pglast` into an AST before any database interaction.
2. Validation rules enforced at parse time:
   - Only `SELECT` statements are permitted. `INSERT`, `UPDATE`, `DELETE`, `COPY`, `DROP`, `ALTER`, `CREATE`, `TRUNCATE`, `CALL`, `DO`, `EXECUTE` are all rejected.
   - Allowed `FROM` targets: `events`, `detections`, `behavioral_baselines`, and the continuous aggregate views (`events_hourly`, `events_daily_actor`, `detections_daily`).
   - Cross-schema references (e.g., `information_schema`, `pg_catalog`) are rejected.
   - Subqueries are permitted only in `WHERE`/`HAVING` clauses and must reference the same allowed tables.
   - Functions: only `COUNT`, `SUM`, `AVG`, `MIN`, `MAX`, `DATE_TRUNC`, `TIME_BUCKET`, `TO_CHAR`, `COALESCE`, `NULLIF`, `ARRAY_AGG` are whitelisted. All other function calls (especially `pg_read_file`, `COPY`, format functions that could do SSRF) are rejected.
3. The RBAC scope predicate is wrapped as a CTE that precedes the user query:
   ```sql
   WITH __scope AS (
     SELECT id FROM events
     WHERE org = ANY(:scoped_orgs)
       AND (repo IS NULL OR repo = ANY(:scoped_repos))
   )
   -- user query executes against this CTE, not raw events
   <user_sql with events replaced by __scope JOIN events>
   ```
4. Query executes under `readonly_query_user` role (has only `SELECT` on permitted objects; cannot access `audit_trail`, `ticketing_configs`, `notification_configs`, `rbac_roles`, or `user_role_assignments`).
5. Hard limits: 30-second query timeout, 100,000-row result cap.

**`POST /query/run` — Response:**
```json
{
  "columns": ["actor", "cnt"],
  "rows": [["deploy-bot", 142], ["alice", 38]],
  "row_count": 2,
  "truncated": false,
  "execution_ms": 84,
  "query_id": "uuid"
}
```

---

### 1.7 Rules

| Method | Path | Role Required | Description |
|--------|------|---------------|-------------|
| `GET`    | `/rules` | `analyst` | List all rules (non-deprecated) with summary fields |
| `POST`   | `/rules` | `rule_author` | Create a new rule (starts in `draft` status) |
| `GET`    | `/rules/{id}` | `analyst` | Get full rule definition including `logic_config` |
| `PUT`    | `/rules/{id}` | `rule_author` | Update rule; creates a new `rule_versions` row, increments `version` |
| `PATCH`  | `/rules/{id}/status` | `rule_author` | Transition status: `draft → active`, `active → deprecated`; also sets `enabled` |
| `DELETE` | `/rules/{id}` | `rule_author` | Soft-delete: sets `status = 'deprecated'`, `enabled = false`; never hard-deletes |
| `POST`   | `/rules/{id}/test` | `rule_author` | Test rule against the last N hours of real events; returns matched events without writing a detection |
| `GET`    | `/rules/{id}/versions` | `analyst` | List version history for a rule |
| `GET`    | `/rules/{id}/versions/{version}` | `analyst` | Get a specific historical version of the rule |
| `GET`    | `/rules/{id}/detections` | `analyst` | List detections produced by this rule (most recent first) |
| `POST`   | `/rules/import` | `rule_author` | Import one or more rules from YAML (request body: multipart file or raw YAML text) |
| `GET`    | `/rules/export` | `rule_author` | Export all active rules as a YAML bundle; `?ids=1,2,3` to export specific rules |

**`POST /rules/{id}/test` — Request body:**
```json
{
  "lookback_hours": 24,
  "org": "optional-narrowing-org",
  "dry_run": true
}
```

**`POST /rules/{id}/test` — Response:**
```json
{
  "rule_id": 7,
  "rule_version": 3,
  "lookback_hours": 24,
  "events_evaluated": 14820,
  "matches": [
    {
      "aggregation_key_value": "alice",
      "count": 47,
      "threshold": 20,
      "window_start": "2026-03-25T06:00:00Z",
      "window_end": "2026-03-25T07:00:00Z",
      "event_ids": [98231, 98245, 98311]
    }
  ],
  "match_count": 1,
  "dry_run": true
}
```

**`POST /rules` and `PUT /rules/{id}` — Request body:**

The request body is the rule YAML schema (see §2a) serialized as JSON or submitted as `Content-Type: application/x-yaml`. The `logic_config` JSONB column stores the parsed rule payload. 

---

### 1.8 Admin

All `/admin/*` endpoints require `sys_admin` role.

| Method | Path | Description |
|--------|------|-------------|
| `GET`    | `/admin/sources` | List all configured ingestion sources |
| `POST`   | `/admin/sources` | Add a new S3 or Azure Blob source |
| `GET`    | `/admin/sources/{id}` | Get source config and current cursor state |
| `PUT`    | `/admin/sources/{id}` | Update source config (region, prefix, poll interval); triggers worker reconnect |
| `PATCH`  | `/admin/sources/{id}/status` | Pause / resume / reset-error on a source |
| `DELETE` | `/admin/sources/{id}` | Deactivate a source (cursor retained for audit) |
| `GET`    | `/admin/retention` | Get current retention config for each data tier |
| `PUT`    | `/admin/retention` | Set retention intervals for events, raw payloads, detections, audit trail |
| `GET`    | `/admin/severity-configs` | List all `severity_configs` rows |
| `PUT`    | `/admin/severity-configs/{id}` | Update custom severity override for an action pattern |
| `POST`   | `/admin/severity-configs` | Add a new action pattern → severity mapping |
| `GET`    | `/admin/notifications` | List notification configs (Slack channels, SMTP targets) |
| `POST`   | `/admin/notifications` | Create notification config |
| `PUT`    | `/admin/notifications/{id}` | Update notification config |
| `DELETE` | `/admin/notifications/{id}` | Delete notification config |
| `POST`   | `/admin/notifications/{id}/test` | Send a test message |
| `GET`    | `/admin/ticketing` | List ticketing integrations (Jira, GitHub Issues) |
| `POST`   | `/admin/ticketing` | Create ticketing integration config |
| `PUT`    | `/admin/ticketing/{id}` | Update ticketing config |
| `DELETE` | `/admin/ticketing/{id}` | Delete ticketing integration |
| `POST`   | `/admin/ticketing/{id}/test` | Test connection to ticketing system |
| `GET`    | `/admin/idp` | List IdP enrichment configs (Okta, Entra, Google Workspace) |
| `POST`   | `/admin/idp` | Add an IdP config |
| `PUT`    | `/admin/idp/{id}` | Update IdP config |
| `DELETE` | `/admin/idp/{id}` | Delete IdP config |
| `POST`   | `/admin/idp/{id}/sync` | Trigger immediate actor metadata sync |
| `GET`    | `/admin/rbac/assignments` | List all role assignments with scope |
| `POST`   | `/admin/rbac/assignments` | Create a role assignment (user or team, with scope) |
| `PUT`    | `/admin/rbac/assignments/{id}` | Update role assignment (role, scope, expiry) |
| `DELETE` | `/admin/rbac/assignments/{id}` | Revoke a role assignment |
| `GET`    | `/admin/rbac/roles` | List roles with their permission sets |
| `GET`    | `/admin/system/health` | Ingestion worker health, detection queue depth, DB connection pool stats |
| `GET`    | `/admin/system/baseline-status` | Behavioral baseline engine status; toggle enabled/disabled |
| `PATCH`  | `/admin/system/baseline-status` | Enable or disable the baseline engine |

---

### 1.9 Integrations

Enrichment lookups require `analyst` role. The enrichment service calls GitHub's REST API **only on-demand, never bulk**.

| Method | Path | Role Required | Description |
|--------|------|---------------|-------------|
| `GET`  | `/integrations/enrich/actor/{login}` | `analyst` | Fetch current actor metadata from configured IdP (Okta/Entra/Google); returns cached `idp_actor_enrichments` row first, falls back to live API call |
| `GET`  | `/integrations/enrich/actor/{login}/github` | `analyst` | On-demand GitHub REST API lookup of actor profile and current org membership (not cached) |
| `GET`  | `/integrations/suppressions` | `analyst` | List active suppression rules |
| `POST` | `/integrations/suppressions` | `rule_author` | Create a new suppression rule |
| `PUT`  | `/integrations/suppressions/{id}` | `rule_author` | Update a suppression rule |
| `PATCH`| `/integrations/suppressions/{id}/deactivate` | `rule_author` | Deactivate a suppression rule (does not delete) |
| `DELETE`| `/integrations/suppressions/{id}` | `rule_author` | Delete a suppression rule permanently |

---

### 1.10 Audit Trail

| Method | Path | Role Required | Description |
|--------|------|---------------|-------------|
| `GET`  | `/audit-trail` | `sys_admin` | List audit trail entries; supports `user_login`, `action_type`, `resource_type`, `resource_id`, `outcome`, `since`, `until` filters; auto-scoped to `audit_trail` hypertable |
| `GET`  | `/audit-trail/{id}` | `sys_admin` | Get a single audit trail entry |

**`GET /audit-trail` — Key response fields per item:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | `bigint` | Entry ID |
| `timestamp` | `ISO8601` | When the action occurred |
| `user_login` | `string` | Actor's GitHub login |
| `ip_address` | `string` | Client IP |
| `action_type` | `string` | e.g., `detection.update_status`, `rule.update`, `query.run` |
| `resource_type` | `string` | e.g., `detection`, `rule`, `suppression` |
| `resource_id` | `string` | String PK of affected resource |
| `parameters` | `object` | Sanitized request context |
| `outcome` | `string` | `success`, `denied`, or `error` |
| `error_detail` | `string` | Error context when `outcome = 'error'` |

---

---

## 2. Detection Engine Design

### 2a. Detection Rule YAML Schema

Rules are authored in YAML and stored as JSONB in `rule_definitions.logic_config`. The YAML is the canonical human-facing format for import/export; the WYSIWYG editor serializes to/from this schema.

```yaml
# ─────────────────────────────────────────────────────────────────────────────
# DETECTION RULE SCHEMA — Full annotated example
# ─────────────────────────────────────────────────────────────────────────────

# Unique slug identifier (URL-safe, lowercase, hyphens). Stable across versions.
# Maps to: rule_definitions.slug
id: "mass-clone-exfiltration"

# Human-readable rule name displayed in the UI.
# Maps to: rule_definitions.name
name: "Mass Repository Clone — Potential Exfiltration"

# Detailed explanation of what this rule detects and why it matters.
# Supports Markdown for rendering in the rule editor.
description: |
  Detects when a single actor clones an unusually large number of distinct
  repositories within a short time window. A burst of git.clone events from
  a single actor may indicate data exfiltration by an insider or a compromised
  account downloading source code at scale.

# Whether the rule is active. Only rules with enabled: true are evaluated.
# Corresponds to: rule_definitions.enabled
enabled: true

# Default severity classification. Overridden per-action by severity_configs table.
# Values: Critical | High | Medium | Low | Info
severity: High

# Base confidence score (0.0–1.0). Used as the starting point for the
# confidence scoring formula before runtime adjustments (see §2d).
# A rule author's assessment of how reliably this rule indicates a true positive.
confidence: 0.75

# Threat category. Maps to rule_definitions.category.
# Values: exfiltration | account_compromise | privilege_escalation |
#         secret_leakage | supply_chain | branch_protection_bypass |
#         pat_abuse | impossible_travel | off_hours_anomaly | other
category: exfiltration

# External references for analyst context (CVEs, blog posts, MITRE ATT&CK, etc.)
references:
  - "https://attack.mitre.org/techniques/T1537/"
  - "https://docs.github.com/en/enterprise-cloud/admin/monitoring-activity-in-your-enterprise"

# ─── EVENT MATCHING ───────────────────────────────────────────────────────────

# action_filters: One or more glob patterns matched against the `action` field
# of each incoming event. Supports '*' (any segment) and '**' (any path).
# An event must match AT LEAST ONE filter to be a candidate for this rule.
# Examples:
#   - "git.clone"          (exact match)
#   - "git.*"              (all git namespace events)
#   - "repo.*"             (all repo namespace events)
#   - "*.policy_override"  (any namespace policy override)
action_filters:
  - "git.clone"

# field_conditions: Additional predicates evaluated against the event's fields.
# All conditions in the list must be satisfied (logical AND).
# Supported operators:
#   eq | ne | gt | gte | lt | lte    — comparison
#   in | not_in                       — membership in a list of values
#   contains | not_contains           — substring match (TEXT fields)
#   exists | not_exists               — field presence check (JSONB fields)
#   matches_glob                      — glob pattern (same syntax as action_filters)
#
# field: dot-notation path. Top-level fields (actor, org, repo, source_ip,
#        geo_country_code, actor_is_bot) are column references.
#        Fields under "data." are JSONB path lookups (e.g., data.transport_protocol).
field_conditions:
  - field: "actor_is_bot"
    operator: "eq"
    value: false          # Only evaluate for human actors; bots handled separately

# ─── THRESHOLD & AGGREGATION ─────────────────────────────────────────────────

# logic_type: How the rule logic is evaluated.
# Values:
#   threshold  — fire when count(events matching action_filters + field_conditions)
#                exceeds `threshold` during `time_window_minutes`
#   pattern    — fire on a single event matching action_filters + field_conditions
#   sequence   — fire when N ordered event types occur for the same aggregation_key
#                within time_window_minutes (see sequence_steps field below)
#   statistical — fire when a metric deviates > N stddev from behavioral_baselines
#                (requires behavioral baseline engine to be enabled)
logic_type: threshold

# threshold: Minimum event count within time_window_minutes that triggers a detection.
# Only relevant when logic_type = threshold.
threshold: 20

# time_window_minutes: Rolling time window for threshold and sequence evaluation.
# The engine queries events within [NOW() - interval, NOW()] for the aggregation_key.
# Also used by impossible_travel and off_hours_anomaly rules for lookback.
time_window_minutes: 60

# aggregation_key: Field name by which events are grouped before counting.
# The threshold is applied per unique value of this field.
# Common values: actor | source_ip | data.hashed_token | org | repo
# For impossible_travel: must be "actor" (evaluated as a pair of events, not count).
aggregation_key: "actor"

# sequence_steps: Only for logic_type = sequence.
# Defines an ordered list of event types that must occur for the same aggregation_key.
# Omit this field for non-sequence rules.
# sequence_steps:
#   - action: "org.recovery_code_failed"
#   - action: "org.recovery_code_used"

# ─── METADATA ─────────────────────────────────────────────────────────────────

# tags: Free-form labels used for filtering in the UI and export bundles.
# Suggested tags: mitre-attack, insider-threat, exfiltration, account-compromise,
#                 supply-chain, compliance, needs-baseline, high-volume
tags:
  - "mitre-attack"
  - "insider-threat"
  - "exfiltration"

# remediation_guidance: Markdown guidance rendered in the detection detail view
# to help analysts investigate and respond to this finding.
remediation_guidance: |
  1. Review the contributing events to identify the full list of cloned repositories.
  2. Check whether the actor has a legitimate reason (e.g., bulk migration task).
  3. If exfiltration is suspected: suspend the actor's GitHub account, rotate any
     PATs and SSH keys associated with the account, and engage your IR team.
  4. Review whether cloned repositories contain secrets or sensitive source code.
  5. Use the GitHub REST API enrichment endpoint to check current org membership
     and verify whether the actor is still an active employee.
```

---

### 2b. Example Rules — All 9 Threat Categories

---

#### Rule 1: Insider Exfiltration — Mass `git.clone` Threshold

```yaml
id: "insider-mass-clone"
name: "Insider Exfiltration — Mass Repository Clone"
description: |
  An actor cloned more than 20 distinct repositories within 60 minutes.
  High clone velocity from a single human actor is a strong exfiltration signal.

enabled: true
severity: High
confidence: 0.75
category: exfiltration

references:
  - "https://attack.mitre.org/techniques/T1537/"

action_filters:
  - "git.clone"

field_conditions:
  - field: "actor_is_bot"
    operator: "eq"
    value: false

logic_type: threshold
threshold: 20
time_window_minutes: 60
aggregation_key: "actor"

tags: ["exfiltration", "insider-threat", "mitre-attack"]

remediation_guidance: |
  1. Identify all repositories cloned in the detection window via contributing events.
  2. Determine whether a legitimate bulk migration or CI job could explain the volume.
  3. If suspicious: suspend actor, rotate credentials, review cloned repo sensitivity.
  4. Escalate to IR if actor recently resigned or was terminated.
```

---

#### Rule 2: Account Compromise — Recovery Code Use After Failed Attempts

```yaml
id: "account-compromise-recovery-code"
name: "Account Compromise — Recovery Code Used After Failures"
description: |
  Detects a sequence where org/enterprise recovery code failures are followed
  by a successful recovery code use from the same actor within 30 minutes.
  This pattern indicates a credential-stuffing or social-engineering attack
  that bypassed MFA using a recovery code.

enabled: true
severity: Critical
confidence: 0.85
category: account_compromise

references:
  - "https://attack.mitre.org/techniques/T1078/"
  - "https://docs.github.com/en/authentication/securing-your-account-with-two-factor-authentication-2fa/recovering-your-account-if-you-lose-your-2fa-credentials"

action_filters:
  - "org.recovery_code_failed"
  - "org.recovery_code_used"
  - "business.recovery_code_failed"
  - "business.recovery_code_used"

field_conditions:
  - field: "actor_is_bot"
    operator: "eq"
    value: false

logic_type: sequence
sequence_steps:
  - action: "org.recovery_code_failed"
    min_count: 1          # at least one failure must precede success
  - action: "org.recovery_code_used"
    min_count: 1

time_window_minutes: 30
aggregation_key: "actor"

tags: ["account-compromise", "mfa-bypass", "mitre-attack"]

remediation_guidance: |
  1. Immediately review the actor's active sessions and revoke all OAuth tokens.
  2. Reset the actor's recovery codes and require MFA re-enrollment.
  3. Check the source IP against known VPN/proxy ranges and impossible travel.
  4. If actor is not the legitimate user, suspend account and engage IR team.
  5. Review what resources the actor accessed after the successful recovery code use.
```

---

#### Rule 3: Privilege Escalation — Team Add + Enterprise Role Assign (Same Actor, Same Window)

```yaml
id: "privilege-escalation-role-assign"
name: "Privilege Escalation — Team Addition Followed by Role Assignment"
description: |
  Detects an actor being added to a team AND receiving an elevated enterprise
  role within 60 minutes. When both actions are performed by (or for) the same
  actor in quick succession, it may indicate unauthorized privilege escalation.
  NOTE: The aggregation_key here is the TARGET actor (data.user), not the
  initiating actor. Both events must target the same user.

enabled: true
severity: High
confidence: 0.70
category: privilege_escalation

references:
  - "https://attack.mitre.org/techniques/T1078.004/"

action_filters:
  - "team.add_member"
  - "enterprise_role.assign"

field_conditions: []   # No additional field conditions; sequence handles matching

logic_type: sequence
sequence_steps:
  - action: "team.add_member"
  - action: "enterprise_role.assign"

time_window_minutes: 60
# Aggregate on the target user (the one receiving privileges), not the actor performing the action.
# The field data.user is the GitHub login of the user whose role/team was changed.
aggregation_key: "data.user"

tags: ["privilege-escalation", "insider-threat", "mitre-attack"]

remediation_guidance: |
  1. Verify whether both actions were authorized through your access request process.
  2. Review which team was joined and what enterprise role was assigned.
  3. If unauthorized: remove the team membership and revoke the enterprise role.
  4. Audit any actions performed by the target actor after the privilege change.
  5. Review who performed the two actions — if the same actor performed both on
     themselves, treat this as Critical severity and escalate immediately.
```

---

#### Rule 4: Secret Leakage — Push Protection Bypass with `publicly_leaked=true`

```yaml
id: "secret-leakage-push-protection-bypass-public"
name: "Secret Leakage — Push Protection Bypass (Publicly Leaked Secret)"
description: |
  A developer bypassed GitHub's secret scanning push protection and the bypassed
  secret is flagged as already publicly leaked (publicly_leaked=true). The secret
  is confirmed exposed and requires immediate rotation.

enabled: true
severity: Critical
confidence: 0.95
category: secret_leakage

references:
  - "https://docs.github.com/en/code-security/secret-scanning/protecting-pushes-with-secret-scanning"
  - "https://attack.mitre.org/techniques/T1552/"

action_filters:
  - "secret_scanning_push_protection.bypass"

field_conditions:
  - field: "data.publicly_leaked"
    operator: "eq"
    value: true

logic_type: pattern   # Single-event rule — every bypass with publicly_leaked=true fires

tags: ["secret-leakage", "supply-chain", "compliance", "mitre-attack"]

remediation_guidance: |
  1. Identify the secret type from data.secret_type and data.token_metadata.
  2. Rotate the leaked secret IMMEDIATELY — it is already publicly known.
  3. Audit all usage of the leaked credential in audit logs and access logs.
  4. Revoke the push protection bypass and block the commit if not yet merged.
  5. Contact the affected service provider if the secret grants external access.
  6. Review whether data.multi_repo is true — if so, the secret exists across
     multiple repositories and all instances must be rotated.
```

---

#### Rule 5: Supply-Chain Attack — Webhook or App Install Outside Business Hours

```yaml
id: "supply-chain-hook-install-off-hours"
name: "Supply-Chain Risk — Webhook or App Install Outside Business Hours"
description: |
  A new webhook or GitHub App was created outside of normal business hours
  (defined as 08:00–18:00 actor-local time, Mon–Fri based on the actor's
  behavioral baseline timezone). Attackers install malicious hooks and apps
  during off-hours to avoid detection. Confidence is moderate due to legitimate
  after-hours automation.

enabled: true
severity: High
confidence: 0.60
category: supply_chain

references:
  - "https://attack.mitre.org/techniques/T1195.003/"
  - "https://attack.mitre.org/techniques/T1546/"

action_filters:
  - "hook.create"
  - "integration_installation.create"

field_conditions:
  - field: "actor_is_bot"
    operator: "eq"
    value: false
  - field: "__outside_baseline_hours"    # Synthetic field injected by detection engine
    operator: "eq"                       # when logic_type=statistical or off_hours_anomaly
    value: true

logic_type: pattern

tags: ["supply-chain", "off-hours", "mitre-attack"]

remediation_guidance: |
  1. Verify whether the hook.create or integration_installation.create was authorized.
  2. Review the webhook target URL (data.config.url) for suspicious domains.
  3. For app installs, verify the app is from your organization's approved list.
  4. If unauthorized: immediately delete the webhook/app and revoke associated tokens.
  5. Audit all events emitted to the webhook or app since installation.
  6. Check all repos the installation has access to via the integration_installation.repositories event.
```

---

#### Rule 6: Branch Protection Bypass — `protected_branch.policy_override`

```yaml
id: "branch-protection-bypass"
name: "Branch Protection Bypass — Policy Override"
description: |
  A user directly overrode a branch protection policy. This is a single-event
  Critical severity indicator — bypassing branch protection can allow force-pushes
  to protected branches, removal of required status checks, or disabling
  required reviewers, all of which can introduce malicious code.

enabled: true
severity: Critical
confidence: 0.90
category: branch_protection_bypass

references:
  - "https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/defining-the-mergeability-of-pull-requests/about-protected-branches"
  - "https://attack.mitre.org/techniques/T1195.001/"

action_filters:
  - "protected_branch.policy_override"

field_conditions: []   # Every occurrence is suspicious regardless of context

logic_type: pattern

tags: ["branch-protection", "supply-chain", "compliance", "mitre-attack"]

remediation_guidance: |
  1. Identify which branch protection policy was overridden (data.override_details).
  2. Determine whether the override was authorized via your change management process.
  3. Review all commits pushed to the affected branch after the override.
  4. Restore the original branch protection policy if override is unauthorized.
  5. If the branch is production or a release branch, initiate code review of
     all commits in the detection window.
  6. Consider whether this correlates with supply-chain or insider-threat indicators.
```

---

#### Rule 7: PAT Abuse — High API Request Volume from Single Token

```yaml
id: "pat-abuse-high-api-volume"
name: "PAT Abuse — Unusually High API Request Volume from Single Token"
description: |
  A single Personal Access Token (identified by hashed_token from api.request
  events) generated more than 500 API requests within 10 minutes. High-volume
  API calls from a single PAT may indicate automated data harvesting, credential
  abuse, or a compromised token being used by an external attacker.
  NOTE: api.request events are opt-in streaming-only and are very high volume;
  this rule requires api.request to be enabled in your GHEC streaming config.

enabled: true
severity: High
confidence: 0.70
category: pat_abuse

references:
  - "https://attack.mitre.org/techniques/T1078/"
  - "https://docs.github.com/en/rest/overview/rate-limiting-for-the-rest-api"

action_filters:
  - "api.request"

field_conditions:
  - field: "data.token_type"
    operator: "in"
    value: ["personal_access_token", "fine_grained_personal_access_token"]
  - field: "data.hashed_token"
    operator: "exists"
    value: true

logic_type: threshold
threshold: 500
time_window_minutes: 10
aggregation_key: "data.hashed_token"   # Count per unique token, not per actor

tags: ["pat-abuse", "account-compromise", "exfiltration", "high-volume"]

remediation_guidance: |
  1. Identify the actor associated with data.hashed_token via contributing events.
  2. Review data.path_info to understand which API endpoints were called at volume.
  3. If the endpoints accessed sensitive data (repos, code contents, org members),
     assess whether data was exfiltrated.
  4. Revoke the PAT immediately if unauthorized or the actor cannot explain the volume.
  5. Check whether the high-volume activity corresponds with a legitimate CI/CD job
     that lacks proper rate-limit controls.
```

---

#### Rule 8: Impossible Travel — Same Actor from IPs > 500 km Apart Within 60 Minutes

```yaml
id: "impossible-travel"
name: "Impossible Travel — Actor Activity from Geographically Distant IPs"
description: |
  The same actor performed authenticated actions from two IP addresses that are
  more than 500 km apart within a 60-minute window. The implied travel speed
  exceeds 900 km/h (configurable), which is physically impossible for a human
  without air travel. Indicates either a compromised credential, VPN use, or
  shared session/token across locations.

enabled: true
severity: High
confidence: 0.65   # Reduced by VPN/proxy prevalence; see field_conditions
category: impossible_travel

references:
  - "https://attack.mitre.org/techniques/T1078/"

action_filters:
  - "git.*"
  - "repo.*"
  - "org.*"
  - "api.request"

field_conditions:
  - field: "actor_is_bot"
    operator: "eq"
    value: false
  - field: "geo_is_proxy"    # MaxMind VPN/proxy/hosting flag
    operator: "eq"
    value: false             # Skip events from known proxy/VPN IPs

logic_type: statistical      # Evaluated by impossible_travel sub-engine (see §2f)
# Special config keys for impossible_travel logic_type:
# (These extend the standard schema; non-standard keys are namespaced under x_config)
x_config:
  engine: "impossible_travel"
  distance_threshold_km: 500
  speed_threshold_kmh: 900
  suppress_proxy_ips: true        # Additional suppression for geo_is_proxy=true
  suppress_bot_actors: true
  vpn_cidr_blocklist_enabled: true  # If true, checks against admin-configured CIDR blocklist

time_window_minutes: 60
aggregation_key: "actor"

tags: ["impossible-travel", "account-compromise", "geo-anomaly", "mitre-attack"]

remediation_guidance: |
  1. Review the two source IPs and their geo-resolved locations.
  2. Check whether either IP is a known VPN, proxy, or corporate gateway.
  3. Ask the actor whether they were using a VPN or corporate proxy.
  4. If neither IP is a proxy and the actor cannot explain both locations:
     a. Suspend the actor's GitHub access.
     b. Revoke all active OAuth tokens and PATs.
     c. Force re-authentication and require MFA verification.
  5. Review what actions were performed from the anomalous IP.
```

---

#### Rule 9: Off-Hours Anomaly — `git.push` Outside Actor Baseline Hours

```yaml
id: "off-hours-push-anomaly"
name: "Off-Hours Anomaly — Git Push Outside Actor Baseline Activity Window"
description: |
  An actor performed a git.push during hours that are statistically anomalous
  relative to their historical activity pattern (z-score > 3 on hourly activity
  histogram). Requires the Behavioral Baseline Engine to be enabled.
  NOT fired within the first 30 days of an actor's history (cold-start period).

enabled: true
severity: Low    # Low by default; raise to Medium/High via severity_configs if desired
confidence: 0.45  # Lower confidence — legitimate schedule changes produce false positives
category: off_hours_anomaly

references:
  - "https://attack.mitre.org/techniques/T1078/"

action_filters:
  - "git.push"

field_conditions:
  - field: "actor_is_bot"
    operator: "eq"
    value: false

logic_type: statistical
x_config:
  engine: "off_hours_anomaly"
  metric: "hourly_push_count"
  z_score_threshold: 3.0
  min_sample_days: 30       # Do not fire if actor has fewer than 30 days of history
  baseline_window_days: 30  # Rolling window used for baseline computation

time_window_minutes: 60
aggregation_key: "actor"

tags: ["off-hours", "anomaly", "needs-baseline", "insider-threat"]

remediation_guidance: |
  1. Review the content of the off-hours push (branch, commit messages, changed files).
  2. Check whether the actor's timezone or work schedule has recently changed.
  3. Correlate with other anomaly indicators for the same actor in the same window.
  4. If this is a one-off event with a clear explanation (on-call, late work), mark
     as false_positive to improve future baseline accuracy.
  5. If combined with unusual repo access or large change sets, escalate to High.
```

---

### 2c. Evaluation Pipeline

#### Trigger

After the Ingestion Worker commits a batch of events, it enqueues a `detection.evaluate_batch` Celery task with the list of new event IDs (max 500 per task). If a batch produces more than 500 IDs, multiple tasks are enqueued sequentially with non-overlapping ID ranges.

```
Ingestion Worker
  └─ COMMIT (events + cursor + dedup)
       └─ celery.send_task("detection.evaluate_batch", args=[event_ids])
```

#### Step 1: Event Fetch

The detection worker fetches the full event rows for the provided IDs in a single query:

```sql
SELECT id, created_at, action, namespace, actor, actor_id, actor_is_bot,
       org, org_id, repo, source_ip, geo_latitude, geo_longitude,
       geo_is_proxy, data
FROM events
WHERE id = ANY(:event_ids)
ORDER BY created_at ASC;
```

#### Step 2: Rule Load

All enabled, active rules are loaded from `rule_definitions` at task start:

```sql
SELECT id, slug, name, logic_type, logic_config, default_severity,
       default_confidence, category, version
FROM rule_definitions
WHERE enabled = TRUE AND status = 'active'
ORDER BY id ASC;
```

Rules are cached in Valkey with a 60-second TTL to avoid a DB query on every batch task. The cache is invalidated immediately when any rule is saved via `PUT /rules/{id}`.

#### Step 3: Action Filter Pass

For each rule, the event list is pre-filtered by `action_filters` using Python `fnmatch.fnmatch()`. Only events whose `action` matches at least one glob pattern proceed to field condition evaluation. This is a fast O(N × M) pass (N events, M rules) that eliminates most combinations before heavier processing.

```python
candidates = [
    ev for ev in events
    if any(fnmatch.fnmatch(ev.action, pat) for pat in rule.action_filters)
]
```

#### Step 4: Field Condition Evaluation

Each candidate event is evaluated against all `field_conditions` (logical AND). Fields prefixed with `data.` are resolved via JSONB path lookup against the event's `data` column. Top-level fields are direct column accesses. Resolution against the `__outside_baseline_hours` synthetic field triggers a lookup against `behavioral_baselines`.

#### Step 5: Rule Logic Dispatch

After field filtering, logic-type-specific evaluation runs:

**`pattern` rules:**
Every event that passes field conditions fires a detection immediately. No aggregation.

**`threshold` rules:**
- The detection engine queries the `events` table for the rolling window:
  ```sql
  SELECT aggregation_key_value, COUNT(*) AS cnt
  FROM events
  WHERE action = ANY(:matching_actions)
    AND created_at >= NOW() - (:time_window_minutes || ' minutes')::interval
    AND org = ANY(:scoped_orgs)   -- mandatory RBAC scope
    -- field_conditions translated to SQL predicates
  GROUP BY aggregation_key_value
  HAVING COUNT(*) >= :threshold;
  ```
- One detection is created per aggregation key value that meets the threshold.
- **Per-rule deduplication:** Before writing, the engine checks whether an `open` or `investigating` detection for the same `rule_id` and `aggregation_key_value` already exists within the last `time_window_minutes`. If found, the existing detection's `event_ids[]` and `window_end` are updated (append) rather than creating a duplicate.

**`sequence` rules:**
- For each unique `aggregation_key_value` in the candidate events, the engine queries the ordered sequence of matching event types:
  ```sql
  SELECT action, created_at, id
  FROM events
  WHERE aggregation_key = :key_value
    AND action = ANY(:all_step_actions)
    AND created_at >= NOW() - (:time_window_minutes || ' minutes')::interval
  ORDER BY created_at ASC;
  ```
- The sequence is validated by checking that each `sequence_steps[].action` appears at least `min_count` times in chronological order. The first event matching step N must precede all events matching step N+1.

**`statistical` (off_hours / behavioral deviation) rules:**
- Requires `behavioral_baselines` to be populated for the actor.
- Cold-start guard: if `sample_count < min_sample_days × min_daily_events` (configurable), the rule is **skipped** for that actor.
- The z-score is computed as: `z = (observed_value - baseline.mean) / MAX(baseline.stddev, 1.0)`.
- If z > `z_score_threshold`, a detection is written.

**`statistical` (impossible_travel) rules:**
- Dispatched to the dedicated impossible travel sub-engine (see §2f).

#### Step 6: Suppression Check

Before writing any detection, the suppression check runs (see §2g for exact order). If suppressed, the detection is discarded silently (no DB write, no notification).

#### Step 7: Detection Write

Passing detections are bulk-inserted into `detections`:
- `severity` is resolved by querying `severity_configs` for the most specific matching `action_pattern` (exact match > namespace wildcard > global `*`).
- `confidence` is computed per §2d.
- `event_ids[]` is populated with all contributing event IDs.
- `context_data` JSONB contains rule-type-specific structured context (threshold count, window boundaries, geo data for travel, z-score for statistical, etc.).

#### Step 8: Post-Detection Tasks

Detection writes trigger the following async Celery tasks (enqueued, not awaited):
- `notification.send_detection` — if a notification config is active and severity meets threshold.
- `ticketing.auto_create_ticket` — if `ticketing_configs.auto_create = true` and the detection's severity is in `auto_create_severity`.
- `baseline.update_incremental` — if baseline engine is enabled and the detection is a `statistical` type (updates the actor's event count for the current window).

---

### 2d. Confidence Scoring

#### Formula

The final confidence score is a float in `[0.0, 1.0]`, derived from the rule's base `confidence` value adjusted by runtime factors:

```
final_score = CLAMP(base_confidence × positive_multiplier / negative_multiplier, 0.0, 1.0)
```

Where `CLAMP(x, 0.0, 1.0)` ensures the result stays within bounds.

#### Positive Factors (raise confidence, multiplicative)

| Factor | Condition | Multiplier |
|--------|-----------|------------|
| **Corroborating events above threshold** | threshold rule: observed_count ≥ 2 × threshold | × 1.20 |
| **Known-bad source IP** | `geo_is_proxy = true` on a rule that considers proxy IPs suspicious | × 1.15 |
| **Multiple source IPs** | threshold/sequence: contributing events span ≥ 2 distinct source IPs | × 1.10 |
| **Actor has baseline** | statistical rule: actor has ≥ 30 days of history (higher statistical validity) | × 1.10 |
| **High z-score** | statistical rule: z-score ≥ 2 × configured threshold | × 1.15 |
| **Multi-step sequence complete** | sequence rule: all steps matched in strict order | × 1.10 |

#### Negative Factors (reduce confidence, multiplicative)

| Factor | Condition | Multiplier |
|--------|-----------|------------|
| **Known proxy/VPN source** | `geo_is_proxy = true` on rules where proxy use is ambiguous (e.g., off-hours) | × 0.80 |
| **Actor is a service account** | `actor` login matches configured service-account prefix patterns (e.g., `*-bot`, `*-ci`) but `actor_is_bot = false` | × 0.85 |
| **Marginal threshold** | threshold rule: observed_count is within 10% above threshold | × 0.90 |
| **Cold-start actor** | statistical rule: actor has between `min_sample_days / 2` and `min_sample_days` days of history | × 0.75 |
| **Off-peak hours rule in business context** | off_hours rule triggered on a weekend for an org with weekend activity in baseline | × 0.80 |

#### Confidence Tier Mapping

The computed `final_score` is mapped to a human-readable tier stored in `detections.confidence`:

| Score Range | Tier |
|-------------|------|
| 0.75 – 1.00 | `high` |
| 0.45 – 0.74 | `medium` |
| 0.00 – 0.44 | `low` |

Detections with `confidence = low` automatically receive a `description` annotation: *"Low confidence — review contributing events carefully before escalating. Potential causes of variability: [factors that applied negative multipliers]."*

---

### 2e. Behavioral Baseline Algorithm

#### Celery Beat Schedule

The `baseline.compute_rolling` task runs hourly via Celery Beat. It is idempotent — re-running for the same window produces the same result.

#### Rolling Window

All baselines use a **rolling 30-day window** ending at the current hour. On each run, the most recent hourly window is computed and upserted into `behavioral_baselines`. The engine does not recompute historical windows unless the `backfill_baselines` admin task is explicitly triggered.

```
window_end   = TRUNC(NOW(), 'hour')
window_start = window_end - INTERVAL '30 days'
```

#### Per-Actor Metrics Tracked

Each metric produces one `behavioral_baselines` row with `baseline_type = 'actor_daily'` (for daily aggregates) or `baseline_type = 'actor_hourly'` (for intra-day patterns):

| `metric_name` | Description | Aggregation |
|---------------|-------------|-------------|
| `push_count` | `git.push` events | Daily count |
| `clone_count` | `git.clone` events | Daily count |
| `pr_count` | `pull_request.*` events | Daily count |
| `unique_repo_count` | Distinct repos interacted with | Daily HLL estimate |
| `unique_ip_count` | Distinct source IPs | Daily HLL estimate |
| `api_request_count` | `api.request` events | Daily count |
| `active_hour_of_week` | Event count per hour-of-week bucket (0–167) | Histogram (168 buckets) |
| `geo_subnet_24` | Top-N source `/24` CIDR subnets | Top-3 by frequency |

#### Normal Hours Computation

The `active_hour_of_week` histogram is an array of 168 counters (7 days × 24 hours), indexed as `day_of_week × 24 + hour_of_day` (UTC-relative, adjusted to actor's most common offset if determinable from GeoIP city timezone).

**Definition of "active hours":** The top 60th percentile buckets of the histogram are classified as active hours. Specifically:

```python
histogram = [count_0, count_1, ..., count_167]  # 30-day rolling counts
threshold = numpy.percentile([x for x in histogram if x > 0], 40)
active_hours = {i for i, cnt in enumerate(histogram) if cnt >= threshold}
```

Any event arriving outside `active_hours` for that actor triggers `__outside_baseline_hours = true` for pattern and statistical rules that use it.

#### Normal Geography Computation

The top 3 source `/24` CIDR subnets by event count over the 30-day window define the actor's "normal geo":

```sql
SELECT
    host(set_masklen(source_ip::inet, 24)) AS subnet_24,
    COUNT(*) AS event_count
FROM events
WHERE actor = :actor
  AND created_at >= :window_start
  AND source_ip IS NOT NULL
GROUP BY 1
ORDER BY 2 DESC
LIMIT 3;
```

These three subnets are stored in `behavioral_baselines` as `metric_name = 'geo_subnet_24'`, `scope_key = actor`, with the subnets encoded in `context_data JSONB`.

#### Anomaly Score Derivation

For continuous metrics (push_count, clone_count, etc.), the anomaly score is the z-score:

```
z = (today_value - mean) / MAX(stddev, 1.0)
```

`MAX(stddev, 1.0)` prevents division-by-zero for actors with perfectly uniform activity. A z-score above the rule's `z_score_threshold` (default 3.0) triggers a detection.

#### Cold-Start Handling

| State | Condition | Behavior |
|-------|-----------|----------|
| **No history** | Actor has zero events in `events` table | All `statistical` / `off_hours_anomaly` rules are **skipped** for this actor |
| **Insufficient history** | Actor has 1–14 days of events | `statistical` rules skipped; `pattern` and `threshold` rules still apply |
| **Growing history** | Actor has 15–29 days of events | `statistical` rules run with reduced confidence (× 0.75 multiplier) and min z-score threshold raised by 50% |
| **Stable history** | Actor has ≥ 30 days of events | Full statistical evaluation with normal confidence scoring |
| **Org fallback** | Actor missing; org `behavioral_baselines` exist | Org-level mean/stddev used instead of actor-level, with an additional × 0.70 confidence penalty |

---

### 2f. Impossible Travel Algorithm

#### Overview

The impossible travel sub-engine runs as a special case of `logic_type: statistical` with `x_config.engine: "impossible_travel"`. It is invoked once per batch per unique `actor` with ≥ 2 distinct `source_ip` values in the candidate events or the preceding time window.

#### Data Gathering

```python
# Fetch all events for this actor in the last time_window_minutes with source_ip present
recent_events = query("""
    SELECT id, created_at, source_ip, geo_latitude, geo_longitude, geo_is_proxy
    FROM events
    WHERE actor = :actor
      AND created_at >= NOW() - (:window_minutes || ' minutes')::interval
      AND source_ip IS NOT NULL
      AND geo_latitude IS NOT NULL
      AND geo_longitude IS NOT NULL
    ORDER BY created_at ASC
""", actor=actor, window_minutes=time_window_minutes)
```

#### Suppression Pre-Checks (before distance calculation)

The following checks are evaluated **before** computing any distances. If any check fires, the actor is skipped entirely for this evaluation pass:

1. `actor_is_bot = true` → **skip**.
2. All events for this actor have identical `source_ip` → **skip** (no travel).
3. All distinct `source_ip` values are in the admin-configured **VPN/proxy CIDR blocklist** → **skip**.
4. All events have `geo_is_proxy = true` → **skip** (MaxMind flags all IPs as proxy).
5. Actor has ≥ 1 field_condition that resolves to `false` → **skip**.

#### Distance and Speed Calculation

For each consecutive pair of events `(e_i, e_{i+1})` where the source IPs differ:

```python
from math import radians, sin, cos, sqrt, atan2

def haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0  # Earth radius in km
    φ1, φ2 = radians(lat1), radians(lat2)
    Δφ = radians(lat2 - lat1)
    Δλ = radians(lon2 - lon1)
    a = sin(Δφ / 2)**2 + cos(φ1) * cos(φ2) * sin(Δλ / 2)**2
    return 2 * R * atan2(sqrt(a), sqrt(1 - a))

distance_km = haversine_km(e_i.geo_latitude, e_i.geo_longitude,
                           e_next.geo_latitude, e_next.geo_longitude)
time_delta_hours = (e_next.created_at - e_i.created_at).total_seconds() / 3600.0

# Guard against simultaneous events (same-second timestamps)
if time_delta_hours < (1 / 3600):   # less than 1 second apart
    implied_speed_kmh = float('inf')
else:
    implied_speed_kmh = distance_km / time_delta_hours
```

#### Threshold Evaluation

A detection is triggered for the pair `(e_i, e_next)` when ALL of the following hold:

1. `distance_km >= distance_threshold_km` (default: **500 km**)
2. `implied_speed_kmh > speed_threshold_kmh` (default: **900 km/h**)
3. Neither `e_i.source_ip` nor `e_next.source_ip` is in the admin-configured CIDR blocklist.
4. Neither event has `geo_is_proxy = true` (if `suppress_proxy_ips = true`).

#### VPN/Proxy CIDR Blocklist

Administrators configure a list of known corporate VPN and proxy CIDRs via `PUT /admin/system/vpn-cidrs`. At detection time, `ip_address in network(cidr)` is checked using Python's `ipaddress` module:

```python
import ipaddress

vpn_networks = [ipaddress.ip_network(cidr) for cidr in blocklist_cidrs]

def is_blocklisted(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    return any(addr in net for net in vpn_networks)
```

If either IP of the pair is blocklisted, the pair is skipped and no detection is written. However, if only one IP is blocklisted and the other is not, the detection fires with a reduced confidence (× 0.70 multiplier) and annotates `context_data.one_ip_is_vpn = true`.

#### Context Data Written to Detection

```json
{
  "ip_a": "203.0.113.10",
  "geo_a": {"lat": 37.77, "lon": -122.41, "city": "San Francisco", "country": "US"},
  "ip_b": "185.220.101.45",
  "geo_b": {"lat": 52.52, "lon": 13.40, "city": "Berlin", "country": "DE"},
  "distance_km": 9142,
  "time_delta_seconds": 1800,
  "implied_speed_kmh": 18284,
  "event_id_a": 98231,
  "event_id_b": 98412,
  "one_ip_is_vpn": false
}
```

---

### 2g. Suppression Evaluation Order

Suppression is checked **once per candidate detection**, immediately before the `INSERT` into `detections`. The following checks are evaluated in strict order. The **first matching check wins** and discards the detection.

```
SUPPRESSION EVALUATION ORDER
══════════════════════════════════════════════════════════════════
 #  Check                              Source              Notes
──────────────────────────────────────────────────────────────────
 1  Actor is a bot                     events.actor_is_bot  Applies only to rules where
                                                           x_config.suppress_bot_actors=true
                                                           OR where field_condition already
                                                           filters actor_is_bot=false.
                                                           Checked first — zero DB cost.

 2  Dedup window                       detections table    An OPEN or INVESTIGATING detection
                                                           for the same (rule_id, aggregation
                                                           _key_value) already exists with
                                                           triggered_at >= NOW() - time_window
                                                           _minutes. Instead of discarding,
                                                           UPDATE the existing detection's
                                                           event_ids[] and window_end.
                                                           (This is technically an update-not-
                                                           suppress, but is evaluated here.)

 3  Rule-level global suppression      detection_suppressions  rule_id matches AND suppress_actor
                                                           IS NULL AND suppress_org IS NULL
                                                           AND suppress_repo IS NULL.
                                                           (Suppresses ALL firings of this rule.)

 4  Rule + actor suppression           detection_suppressions  rule_id matches AND suppress_actor
                                                           = detection.actor.
                                                           (Most specific: this rule + this actor.)

 5  Rule + org suppression             detection_suppressions  rule_id matches AND suppress_org
                                                           = detection.org.

 6  Rule + repo suppression            detection_suppressions  rule_id matches AND suppress_repo
                                                           = detection.repo.

 7  Global actor suppression           detection_suppressions  rule_id IS NULL AND suppress_actor
    (cross-rule)                                           = detection.actor.
                                                           (Suppresses all rules for this actor.)

 8  Global org suppression             detection_suppressions  rule_id IS NULL AND suppress_org
    (cross-rule)                                           = detection.org.

 9  Global repo suppression            detection_suppressions  rule_id IS NULL AND suppress_repo
    (cross-rule)                                           = detection.repo.

10  Expired suppression skip           detection_suppressions  Any matched suppression where
                                                           expires_at IS NOT NULL AND
                                                           expires_at < NOW() is skipped
                                                           (treated as if it doesn't exist).
                                                           Active=false rows are also skipped.
══════════════════════════════════════════════════════════════════
```

#### Implementation Notes

- Checks 3–9 are resolved in a single query against `detection_suppressions` with `active = true AND (expires_at IS NULL OR expires_at > NOW())`. The ordering above is applied in Python after fetching all matching rows, not in SQL.
- Check 2 (dedup window) is the one case where a candidate detection is **not discarded** but instead causes an `UPDATE` to the existing detection. This update resets `window_end` and appends new `event_ids`, keeping a single detection per rolling window rather than flooding analysts with repeated alerts.
- A suppressed detection matched by checks 3–9 is silently discarded — **no row is written** to `detections`. This is intentional: suppression rules are an analyst configuration tool, not an evidence trail. The underlying events remain fully queryable.
- The suppression check result is recorded in `audit_trail` with `action_type = 'detection.suppressed'`, `resource_type = 'suppression'`, and `resource_id = suppression.id`. This allows `sys_admin` users to audit which suppressions are actively firing and identify overly-broad suppressions.
```
