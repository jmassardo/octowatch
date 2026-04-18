# Lead Time Enhancement — Technical Architecture Specification

**Status**: Ready for Implementation  
**Date**: 2026-04-18  
**Stories**: 1–7 from strategy output  

---

## 1. Data Model Changes (Stories 1, 3, 7)

All changes are additive JSONB fields — no migrations required.

### 1.1 PR Event Data — New Fields (Stories 1, 7)

Add these fields to the `data` JSONB blob built in the `pull_requests` handler of `_fetch_page()` (line ~1888 of `github_sync_worker.py`):

```python
"data": json.dumps({
    # --- existing fields ---
    "number": pr_number,
    "title": pr.get("title", ""),
    "state": state,
    "merged": merged,
    "url": pr.get("html_url", ""),
    "additions": pr.get("additions", 0),
    "deletions": pr.get("deletions", 0),
    "changed_files": pr.get("changed_files", 0),
    # --- NEW fields (Story 1) ---
    "merge_commit_sha": pr.get("merge_commit_sha"),      # str|None — SHA of the merge commit
    "head_sha": (pr.get("head") or {}).get("sha"),        # str|None — tip of the PR branch
    "head_ref": (pr.get("head") or {}).get("ref"),        # str|None — branch name (e.g. "feat/x")
    # --- NEW field (Story 7) ---
    "pr_created_at": pr.get("created_at"),                # str|None — ISO 8601 of PR creation
    # --- NEW field (Story 3) — populated by GraphQL enrichment ---
    "linked_issues": [],                                  # list[dict] — see §3.3
    # --- existing user field preserved ---
    "user": {"login": actor_login, "id": actor_id},
})
```

**Source**: All new fields are present in the REST `GET /repos/{owner}/{repo}/pulls` response. `merge_commit_sha` is a top-level field. `head.sha` and `head.ref` are nested under the `head` object. `created_at` is already being read for cutoff logic but not stored in `data`.

**Document ID**: Unchanged — `pr-{org}/{repo_name}#{pr_number}-{action_suffix}`

### 1.2 Workflow Run Event Data — New Field (Story 5)

Add `head_sha` to the workflow run `data` JSONB blob built in the `workflow_runs` handler (~line 2031):

```python
"data": json.dumps({
    # --- existing fields ---
    "workflow_name": run.get("name", ""),
    "workflow_id": run.get("workflow_id", 0),
    "run_number": run.get("run_number", 0),
    "run_id": run_id,
    "head_branch": run.get("head_branch", ""),
    "event": run.get("event", ""),
    "conclusion": conclusion,
    "status": run_status,
    "run_started_at": run_started_str,
    "updated_at": updated_str,
    "html_url": run.get("html_url", ""),
    "duration_seconds": duration_seconds,
    # --- NEW field (Story 5) ---
    "head_sha": run.get("head_sha"),  # str|None — commit SHA that triggered the run
})
```

**Source**: `head_sha` is a top-level field in the `GET /repos/{owner}/{repo}/actions/runs` response, already returned by the API but currently discarded.

**Document ID**: Unchanged — `workflow-run-{org}/{repo_name}-{run_id}`


### 1.3 Issue Event Data — New Entity (Story 4)

New `data` JSONB structure for issue events:

```python
{
    "number": int,              # issue number
    "title": str,               # issue title
    "state": str,               # "open" | "closed"
    "state_reason": str | None, # "completed" | "not_planned" | None
    "url": str,                 # html_url
    "labels": list[str],        # label names
    "milestone": str | None,    # milestone title
    "assignees": list[str],     # assignee login names
    "issue_created_at": str,    # ISO 8601 — issue creation date
    "closed_at": str | None,    # ISO 8601 — when closed
    "user": {"login": str, "id": int}
}
```

**Action naming**: `issue.opened`, `issue.closed`  
**Document ID**: `issue-{org}/{repo_name}#{issue_number}-{state}`  
**`created_at` (event timestamp)**: For `issue.opened` → `issue.created_at`; for `issue.closed` → `issue.closed_at` (fallback: `issue.updated_at`)  

### 1.4 Deployment Event Data — New Entity (Story 6)

Two action types:

**Deployment creation** — `deployment.created`:
```python
{
    "deployment_id": int,       # deployment id
    "environment": str,         # "production", "staging", etc.
    "ref": str,                 # branch/tag/SHA deployed
    "sha": str,                 # exact commit SHA deployed
    "task": str,                # "deploy" (usually)
    "description": str | None,  # user-provided description
    "url": str,                 # html_url
    "creator": {"login": str, "id": int}
}
```

