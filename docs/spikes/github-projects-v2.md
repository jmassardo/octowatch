# Spike: GitHub Projects V2 Data Integration

**Issue**: #163
**Date**: 2026-05-11
**Status**: Complete

---

## 1. Summary

This spike evaluates integrating GitHub Projects V2 data into OctoWatch to provide visibility into work item management — status tracking, iteration/sprint progress, cycle time, and delivery health metrics.

**Conclusion**: Integration is **feasible** and aligns well with the existing sync architecture. OctoWatch already uses GraphQL + cursor-based pagination for enterprise syncs, and the GitHub App just needs one new org-level permission (`Projects: Read`). The recommended MVP is a read-only sync of projects, items, and status fields on an hourly schedule.

---

## 2. API Capabilities

### 2.1 Available Data via GraphQL

GitHub Projects V2 is accessible exclusively through the **GraphQL API** (`projectV2` / `projectsV2` queries). Available data:

| Data | Query Path | Notes |
|------|-----------|-------|
| Projects (list) | `organization.projectsV2` | Title, URL, closed, createdAt, updatedAt |
| Project items | `node(id).items` | Issues, PRs, draft issues; paginated (max 100/page) |
| Custom fields | `node(id).fields` | Text, number, date, single-select, iteration |
| Status field | `ProjectV2SingleSelectField` | Just a single-select field named "Status" with options |
| Iterations | `ProjectV2IterationField` | Sprint definitions with start date + duration |
| Item field values | `item.fieldValues` | Polymorphic — 10+ inline fragment types |
| Linked content | `item.content` | Issue/PR details (number, state, repo, assignees) |

### 2.2 Key Limitations

- **Field values are highly polymorphic**: Reading field values requires handling 10+ `ProjectV2ItemField*Value` types via inline fragments
- **REDACTED items**: If the App lacks permission on an item's repo, `type` returns `REDACTED` with no accessible fields
- **Webhooks are in public preview**: `projects_v2_item` and `projects_v2` events may change without notice
- **No REST API**: Projects V2 is GraphQL-only

---

## 3. Authentication & Permissions

### 3.1 Current OctoWatch Auth

OctoWatch authenticates via a **GitHub App** with installation tokens (see `backend/app/services/github_token_service.py`). This is the ideal auth method for Projects V2.

### 3.2 Required Permission Change

| Permission | Level | Current | Required |
|-----------|-------|---------|----------|
| **Organization Projects** | Read | ❌ Not granted | ✅ Add this |

This is an **org-level permission** (not repo-level). Adding it requires:
1. Update the GitHub App settings to request `Organization projects: Read`
2. Existing installations will need to **approve** the new permission request
3. No code changes needed for token exchange — same `POST /app/installations/{id}/access_tokens` flow

### 3.3 Scope Summary

- GitHub App: `Organization projects: Read` (sufficient for all read queries)
- Classic PAT fallback: `read:project` scope
- Fine-grained PAT: `Projects: Read` (⚠️ cannot access user-owned projects)

---

## 4. Rate Limit Impact Assessment

### 4.1 Query Cost Model

GitHub GraphQL uses a point-based rate limit (5,000 pts/hour for Apps, up to 12,500 with many repos/users).

**Proposed sync query cost** (items with field values per project):

```
items(first: 100)              = 100
  fieldValues(first: 20)       = 100 × 20 = 2,000
  content.assignees(first: 10) = 100 × 10 = 1,000
Total nodes = 3,101 → 3,101 / 100 = ~32 points per query
```

### 4.2 Estimates by Org Size

| Org Size | Projects | Items/Project | Total Items | Queries | Points | % of 5K Budget |
|----------|----------|---------------|-------------|---------|--------|----------------|
| Small | 10 | 50 | 500 | 15 | ~480 | 10% |
| Medium | 50 | 100 | 5,000 | 100 | ~3,200 | 64% |
| Large | 200 | 200 | 40,000 | 600 | ~19,200 | 384% ⚠️ |

### 4.3 Mitigation for Large Orgs

- **Incremental sync**: Only re-sync projects with `updatedAt` after last sync timestamp
- **Configurable project allowlist**: Let admins select which projects to sync
- **Spread across hours**: Schedule incremental checks every hour, full sync daily
- **Rate limit monitoring**: Reuse existing `GitHubRateLimiter` from `github_sync_worker.py`
- **Budget**: Reserve 1,000 pts/hour for projects sync (20% of budget), leaving 4,000 for existing enterprise sync

**Verdict**: Feasible for small/medium orgs on hourly schedule. Large orgs need incremental sync + allowlisting.

---

## 5. Proposed Data Model

### 5.1 New Tables

