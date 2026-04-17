# OctoWatch — Detection & Health Signal Expansion: Architecture Specification

**Status:** Implementation-ready  
**Produced by:** Architecture & Security Agent  
**Date:** 2026-03-27  
**Scope:** User stories US-1A through US-5C (Groups 1, 2, 3, 5)

---

## Table of Contents

1. [Detection Rule Seed Data](#1-detection-rule-seed-data)
2. [Detection Engine Enhancements](#2-detection-engine-enhancements)
3. [External Collaborator Registry Table](#3-external-collaborator-registry-table)
4. [Health Signal SQL Queries](#4-health-signal-sql-queries)
5. [Security Controls](#5-security-controls)
6. [Alembic Migration Checklist](#6-alembic-migration-checklist)

---

## 1. Detection Rule Seed Data

All rules are seeded via Alembic migration `0002_seed_expansion_rules.py`. Each uses the existing `rule_definitions` schema and the new JSON-DSL format (with `action_filters` / `field_conditions`).

### Pre-flight: Confirm logic_config DSL version

Every rule below assumes the **v2 DSL** (`action_filters` list + `field_conditions` array) as implemented in the current `detection_service.py`. The old `conditions[].field/op/value` format from the task header is from the previous schema iteration and **must not** be used in new seeds.

---

### US-1A — Bulk Repository Harvesting

**Requires engine enhancement §2.1 (`distinct_count_field`) before this rule fires correctly.**

```sql
INSERT INTO rule_definitions (
    name, slug, description, category,
    default_severity, default_confidence,
    logic_type, logic_config,
    enabled, status, version, created_by
) VALUES (
    'Bulk Repository Harvesting',
    'bulk-repo-harvesting',
    'A single actor cloned more than 15 distinct repositories within a 1-hour window. '
    'Indicates possible data exfiltration or credential-shared scraping.',
    'data_exfiltration',
    'high', 'medium',
    'threshold',
    '{
        "action_filters":         ["git.clone"],
        "time_window_minutes":    60,
        "threshold":              15,
        "aggregation_key":        "actor",
        "distinct_count_field":   "repo",
        "confidence":             0.70,
        "x_config": {
            "description": "Counts distinct repo values, not raw clone events. "
                           "Requires engine support for distinct_count_field."
        }
    }',
    TRUE, 'active', 1, 'system'
);
```

**Validation:** `distinct_count_field` must be in the engine's `SAFE_TOP_LEVEL_COLUMNS` whitelist (see §2.1). Do not deploy this rule before the engine enhancement is merged.

---

### US-1B(1) — Classic PAT with Overly Broad Scope

```sql
INSERT INTO rule_definitions (
    name, slug, description, category,
    default_severity, default_confidence,
    logic_type, logic_config,
    enabled, status, version, created_by
) VALUES (
    'Classic PAT Created with Full Repo Scope',
    'pat-classic-full-repo-scope',
    'A classic Personal Access Token was created with the "repo" scope, which grants '
    'full read/write access to all repositories. Classic PATs with this scope are a '
    'significant exfiltration risk if stolen.',
    'access_control',
    'high', 'medium',
    'pattern',
    '{
        "action_filters": ["personal_access_token.create"],
        "field_conditions": [
            {
                "field":    "data.token_type",
                "operator": "eq",
                "value":    "classic"
            },
            {
                "field":    "data.token_scopes",
                "operator": "scope_contains",
                "value":    "repo"
            }
        ],
        "confidence": 0.65,
        "x_config": {
            "scope_note": "scope_contains is a new operator (§2.3). It checks whether "
                          "the comma/space-separated scope string contains 'repo' as a "
                          "whole word, not as a prefix like 'repo:status'."
        }
    }',
    TRUE, 'active', 1, 'system'
);
```

**Dependence:** Requires `scope_contains` operator (§2.3). Until implemented, use the interim `matches_glob` alternative below — but understand it produces false positives for `repo:status` and `repo:deployment` scopes:

```jsonc
// INTERIM (false-positive risk): replace field_conditions[1] with:
{ "field": "data.token_scopes", "operator": "matches_glob", "value": "*repo*" }
```

**Normalization recommendation:** The ingestion worker should normalize `token_scopes` from a space/comma-separated string to a JSONB array `token_scopes_parsed: ["repo", "workflow", ...]` during event processing. This makes scope membership queries trivial and eliminates the need for the `scope_contains` operator entirely. Add to `AbstractIngestWorker._normalize_event()`:

```python
if event.get("action") == "personal_access_token.create":
    raw_scopes = event.get("token_scopes", "")
    event["token_scopes_parsed"] = [s.strip() for s in raw_scopes.replace(",", " ").split() if s.strip()]
```

Once deployed, the `field_conditions` can use `{"field": "data.token_scopes_parsed", "operator": "contains", "value": "repo"}` without any new operator.

---

### US-1B(2) — Fine-Grained PAT with Write Access to All Repositories

```sql
INSERT INTO rule_definitions (
    name, slug, description, category,
    default_severity, default_confidence,
    logic_type, logic_config,
    enabled, status, version, created_by
) VALUES (
    'Fine-Grained PAT with All-Repository Write Access',
    'pat-fine-grained-all-repos-write',
    'A fine-grained PAT was created with access to all repositories and includes write-level '
    'permissions. Fine-grained PATs scoped to all repos are equivalent in blast radius to a '
    'classic PAT with the repo scope.',
    'access_control',
    'high', 'medium',
    'pattern',
    '{
        "action_filters": ["personal_access_token.create"],
        "field_conditions": [
            {
                "field":    "data.token_type",
                "operator": "eq",
                "value":    "fine-grained"
            },
            {
                "field":    "data.token_repositories_type",
                "operator": "eq",
                "value":    "all"
            }
        ],
        "confidence": 0.65
    }',
    TRUE, 'active', 1, 'system'
);
```

**Note:** GitHub audit logs for fine-grained PATs include `token_repositories_type` with values `"all"`, `"selected"`, or `"public"`. The write-permission check is omitted here intentionally — a fine-grained PAT with read-only access to all repos is still a significant exfiltration risk and warrants a High alert.

---

### US-1B(3) — GitHub App Installation at Organization Level

```sql
INSERT INTO rule_definitions (
    name, slug, description, category,
    default_severity, default_confidence,
    logic_type, logic_config,
    enabled, status, version, created_by
) VALUES (
    'GitHub App Installed at Organization Scope',
    'integration-install-org-level',
    'A GitHub App was installed with organization-level scope, granting it access to all '
    'repositories in the org. Org-level app installations should be reviewed for permissions '
    'granted to external services.',
    'access_control',
    'high', 'low',
    'pattern',
    '{
        "action_filters": ["integration_installation.create"],
        "field_conditions": [
            {
                "field":    "data.installation_target_type",
                "operator": "eq",
                "value":    "Organization"
            }
        ],
        "confidence": 0.55,
        "x_config": {
            "note": "Low confidence because org-level app installs are common and legitimate. "
                    "Analysts should review the app name/permissions in context_data before escalating."
        }
    }',
    TRUE, 'active', 1, 'system'
);
```

---

### US-2A(1) — Secret Scanning Push Protection Bypass

```sql
INSERT INTO rule_definitions (
    name, slug, description, category,
    default_severity, default_confidence,
    logic_type, logic_config,
    enabled, status, version, created_by
) VALUES (
    'Secret Scanning Push Protection Bypass',
    'push-protection-bypass',
    'A developer bypassed GitHub secret scanning push protection. The commit may contain a '
    'hardcoded secret (API key, token, credential) that was flagged and intentionally overridden. '
    'Each occurrence should be reviewed.',
    'bypass',
    'medium', 'high',
    'pattern',
    '{
        "action_filters": ["secret_scanning.push_protection.bypass"],
        "field_conditions": [],
        "confidence": 0.80
    }',
    TRUE, 'active', 1, 'system'
);
```

---

### US-2A(2) — Branch Protection Policy Override

```sql
INSERT INTO rule_definitions (
    name, slug, description, category,
    default_severity, default_confidence,
    logic_type, logic_config,
    enabled, status, version, created_by
) VALUES (
    'Branch Protection Policy Override',
    'branch-protection-override',
    'An actor overrode a branch protection rule. This allows direct pushes to protected '
    'branches, bypassing required reviews, status checks, or other safeguards.',
    'bypass',
    'medium', 'high',
    'pattern',
    '{
        "action_filters": [
            "protected_branch.policy_override",
            "branch_protection_rule.policy_override"
        ],
        "field_conditions": [],
        "confidence": 0.80
    }',
    TRUE, 'active', 1, 'system'
);
```

**Note:** GitHub uses `protected_branch.policy_override` in modern audit logs and `branch_protection_rule.policy_override` in some older EMU variants. Both are included to handle both.

---

### US-2B — Repeat Bypass Offender (3+ bypasses in 7 days)

**Requires engine fix §2.2 (aggregation key filter bug) to work correctly.**

```sql
INSERT INTO rule_definitions (
    name, slug, description, category,
    default_severity, default_confidence,
    logic_type, logic_config,
    enabled, status, version, created_by
) VALUES (
    'Repeat Bypass Offender',
    'repeat-bypass-offender',
    'An actor has performed 3 or more protection bypasses (push protection bypass, branch '
    'protection override, or dismiss-stale-reviews) within a 7-day rolling window. Repeat '
    'bypass behaviour indicates a systemic disregard for security controls.',
    'bypass',
    'high', 'high',
    'threshold',
    '{
        "action_filters": [
            "secret_scanning.push_protection.bypass",
            "protected_branch.policy_override",
            "branch_protection_rule.policy_override",
            "protected_branch.update"
        ],
        "field_conditions": [
            {
                "field":    "actor_is_bot",
                "operator": "eq",
                "value":    false
            }
        ],
        "time_window_minutes": 10080,
        "threshold":           3,
        "aggregation_key":     "actor",
        "confidence":          0.75,
        "x_config": {
            "multi_action_note": "action_filters already supports multiple actions via ANY() in SQL. "
                                 "The field_conditions filter on protected_branch.update is intentionally "
                                 "broad — an x_config.filter_map can narrow it once that engine feature exists.",
            "admin_escalation": "Severity escalation to Critical for org-admin actors is handled via "
                                "a separate rule (see repeat-bypass-offender-admin). IDP enrichment is "
                                "required for automated admin detection."
        }
    }',
    TRUE, 'active', 1, 'system'
);
```

**Protected_branch.update + dismiss_stale_reviews narrowing:** The `protected_branch.update` action fires for ANY branch protection edit, not just dismiss-reviews. To narrow to dismiss-review events only, add a `field_conditions` entry once per-action condition routing is implemented (§2.4). Until then, this rule will produce some false positives from other branch protection changes — acceptable for a High-severity rule where analyst triage is expected.

#### Admin-Bypass Critical Variant

This rule fires for every bypass by an actor whose title/role in `idp_actor_enrichments` indicates org admin status. It requires IDP sync to be active.

```sql
INSERT INTO rule_definitions (
    name, slug, description, category,
    default_severity, default_confidence,
    logic_type, logic_config,
    enabled, status, version, created_by
) VALUES (
    'Org Admin Actor Protection Bypass',
    'admin-bypass-critical',
    'An actor with org admin or owner role bypassed a security protection control. Admin-initiated '
    'bypasses carry higher risk as they leave no audit-side guardrails remaining.',
    'bypass',
    'critical', 'high',
    'pattern',
    '{
        "action_filters": [
            "secret_scanning.push_protection.bypass",
            "protected_branch.policy_override",
            "branch_protection_rule.policy_override"
        ],
        "field_conditions": [
            {
                "field":    "actor_is_bot",
                "operator": "eq",
                "value":    false
            },
            {
                "field":    "data.user_programmatic_access_type",
                "operator": "not_exists"
            }
        ],
        "confidence": 0.85,
        "x_config": {
            "admin_check_note": "This rule fires for all bypass events at Critical severity. "
                                "Scope it to admin actors only by enabling the suppress-non-admin "
                                "suppression rule after IDP role data is available. "
                                "Alternatively, use severity_configs to downgrade non-admin bypass "
                                "actions and leave this rule as the Critical baseline."
        }
    }',
    FALSE,
    'draft', 1, 'system'
);
```

**This rule ships as `enabled=FALSE, status='draft'`** to avoid alert fatigue before IDP role data is populated. Activate after scoping via suppression rules for non-admin actors.

---

### US-5A(1) — External Collaborator Granted (Medium)

```sql
INSERT INTO rule_definitions (
    name, slug, description, category,
    default_severity, default_confidence,
    logic_type, logic_config,
    enabled, status, version, created_by
) VALUES (
    'External Collaborator Granted Access',
    'external-collaborator-grant',
    'A user outside the GitHub organization was granted repository or org-level access. '
    'External collaborator grants should be reviewed to ensure they follow the principle '
    'of least privilege.',
    'access_control',
    'medium', 'high',
    'pattern',
    '{
        "action_filters": [
            "org.add_outside_collaborator",
            "repo.add_member"
        ],
        "field_conditions": [
            {
                "field":    "data.role",
                "operator": "eq",
                "value":    "outside_collaborator"
            }
        ],
        "confidence": 0.75
    }',
    TRUE, 'active', 1, 'system'
);
```

---

### US-5A(2) — External Collaborator with Elevated Permissions (High)

```sql
INSERT INTO rule_definitions (
    name, slug, description, category,
    default_severity, default_confidence,
    logic_type, logic_config,
    enabled, status, version, created_by
) VALUES (
    'External Collaborator Granted Elevated Permissions',
    'external-collaborator-elevated',
    'An external collaborator (outside_collaborator) was granted admin or maintain-level '
    'permissions. Elevated access for external parties significantly increases supply-chain '
    'and insider-threat risk.',
    'access_control',
    'high', 'high',
    'pattern',
    '{
        "action_filters": [
            "org.add_outside_collaborator",
            "repo.add_member"
        ],
        "field_conditions": [
            {
                "field":    "data.role",
                "operator": "eq",
                "value":    "outside_collaborator"
            },
            {
                "field":    "data.permission",
                "operator": "in",
                "value":    ["admin", "maintain"]
            }
        ],
        "confidence": 0.85
    }',
    TRUE, 'active', 1, 'system'
);
```

---

### US-5A(3) — EMU Guest Enterprise Role Grant

```sql
INSERT INTO rule_definitions (
    name, slug, description, category,
    default_severity, default_confidence,
    logic_type, logic_config,
    enabled, status, version, created_by
) VALUES (
    'Enterprise Managed User Guest Role Granted',
    'emu-guest-role-grant',
    'In an EMU (Enterprise Managed Users) environment, a user was assigned the guest '
    'enterprise role via business-plus features. Guest roles in EMU bypass standard '
    'org membership controls and should be approved explicitly.',
    'access_control',
    'medium', 'high',
    'pattern',
    '{
        "action_filters": [
            "enterprise.grant_business_plus_features",
            "enterprise.invite_member"
        ],
        "field_conditions": [
            {
                "field":    "data.enterprise_role",
                "operator": "eq",
                "value":    "guest"
            }
        ],
        "confidence": 0.75,
        "x_config": {
            "note": "EMU-only. If your org does not use GitHub Enterprise Managed Users, "
                    "disable this rule to avoid false positives."
        }
    }',
    FALSE, 'draft', 1, 'system'
);
```

Ships as `enabled=FALSE` — must be explicitly activated by sys_admin for EMU deployments.

---

### Seed migration skeleton

The Development Agent should produce `backend/alembic/versions/0002_seed_expansion_rules.py` containing all INSERTs above inside `upgrade()` with matching `DELETE` statements in `downgrade()`:

```python
def downgrade() -> None:
    slugs = [
        "bulk-repo-harvesting",
        "pat-classic-full-repo-scope",
        "pat-fine-grained-all-repos-write",
        "integration-install-org-level",
        "push-protection-bypass",
        "branch-protection-override",
        "repeat-bypass-offender",
        "admin-bypass-critical",
        "external-collaborator-grant",
        "external-collaborator-elevated",
        "emu-guest-role-grant",
    ]
    op.execute(
        text("DELETE FROM rule_definitions WHERE slug = ANY(:slugs)"),
        {"slugs": slugs},
    )
```

---

## 2. Detection Engine Enhancements

All enhancements are to `backend/app/services/detection_service.py`. No schema changes required.

### 2.1 — `distinct_count_field` support in threshold evaluator

**Current behaviour:** `evaluate_threshold_rule` counts `COUNT(*)` across all events in the window for the aggregation key. US-1A needs `COUNT(DISTINCT repo)`.

**Config key:** `distinct_count_field` (optional string). When present, changes the counting semantics from raw event count to distinct-value count for the named field.

**Allowed fields (whitelist — injection safety):**

```python
# In detection_service.py, module-level constant
_SAFE_DISTINCT_COLUMNS: frozenset[str] = frozenset({
    "actor", "org", "repo", "source_ip",
    "user_agent", "geo_country_code", "action",
})
```

Fields not in this whitelist must raise a `ValueError` when the rule is loaded, preventing misconfigured rules from executing arbitrary SQL column names.

**Corrected `evaluate_threshold_rule` (combines aggregation-key bug fix + distinct_count_field):**

```python
async def evaluate_threshold_rule(
    session: AsyncSession,
    rule: RuleDefinition,
    events: list[AuditEvent],
    scoped_orgs: list[str],
) -> list[dict[str, Any]]:
    config = rule.logic_config
    threshold: int = config.get("threshold", 1)
    window_minutes: int = config.get("time_window_minutes", 60)
    agg_key: str = config.get("aggregation_key", "actor")
    action_filters: list[str] = config.get("action_filters", [])
    distinct_field: str | None = config.get("distinct_count_field")

    # Validate distinct_count_field against whitelist
    if distinct_field and distinct_field not in _SAFE_DISTINCT_COLUMNS:
        raise ValueError(
            f"Rule {rule.slug}: distinct_count_field '{distinct_field}' is not in "
            f"the allowed column whitelist. Allowed: {sorted(_SAFE_DISTINCT_COLUMNS)}"
        )

    # Validate aggregation_key against whitelist
    if agg_key not in _SAFE_DISTINCT_COLUMNS:
        raise ValueError(
            f"Rule {rule.slug}: aggregation_key '{agg_key}' is not in the allowed "
            f"column whitelist. Allowed: {sorted(_SAFE_DISTINCT_COLUMNS)}"
        )

    matching = [e for e in events if event_matches_rule(e, rule)]
    if not matching:
        return []

    # Collect unique aggregation key values from the current event batch
    agg_values: set[str] = set()
    for ev in matching:
        val = getattr(ev, agg_key, None)
        if val is not None:
            agg_values.add(str(val))

    results = []
    window_start = datetime.now(UTC) - timedelta(minutes=window_minutes)

    for agg_value in agg_values:
        # Build parameterized query — agg_key and distinct_field are
        # validated against the whitelist above, so safe to interpolate
        # into the SQL template as literal column references.
        if distinct_field:
            count_expr = f"COUNT(DISTINCT {distinct_field})"
        else:
            count_expr = "COUNT(*)"

        agg_filter_col = agg_key  # already whitelist-validated

        result = await session.execute(
            text(f"""
                SELECT {count_expr} AS cnt
                FROM events
                WHERE created_at    >= :window_start
                  AND action         = ANY(:actions)
                  AND org            = ANY(:scoped_orgs)
                  AND {agg_filter_col} = :agg_value
            """),
            {
                "window_start": window_start,
                "actions":      action_filters if action_filters else None,
                "scoped_orgs":  scoped_orgs if scoped_orgs else [""],
                "agg_value":    agg_value,
            },
        )
        # If action_filters is empty, skip — do not match all actions
        if not action_filters:
            continue

        row = result.fetchone()
        count = row[0] if row else 0

        if count >= threshold:
            results.append({
                "aggregation_key_value": agg_value,
                "count": count,
                "threshold": threshold,
                "distinct_field": distinct_field,
                "window_start": window_start,
                "window_end": datetime.now(UTC),
                "event_ids": [e.id for e in matching],
            })

    return results
```

**Bug fixed:** The prior implementation omitted `AND {agg_key} = :agg_value` from the SQL, causing the count to include ALL actors' events in the window rather than the specific actor being evaluated. This would cause spurious threshold firings in high-activity orgs.

**field_conditions integration:** The implementation above relies on Python-side `event_matches_rule` to filter the initial candidate set, then queries the DB for the authoritative count. This is the existing pattern and is retained. For large-volume deployments (>100K events/hour), consider translating `field_conditions` into SQL predicates inside `evaluate_threshold_rule` to reduce DB scan scope. That is a performance optimization, not a correctness fix, and can be deferred.

---

### 2.2 — Multi-action threshold support (confirmation + action_filters empty-guard fix)

**Status:** `action_filters` already accepts a list and passes it as `ANY(:actions)` in SQL. Multi-action correlation (US-2B) works correctly once the aggregation key bug (§2.1) is fixed.

**Bug to fix:** The current code contains:
```python
"actions": action_filters or ["*"],
```
The fallback `["*"]` is incorrect — `action = ANY(ARRAY['*'])` matches only the literal string `"*"`, not all actions. The corrected code should skip evaluation when `action_filters` is empty:

```python
if not action_filters:
    logger.warning("detection.threshold_rule_no_action_filters", rule_slug=rule.slug)
    return []
```

This guard is already shown in §2.1's implementation. No additional changes are needed for multi-action support.

---

### 2.3 — New `scope_contains` field condition operator

Add to `evaluate_field_condition` in `detection_service.py`:

```python
case "scope_contains":
    # Handles comma-separated OR space-separated scope strings.
    # Matches only whole-word scope names, not prefixes.
    # e.g., scope_contains("repo") matches "repo,workflow" but NOT "repo:status,workflow"
    if actual is None:
        return False
    # Normalize separators; GitHub classic PATs use commas, older API uses spaces
    tokens = {t.strip() for t in str(actual).replace(",", " ").split()}
    return str(expected) in tokens
```

No schema changes. The operator is purely evaluated in Python and is input-validated via the same `condition["operator"]` match statement. Unknown operators fall through to the default `case _:` with a logged warning.

---

### 2.4 — Future: per-action field condition routing (deferred)

US-2B currently captures `protected_branch.update` broadly to catch dismiss-stale-reviews changes. A future `x_config.action_field_conditions` map would allow different `field_conditions` per action within a single threshold rule:

```jsonc
// Future config (not implemented now):
"action_field_conditions": {
    "protected_branch.update": [
        { "field": "data.setting", "operator": "eq", "value": "dismiss_stale_reviews_on_push" }
    ]
}
```

This is a medium-complexity engine addition that can be deferred to a future sprint without blocking US-2B. Document as a known limitation in the rule description text.

---

## 3. External Collaborator Registry Table

### 3.1 DDL

```sql
-- Migration: 0002_seed_expansion_rules.py (or a separate 0003_external_collaborators.py)

CREATE TABLE external_collaborators (
    id               BIGSERIAL    PRIMARY KEY,

    -- Scope
    org              TEXT         NOT NULL,
    repo             TEXT,                         -- NULL = org-level; NOT NULL = repo-specific

    -- Identity
    github_login     TEXT         NOT NULL,
    github_id        BIGINT,

    -- Access
    role             TEXT         NOT NULL
                     CHECK (role IN (
                         'read', 'triage', 'write', 'maintain', 'admin',
                         'outside_collaborator', 'guest_collaborator'
                     )),
    granted_at       TIMESTAMPTZ  NOT NULL,
    granted_by       TEXT,

    -- Lifecycle
    is_active        BOOLEAN      NOT NULL DEFAULT TRUE,
    removed_at       TIMESTAMPTZ,
    removed_by       TEXT,

    -- Activity tracking (updated by any audit event from this actor in this org/repo)
    last_event_at    TIMESTAMPTZ,

    -- Trace back to the ingested event that created/updated this row
    source_event_id  BIGINT,

    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    -- One active row per (org, repo-or-null, login) combination
    CONSTRAINT uq_ext_collab_scope UNIQUE NULLS NOT DISTINCT (org, repo, github_login)
);

CREATE INDEX idx_ext_collab_org          ON external_collaborators (org, is_active);
CREATE INDEX idx_ext_collab_login        ON external_collaborators (github_login, is_active);
CREATE INDEX idx_ext_collab_last_event   ON external_collaborators (last_event_at DESC)
    WHERE is_active = TRUE;
CREATE INDEX idx_ext_collab_removed      ON external_collaborators (removed_at)
    WHERE removed_at IS NOT NULL;
```

**UNIQUE NULLS NOT DISTINCT** requires PostgreSQL 15+. If running on PG 14, replace with an expression index:

```sql
-- PG 14 fallback:
CREATE UNIQUE INDEX uq_ext_collab_scope
ON external_collaborators (org, COALESCE(repo, ''), github_login);
```

TimescaleDB compatibility: `external_collaborators` is a regular PostgreSQL table — **do not** convert to a hypertable; it tracks current state, not a time series.

### 3.2 Lifecycle: which events update it

| GitHub action | Operation | Notes |
|---|---|---|
| `org.add_outside_collaborator` | `INSERT ... ON CONFLICT DO UPDATE SET role=..., granted_at=..., is_active=TRUE, removed_at=NULL` | Upsert: may re-add a previously removed collaborator |
| `repo.add_member` where `role = outside_collaborator` | Same upsert | Repo-scoped addition |
| `org.remove_outside_collaborator` | `UPDATE SET is_active=FALSE, removed_at=..., removed_by=...` | Soft-delete |
| `repo.remove_member` | `UPDATE SET is_active=FALSE, removed_at=..., removed_by=...` | Repo-scoped removal |
| `member.edited` where permission changed | `UPDATE SET role=..., updated_at=NOW()` | Role change |
| Any audit event from `github_login` in matching `org`/`repo` | `UPDATE SET last_event_at=created_at WHERE github_login=... AND org=... AND is_active=TRUE` | Activity ping |

### 3.3 Where to implement the upsert

The `external_collaborators` table is updated in **two places**:

1. **Baseline import worker** (`backend/app/workers/baseline/`): on first deployment, replay all historical `org.add_outside_collaborator` and `repo.add_member` events to seed the table. Filter to the most recent grant/removal per (org, repo, login) pair.

2. **Ingestion detection hook**: after the bulk insert in `AbstractIngestWorker.ingest_batch()`, run a lightweight SQL upsert for any events in the batch that match the lifecycle actions above. This keeps the registry current in near-real-time.

The update is a low-contention `UPDATE ... WHERE github_login = :login AND org = :org` path, not a high-write table, so no concurrency concerns.

---

## 4. Health Signal SQL Queries

All queries include an `AND org = ANY(:scoped_orgs)` clause. The backend must inject the caller's RBAC-scoped org list into every execution. **Never omit this filter** — its absence is a broken-access-control vulnerability.

The Development Agent must wrap each query in a service function in `backend/app/services/health_signal_service.py` that:
1. Accepts `scoped_orgs: list[str]` as a parameter
2. Passes it as a bound parameter — never string-interpolates org names into SQL
3. Returns a `list[dict]` or Pydantic schema

---

### US-1C — PAT Token Age Health Signal

**Card: Org Health > Access & Identity tab — PAT Health**

```sql
-- PATs with no expiry (created within the last 365 days, still valid)
-- Signal: "X PATs have no expiry date"
SELECT
    actor                                       AS github_login,
    data->>'token_name'                         AS token_name,
    data->>'token_id'                           AS token_id,
    data->>'token_type'                         AS token_type,
    created_at                                  AS created_at,
    EXTRACT(DAY FROM NOW() - created_at)::INT   AS age_days,
    'no_expiry'                                 AS signal_type
FROM events
WHERE action  = 'personal_access_token.create'
  AND org     = ANY(:scoped_orgs)
  AND created_at >= NOW() - INTERVAL '365 days'
  AND (
        data->>'token_expiry_date' IS NULL
     OR data->>'token_expiry_date' = ''
  )

UNION ALL

-- PATs that have passed their expiry date (token_expired is audit-log-injected on expiry)
-- Signal: "Y PATs are currently expired"
SELECT
    actor                                       AS github_login,
    data->>'token_name'                         AS token_name,
    data->>'token_id'                           AS token_id,
    data->>'token_type'                         AS token_type,
    created_at                                  AS created_at,
    EXTRACT(DAY FROM NOW() - created_at)::INT   AS age_days,
    'expired'                                   AS signal_type
FROM events
WHERE action = 'personal_access_token.create'
  AND org    = ANY(:scoped_orgs)
  AND (data->>'token_expired')::BOOLEAN = TRUE

UNION ALL

-- PATs older than 90 days with no expiry
-- Signal: "Z PATs are >90 days old"
SELECT
    actor                                       AS github_login,
    data->>'token_name'                         AS token_name,
    data->>'token_id'                           AS token_id,
    data->>'token_type'                         AS token_type,
    created_at                                  AS created_at,
    EXTRACT(DAY FROM NOW() - created_at)::INT   AS age_days,
    'stale_90d'                                 AS signal_type
FROM events
WHERE action     = 'personal_access_token.create'
  AND org        = ANY(:scoped_orgs)
  AND created_at <= NOW() - INTERVAL '90 days'
  AND (
        data->>'token_expiry_date' IS NULL
     OR data->>'token_expiry_date' = ''
  )

ORDER BY age_days DESC;
```

**Summary counts** (for the health card stat pills):

```sql
SELECT
    COUNT(*) FILTER (WHERE data->>'token_expiry_date' IS NULL
                        OR data->>'token_expiry_date' = '')   AS no_expiry_count,
    COUNT(*) FILTER (WHERE (data->>'token_expired')::BOOLEAN = TRUE) AS expired_count,
    COUNT(*) FILTER (WHERE created_at <= NOW() - INTERVAL '90 days'
                       AND (data->>'token_expiry_date' IS NULL
                         OR data->>'token_expiry_date' = ''))  AS stale_90d_count
FROM events
WHERE action = 'personal_access_token.create'
  AND org    = ANY(:scoped_orgs)
  AND created_at >= NOW() - INTERVAL '365 days';
```

---

### US-1D — Dormant/Unused Tokens

**Card: Org Health > Access & Identity tab — PAT Health (same card as US-1C)**

Signal: "W PATs created >30 days ago with no usage events".

```sql
-- Find PATs that were created but have never had a corresponding usage event
-- within the 30-day grace period after creation.
-- GitHub logs personal_access_token.access when a PAT is used via the API.
SELECT
    create_evt.actor                                AS github_login,
    create_evt.data->>'token_id'                    AS token_id,
    create_evt.data->>'token_name'                  AS token_name,
    create_evt.data->>'token_type'                  AS token_type,
    create_evt.created_at                           AS created_at,
    EXTRACT(DAY FROM NOW() - create_evt.created_at)::INT AS age_days,
    MAX(use_evt.created_at)                         AS last_used_at
FROM events AS create_evt
LEFT JOIN events AS use_evt
    ON  use_evt.action  = 'personal_access_token.access'
    AND use_evt.org     = ANY(:scoped_orgs)
    AND use_evt.data->>'token_id' = create_evt.data->>'token_id'
    AND use_evt.created_at BETWEEN create_evt.created_at
                               AND create_evt.created_at + INTERVAL '30 days'
WHERE create_evt.action  = 'personal_access_token.create'
  AND create_evt.org     = ANY(:scoped_orgs)
  AND create_evt.created_at <= NOW() - INTERVAL '30 days'
GROUP BY
    create_evt.actor,
    create_evt.data->>'token_id',
    create_evt.data->>'token_name',
    create_evt.data->>'token_type',
    create_evt.created_at
HAVING MAX(use_evt.created_at) IS NULL   -- no usage event found in the 30-day window
ORDER BY create_evt.created_at DESC;
```

**TimescaleDB note:** This query joins two ranges of the `events` hypertable. TimescaleDB will push down `create_evt.created_at >=` and `use_evt.created_at BETWEEN ...` to chunk-level pruning. To keep scan scope bounded, consider adding `AND create_evt.created_at >= NOW() - INTERVAL '180 days'` unless the full history is needed for the health card.

---

### US-2C — Top Bypass Offenders Table

**Card: Org Health > Access & Identity tab — Bypass Repeat Offenders**

```sql
SELECT
    actor,
    COUNT(*)                                    AS total_bypasses,
    COUNT(*) FILTER (WHERE action = 'secret_scanning.push_protection.bypass')
                                                AS push_protection_bypasses,
    COUNT(*) FILTER (WHERE action IN (
        'protected_branch.policy_override',
        'branch_protection_rule.policy_override'
    ))                                          AS branch_protection_overrides,
    MIN(created_at)                             AS first_bypass_at,
    MAX(created_at)                             AS last_bypass_at,
    COUNT(DISTINCT DATE_TRUNC('day', created_at)) AS active_days
FROM events
WHERE action = ANY(ARRAY[
    'secret_scanning.push_protection.bypass',
    'protected_branch.policy_override',
    'branch_protection_rule.policy_override'
  ])
  AND org         = ANY(:scoped_orgs)
  AND created_at >= NOW() - INTERVAL '90 days'    -- :lookback_days configurable
  AND actor       IS NOT NULL
  AND actor_is_bot = FALSE
GROUP BY actor
HAVING COUNT(*) >= 1
ORDER BY total_bypasses DESC
LIMIT :limit;   -- default 20, max 100, validated server-side
```

The `:lookback_days` and `:limit` parameters are accepted from the API query string and validated to `[7, 365]` and `[1, 100]` respectively before being bound.

---

### US-3A — Stale Repositories (no event activity > 90 days)

**Card: Org Health > Repository Health tab**

```sql
WITH repo_last_activity AS (
    SELECT
        org,
        repo,
        MAX(created_at) AS last_event_at
    FROM events
    WHERE org  = ANY(:scoped_orgs)
      AND repo IS NOT NULL
    GROUP BY org, repo
)
SELECT
    org,
    repo,
    last_event_at,
    EXTRACT(DAY FROM NOW() - last_event_at)::INT AS days_since_activity
FROM repo_last_activity
WHERE last_event_at <= NOW() - INTERVAL '90 days'   -- :stale_threshold_days configurable
ORDER BY last_event_at ASC
LIMIT :limit;
```

This query benefits from the `idx_events_repo` index on `(repo, created_at DESC)`. For orgs with many repositories, the `MAX(created_at) GROUP BY repo` scan is bounded by TimescaleDB chunk pruning on the `WHERE` clause if a lookback limit is applied. Recommend adding `AND created_at >= NOW() - INTERVAL '2 years'` unless full history is required.

---

### US-3B — Archived Repositories Still Present

**Card: Org Health > Repository Health tab**

```sql
-- Repos that were archived but never deleted
WITH
archived AS (
    SELECT DISTINCT ON (org, repo)
        org, repo, created_at AS archived_at, actor AS archived_by
    FROM events
    WHERE action = 'repo.archived'
      AND org    = ANY(:scoped_orgs)
      AND repo   IS NOT NULL
    ORDER BY org, repo, created_at DESC   -- most recent archive event per repo
),
deleted AS (
    SELECT DISTINCT org, repo
    FROM events
    WHERE action IN ('repo.destroy', 'repo.delete')
      AND org    = ANY(:scoped_orgs)
      AND repo   IS NOT NULL
)
SELECT
    a.org,
    a.repo,
    a.archived_at,
    a.archived_by,
    EXTRACT(DAY FROM NOW() - a.archived_at)::INT AS days_since_archived
FROM archived a
LEFT JOIN deleted d
    ON d.org  = a.org
   AND d.repo = a.repo
WHERE d.repo IS NULL    -- no delete event found after archival
ORDER BY a.archived_at ASC
LIMIT :limit;
```

---

### US-3C — Abandoned Forks (no push within 30 days of fork)

**Card: Org Health > Repository Health tab**

```sql
WITH forks AS (
    SELECT
        actor,
        org,
        repo,                           -- the forked repo name (created in the actor's namespace)
        created_at AS forked_at
    FROM events
    WHERE action       = 'repo.fork'
      AND org          = ANY(:scoped_orgs)
      AND repo         IS NOT NULL
      AND created_at   BETWEEN NOW() - INTERVAL '180 days'   -- bounded lookback
                           AND NOW() - INTERVAL '30 days'    -- old enough to evaluate
),
fork_pushes AS (
    SELECT DISTINCT repo
    FROM events
    WHERE action       IN ('git.push', 'push')
      AND org          = ANY(:scoped_orgs)
      AND repo         IS NOT NULL
      AND created_at   >= NOW() - INTERVAL '180 days'
)
SELECT
    f.actor,
    f.org,
    f.repo,
    f.forked_at,
    EXTRACT(DAY FROM NOW() - f.forked_at)::INT AS days_since_fork
FROM forks f
LEFT JOIN fork_pushes p ON p.repo = f.repo
WHERE p.repo IS NULL                    -- no push event found for this repo
ORDER BY f.forked_at ASC
LIMIT :limit;
```

**Caveat:** Push events to forked repos may appear under the forker's personal namespace, not the org's, depending on how GitHub routes the audit log entry. If `org` on push events differs from the fork's org, this query will not match. Validate against live audit log data before shipping. If needed, remove the `org = ANY(:scoped_orgs)` filter on `fork_pushes` (RBAC is still enforced on the `forks` CTE).

---

### US-5B — External Collaborator Registry

**Card: Org Health > Access & Identity tab — External Collaborators**

```sql
SELECT
    ec.github_login,
    ec.org,
    ec.repo,
    ec.role,
    ec.granted_at,
    ec.granted_by,
    ec.last_event_at,
    CASE
        WHEN ec.last_event_at IS NULL
             THEN NULL
        ELSE EXTRACT(DAY FROM NOW() - ec.last_event_at)::INT
    END                         AS days_since_last_event,
    ia.email                    AS idp_email,
    ia.employment_status        AS idp_employment_status
FROM external_collaborators ec
LEFT JOIN idp_actor_enrichments ia
    ON  ia.github_login = ec.github_login
    AND ia.idp_provider = :idp_provider       -- optional filter; NULL = skip join
WHERE ec.org       = ANY(:scoped_orgs)
  AND ec.is_active = TRUE
ORDER BY ec.granted_at DESC
LIMIT :limit;
```

**Summary: counts for the stat pill strip:**

```sql
SELECT
    COUNT(*)                                                     AS total_active,
    COUNT(*) FILTER (WHERE repo IS NULL)                         AS org_level_count,
    COUNT(*) FILTER (WHERE role IN ('admin', 'maintain'))        AS elevated_count,
    COUNT(*) FILTER (
        WHERE last_event_at IS NULL
           OR last_event_at < NOW() - INTERVAL '60 days'
    )                                                            AS dormant_count
FROM external_collaborators
WHERE org       = ANY(:scoped_orgs)
  AND is_active = TRUE;
```

---

### US-5C — Dormant External Collaborators

**Card: Org Health > Access & Identity tab (same card as US-5B, sub-filter)**

```sql
SELECT
    github_login,
    org,
    repo,
    role,
    granted_at,
    last_event_at,
    CASE
        WHEN last_event_at IS NULL
             THEN EXTRACT(DAY FROM NOW() - granted_at)::INT
        ELSE EXTRACT(DAY FROM NOW() - last_event_at)::INT
    END                         AS days_inactive
FROM external_collaborators
WHERE org       = ANY(:scoped_orgs)
  AND is_active = TRUE
  AND (
        last_event_at IS NULL                              -- never had any activity recorded
     OR last_event_at < NOW() - INTERVAL '60 days'        -- :dormancy_days configurable
  )
ORDER BY days_inactive DESC
LIMIT :limit;
```

---

## 5. Security Controls

### 5.1 RBAC enforcement — mandatory pattern

Every new health signal endpoint and the external collaborators API **must** call `rbac_service.get_scoped_orgs(current_user)` and pass the result to the query function. This is a non-negotiable correctness requirement.

Pattern (from `backend/app/deps.py`):

```python
async def health_signal_endpoint(
    db: AsyncSession = Depends(get_db),
    current_user: UserContext = Depends(get_current_user),
) -> ...:
    scoped_orgs = await rbac_service.get_scoped_orgs(db, current_user)
    if not scoped_orgs:
        raise HTTPException(status_code=403, detail="No org access")
    return await health_signal_service.query_X(db, scoped_orgs=scoped_orgs, ...)
```

Never pass `scoped_orgs=["*"]` or omit the filter. If a sys_admin legitimately needs cross-org visibility, the RBAC service must return the explicit list of all orgs the admin has access to, not a wildcard.

### 5.2 Input validation for new config fields

**`distinct_count_field`** — validated in the engine against `_SAFE_DISTINCT_COLUMNS` whitelist at rule evaluation time. Validation is also recommended at rule-create time in the rules router:

```python
# In backend/app/routers/rules.py, rule creation handler
if (distinct_field := logic_config.get("distinct_count_field")) is not None:
    if distinct_field not in SAFE_DISTINCT_COLUMNS:
        raise HTTPException(
            status_code=422,
            detail=f"distinct_count_field '{distinct_field}' is not a permitted column."
        )
```

**`aggregation_key`** — same whitelist check applies; already referenced in §2.1.

**Health signal query parameters** — `lookback_days`, `limit`, `stale_threshold_days`, `dormancy_days` are all integer values accepted from query string. They must be validated to a bounded range, e.g.:

```python
lookback_days: int = Query(default=90, ge=7, le=365)
limit: int         = Query(default=50, ge=1, le=100)
```

FastAPI's `Query(ge=..., le=...)` handles this without additional code.

**`idp_provider` filter** in US-5B — must be validated against the enum set `{'okta', 'entra', 'google_workspace', None}` to prevent injection. FastAPI `Enum` query parameter type handles this.

### 5.3 No new credentials introduced

All new rules operate on existing events data. The `external_collaborators` table is populated by the ingestion worker (which already has DB write access) and the baseline worker (same). No new API keys, service accounts, or credential stores are required.

### 5.4 SQL injection — parameterized query compliance

The two column names interpolated into SQL templates in §2.1 (`agg_filter_col`, `count_expr`) are constructed only from whitelist-validated values. The whitelists are `frozenset` constants with no user input influencing their content. This pattern is safe; document it clearly so future engineers understand why the column name interpolation is intentional and not a vulnerability.

The `scope_contains` operator evaluates entirely in Python with no SQL generation. Safe.

### 5.5 Audit trail

All `external_collaborators` write operations (insert, soft-delete) made through the API (not the ingestion worker) must be logged to `audit_trail`. The ingestion worker path is exempt since it is a system actor — but the event source_event_id on each row provides lineage.

---

## 6. Alembic Migration Checklist

The CI pipeline runs `alembic upgrade head → downgrade -1 → upgrade head` on every PR that touches `alembic/versions/`. All new migrations must satisfy:

- [ ] `upgrade()` is idempotent (uses `IF NOT EXISTS`, `ON CONFLICT DO NOTHING`, etc. where appropriate)
- [ ] `downgrade()` cleanly reverses every DDL and DML change
- [ ] `external_collaborators` table DDL uses `UNIQUE NULLS NOT DISTINCT` (PG 15+) or the expression index fallback (PG 14). Check the runtime PostgreSQL version first: `SELECT version()`.
- [ ] All `INSERT INTO rule_definitions` rows in `upgrade()` have matching `DELETE FROM rule_definitions WHERE slug = ANY(:slugs)` in `downgrade()`
- [ ] No raw string interpolation of user-controlled data in any migration DDL/DML
- [ ] Migration runs cleanly against both the TimescaleDB Docker image (CI) and the production DB version

---

## Summary: What the Development Agent Must Build

### Files to create/modify

| File | Change |
|---|---|
| `backend/alembic/versions/0002_seed_expansion_rules.py` | New migration: all 11 rule INSERTs + `external_collaborators` DDL |
| `backend/app/services/detection_service.py` | §2.1 threshold evaluator rewrite + §2.3 `scope_contains` operator |
| `backend/app/services/health_signal_service.py` | New service: all 8 health signal query functions, each accepting `scoped_orgs` |
| `backend/app/models/external_collaborator.py` | New ORM model for `external_collaborators` |
| `backend/app/routers/health_signals.py` | New router: `GET /api/v1/health-signals/{signal_type}` endpoints |
| `backend/app/workers/ingestion/base.py` | Upsert hook for `external_collaborators` after batch insert |
| `backend/tests/test_detection_service.py` | New tests: `distinct_count_field`, multi-action threshold, `scope_contains` operator, agg-key bug regression test |
| `backend/tests/test_health_signal_service.py` | New test file: all 8 signal queries with org-scope enforcement |

### Critical correctness constraints

1. **Aggregation key filter bug (§2.1):** The existing `evaluate_threshold_rule` does not filter by the aggregation key value in its DB query. This means threshold rules in multi-actor orgs will fire incorrectly — all counts are inflated across ALL actors. This is a correctness regression that affects **all existing threshold rules**, not just the new ones. It must be fixed before any threshold rule is trusted in production.

2. **`distinct_count_field` whitelist (§2.1):** Column whitelist is mandatory. The alternative (parameterized column names) is not possible in standard SQL — column names cannot be parameterized. Only the explicit whitelist approach is safe.

3. **`UNIQUE NULLS NOT DISTINCT` (§3.1):** Verify PostgreSQL version. The expression-index fallback is functionally identical but syntactically different. Choose based on runtime version detection in the migration.

4. **Health signal query lookback bounds (§4):** Unbounded scans of the `events` hypertable are expensive. Every health signal query should have a reasonable `created_at >= NOW() - INTERVAL 'X'` bound documented in the service function signature. Defaults are shown in the queries; make them configurable via query params with server-side `Query(ge=..., le=...)` bounds.