**Deployment status** — `deployment_status.{state}` (e.g., `deployment_status.success`, `deployment_status.failure`):
```python
{
    "deployment_id": int,           # parent deployment id
    "status_id": int,               # deployment_status id
    "environment": str,             # inherited from deployment
    "state": str,                   # "success" | "failure" | "error" | "pending" | "in_progress"
    "sha": str,                     # commit SHA (from parent deployment)
    "description": str | None,
    "environment_url": str | None,  # the deployed URL
    "url": str,                     # API url of this status
    "creator": {"login": str, "id": int}
}
```

**Document IDs**:
- Deployment: `deployment-{org}/{repo_name}-{deployment_id}`
- Deployment status: `deploy-status-{org}/{repo_name}-{deployment_id}-{status_id}`

---

## 2. New Sync Handler Specifications (Stories 2, 4)

### 2.1 Issues Sync Handler (Story 2)

**Entity type string**: `"issues"`  
**Registration**: Add to `ScopeType` Literal (line ~117), `_ORG_ENTITIES` set (line ~354), and `_upsert_items` dispatcher → route to `_upsert_activity_events`.

**API Endpoint**: `GET /repos/{owner}/{repo}/issues`

**Parameters**:
```python
params = {
    "state": "all",
    "sort": "updated",
    "direction": "desc",
    "per_page": page_size,  # 100
    "page": page,
    "since": since_dt.strftime('%Y-%m-%dT%H:%M:%SZ'),  # delta_since or 90d ago
}
```

**Filtering**: The GitHub issues endpoint returns PRs mixed in. Filter them out:
```python
if issue.get("pull_request"):
    continue  # Skip — this is a PR, not an issue
```

**Cursor format**: Same repo-iteration pattern as `pull_requests`:
```json
{"repo_idx": 0, "page": 1}
```

**Delta/cutoff logic**: Same pattern as `pull_requests` — sort by `updated`, stop when `updated_at < cutoff`. Default 90-day window for initial sync.

**Item construction**:
```python
state = issue.get("state", "open")
if state == "closed":
    action = "issue.closed"
    ts_str = issue.get("closed_at") or issue.get("updated_at") or issue.get("created_at")
else:
    action = "issue.opened"
    ts_str = issue.get("created_at")

actor = (issue.get("user") or {})
items.append({
    "action": action,
    "actor": actor.get("login"),
    "actor_id": actor.get("id"),
    "actor_is_bot": bool(actor.get("login", "").endswith("[bot]")),
    "org": org,
    "repo": f"{org}/{repo_name}",
    "created_at": parse_iso(ts_str),
    "document_id": f"issue-{org}/{repo_name}#{issue['number']}-{state}",
    "data": json.dumps({
        "number": issue["number"],
        "title": issue.get("title", ""),
        "state": state,
        "state_reason": issue.get("state_reason"),
        "url": issue.get("html_url", ""),
        "labels": [l["name"] for l in (issue.get("labels") or [])],
        "milestone": (issue.get("milestone") or {}).get("title"),
        "assignees": [a["login"] for a in (issue.get("assignees") or [])],
        "issue_created_at": issue.get("created_at"),
        "closed_at": issue.get("closed_at"),
        "user": {"login": actor.get("login"), "id": actor.get("id")},
    }),
    "ingestion_source": "github_api_sync",
    "source_file_path": f"api/{org}/{repo_name}/issues",
})
```

**Placement in `_fetch_page()`**: Add a new `if entity_type == "issues":` block after the `pull_requests` block (~line 1930), following the same repo-iteration structure verbatim.

**Token scope**: Requires `issues:read` on the GitHub App installation. Already covered by typical OctoWatch App permissions.

### 2.2 Deployments Sync Handler (Story 4)

**Entity type string**: `"deployments"`  
**Registration**: Add to `ScopeType`, `_ORG_ENTITIES`, route to `_upsert_activity_events`.

**API Endpoints** (nested):
1. `GET /repos/{owner}/{repo}/deployments` — list deployments
2. `GET /repos/{owner}/{repo}/deployments/{deployment_id}/statuses` — list statuses per deployment

**Deployments list parameters**:
```python
params = {
    "per_page": page_size,  # 100
    "page": page,
}
```