```sql
-- Projects
CREATE TABLE github_projects (
    id              BIGSERIAL PRIMARY KEY,
    node_id         TEXT NOT NULL UNIQUE,      -- "PVT_..." GraphQL ID
    org_login       TEXT NOT NULL,
    number          INTEGER NOT NULL,
    title           TEXT NOT NULL,
    short_description TEXT,
    url             TEXT NOT NULL,
    is_public       BOOLEAN NOT NULL DEFAULT false,
    closed          BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL,
    synced_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(org_login, number)
);

-- Project fields (schema definition — not per-item values)
CREATE TABLE github_project_fields (
    id              BIGSERIAL PRIMARY KEY,
    node_id         TEXT NOT NULL UNIQUE,      -- "PVTF_..." / "PVTSSF_..." / "PVTIF_..."
    project_id      BIGINT NOT NULL REFERENCES github_projects(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    data_type       TEXT NOT NULL,             -- TEXT, NUMBER, DATE, SINGLE_SELECT, ITERATION, etc.
    options_json    JSONB,                     -- Single-select options / iteration config
    synced_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(project_id, node_id)
);

-- Project items (issues, PRs, drafts linked to a project)
CREATE TABLE github_project_items (
    id              BIGSERIAL PRIMARY KEY,
    node_id         TEXT NOT NULL UNIQUE,      -- "PVTI_..." GraphQL ID
    project_id      BIGINT NOT NULL REFERENCES github_projects(id) ON DELETE CASCADE,
    item_type       TEXT NOT NULL,             -- ISSUE, PULL_REQUEST, DRAFT_ISSUE, REDACTED
    is_archived     BOOLEAN NOT NULL DEFAULT false,

    -- Denormalized content fields (from item.content)
    content_node_id TEXT,                      -- Issue/PR GraphQL ID
    content_number  INTEGER,
    content_title   TEXT,
    content_state   TEXT,                      -- OPEN, CLOSED, MERGED
    content_url     TEXT,
    content_repo    TEXT,                      -- "owner/repo"

    -- Denormalized key field values for fast queries
    status_value    TEXT,                      -- Current Status option name
    status_option_id TEXT,                     -- Status option ID (stable across renames)
    iteration_title TEXT,                      -- Current iteration/sprint name
    iteration_id    TEXT,                      -- Iteration ID

    -- All field values stored as JSONB for flexibility
    field_values_json JSONB,                   -- {field_name: {type, value, ...}, ...}

    created_at      TIMESTAMPTZ NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL,
    synced_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_project_items_project ON github_project_items(project_id);
CREATE INDEX idx_project_items_status ON github_project_items(status_value);
CREATE INDEX idx_project_items_iteration ON github_project_items(iteration_title);
CREATE INDEX idx_project_items_content_repo ON github_project_items(content_repo);
CREATE INDEX idx_project_items_type ON github_project_items(item_type);

-- Iteration snapshots (for burndown/velocity calculations)
CREATE TABLE github_project_iterations (
    id              BIGSERIAL PRIMARY KEY,
    project_id      BIGINT NOT NULL REFERENCES github_projects(id) ON DELETE CASCADE,
    field_node_id   TEXT NOT NULL,             -- The iteration field's node ID
    iteration_id    TEXT NOT NULL,             -- GitHub's short hex ID
    title           TEXT NOT NULL,
    start_date      DATE NOT NULL,
    duration_days   INTEGER NOT NULL,
    is_completed    BOOLEAN NOT NULL DEFAULT false,
    synced_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(project_id, field_node_id, iteration_id)
);
```

### 5.2 Design Decisions

- **Denormalized status/iteration on items**: Enables fast dashboard queries without JSONB parsing
- **JSONB `field_values_json`**: Stores all field values flexibly — custom fields vary per project
- **`options_json` on fields**: Captures single-select options and iteration configs
- **No separate assignees table**: Stored in `field_values_json` — cross-referencing with existing `enterprise_members` is done at query time
- **`content_repo` as text**: Avoids FK to repositories table — projects may reference repos not yet synced

### 5.3 Storage Estimate

| Component | Per Item | 5,000 Items | 40,000 Items |
|-----------|----------|-------------|--------------|
| `github_project_items` row | ~2 KB | ~10 MB | ~80 MB |
| `github_project_fields` | ~0.5 KB × 20 fields × 50 projects | ~0.5 MB | ~2 MB |
| `github_project_iterations` | negligible | ~0.1 MB | ~0.5 MB |
| **Total** | | **~11 MB** | **~83 MB** |

Negligible compared to existing event data volumes.

---

## 6. Proposed Sync Strategy

### 6.1 Architecture

Follow the existing pattern in `github_sync_worker.py`:
- **Celery task** with `asyncio.run()` wrapper
- **`_graphql_page()` helper** reused for all GraphQL calls
- **`EnterpriseSyncEntityCursor`** pattern for resumable pagination
- **GitHub App installation tokens** via `GitHubTokenService`

### 6.2 Sync Flow

```
1. List projects for each synced org
   → Upsert github_projects, mark stale projects as closed
   
2. For each project:
   a. Fetch fields → Upsert github_project_fields
   b. Fetch iterations → Upsert github_project_iterations
   c. Paginate items (100/page):
      → Parse polymorphic field values
      → Denormalize status + iteration
      → Upsert github_project_items
      → Update cursor after each page
```

### 6.3 Incremental Sync

- **Project-level**: Skip projects where `updatedAt` ≤ last `synced_at`
- **Item-level**: Use `items(first:100, after:cursor)` with cursor resume
- **Full re-sync**: Weekly full sync to catch any missed webhook events or cursor drift

### 6.4 Schedule

| Task | Frequency | Purpose |
|------|-----------|---------|
| `sync-github-projects` | Every 60 minutes | Incremental item sync |
| `sync-github-projects-full` | Weekly (Sunday 03:00 UTC) | Full re-sync |

### 6.5 Webhook Integration (Phase 2)

Register for `projects_v2_item` org webhook events to get near-real-time status changes. Since webhooks are in **public preview**, treat this as a Phase 2 enhancement and rely on polling for MVP.

---

## 7. Feasible Metrics

### 7.1 MVP Metrics (from sync data alone)

| Metric | Derivation | Enhances |
|--------|-----------|----------|
| **Sprint velocity** | Count items where `status_value = 'Done'` per iteration | #126 |
| **Throughput** | Items completed per week (grouping by `updated_at`) | #126 |
| **WIP count** | Items where `status_value = 'In Progress'` | #126 |
| **Cycle time** | Diff between item status transitions (requires history — see 7.2) | #126 |
| **Work distribution** | Items per assignee per project | #127 |
| **Stale items** | Items in non-terminal status with `updated_at` > 14d ago | #127 |
| **Project health** | % items Done vs Total per iteration | #126 |
| **Backlog size** | Items where `status_value` ∈ ('Todo', 'Backlog') | #126 |

### 7.2 Advanced Metrics (Requires Status History)

Cycle time and lead time require tracking **when** items transition between statuses. Two approaches:

1. **Snapshot diffs**: Store a `github_project_item_history` table with periodic snapshots of `status_value`. Compare consecutive snapshots to derive transitions.
2. **Webhook events**: `projects_v2_item` `edited` action includes `changes.field_value` — capture transition timestamps in real time.

Recommend approach #1 for MVP (simpler, no webhook dependency), upgrade to #2 when webhooks stabilize.

### 7.3 Copilot Correlation (enhances #128)

Cross-reference `github_project_items.content_repo` + `content_number` with existing Copilot metrics tables to answer:
- Do teams using Copilot close more items per sprint?
- Is PR-to-merge time shorter for Copilot-assisted PRs linked to project items?

---

## 8. Implementation Plan

### Phase 0: Audit Log Detections (No Dependencies — Ship Immediately)

| Step | Description | Effort |
|------|------------|--------|
| 0a | Add 6 project governance rules to `rule_library.json` | Small |
| 0b | Add posture check for public projects + external collaborators | Small |
| 0c | Tests for new detection rules | Small |

### Phase 1: MVP — Read-Only Sync (Recommended First Iteration)

| Step | Description | Effort |
|------|------------|--------|
| 1 | Add `Projects: Read` permission to GitHub App | Config change |
| 2 | Alembic migration for 4 new tables | Small |
| 3 | SQLAlchemy models in `models/github_projects.py` | Small |
| 4 | `workers/github_projects_worker.py` — Celery task with GraphQL sync | Medium |
| 5 | Beat schedule entry (`sync-github-projects`, 60 min) | Small |
| 6 | Admin API endpoints to list/configure monitored projects | Small |
| 7 | Unit tests for worker + models | Medium |

### Phase 2: Dashboard & Metrics

| Step | Description | Effort |
|------|------------|--------|
| 8 | API endpoints for velocity/throughput/WIP queries | Medium |
| 9 | Frontend "Projects" page — project list + item table | Medium |
| 10 | Velocity/sprint dashboard widgets | Medium |
| 11 | Status history snapshot table + cycle time metrics | Medium |

### Phase 3: Real-Time & Advanced

| Step | Description | Effort |
|------|------------|--------|
| 12 | Webhook handler for `projects_v2_item` events | Medium |
| 13 | Copilot correlation metrics | Small |
| 14 | Cross-project dependency visualization | Large |

---

## 9. MVP Scope Recommendation

**Build Phase 1** (steps 1–7):

- Sync projects, fields, iterations, and items for all orgs on a 60-minute schedule
- Store data in 4 new tables with denormalized status/iteration for fast queries
- Admin endpoint to configure which projects to sync (optional allowlist)
- Reuse existing `_graphql_page()`, `GitHubRateLimiter`, and cursor patterns
- No UI in MVP — data is queryable via API for downstream dashboard work