> The deployments endpoint does not support `since` filtering or `sort`. It returns deployments in reverse chronological order by default. Use `created_at` comparison for cutoff.

**Cursor format**: Extended repo-iteration with deployment sub-pagination:
```json
{"repo_idx": 0, "page": 1}
```
> Statuses are fetched inline per deployment (typically ≤5 statuses each, no sub-cursor needed). If a deployment has >100 statuses, only the first page is taken (extremely rare).

**Nested fetch flow**:
```
for each repo:
    GET /repos/{owner}/{repo}/deployments?page=N
    for each deployment:
        GET /repos/{owner}/{repo}/deployments/{id}/statuses?per_page=100
        emit deployment.created event
        for each status:
            emit deployment_status.{state} event
```

**Delta/cutoff logic**: Compare `deployment.created_at` against cutoff; stop when deployments are older than cutoff (they're returned newest-first). Skip entire deployment (and its statuses) if older than cutoff.

**Item construction — deployment**:
```python
creator = deployment.get("creator") or {}
items.append({
    "action": "deployment.created",
    "actor": creator.get("login"),
    "actor_id": creator.get("id"),
    "actor_is_bot": bool(creator.get("login", "").endswith("[bot]")),
    "org": org,
    "repo": f"{org}/{repo_name}",
    "created_at": parse_iso(deployment["created_at"]),
    "document_id": f"deployment-{org}/{repo_name}-{deployment['id']}",
    "data": json.dumps({
        "deployment_id": deployment["id"],
        "environment": deployment.get("environment", ""),
        "ref": deployment.get("ref", ""),
        "sha": deployment.get("sha", ""),
        "task": deployment.get("task", "deploy"),
        "description": deployment.get("description"),
        "url": deployment.get("html_url") or deployment.get("url", ""),
        "creator": {"login": creator.get("login"), "id": creator.get("id")},
    }),
    "ingestion_source": "github_api_sync",
    "source_file_path": f"api/{org}/{repo_name}/deployments",
})
```

**Item construction — deployment status**:
```python
status_creator = status.get("creator") or {}
items.append({
    "action": f"deployment_status.{status.get('state', 'unknown')}",
    "actor": status_creator.get("login"),
    "actor_id": status_creator.get("id"),
    "actor_is_bot": bool(status_creator.get("login", "").endswith("[bot]")),
    "org": org,
    "repo": f"{org}/{repo_name}",
    "created_at": parse_iso(status["created_at"]),
    "document_id": f"deploy-status-{org}/{repo_name}-{deployment['id']}-{status['id']}",
    "data": json.dumps({
        "deployment_id": deployment["id"],
        "status_id": status["id"],
        "environment": deployment.get("environment", ""),
        "state": status.get("state", ""),
        "sha": deployment.get("sha", ""),
        "description": status.get("description"),
        "environment_url": status.get("environment_url"),
        "url": status.get("url", ""),
        "creator": {"login": status_creator.get("login"), "id": status_creator.get("id")},
    }),
    "ingestion_source": "github_api_sync",
    "source_file_path": f"api/{org}/{repo_name}/deployments/{deployment['id']}/statuses",
})
```

**API budget**: Deployment status fetches are O(deployments × repos). See §6 for throttling strategy.

**Token scope**: Requires `deployments:read` on the GitHub App. Must be explicitly added in the App configuration.

### 2.3 Dispatcher Registration Summary

```python
# ScopeType Literal — add:
"issues",
"deployments",

# _ORG_ENTITIES set — add:
"issues",
"deployments",

# _upsert_items dispatcher — extend the existing branch:
elif entity_type in ("repo_commits", "pull_requests", "workflow_runs", "issues", "deployments"):
    await _upsert_activity_events(session, org_str, items)
```

---

## 3. GraphQL Enrichment Design (Story 3)

### 3.1 Architecture

GraphQL enrichment runs **inline within the PR fetch flow**, not as a separate entity type. After the REST page of PRs is fetched and items are built, merged PRs in the current batch are enriched with linked issue data via a single batched GraphQL call.

This avoids a separate sync pass, keeps enrichment atomic with the PR page, and reuses the same rate limiter.

### 3.2 Trigger Condition

Only enrich PRs where:
1. `merged == True` (linked issues only matter for lead time of merged PRs)
2. The PR is within the sync window (not skipped by delta cutoff)

### 3.3 GraphQL Query

Batch up to **25 merged PRs per GraphQL request** using aliases:

```graphql
query LinkedIssues {
  pr0: repository(owner: "org", name: "repo") {
    pullRequest(number: 123) {
      closingIssuesReferences(first: 10) {
        nodes {
          number
          createdAt
          repository { nameWithOwner }
        }
      }
    }
  }
  pr1: repository(owner: "org", name: "repo") {
    pullRequest(number: 456) {
      closingIssuesReferences(first: 10) {
        nodes {
          number
          createdAt
          repository { nameWithOwner }
        }
      }
    }
  }
  # ... up to pr24
}
```

**Why aliases over `nodes` query**: Each PR may be in a different repo within the same page (repo-iteration pattern returns all repos). Aliases let us batch cross-repo queries.

**`first: 10`**: A PR rarely closes more than a handful of issues. 10 is a safe upper bound.

### 3.4 Response Processing

Parse the aliased response and inject into the corresponding item's `data.linked_issues`:

```python
linked_issues = []
for node in pr_data["closingIssuesReferences"]["nodes"]:
    linked_issues.append({
        "number": node["number"],
        "created_at": node["createdAt"],  # ISO 8601
        "repo": node["repository"]["nameWithOwner"],
    })
```

Update the item's `data` dict (before `json.dumps`) to include:
```python
data_dict["linked_issues"] = linked_issues
```

### 3.5 Implementation Location

Add a helper function `_enrich_prs_with_linked_issues()`:

```python
async def _enrich_prs_with_linked_issues(
    items: list[dict],
    token: str,
    rate_limiter: GitHubRateLimiter,
) -> None:
    """Mutate *items* in-place: add linked_issues to merged PR data blobs.
    
    Best-effort: on GraphQL failure, items retain empty linked_issues lists.
    """
```

Call it at the end of the `pull_requests` handler, before returning `items`:

```python
# After building all items for this page, enrich merged PRs
merged_items = [i for i in items if i["action"] == "pull_request.merged"]
if merged_items:
    await _enrich_prs_with_linked_issues(merged_items, token, rate_limiter)
```

### 3.6 Error Handling

- **GraphQL errors**: Log warning, leave `linked_issues` as `[]`. Never fail the sync page.
- **Partial errors**: GraphQL can return partial data with errors. Process whatever data is returned; log individual alias failures.
- **Rate limiting**: The `_graphql_page()` helper already handles 429/403 via the rate limiter. If rate-limited, return empty — the next delta sync will re-fetch these PRs (they'll still be within the updated_at window).
- **Permission denied**: If the token lacks the required scope, GraphQL returns `null` for the field. Handle gracefully — log once, skip enrichment.

### 3.7 Rate Budget

- **GraphQL rate limit**: 5,000 points/hour. Each aliased query costs 1 point per alias + 1 for the query = ~26 points for a batch of 25 PRs.
- **Typical load**: 100 merged PRs per sync → 4 GraphQL requests → 104 points. Well within budget.
- **Worst case**: 1,000 merged PRs (large enterprise catch-up) → 40 requests → ~1,040 points. Still under 25% of hourly budget.
- The existing REST sync consumes REST rate limit (15,000/hour separate pool). GraphQL has its own pool, so enrichment doesn't compete with REST fetches.

---

## 4. Lead Time SQL Design (Story 6)

### 4.1 CTE Query Structure

Replace the existing `pr_lifecycle_stmt` in `get_metrics_that_matter()` with this CTE-based query:

```sql
WITH merged_prs AS (
    -- All merged PRs in the window
    SELECT
        repo,
        data->>'number'                          AS pr_num,
        created_at                                AS merge_event_ts,
        (data->>'pr_created_at')::timestamptz     AS pr_created_at,
        data->>'merge_commit_sha'                 AS merge_commit_sha,
        data->>'head_sha'                         AS head_sha,
        data->'linked_issues'                     AS linked_issues_json
    FROM events
    WHERE action = 'pull_request.merged'
      AND created_at >= :start
      AND actor NOT LIKE '%[bot]'
      {org_filter}
),

-- START TIME: earliest linked issue created_at, falling back to PR created_at
start_times AS (
    SELECT
        m.repo,
        m.pr_num,
        m.merge_event_ts,
        m.merge_commit_sha,
        m.head_sha,
        m.pr_created_at,
        COALESCE(
            -- Fallback level 1: MIN(linked_issue.created_at)
            (
                SELECT MIN((issue_ref->>'created_at')::timestamptz)
                FROM jsonb_array_elements(m.linked_issues_json) AS issue_ref
                WHERE issue_ref->>'created_at' IS NOT NULL
            ),
            -- Fallback level 2: PR created_at
            m.pr_created_at,
            -- Fallback level 3: merge event timestamp (should never reach here)
            m.merge_event_ts
        ) AS start_time
    FROM merged_prs m
),

-- FINISH TIME: first successful deployment_status, else first successful workflow_run on merge SHA, else merge timestamp
finish_times AS (
    SELECT
        s.repo,
        s.pr_num,
        s.start_time,
        COALESCE(
            -- Fallback level 1: deployment_status.success matching merge_commit_sha
            (
                SELECT MIN(d.created_at)
                FROM events d
                WHERE d.action = 'deployment_status.success'
                  AND d.repo = s.repo
                  AND d.data->>'sha' = s.merge_commit_sha
                  AND d.created_at >= s.merge_event_ts
                  AND d.created_at < s.merge_event_ts + INTERVAL '7 days'
                  AND s.merge_commit_sha IS NOT NULL
            ),
            -- Fallback level 2: workflow_run.success matching merge_commit_sha via head_sha
            (
                SELECT MIN(w.created_at)
                FROM events w
                WHERE w.action = 'workflow_run.success'
                  AND w.repo = s.repo
                  AND w.data->>'head_sha' = s.merge_commit_sha
                  AND w.created_at >= s.merge_event_ts
                  AND w.created_at < s.merge_event_ts + INTERVAL '7 days'
                  AND s.merge_commit_sha IS NOT NULL
            ),
            -- Fallback level 3: merge timestamp
            s.merge_event_ts
        ) AS finish_time
    FROM start_times s
)

SELECT
    AVG(EXTRACT(EPOCH FROM (finish_time - start_time)) / 3600.0) AS avg_lead_time_hours,
    PERCENTILE_CONT(0.5) WITHIN GROUP (
        ORDER BY EXTRACT(EPOCH FROM (finish_time - start_time)) / 3600.0
    ) AS median_lead_time_hours,
    COUNT(*) AS pr_count
FROM finish_times
WHERE finish_time > start_time  -- sanity guard
```

### 4.2 Query Design Decisions

| Decision | Rationale |
|----------|-----------|
| Lateral subquery in `start_times` for linked issues | `jsonb_array_elements` is cheap for small arrays (≤10 elements). No JOIN explosion risk. |
| Correlated subqueries in `finish_times` | Bounded by `INTERVAL '7 days'` window and repo match. TimescaleDB chunk exclusion applies via `created_at` range. |
| `merge_commit_sha` correlation for finish | This is how GitHub signals "the workflow ran on the merged code". When a PR is merged, the merge commit SHA appears as `head_sha` on the resulting workflow run. |
| `INTERVAL '7 days'` cap on finish lookback | Prevents matching unrelated deployment/workflow events from weeks later. Deployments/workflows running >7 days after merge are not attributable to this PR. |
| Median alongside average | Average is skewed by outliers. Median provides the representative programmer experience. |
| `finish_time > start_time` guard | Prevents negative lead times from clock skew or data anomalies. |

### 4.3 Backward Compatibility

The existing `avg_pr_lifecycle_hours` field in the response is **preserved**. The new query populates **additional** fields:

```python
return {
    "shipping_faster": {
        "avg_pr_lifecycle_hours": avg_pr_lifecycle_hours,          # KEEP - old metric
        "avg_lead_time_hours": avg_lead_time_hours,               # NEW - enhanced metric
        "median_lead_time_hours": median_lead_time_hours,         # NEW
        "lead_time_pr_count": lead_time_pr_count,                 # NEW - sample size
        # ... rest unchanged
    }
}
```

### 4.4 Index Recommendations

Create a new Alembic migration (next available revision number) with these partial expression indexes:

```sql
-- Index 1: merged PRs lookup (drives the merged_prs CTE)
-- Replaces/supplements existing idx_events_pr_lifecycle which covers different actions
CREATE INDEX IF NOT EXISTS idx_events_pr_merged
    ON events (org, repo, created_at DESC)
    WHERE action = 'pull_request.merged';

-- Index 2: deployment_status.success by SHA (finish time fallback 1)
CREATE INDEX IF NOT EXISTS idx_events_deploy_status_sha
    ON events (repo, (data->>'sha'), created_at)
    WHERE action = 'deployment_status.success';

-- Index 3: workflow_run.success by head_sha (finish time fallback 2)
CREATE INDEX IF NOT EXISTS idx_events_workflow_success_sha
    ON events (repo, (data->>'head_sha'), created_at)
    WHERE action = 'workflow_run.success';

-- Index 4: issues by repo+number (for issue.opened lookups if needed later)
CREATE INDEX IF NOT EXISTS idx_events_issue_opened
    ON events (repo, (data->>'number'), created_at)
    WHERE action = 'issue.opened';
```

**Why partial indexes**: Each index only covers the specific action type, keeping the index small. TimescaleDB creates per-chunk indexes automatically, so these stay proportional to the 1-week chunk size.

**Size estimate**: With 10K events/week total, the PR-merged index covers ~500-1,000 events/chunk. Each index adds <1MB per chunk.

### 4.5 Per-Repo Lead Time Breakdown

For the trend/drill-down, the same CTE structure can be wrapped with a `GROUP BY repo`:

```sql
-- Add to the final SELECT:
SELECT
    repo,
    AVG(EXTRACT(EPOCH FROM (finish_time - start_time)) / 3600.0) AS avg_lead_time_hours,
    PERCENTILE_CONT(0.5) WITHIN GROUP (
        ORDER BY EXTRACT(EPOCH FROM (finish_time - start_time)) / 3600.0
    ) AS median_lead_time_hours,
    COUNT(*) AS pr_count
FROM finish_times
WHERE finish_time > start_time
GROUP BY repo
ORDER BY avg_lead_time_hours DESC
```

This is a separate query — not included in the main `get_metrics_that_matter()` call. Expose it via a dedicated endpoint or parameter if the frontend needs it.

---

## 5. Security Considerations

### 5.1 Token Scope Requirements

| Entity Type | Required GitHub App Permission | Scope |
|-------------|-------------------------------|-------|
| `issues` | `issues:read` | Repository |
| `deployments` | `deployments:read` | Repository |
| `pull_requests` (existing + enrichment) | `pull_requests:read` | Repository |
| `workflow_runs` (existing) | `actions:read` | Repository |
| GraphQL `closingIssuesReferences` | `issues:read` + `pull_requests:read` | Repository |

The `issues:read` scope is typically granted by default when OctoWatch's GitHub App is installed. `deployments:read` must be explicitly added to the App's permission manifest.

**Action required**: Update the GitHub App's permissions page to add `deployments:read` (Repository permission). Existing installations will need to approve the permission change.

### 5.2 Data Exposure

- Issue titles and labels are stored in JSONB. They may contain sensitive project names. These are already governed by the same RBAC scope enforcement as all other events (`org` filter on queries, scope check on event retrieval).
- Deployment environment URLs (`environment_url`) could reveal internal infrastructure URLs. They should not be exposed in public-facing dashboards.
- `merge_commit_sha` and `head_sha` are not sensitive but could be used for repository enumeration. Access is already gated by the events API RBAC.

### 5.3 Input Validation

- **Issue/deployment data from GitHub API**: The REST responses are typed by GitHub. However, always use `.get()` with defaults for all fields. Never trust field presence.
- **GraphQL response**: May contain partial data with errors array. Always check for `None` before accessing nested fields.
- **Linked issue `created_at` in JSONB**: Stored as ISO string, parsed at query time via `::timestamptz`. Invalid dates will produce `NULL` and be excluded by `COALESCE` fallback — safe.
- **Document IDs**: Constructed from org/repo/number which are all from GitHub's API response. No user-supplied input enters document IDs.
- **SQL injection**: All queries use parameterized `:param` bindings. The `org_filter` is constructed from a trusted boolean check (`if org else ""`), not from user input directly. The `org` value is always passed as a bind parameter.

### 5.4 Rate Limit Abuse Prevention

Deployment status fetches are nested (N deployments × M repos). To prevent runaway API consumption:
- Cap deployment fetch to repos with recent activity only (use same `delta_since` cutoff)
- Cap status fetches to **3 pages max** per deployment (300 statuses). If exceeded, log a warning and move on.
- The existing `rate_limiter.acquire()` in `_github_get()` enforces the global 15,000 REST calls/hour budget.

---

## 6. Performance Considerations

### 6.1 API Budget Impact

**Current budget consumption** (per sync cycle, ~100 repos):

| Entity | API Calls | Notes |
|--------|-----------|-------|
| `pull_requests` | ~200 | 2 pages avg per repo |
| `workflow_runs` | ~150 | 1.5 pages avg per repo |
| **Subtotal (existing)** | **~350** | |

**New additions**:

| Entity | API Calls | Notes |
|--------|-----------|-------|
| `issues` | ~200 | 2 pages avg per repo (same pattern as PRs) |
| `deployments` | ~150 | 1.5 pages avg per repo |
| Deployment statuses | ~300 | ~2 deployments/repo × 1 status page each |
| GraphQL enrichment | ~8 | ~200 merged PRs / 25 per batch |
| **Subtotal (new)** | **~658** | |
| **Grand total** | **~1,008** | Well within 15K REST + 5K GraphQL/hour |

**Worst case** (1,000 repos, catch-up sync): ~10,000 REST calls + ~160 GraphQL calls. Fits within rate limits with headroom but will take ~20 minutes due to rate limiter pacing.

### 6.2 Query Performance on 10K+ Events

**Lead time query analysis**:

1. **`merged_prs` CTE**: Scans `events` with `action = 'pull_request.merged'` and `created_at >= :start`. Uses `idx_events_pr_merged` (partial index). For 30-day window, typically 500–2,000 rows. **Cost: one index scan, <10ms.**

2. **`start_times` CTE**: For each merged PR, calls `jsonb_array_elements` on `linked_issues_json`. Average array size ≤3. No table scan — operates on the CTE result set. **Cost: CPU-bound, <5ms.**

3. **`finish_times` CTE**: Two correlated subqueries per merged PR:
   - `deployment_status.success` lookup: Uses `idx_events_deploy_status_sha`. Bounded by `INTERVAL '7 days'` + repo match. **Per-PR cost: one index seek.**
   - `workflow_run.success` lookup: Uses `idx_events_workflow_success_sha`. Same bounds. **Per-PR cost: one index seek.**
   - For 1,000 merged PRs: 2,000 index seeks. TimescaleDB chunk exclusion reduces this to 1–2 chunks. **Total cost: ~50–100ms.**

4. **Final aggregation**: `AVG` + `PERCENTILE_CONT` on 500–2,000 rows. **Cost: <5ms.**

**Total estimated query time**: 50–150ms for a 30-day window with 10K+ total events. Acceptable for a dashboard query.

**At scale (100K+ events)**: The partial indexes and TimescaleDB chunk pruning keep the query from degrading. The correlated subqueries are bounded by the 7-day window and always hit indexes. No full table scans.

### 6.3 Ingestion Performance

- All new entity types use the same `_upsert_activity_events()` codepath — single-row INSERT with dedup check. No schema changes.
- Issue sync adds ~500–2,000 events per sync cycle (comparable to existing PR volume).
- Deployment sync adds ~200–500 events per sync cycle.
- Linked issues are embedded in PR event JSONB — no additional rows.
- Dedup via `event_dedup` table ensures idempotent re-syncs.

### 6.4 TimescaleDB Chunk Considerations

All new events get the same `created_at` partitioning as existing events. No chunk configuration changes needed. Weekly chunks handle the additional volume without issue.

---

## Implementation Sequence

Execute in story order for minimal risk:

| Order | Story | What changes | Files modified |
|-------|-------|--------------|----------------|
| 1 | Story 1 (XS) | Add `merge_commit_sha`, `head_sha`, `head_ref` to PR data | `github_sync_worker.py` |
| 2 | Story 7 (XS) | Add `pr_created_at` to PR data | `github_sync_worker.py` |
| 3 | Story 5 (XS) | Add `head_sha` to workflow_run data | `github_sync_worker.py` |
| 4 | Story 2 (S) | New `issues` sync handler | `github_sync_worker.py` |
| 5 | Story 3 (M) | GraphQL enrichment for linked issues | `github_sync_worker.py` |
| 6 | Story 4 (M) | New `deployments` sync handler | `github_sync_worker.py` |
| 7 | Story 6 (L) | Rewrite lead time SQL + add indexes | `report_service.py`, new Alembic migration |

Stories 1–3 are safe to ship independently — they only add fields to existing JSONB blobs. Story 6 depends on all prior stories for data availability but degrades gracefully (COALESCE chain falls back when data is missing).