**Explicitly out of scope for MVP**:
- Webhook integration (preview API, defer to Phase 3)
- Write operations (mutations) — OctoWatch is read-only
- User-owned projects (org-only for now)
- Frontend dashboard (Phase 2)

---

## 10. Audit Log Detections & Org Posture (Zero-API-Cost)

Independently of the GraphQL sync, OctoWatch already ingests audit log events via HEC/webhook. GitHub emits several `project.*` events that map directly to security-relevant governance changes. These can be surfaced through the existing detection rule engine and org posture views **with no additional API calls or permissions**.

### 10.1 Proposed Detection Rules

Add to `rule_library.json` using the existing `logic_type: "pattern"` + `action_filters` pattern:

| Rule Slug | Action Filter(s) | Category | Severity | What It Catches |
|-----------|-----------------|----------|----------|-----------------|
| `project-visibility-public` | `project.visibility_public` | `data_exfiltration` | critical | A project (and all its items) was made publicly visible |
| `project-collaborator-added-external` | `project_collaborator.add` | `privilege_escalation` | high | External collaborator added to a project — potential data exposure |
| `project-collaborator-role-escalated` | `project_collaborator.update` | `privilege_escalation` | medium | Collaborator role upgraded (e.g., read → admin) |
| `project-base-role-elevated` | `project_base_role.update` | `privilege_escalation` | high | Default project access level raised for all org members |
| `project-deleted` | `project.delete` | `defense_evasion` | high | Project deleted — potential evidence destruction |
| `project-field-deleted` | `project_field.delete` | `defense_evasion` | medium | Custom field removed — could hide tracking data |

### 10.2 Rule Configuration Examples

```json
{
  "name": "Project Made Public",
  "slug": "project-visibility-public",
  "description": "Detects when a GitHub Project is changed from private to public visibility, potentially exposing work items, issue titles, and planning data.",
  "category": "data_exfiltration",
  "default_severity": "critical",
  "default_confidence": "high",
  "logic_type": "pattern",
  "logic_config": {
    "action_filters": ["project.visibility_public"],
    "field_conditions": [],
    "confidence": 0.9
  }
}
```

```json
{
  "name": "External Collaborator Added to Project",
  "slug": "project-collaborator-added-external",
  "description": "Detects when a collaborator is added to a GitHub Project. External collaborators gain visibility into issue titles, status, and planning data across all linked repos.",
  "category": "privilege_escalation",
  "default_severity": "high",
  "default_confidence": "high",
  "logic_type": "pattern",
  "logic_config": {
    "action_filters": ["project_collaborator.add"],
    "field_conditions": [
      {
        "field": "data.collaborator_type",
        "operator": "eq",
        "value": "User"
      }
    ],
    "confidence": 0.8
  }
}
```

### 10.3 Org Posture Integration

Since projects are owned by orgs, project governance signals should feed into the existing `OrgPosture` model (`schemas/posture.py`). Proposed additions to `OrgPosture`:

| New Field | Type | Source |
|-----------|------|--------|
| `public_projects_count` | `int` | Count of projects with `is_public=true` from `github_projects` table (Phase 1 sync) |
| `project_external_collaborator_count` | `int` | Count from `project_collaborator.add` audit events or from GraphQL sync |
| `project_detections` | `list[PostureCheckResult]` | Roll up project-related detections into org posture checks |

The posture score calculation should penalize:
- **Any public projects** in the org (critical — mirrors repo-visibility-public logic)
- **External collaborators on projects** (high — data exposure risk)
- **Elevated base roles** (medium — overly permissive defaults)

### 10.4 Implementation Notes

- **No new permissions needed**: Audit log events are already ingested — just add rule definitions
- **No rate limit impact**: Detection rules fire on existing event data
- **Phase 1 quick win**: The 6 detection rules can ship immediately (just `rule_library.json` entries)
- **Phase 1+**: Posture fields (`public_projects_count`, etc.) depend on the GraphQL sync tables existing
- **Existing pattern**: Follows exactly the same approach as `repo-visibility-public` and `branch-protection-disabled` rules

---

## 11. Open Questions for Team Discussion

1. **Project selection**: Sync all org projects by default, or require admin opt-in per project?
2. **Sync frequency**: 60 minutes proposed — is this fresh enough for sprint dashboards?
3. **Rate limit budget**: Allocating 20% (1,000 pts/hour) of the GraphQL budget — acceptable?
4. **History tracking**: Start with snapshot diffs for cycle time, or wait for webhook-based approach?
5. **Multi-org projects**: Some projects span repos across orgs — handle in MVP or defer?
6. **Detection rules**: Ship the 6 audit-log-based rules in advance of the GraphQL sync, or bundle them together?
