# OctoWatch — Audit Log Coverage Expansion: Implementation Plan & Spec

**Version:** 1.0  
**Date:** 2026-03-27  
**Status:** Draft — Pending Review  
**Produced by:** Tech Lead  
**Depends on:** [docs/detection-health-signal-spec.md](detection-health-signal-spec.md), [docs/api-and-detection-design.md](api-and-detection-design.md), [docs/architecture.md](architecture.md)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Scope & Guiding Principles](#2-scope--guiding-principles)
3. [Phased Delivery Plan](#3-phased-delivery-plan)
4. [Phase 1 — Security Foundational Layer](#4-phase-1--security-foundational-layer)
5. [Phase 2 — Security Operations Depth](#5-phase-2--security-operations-depth)
6. [Phase 3 — Engineering & Operations Layer](#6-phase-3--engineering--operations-layer)
7. [Phase 4 — Advanced Threat Correlation](#7-phase-4--advanced-threat-correlation)
8. [Backend API Changes](#8-backend-api-changes)
9. [Frontend Changes](#9-frontend-changes)
10. [Detection Rule Schemas](#10-detection-rule-schemas)
11. [Database Migrations](#11-database-migrations)
12. [Cross-Cutting Concerns](#12-cross-cutting-concerns)
13. [Test Plan](#13-test-plan)
14. [Definition of Done](#14-definition-of-done)

---

## 1. Executive Summary

Octowatch's audit log ingestion pipeline is generic and event-agnostic — it ingests and stores all GitHub audit log events equally. However, the detection engine, health signal service, and UI currently interpret only a narrow slice of available event namespaces: primarily PATs, push protection bypasses, repository hygiene, and impossible travel.

A comprehensive review of the GitHub Enterprise Cloud audit log surface (110+ event namespaces, 400+ distinct action types) against Octowatch's current detection and health signal coverage reveals the following:

| Audit Log Namespaces Available | Currently with Dedicated Coverage | Gap |
|---|---|---|
| ~110 | ~8 | ~102 |

This specification defines a four-phase implementation plan to close that gap with purpose-built detections, health signals, metrics, and UI surfaces for three primary audiences:

- **Security professionals** — threat detection, alert quality, posture monitoring
- **Engineering managers** — SDLC health, workflow governance, repository hygiene
- **Operations teams** — Copilot governance, runner fleet, cost signals, audit integrity

**Total estimated engineering scope:** 4 phases, 19 work streams, 68 user stories.

---

## 2. Scope & Guiding Principles

### 2.1 In Scope

- New detection rules seeded via Alembic migration
- New health signal SQL queries added to `health_signal_service.py`
- New API endpoints (or extensions to existing ones) in `backend/app/routers/`
- New frontend pages and components in `frontend/src/`
- Database schema additions (new tables, new indices, new materialized views)
- Updates to `ingest_worker.py` for field normalization required by new rules
- Backend test coverage for all new services and endpoints

### 2.2 Out of Scope

- Changes to the core detection engine evaluation pipeline (covered by prior spec)
- Changes to the ingestion storage backend (S3/Blob/MinIO architecture)
- Multi-tenancy or plugin system (ROADMAP items)
- Real-time alerting via Slack/email (separate roadmap item, but socket events from Phase 1 are prerequisite infrastructure)

### 2.3 Guiding Principles

1. **No false security** — every new signal must include a documented false-positive profile and recommended suppression strategy.
2. **RBAC scope injection is non-negotiable** — all new SQL queries follow the same `org = ANY(:scoped_orgs)` mandatory predicate pattern as existing queries.
3. **Additive over breaking** — no existing API contracts, rule schemas, or DB table structures may be modified in ways that break existing functionality.
4. **Each phase independently deployable** — phases ship as separate PRs and can be toggled at the feature-flag level.
5. **Security events always P0** — any signal that can blind the monitoring system itself (audit stream tampering, GHAS-disable) is prioritized above all else.

---

## 3. Phased Delivery Plan

### Phase Overview

| Phase | Name | Audience | Namespaces Covered | Duration |
|---|---|---|---|---|
| 1 | Security Foundational Layer | Security | `secret_scanning_alert`, `audit_log_streaming`, `repo.access` visibility, `ip_allow_list`, `org.disable_saml`, `org.member_to_admin` | Weeks 1–3 |
| 2 | Security Operations Depth | Security | `code_scanning`, `hook`, `oauth_application`, `integration`, `repository_vulnerability_alert`, `security_configuration`, GHAS-disable events | Weeks 4–7 |
| 3 | Engineering & Operations Layer | Eng Mgrs, Ops | `workflows`, `environment`, `copilot`, `codespaces`, `packages`, `protected_branch`, `repository_ruleset`, self-hosted runners | Weeks 8–11 |
| 4 | Advanced Threat Correlation | Security, all | Multi-event threat chains, behavioral enrichment, CI/CD secret harvest, webhook intelligence | Weeks 12–16 |

### Dependency Graph

```
Phase 1 ──────────────────────────────────────► Phase 2
    │                                               │
    │  (detection engine sequence rules from P1)    │
    └──────────────────────────────┬────────────────┘
                                   ▼
                               Phase 3
                                   │
                                   ▼
                               Phase 4
                        (consumes all prior signals)
```

Phase 3 can begin as soon as Phase 1 is complete; it does not require Phase 2. Phase 4 requires all prior phases.

---

## 4. Phase 1 — Security Foundational Layer

**Goal:** Surface the highest-severity, lowest-latency security signals first. Phase 1 covers events that can blind the monitoring system or represent immediate incident conditions.

### 4.1 Audit Log Streaming Integrity (P0)

**Threat:** An attacker with org-owner access can disable or redirect audit log streaming, removing OctoWatch's visibility entirely.

**Events:** `audit_log_streaming.create`, `audit_log_streaming.update`, `audit_log_streaming.destroy`, `audit_log_streaming.check`, `audit_log_streaming.enabled`, `audit_log_streaming.disabled`

#### 4.1.1 Detection Rules

**Rule: Audit Stream Destination Modified**
```yaml
name: Audit Log Stream Destination Changed
slug: audit-stream-destination-changed
category: defense_evasion
default_severity: critical
default_confidence: high
logic_type: pattern
logic_config:
  action_filters:
    - "audit_log_streaming.update"
    - "audit_log_streaming.create"
  field_conditions: []
  confidence: 0.90
  x_config:
    rationale: >
      Any change to the streaming destination should be treated as critical
      regardless of who made it. Legitimate changes should be rare, planned,
      and correlation-checked against a change request workflow.
```

**Rule: Audit Stream Disabled**
```yaml
name: Audit Log Streaming Disabled
slug: audit-stream-disabled
category: defense_evasion
default_severity: critical
default_confidence: high
logic_type: pattern
logic_config:
  action_filters:
    - "audit_log_streaming.disabled"
    - "audit_log_streaming.destroy"
  field_conditions: []
  confidence: 0.95
```

#### 4.1.2 Health Signal

Add `get_audit_stream_status()` to `health_signal_service.py`:

```sql
-- Returns the most recent streaming configuration event per org.
-- A NULL row or a 'disabled' event in the last 24h is a health warning.
SELECT
    org,
    action,
    actor,
    created_at,
    EXTRACT(HOURS FROM NOW() - created_at)::INT AS hours_ago
FROM events
WHERE action LIKE 'audit_log_streaming.%'
  AND org = ANY(:scoped_orgs)
  AND created_at >= NOW() - INTERVAL '7 days'
ORDER BY created_at DESC
LIMIT 1 PER GROUP -- group per org using DISTINCT ON (org)
```

Use `DISTINCT ON (org) ... ORDER BY org, created_at DESC` in practice.

#### 4.1.3 Ingestion Gap Detection

Add a background health check (new Celery beat task: `check_ingestion_gaps`) that fires every 60 minutes:
- For each configured org, checks if an event has been ingested in the last 90 minutes
- If not, emits a `SYSTEM` health warning into a new `system_health_events` table
- The frontend Dashboard picks this up and shows a "Data gap — no events ingested for X minutes" banner

**New table required:** `system_health_events` — see §11.1.

---

### 4.2 Security Feature Disable Detection (P0)

**Threat:** Disabling secret scanning, CodeQL, or GHAS on repos removes automated defenses.

**Events to monitor:**
- `secret_scanning.disable`, `secret_scanning_new_repos.disable`
- `repository_secret_scanning.disable`, `repository_secret_scanning_push_protection.disable`
- `repo.codeql_disabled`, `org.codeql_disabled`
- `repo.advanced_security_disabled`, `org.advanced_security_disabled_on_all_repos`
- `dependency_graph.disable`, `dependabot_alerts.disable_for_new_repos`

#### 4.2.1 Detection Rules

**Rule: Bulk Security Feature Disable**
```yaml
name: Multiple Security Features Disabled Within 1 Hour
slug: bulk-security-feature-disable
category: defense_evasion
default_severity: critical
default_confidence: high
logic_type: threshold
logic_config:
  action_filters:
    - "secret_scanning.disable"
    - "secret_scanning_new_repos.disable"
    - "repository_secret_scanning.disable"
    - "repo.codeql_disabled"
    - "org.codeql_disabled"
    - "repo.advanced_security_disabled"
    - "org.advanced_security_disabled_on_all_repos"
    - "dependabot_alerts.disable_for_new_repos"
    - "dependency_graph.disable"
  time_window_minutes: 60
  threshold: 3
  aggregation_key: actor
  confidence: 0.85
  x_config:
    rationale: >
      Three or more distinct security-feature disable events from the same
      actor within one hour is a strong indicator of deliberate coverage removal,
      either as pre-attack staging or insider threat.
```

**Rule: Single High-Value Disable (individual rules per namespace)**

Create individual `pattern` rules for each action in the list above at `high` severity. These provide signal when the bulk rule doesn't fire.

#### 4.2.2 Health Signal: Security Posture Coverage Map

Add `get_security_coverage()` to `health_signal_service.py`. This query derives the current security enablement state for each repo by replaying the most recent enable/disable event per feature per repo:

```sql
WITH feature_states AS (
    SELECT DISTINCT ON (org, repo, namespace)
        org, repo, namespace,
        action,
        created_at,
        actor,
        CASE
            WHEN action LIKE '%.disable%' OR action LIKE '%_disabled%' THEN 'disabled'
            ELSE 'enabled'
        END AS state
    FROM events
    WHERE org = ANY(:scoped_orgs)
      AND namespace IN (
          'secret_scanning', 'repository_secret_scanning',
          'dependency_graph', 'dependabot_alerts', 'dependabot_security_updates'
      )
      AND repo IS NOT NULL
      AND created_at >= NOW() - INTERVAL '90 days'
    ORDER BY org, repo, namespace, created_at DESC
),
repo_counts AS (
    SELECT
        org,
        COUNT(DISTINCT repo) AS total_repos,
        COUNT(DISTINCT repo) FILTER (
            WHERE namespace = 'secret_scanning' AND state = 'enabled'
        ) AS secret_scanning_enabled,
        COUNT(DISTINCT repo) FILTER (
            WHERE namespace = 'dependabot_alerts' AND state = 'enabled'
        ) AS dependabot_enabled
    FROM feature_states
    GROUP BY org
)
SELECT * FROM repo_counts;
```

**Note:** This is a best-effort approximation from stream events. True current state requires a GitHub API call. A future enhancement (Phase 2) can augment this with the REST API via the existing `github-enterprise-sync` integration.

---

### 4.3 Secret Scanning Alert Health (P1)

**Events:** `secret_scanning_alert.*`, `secret_scanning_push_protection.*`

#### 4.3.1 New Health Signals

Add `get_secret_scanning_alert_health()` to `health_signal_service.py`:

```sql
WITH alerts AS (
    SELECT
        org,
        data->>'number'                         AS alert_number,
        data->>'secret_type'                    AS secret_type,
        data->>'secret_type_display_name'       AS secret_type_display_name,
        (data->>'publicly_leaked')::BOOLEAN     AS publicly_leaked,
        (data->>'multi_repo')::BOOLEAN          AS multi_repo,
        action,
        actor,
        created_at
    FROM events
    WHERE namespace = 'secret_scanning_alert'
      AND org = ANY(:scoped_orgs)
      AND created_at >= NOW() - INTERVAL '90 days'
),
opens AS (
    SELECT org, alert_number, secret_type, publicly_leaked, created_at AS opened_at
    FROM alerts WHERE action = 'secret_scanning_alert.create'
),
resolves AS (
    SELECT org, alert_number, created_at AS resolved_at
    FROM alerts WHERE action = 'secret_scanning_alert.resolve'
),
mttr AS (
    SELECT
        o.org,
        AVG(EXTRACT(HOURS FROM r.resolved_at - o.opened_at)) AS avg_hours_to_resolve,
        COUNT(*) AS resolved_count
    FROM opens o
    JOIN resolves r USING (org, alert_number)
    GROUP BY o.org
),
unresolved AS (
    SELECT
        o.org,
        COUNT(*) AS unresolved_total,
        COUNT(*) FILTER (WHERE NOW() - o.opened_at > INTERVAL '7 days')  AS unresolved_gt_7d,
        COUNT(*) FILTER (WHERE NOW() - o.opened_at > INTERVAL '30 days') AS unresolved_gt_30d,
        COUNT(*) FILTER (WHERE o.publicly_leaked = TRUE)                  AS publicly_leaked_count
    FROM opens o
    LEFT JOIN resolves r USING (org, alert_number)
    WHERE r.alert_number IS NULL
    GROUP BY o.org
)
SELECT
    u.org,
    u.unresolved_total,
    u.unresolved_gt_7d,
    u.unresolved_gt_30d,
    u.publicly_leaked_count,
    m.avg_hours_to_resolve,
    m.resolved_count
FROM unresolved u
LEFT JOIN mttr m USING (org);
```

#### 4.3.2 Detection Rules

**Rule: Secret Leaked to Public Repository**
```yaml
name: Secret Scanning Alert — Public Leak
slug: secret-scanning-public-leak
category: data_exfiltration
default_severity: critical
default_confidence: high
logic_type: pattern
logic_config:
  action_filters:
    - "secret_scanning_alert.public_leak"
    - "secret_scanning_alert.create"
  field_conditions:
    - field: data.publicly_leaked
      operator: eq
      value: true
  confidence: 0.95
```

**Rule: Secret Scanning Alert Dismissal Spike**
```yaml
name: High Alert Dismissal Rate — Possible Alert Fatigue
slug: secret-scanning-dismissal-spike
category: posture_degradation
default_severity: high
default_confidence: medium
logic_type: threshold
logic_config:
  action_filters:
    - "secret_scanning_alert.resolve"
  time_window_minutes: 480   # 8-hour window
  threshold: 10
  aggregation_key: actor
  confidence: 0.70
  x_config:
    rationale: >
      Ten or more secret scanning alert resolutions from a single actor within
      8 hours suggests bulk dismissal. Combine with a review of the resolution
      field values (won_'t_fix, used_in_tests) to assess legitimacy.
```

**Rule: Push Protection Bypass — Repeated Offender**
(Already partially covered — extend existing bypass rule with the `request_reviewer` field context)

---

### 4.4 Repository Visibility Change Detection (P1)

**Events:** `repo.access`

#### 4.4.1 Detection Rule

```yaml
name: Private Repository Made Public
slug: repo-private-to-public
category: data_exfiltration
default_severity: critical
default_confidence: high
logic_type: pattern
logic_config:
  action_filters:
    - "repo.access"
  field_conditions:
    - field: data.visibility
      operator: eq
      value: public
    - field: data.previous_visibility
      operator: eq
      value: private
  confidence: 0.95
  x_config:
    note: >
      The 'previous_visibility' field is present in repo.access events. An
      'internal → public' change should also fire — add a second rule variant
      or extend field_conditions with an 'in' operator on previous_visibility.
```

**Rule: Internal Repository Made Public**
```yaml
name: Internal Repository Made Public
slug: repo-internal-to-public
category: data_exfiltration
default_severity: high
default_confidence: high
logic_type: pattern
logic_config:
  action_filters:
    - "repo.access"
  field_conditions:
    - field: data.visibility
      operator: eq
      value: public
    - field: data.previous_visibility
      operator: eq
      value: internal
  confidence: 0.90
```

#### 4.4.2 Health Signal: Repository Visibility Distribution

New query in `health_signal_service.py` — `get_repo_visibility_trends()`:

```sql
-- Tracks private→public and internal→public transitions over rolling 90 days
SELECT
    DATE_TRUNC('week', created_at)           AS week,
    org,
    data->>'previous_visibility'             AS from_visibility,
    data->>'visibility'                       AS to_visibility,
    COUNT(*)                                 AS change_count,
    ARRAY_AGG(repo ORDER BY created_at DESC) AS repos_changed
FROM events
WHERE action = 'repo.access'
  AND org = ANY(:scoped_orgs)
  AND data->>'visibility' = 'public'
  AND data->>'previous_visibility' IN ('private', 'internal')
  AND created_at >= NOW() - INTERVAL '90 days'
GROUP BY 1, 2, 3, 4
ORDER BY week DESC;
```

---

### 4.5 Privilege Escalation Detection (P1)

**Events:** `org.member_to_admin`, `organization_role.*`, `org.integration_manager_added`, `team.*` (membership changes)

#### 4.5.1 Detection Rules

**Rule: Member Promoted to Organization Owner**
```yaml
name: Member Promoted to Organization Owner
slug: org-member-to-admin
category: privilege_escalation
default_severity: high
default_confidence: high
logic_type: pattern
logic_config:
  action_filters:
    - "org.member_to_admin"
  field_conditions: []
  confidence: 0.90
  x_config:
    note: >
      Combine with GeoIP signals on the actor's concurrent login events to
      detect anomalous-location privilege grants.
```

**Rule: Integration Manager Role Granted**
```yaml
name: Integration Manager Role Granted
slug: org-integration-manager-granted
category: privilege_escalation
default_severity: high
default_confidence: high
logic_type: pattern
logic_config:
  action_filters:
    - "org.integration_manager_added"
  field_conditions: []
  confidence: 0.85
  x_config:
    rationale: >
      Integration manager role grants broad administrative access to all GitHub
      Apps in the organization. This should be rare and deliberate.
```

**Rule: Custom Org Role Created with Elevated Permissions**
```yaml
name: Custom Organization Role Created
slug: custom-org-role-created
category: privilege_escalation
default_severity: medium
default_confidence: medium
logic_type: pattern
logic_config:
  action_filters:
    - "organization_role.create"
    - "organization_role.update"
  field_conditions: []
  confidence: 0.65
  x_config:
    note: >
      The role_permissions JSONB field should be inspected to determine whether
      the role includes sensitive permissions. A future enhancement can parse
      this field and escalate severity automatically.
```

#### 4.5.2 Role Activity Health Signal

Add `get_privilege_change_summary()` to `health_signal_service.py`:

```sql
SELECT
    org,
    COUNT(*) FILTER (WHERE action = 'org.member_to_admin')            AS admin_promotions,
    COUNT(*) FILTER (WHERE action = 'org.integration_manager_added')  AS integration_mgr_grants,
    COUNT(*) FILTER (WHERE action LIKE 'organization_role.%')         AS custom_role_changes,
    MIN(created_at)                                                    AS earliest_event,
    MAX(created_at)                                                    AS latest_event
FROM events
WHERE action IN (
    'org.member_to_admin',
    'org.integration_manager_added',
    'organization_role.create',
    'organization_role.update',
    'organization_role.destroy'
)
  AND org = ANY(:scoped_orgs)
  AND created_at >= NOW() - INTERVAL '30 days'
GROUP BY org;
```

---

### 4.6 IP Allowlist Control Monitoring (P1)

**Events:** `ip_allow_list.disable`, `ip_allow_list.disable_for_installed_apps`, `ip_allow_list_entry.destroy`

#### 4.6.1 Detection Rules

**Rule: IP Allowlist Disabled**
```yaml
name: IP Allow List Disabled
slug: ip-allowlist-disabled
category: access_control
default_severity: high
default_confidence: high
logic_type: pattern
logic_config:
  action_filters:
    - "ip_allow_list.disable"
    - "ip_allow_list.disable_for_installed_apps"
  field_conditions: []
  confidence: 0.90
```

**Rule: IP Allowlist Entry Bulk Removal**
```yaml
name: Bulk IP Allowlist Entry Removal
slug: ip-allowlist-bulk-removal
category: access_control
default_severity: high
default_confidence: medium
logic_type: threshold
logic_config:
  action_filters:
    - "ip_allow_list_entry.destroy"
  time_window_minutes: 30
  threshold: 5
  aggregation_key: actor
  confidence: 0.80
```

---

### 4.7 SAML/SSO Monitoring (P1)

**Events:** `org.disable_saml`, `org.enable_saml`, `org.sso_response`

#### 4.7.1 Detection Rules

**Rule: SAML SSO Disabled**
```yaml
name: SAML Single Sign-On Disabled
slug: saml-sso-disabled
category: access_control
default_severity: critical
default_confidence: high
logic_type: pattern
logic_config:
  action_filters:
    - "org.disable_saml"
  field_conditions: []
  confidence: 0.95
  x_config:
    rationale: >
      Disabling SAML SSO removes the requirement for federated identity and
      allows members to authenticate with only a GitHub password, bypassing
      enterprise MFA and identity governance policies.
```

#### 4.7.2 Health Signal

Add `get_sso_health()` to `health_signal_service.py` — returns the most recent SSO enable/disable state per org and last SSO response event timestamp.

---

### Phase 1 Backend Work Summary

| Work Item | File(s) | Effort |
|---|---|---|
| 14 new detection rules (Alembic migration) | `alembic/versions/0004_phase1_security_rules.py` | M |
| 6 new health signal SQL functions | `app/services/health_signal_service.py` | M |
| `system_health_events` table + migration | `app/models/`, `alembic/versions/0005_system_health_events.py` | S |
| `check_ingestion_gaps` Celery beat task | `app/workers/ingest_worker.py` | S |
| New `/health/security-posture` endpoint | `app/routers/health.py` | S |
| New `/health/secret-scanning` endpoint | `app/routers/health.py` | S |
| Tests | `tests/test_health_signal_service.py`, `tests/test_detection_service.py` | M |

---

## 5. Phase 2 — Security Operations Depth

**Goal:** Deliver full-spectrum security coverage for code scanning, supply chain, OAuth/app governance, and vulnerability management.

### 5.1 Code Scanning Alert Management

**Events:** `code_scanning.alert_closed_by_user`, `code_scanning.alert_reappeared`, `code_scanning.alert_closure_requested`, `code_scanning.alert_closure_denied`

#### 5.1.1 Detection Rules

**Rule: Code Scanning Alert Bulk Dismissal**
```yaml
name: Code Scanning Alert Bulk Dismissal
slug: code-scanning-bulk-dismissal
category: posture_degradation
default_severity: high
default_confidence: medium
logic_type: threshold
logic_config:
  action_filters:
    - "code_scanning.alert_closed_by_user"
  time_window_minutes: 120
  threshold: 5
  aggregation_key: actor
  confidence: 0.75
```

**Rule: Code Scanning Alert Reappeared After Fix**
```yaml
name: Previously Fixed Code Scanning Alert Reappeared
slug: code-scanning-alert-reappeared
category: posture_degradation
default_severity: medium
default_confidence: medium
logic_type: pattern
logic_config:
  action_filters:
    - "code_scanning.alert_reappeared"
  field_conditions: []
  confidence: 0.60
  x_config:
    rationale: >
      Alert reappearance after a fix indicates a regression. Frequent reappearance
      on the same repo suggests incomplete remediation or architectural debt.
```

#### 5.1.2 Health Signal: Code Scanning Coverage & MTTR

New `get_code_scanning_health()` function:

```sql
WITH created AS (
    SELECT org, repo, data->>'alert_number' AS alert_num, created_at AS opened_at
    FROM events
    WHERE action = 'code_scanning.alert_created'
      AND org = ANY(:scoped_orgs)
      AND created_at >= NOW() - INTERVAL '90 days'
),
closed AS (
    SELECT org, repo, data->>'alert_number' AS alert_num, created_at AS closed_at
    FROM events
    WHERE action = 'code_scanning.alert_closed_by_user'
      AND org = ANY(:scoped_orgs)
      AND created_at >= NOW() - INTERVAL '90 days'
),
dismissed AS (
    SELECT org, repo, COUNT(*) AS dismissed_count
    FROM events
    WHERE action = 'code_scanning.alert_closed_by_user'
      AND org = ANY(:scoped_orgs)
      AND created_at >= NOW() - INTERVAL '30 days'
    GROUP BY org, repo
),
reappeared AS (
    SELECT org, repo, COUNT(*) AS reappear_count
    FROM events
    WHERE action = 'code_scanning.alert_reappeared'
      AND org = ANY(:scoped_orgs)
      AND created_at >= NOW() - INTERVAL '30 days'
    GROUP BY org, repo
)
SELECT
    c.org,
    c.repo,
    COUNT(*) AS total_alerts_30d,
    AVG(EXTRACT(HOURS FROM cl.closed_at - c.opened_at)) AS avg_hours_to_close,
    COALESCE(d.dismissed_count, 0)                      AS dismissed_30d,
    COALESCE(r.reappear_count, 0)                       AS reappeared_30d
FROM created c
LEFT JOIN closed cl USING (org, repo, alert_num)
LEFT JOIN dismissed d USING (org, repo)
LEFT JOIN reappeared r USING (org, repo)
GROUP BY c.org, c.repo, d.dismissed_count, r.reappear_count
ORDER BY total_alerts_30d DESC
LIMIT :limit;
```

---

### 5.2 Webhook Threat Surface

**Events:** `hook.create`, `hook.destroy`, `hook.events_changed`

#### 5.2.1 Detection Rules

**Rule: Webhook Created to External Domain**
```yaml
name: Webhook Created to External Domain
slug: webhook-external-domain
category: data_exfiltration
default_severity: high
default_confidence: medium
logic_type: pattern
logic_config:
  action_filters:
    - "hook.create"
  field_conditions:
    - field: data.hook_url
      operator: not_contains
      value: github.com
  confidence: 0.70
  x_config:
    note: >
      This rule is intentionally broad. Operators should suppress known-good
      webhook destinations (e.g., their SIEM URL, Slack webhook URL) using
      the suppression system. The 'not_contains github.com' condition catches
      most external destinations; a domain allowlist in x_config is the
      preferred long-term approach once the detection engine supports it.
    suppression_guidance: >
      Create repo-scoped suppressions for known webhook destinations. A future
      enhancement will add an 'approved_webhook_domains' list to org config.
```

**Rule: Bulk Webhook Creation**
```yaml
name: Bulk Webhook Creation by Single Actor
slug: webhook-bulk-creation
category: data_exfiltration
default_severity: high
default_confidence: high
logic_type: threshold
logic_config:
  action_filters:
    - "hook.create"
  time_window_minutes: 60
  threshold: 5
  aggregation_key: actor
  confidence: 0.85
```

**Rule: Webhook All-Events Subscription**
```yaml
name: Webhook Subscribed to All Repository Events
slug: webhook-all-events
category: data_exfiltration
default_severity: medium
default_confidence: medium
logic_type: pattern
logic_config:
  action_filters:
    - "hook.create"
    - "hook.events_changed"
  field_conditions:
    - field: data.events
      operator: contains
      value: "*"
  confidence: 0.65
```

---

### 5.3 OAuth App & GitHub App Governance

**Events:** `oauth_application.*`, `org.oauth_app_access_approved`, `org.disable_oauth_app_restrictions`, `integration.*`, `integration_installation.*`

#### 5.3.1 Detection Rules

**Rule: OAuth App Restrictions Disabled**
```yaml
name: OAuth App Access Restrictions Disabled
slug: oauth-app-restrictions-disabled
category: access_control
default_severity: high
default_confidence: high
logic_type: pattern
logic_config:
  action_filters:
    - "org.disable_oauth_app_restrictions"
  field_conditions: []
  confidence: 0.90
```

**Rule: GitHub App All-Token Revocation**
```yaml
name: GitHub App All Tokens Revoked
slug: github-app-all-tokens-revoked
category: incident_response
default_severity: high
default_confidence: high
logic_type: pattern
logic_config:
  action_filters:
    - "integration.revoke_all_tokens"
  field_conditions: []
  confidence: 0.90
  x_config:
    rationale: >
      Revoking all tokens for a GitHub App is typically done in response to a
      security incident (compromised app credentials). This is both a detection
      signal (something bad happened) and a positive response indicator.
```

**Rule: New OAuth App Approved from Unusual Location**
```yaml
name: OAuth App Approved from Unusual Country
slug: oauth-app-approved-unusual-location
category: access_control
default_severity: medium
default_confidence: medium
logic_type: sequence
logic_config:
  action_filters:
    - "org.oauth_app_access_approved"
  field_conditions:
    - field: geo_country_code
      operator: not_in
      value: []   # Populated per-org via config; empty list disables geographic filter
  confidence: 0.60
  x_config:
    note: >
      The country whitelist in field_conditions.value is empty by default,
      which disables the geographic filter. Operators must populate this list
      with their expected countries for this rule to be meaningful.
```

#### 5.3.2 Health Signal: App & OAuth Inventory

Add `get_app_governance_summary()` to `health_signal_service.py`:

```sql
SELECT
    org,
    COUNT(*) FILTER (WHERE action = 'integration_installation.create') AS apps_installed_90d,
    COUNT(*) FILTER (WHERE action = 'integration_installation.delete') AS apps_removed_90d,
    COUNT(*) FILTER (WHERE action = 'org.oauth_app_access_approved')   AS oauth_apps_approved_90d,
    COUNT(*) FILTER (WHERE action = 'org.oauth_app_access_denied')     AS oauth_apps_denied_90d,
    COUNT(*) FILTER (WHERE action = 'integration.revoke_all_tokens')   AS token_revocations_90d
FROM events
WHERE action IN (
    'integration_installation.create',
    'integration_installation.delete',
    'org.oauth_app_access_approved',
    'org.oauth_app_access_denied',
    'integration.revoke_all_tokens'
)
  AND org = ANY(:scoped_orgs)
  AND created_at >= NOW() - INTERVAL '90 days'
GROUP BY org;
```

---

### 5.4 Dependabot Vulnerability Tracking

**Events:** `repository_vulnerability_alert.*`, `dependabot_alerts.*`

#### 5.4.1 Detection Rules

**Rule: Dependabot Alerts Disabled on Repo with Open Criticals**

This requires a two-pass evaluation (check if there are open alerts before triggering), which exceeds current engine capabilities. **Implement as a health signal query only in Phase 2; defer correlated detection rule to Phase 4.**

#### 5.4.2 Health Signal: Vulnerability Aging

Add `get_vulnerability_aging()` to `health_signal_service.py`:

```sql
WITH created_alerts AS (
    SELECT
        org,
        repo,
        data->>'alert_number'         AS alert_number,
        data->>'severity'             AS severity,
        data->>'package_name'         AS package_name,
        data->>'affected_range'       AS affected_range,
        created_at                    AS alert_created_at
    FROM events
    WHERE action = 'repository_vulnerability_alert.create'
      AND org = ANY(:scoped_orgs)
      AND created_at >= NOW() - INTERVAL '180 days'
),
dismissed_alerts AS (
    SELECT org, repo, data->>'alert_number' AS alert_number
    FROM events
    WHERE action IN (
        'repository_vulnerability_alert.dismiss',
        'repository_vulnerability_alert.resolve'
    )
      AND org = ANY(:scoped_orgs)
      AND created_at >= NOW() - INTERVAL '180 days'
)
SELECT
    c.org,
    COUNT(*) FILTER (WHERE d.alert_number IS NULL)                                          AS total_open,
    COUNT(*) FILTER (WHERE d.alert_number IS NULL AND c.severity = 'critical')              AS open_critical,
    COUNT(*) FILTER (WHERE d.alert_number IS NULL AND c.severity = 'high')                 AS open_high,
    COUNT(*) FILTER (WHERE d.alert_number IS NULL
                       AND NOW() - c.alert_created_at > INTERVAL '30 days')                AS open_gt_30d,
    COUNT(*) FILTER (WHERE d.alert_number IS NULL
                       AND c.severity = 'critical'
                       AND NOW() - c.alert_created_at > INTERVAL '14 days')                AS critical_open_gt_14d,
    AVG(EXTRACT(DAYS FROM NOW() - c.alert_created_at))
        FILTER (WHERE d.alert_number IS NULL)                                               AS avg_open_days
FROM created_alerts c
LEFT JOIN dismissed_alerts d USING (org, repo, alert_number)
GROUP BY c.org;
```

---

### 5.5 Source Code Exfiltration Detection

**Events:** `repo.download_zip`, `git.clone`, `git.fetch`

#### 5.5.1 Detection Rules

**Rule: Bulk Repository ZIP Downloads**
```yaml
name: Bulk Repository Archive Downloads
slug: bulk-repo-zip-download
category: data_exfiltration
default_severity: high
default_confidence: high
logic_type: threshold
logic_config:
  action_filters:
    - "repo.download_zip"
  time_window_minutes: 60
  threshold: 5
  aggregation_key: actor
  distinct_count_field: repo
  confidence: 0.85
```

**Rule: Private Repo Forked + Immediately Downloaded**
```yaml
name: Private Repository Forked Then Archived
slug: private-repo-fork-then-zip
category: data_exfiltration
default_severity: high
default_confidence: medium
logic_type: sequence
logic_config:
  action_filters:
    - "repo.fork"
    - "repo.download_zip"
  sequence_window_minutes: 30
  aggregation_key: actor
  field_conditions:
    - field: data.visibility
      operator: in
      value: ["private", "internal"]
  confidence: 0.80
```

---

### Phase 2 Backend Work Summary

| Work Item | File(s) | Effort |
|---|---|---|
| 12 new detection rules (Alembic migration) | `alembic/versions/0006_phase2_security_rules.py` | M |
| 4 new health signal SQL functions | `app/services/health_signal_service.py` | M |
| `/health/code-scanning` endpoint | `app/routers/health.py` | S |
| `/health/vulnerabilities` endpoint | `app/routers/health.py` | S |
| `/health/app-governance` endpoint | `app/routers/health.py` | S |
| Tests | `tests/` | L |

---

## 6. Phase 3 — Engineering & Operations Layer

**Goal:** Surface engineering velocity, CI/CD health, Copilot governance, Codespace cost signals, and deployment security for engineering managers and operations teams.

### 6.1 GitHub Actions Workflow Health

**Events:** `workflows.completed_workflow_run`, `workflows.disable_workflow`, `workflows.prepared_workflow_job`

#### 6.1.1 Health Signals

Add `get_workflow_health()` to `health_signal_service.py`:

```sql
WITH run_outcomes AS (
    SELECT
        org,
        repo,
        data->>'name'           AS workflow_name,
        data->>'workflow_id'    AS workflow_id,
        data->>'conclusion'     AS conclusion,
        data->>'head_branch'    AS head_branch,
        created_at
    FROM events
    WHERE action = 'workflows.completed_workflow_run'
      AND org = ANY(:scoped_orgs)
      AND created_at >= NOW() - INTERVAL '30 days'
)
SELECT
    org,
    repo,
    workflow_name,
    COUNT(*)                                                            AS total_runs,
    COUNT(*) FILTER (WHERE conclusion = 'success')                     AS successes,
    COUNT(*) FILTER (WHERE conclusion = 'failure')                     AS failures,
    COUNT(*) FILTER (WHERE conclusion = 'cancelled')                   AS cancelled,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE conclusion = 'failure')
        / NULLIF(COUNT(*), 0), 2
    )                                                                   AS failure_rate_pct,
    MAX(created_at)                                                     AS last_run_at
FROM run_outcomes
GROUP BY org, repo, workflow_name
HAVING COUNT(*) >= 5  -- Only report on workflows with statistically meaningful runs
ORDER BY failure_rate_pct DESC
LIMIT :limit;
```

Also add `get_workflow_secret_usage()` — aggregate `secrets_passed` counts from `workflows.prepared_workflow_job`:

```sql
SELECT
    org,
    repo,
    data->>'job_name'                       AS job_name,
    data->>'workflow_run_id'                AS workflow_run_id,
    jsonb_array_length(
        COALESCE((data->'secrets_passed')::JSONB, '[]'::JSONB)
    )                                       AS secrets_count,
    created_at
FROM events
WHERE action = 'workflows.prepared_workflow_job'
  AND org = ANY(:scoped_orgs)
  AND created_at >= NOW() - INTERVAL '7 days'
  AND jsonb_array_length(
      COALESCE((data->'secrets_passed')::JSONB, '[]'::JSONB)
  ) > :threshold
ORDER BY secrets_count DESC
LIMIT :limit;
```

#### 6.1.2 Detection Rule: CI/CD Secret Harvest

```yaml
name: Workflow Job Accessing Excessive Secrets
slug: workflow-excessive-secrets
category: data_exfiltration
default_severity: high
default_confidence: medium
logic_type: pattern
logic_config:
  action_filters:
    - "workflows.prepared_workflow_job"
  field_conditions:
    - field: data.secrets_passed_count
      operator: gte
      value: 10
  confidence: 0.65
  x_config:
    normalization_required: true
    note: >
      The ingest worker must normalize secrets_passed from an array to a count
      field 'secrets_passed_count' before this rule can evaluate it. Add to
      AbstractIngestWorker._normalize_event() for the workflows namespace.
```

**Required ingest normalization** — add to `ingest_worker.py`:
```python
# In _normalize_event(), for action = 'workflows.prepared_workflow_job':
if action == "workflows.prepared_workflow_job":
    secrets = data.get("secrets_passed", [])
    data["secrets_passed_count"] = len(secrets) if isinstance(secrets, list) else 0
    # Do NOT store the secret names themselves in the normalized payload
    data.pop("secrets_passed", None)
```

---

### 6.2 Branch Protection & Merge Governance

**Events:** `protected_branch.*`, `repository_ruleset.*`, `required_status_check.*`

#### 6.2.1 Detection Rules

**Rule: Branch Protection Weakened**
```yaml
name: Branch Protection Rule Weakened
slug: branch-protection-weakened
category: posture_degradation
default_severity: high
default_confidence: medium
logic_type: pattern
logic_config:
  action_filters:
    - "protected_branch.update_admin_enforced"
    - "protected_branch.update_pull_request_reviews_enforcement_level"
    - "protected_branch.policy_override"
  field_conditions: []
  confidence: 0.75
  x_config:
    note: >
      The specific weakening direction can be inferred from field deltas in the
      event payload, but requires per-field evaluation not currently supported
      in the rule DSL. A future 'delta_condition' operator can refine this.
      For now, all changes to these actions fire the rule and rely on analyst
      triage.
```

**Rule: Required Status Check Removed**
```yaml
name: Required Status Check Removed from Protected Branch
slug: required-status-check-removed
category: posture_degradation
default_severity: medium
default_confidence: high
logic_type: pattern
logic_config:
  action_filters:
    - "required_status_check.destroy"
  field_conditions: []
  confidence: 0.80
```

#### 6.2.2 Health Signal: Branch Protection Coverage

Add `get_branch_protection_health()`:

```sql
WITH protection_changes AS (
    SELECT
        org, repo, action, actor, created_at,
        CASE
            WHEN action LIKE '%policy_override%' THEN 'override'
            WHEN action LIKE '%update%' OR action LIKE '%create%' THEN 'modified'
            WHEN action IN ('protected_branch.destroy', 'required_status_check.destroy') THEN 'removed'
            ELSE 'other'
        END AS change_type
    FROM events
    WHERE namespace IN ('protected_branch', 'required_status_check', 'repository_ruleset')
      AND org = ANY(:scoped_orgs)
      AND created_at >= NOW() - INTERVAL '30 days'
)
SELECT
    org,
    COUNT(*) FILTER (WHERE change_type = 'removed')   AS protections_removed_30d,
    COUNT(*) FILTER (WHERE change_type = 'override')  AS policy_overrides_30d,
    COUNT(*) FILTER (WHERE change_type = 'modified')  AS protections_modified_30d,
    COUNT(DISTINCT actor)                              AS distinct_actors,
    COUNT(DISTINCT repo)                               AS distinct_repos_affected
FROM protection_changes
GROUP BY org;
```

---

### 6.3 Deployment Environment Security

**Events:** `environment.*`

#### 6.3.1 Detection Rules

**Rule: Production Environment Self-Review Enabled**
```yaml
name: Deployment Self-Review Enabled on Environment
slug: environment-self-review-enabled
category: posture_degradation
default_severity: high
default_confidence: medium
logic_type: pattern
logic_config:
  action_filters:
    - "environment.update_protection_rule"
  field_conditions:
    - field: data.prevent_self_review
      operator: eq
      value: false
  confidence: 0.70
  x_config:
    note: >
      Enabling self-review on deployment environments allows an actor to both
      open and approve a deployment to production without a second-person check.
      This is a critical control weakening for any environment mapped to
      production infrastructure.
```

**Rule: Deployment Approver List Emptied**
```yaml
name: Deployment Environment Approvers Removed
slug: environment-approvers-removed
category: posture_degradation
default_severity: high
default_confidence: high
logic_type: pattern
logic_config:
  action_filters:
    - "environment.update_protection_rule"
  field_conditions:
    - field: data.approvers
      operator: eq
      value: []
  confidence: 0.85
```

---

### 6.4 Copilot Governance

**Events:** `copilot.cfb_seat_management_changed`, `copilot.content_exclusion_changed`, `copilot.swe_agent_repo_enabled`, `copilot.custom_instructions_updated`, `copilot.cfb_seat_added`, `copilot.cfb_seat_cancelled`

#### 6.4.1 Detection Rules

**Rule: Copilot Seat Management Opened to All Members**
```yaml
name: Copilot Access Opened to All Organization Members
slug: copilot-seats-opened-to-all
category: posture_change
default_severity: medium
default_confidence: high
logic_type: pattern
logic_config:
  action_filters:
    - "copilot.cfb_seat_management_changed"
  field_conditions:
    - field: data.new_value
      operator: eq
      value: all_members
  confidence: 0.80
  x_config:
    rationale: >
      Changing from 'selected_members' to 'all_members' dramatically expands
      Copilot's data access surface. This may be an intentional policy decision
      or an unintended scope expansion.
```

**Rule: Copilot Coding Agent Enabled on Repository**
```yaml
name: Copilot Coding Agent Enabled on Repository
slug: copilot-swe-agent-repo-enabled
category: posture_change
default_severity: medium
default_confidence: high
logic_type: pattern
logic_config:
  action_filters:
    - "copilot.swe_agent_repo_enabled"
  field_conditions: []
  confidence: 0.75
  x_config:
    rationale: >
      Enabling the Copilot coding agent grants GitHub Copilot the ability to
      open PRs, push commits, and modify code in the repository autonomously.
      This should be tracked and reviewed for sensitive repositories.
```

**Rule: Copilot Custom Instructions Modified**
```yaml
name: Copilot Custom Instructions Updated
slug: copilot-custom-instructions-changed
category: posture_change
default_severity: low
default_confidence: high
logic_type: pattern
logic_config:
  action_filters:
    - "copilot.custom_instructions_created"
    - "copilot.custom_instructions_updated"
  field_conditions: []
  confidence: 0.70
```

#### 6.4.2 Health Signal: Copilot Seat Utilization

Add `get_copilot_seat_health()`:

```sql
WITH seat_events AS (
    SELECT
        org,
        action,
        actor,
        data->>'user' AS target_user,
        created_at
    FROM events
    WHERE namespace = 'copilot'
      AND action IN (
          'copilot.cfb_seat_added',
          'copilot.cfb_seat_cancelled',
          'copilot.cfb_seat_assignment_created',
          'copilot.cfb_seat_assignment_unassigned'
      )
      AND org = ANY(:scoped_orgs)
      AND created_at >= NOW() - INTERVAL '90 days'
)
SELECT
    org,
    COUNT(*) FILTER (WHERE action LIKE '%seat_added%'
                        OR action LIKE '%seat_assignment_created%')   AS seats_granted_90d,
    COUNT(*) FILTER (WHERE action LIKE '%cancelled%'
                        OR action LIKE '%unassigned%')                AS seats_removed_90d,
    COUNT(DISTINCT target_user) FILTER (
        WHERE action LIKE '%seat_added%'
    )                                                                  AS unique_users_granted,
    MAX(created_at) FILTER (
        WHERE action = 'copilot.cfb_seat_management_changed'
    )                                                                  AS last_policy_change_at
FROM seat_events
GROUP BY org;
```

---

### 6.5 Codespace Sprawl & Cost Monitoring

**Events:** `codespaces.create`, `codespaces.destroy`, `codespaces.suspend_environment`, `codespaces.export_environment`

#### 6.5.1 Detection Rule

**Rule: Codespace Exported from Sensitive Repository**
```yaml
name: Codespace Environment Exported to Branch
slug: codespace-export-from-repo
category: data_exfiltration
default_severity: medium
default_confidence: medium
logic_type: pattern
logic_config:
  action_filters:
    - "codespaces.export_environment"
  field_conditions: []
  confidence: 0.60
  x_config:
    note: >
      codespaces.export_environment pushes the entire codespace state as a
      branch commit. For repositories containing sensitive configuration or
      credentials, this can act as an exfiltration path. Severity should be
      elevated to 'high' for repos tagged as sensitive via custom_properties.
```

#### 6.5.2 Health Signal: Codespace Cost Signal

Add `get_codespace_cost_signals()`:

```sql
WITH codespace_lifecycle AS (
    SELECT DISTINCT ON (org, data->>'name', actor)
        org,
        repo,
        actor,
        data->>'name'         AS codespace_name,
        data->>'machine_type' AS machine_type,
        action,
        created_at
    FROM events
    WHERE namespace = 'codespaces'
      AND org = ANY(:scoped_orgs)
      AND created_at >= NOW() - INTERVAL '30 days'
    ORDER BY org, data->>'name', actor, created_at DESC
),
created AS (
    SELECT org, repo, actor, codespace_name, machine_type, created_at AS created_at
    FROM codespace_lifecycle WHERE action = 'codespaces.create'
),
suspended AS (
    SELECT org, codespace_name, created_at AS suspended_at
    FROM codespace_lifecycle WHERE action = 'codespaces.suspend_environment'
),
destroyed AS (
    SELECT org, codespace_name
    FROM codespace_lifecycle WHERE action = 'codespaces.destroy'
)
SELECT
    c.org,
    COUNT(*) FILTER (WHERE d.codespace_name IS NULL
                       AND s.codespace_name IS NULL)             AS active_never_suspended,
    COUNT(*) FILTER (WHERE c.machine_type IN ('largePremium', 'xLargePremium',
                                               '16core', '32core'))
                                                                  AS large_machine_count,
    COUNT(DISTINCT c.actor)                                       AS unique_users_with_codespaces,
    MAX(c.created_at)                                             AS most_recent_create
FROM created c
LEFT JOIN destroyed d USING (org, codespace_name)
LEFT JOIN suspended s USING (org, codespace_name)
GROUP BY c.org;
```

---

### 6.6 Self-Hosted Runner Fleet Health

**Events:** `org.self_hosted_runner_updated`, `repo.add_self_hosted_runner`, `org.add_self_hosted_runner`

#### 6.6.1 Health Signal

Add `get_runner_fleet_health()`:

```sql
SELECT
    org,
    repo,
    data->>'runner_id'           AS runner_id,
    data->>'runner_name'         AS runner_name,
    data->>'source_version'      AS source_version,
    data->>'target_version'      AS target_version,
    data->>'runner_group_name'   AS runner_group,
    action,
    created_at
FROM events
WHERE action IN (
    'org.self_hosted_runner_updated',
    'repo.self_hosted_runner_updated',
    'org.add_self_hosted_runner',
    'repo.add_self_hosted_runner'
)
  AND org = ANY(:scoped_orgs)
  AND created_at >= NOW() - INTERVAL '7 days'
ORDER BY created_at DESC
LIMIT :limit;
```

---

### Phase 3 Backend Work Summary

| Work Item | File(s) | Effort |
|---|---|---|
| 10 new detection rules (Alembic migration) | `alembic/versions/0007_phase3_ops_rules.py` | M |
| 6 new health signal SQL functions | `app/services/health_signal_service.py` | L |
| Ingest worker normalization for `secrets_passed` | `app/workers/ingest_worker.py` | S |
| 4 new API endpoints | `app/routers/health.py`, `app/routers/velocity.py` | M |
| Frontend: Copilot tab on Org Health page | `frontend/src/pages/OrgHealth.tsx` | M |
| Frontend: Workflow health table on Velocity page | `frontend/src/pages/Velocity.tsx` | S |
| Frontend: Codespace cost card on Org Health page | `frontend/src/pages/OrgHealth.tsx` | S |
| Tests | `tests/` | L |

---

## 7. Phase 4 — Advanced Threat Correlation

**Goal:** Implement multi-event correlation rules (threat chains), behavioral enrichment for new namespaces, and supply chain threat detection that spans the CI/CD pipeline.

### 7.1 Multi-Event Threat Chain Detection

Phase 4 requires extending the detection engine's `sequence` logic type to support cross-namespace event chains. The current sequence engine matches events within a single namespace.

#### 7.1.1 Engine Enhancement: Cross-Namespace Sequences

Add `cross_namespace_sequence` logic type to `detection_service.py`:

```python
async def evaluate_cross_namespace_sequence(
    session: AsyncSession,
    rule: RuleDefinition,
    events: list[AuditEvent],
    scoped_orgs: list[str],
) -> list[dict[str, Any]]:
    """
    Evaluates a sequence of steps matching different action filters
    with a shared aggregation key (typically actor) within a time window.
    
    Each step in 'steps' has:
      - action_filters: list[str]
      - field_conditions: list[dict]
      - min_count: int (default 1)
    
    All steps must match at least min_count events within time_window_minutes
    for the same aggregation_key_value.
    """
```

Config schema for this new type:
```yaml
logic_type: cross_namespace_sequence
logic_config:
  aggregation_key: actor
  time_window_minutes: 120
  require_distinct_steps: true   # each step must match a different event
  steps:
    - step: 1
      action_filters: ["secret_scanning.disable"]
      field_conditions: []
    - step: 2
      action_filters: ["org.disable_saml"]
      field_conditions: []
    - step: 3
      action_filters: ["ip_allow_list.disable"]
      field_conditions: []
```

#### 7.1.2 Supply Chain Threat Chain

```yaml
name: Supply Chain Staging — New Repo + Secret + Workflow
slug: supply-chain-staging-sequence
category: supply_chain
default_severity: critical
default_confidence: medium
logic_type: cross_namespace_sequence
logic_config:
  aggregation_key: actor
  time_window_minutes: 30
  require_distinct_steps: true
  steps:
    - step: 1
      action_filters: ["repo.create"]
      field_conditions: []
    - step: 2
      action_filters:
        - "repo.create_actions_secret"
        - "org.create_actions_secret"
      field_conditions: []
    - step: 3
      action_filters: ["workflows.created_workflow_run"]
      field_conditions: []
  confidence: 0.75
  x_config:
    rationale: >
      An actor who creates a new repository, immediately adds a secret, and
      then triggers a workflow run within 30 minutes may be staging a supply
      chain attack — particularly if the new repo has no prior commit history
      and the workflow calls external actions.
```

#### 7.1.3 Security Control Erasure Chain

```yaml
name: Security Control Erasure — Multiple Controls Removed
slug: security-control-erasure
category: defense_evasion
default_severity: critical
default_confidence: high
logic_type: cross_namespace_sequence
logic_config:
  aggregation_key: actor
  time_window_minutes: 1440  # 24 hours
  require_distinct_steps: true
  steps:
    - step: 1
      action_filters:
        - "secret_scanning.disable"
        - "repo.codeql_disabled"
        - "org.advanced_security_disabled_on_all_repos"
      field_conditions: []
    - step: 2
      action_filters:
        - "org.disable_saml"
        - "ip_allow_list.disable"
        - "org.disable_oauth_app_restrictions"
      field_conditions: []
  confidence: 0.90
```

#### 7.1.4 Privilege Pivot After Admin Grant

```yaml
name: OAuth App Approved Immediately After Privilege Escalation
slug: privilege-pivot-oauth-approval
category: privilege_escalation
default_severity: critical
default_confidence: high
logic_type: cross_namespace_sequence
logic_config:
  aggregation_key: actor
  time_window_minutes: 60
  require_distinct_steps: true
  steps:
    - step: 1
      action_filters:
        - "org.member_to_admin"
        - "org.integration_manager_added"
      field_conditions: []
    - step: 2
      action_filters:
        - "org.oauth_app_access_approved"
        - "integration_installation.create"
      field_conditions: []
  confidence: 0.85
```

#### 7.1.5 Insider Bulk Exfiltration

```yaml
name: Insider Bulk Repository Exfiltration
slug: insider-bulk-exfil
category: data_exfiltration
default_severity: critical
default_confidence: high
logic_type: cross_namespace_sequence
logic_config:
  aggregation_key: actor
  time_window_minutes: 120
  require_distinct_steps: false
  steps:
    - step: 1
      action_filters: ["repo.download_zip", "git.clone"]
      min_count: 3
      field_conditions: []
    - step: 2
      action_filters: ["git.fetch"]
      min_count: 5
      field_conditions: []
  confidence: 0.80
```

---

### 7.2 Behavioral Baseline Expansion

The existing behavioral baseline engine computes per-actor hourly/daily activity norms. In Phase 4, extend `BehavioralBaseline` to track:

- `push_protection_bypass_frequency` — normal bypass rate per actor
- `secret_scanning_alert_dismissal_rate` — normal dismissal rate per actor
- `workflow_failure_rate` — per-actor workflow failure rate
- `admin_action_frequency` — baseline rate of privileged admin events per actor

New column additions to `behavioral_baselines` table:

```sql
ALTER TABLE behavioral_baselines
    ADD COLUMN IF NOT EXISTS push_bypass_hourly_mean   DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS push_bypass_hourly_stddev DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS alert_dismiss_daily_mean  DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS alert_dismiss_daily_stddev DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS admin_action_daily_mean   DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS admin_action_daily_stddev DOUBLE PRECISION;
```

---

### 7.3 Webhook Threat Intelligence Integration

**New capability:** In Phase 4, extend the `hook.create` detection to consult a local threat intelligence list of known-malicious webhook domains.

- New table: `threat_intel_domains` — stores domain patterns with source and confidence
- New service: `app/services/threat_intel_service.py` — loads and queries the list
- Detection engine hook: After a webhook creation event matches `webhook-external-domain`, call `threat_intel_service.check_domain()` and escalate severity if a match is found

```python
# threat_intel_service.py
async def is_malicious_domain(session: AsyncSession, url: str) -> tuple[bool, str | None]:
    """Check if a URL's domain matches any known-malicious entry."""
    from urllib.parse import urlparse
    domain = urlparse(url).hostname
    if not domain:
        return False, None
    stmt = select(ThreatIntelDomain).where(
        ThreatIntelDomain.active.is_(True)
    )
    # ... fnmatch-based comparison
```

---

### Phase 4 Backend Work Summary

| Work Item | File(s) | Effort |
|---|---|---|
| `cross_namespace_sequence` engine logic type | `app/services/detection_service.py` | L |
| 5 new threat chain detection rules | `alembic/versions/0008_phase4_chain_rules.py` | M |
| Behavioral baseline column additions | `alembic/versions/0009_baseline_expansion.py` | S |
| New `threat_intel_domains` table + service | `app/models/`, `app/services/threat_intel_service.py` | M |
| Tests | `tests/` | L |

---

## 8. Backend API Changes

### 8.1 New Endpoints

All new endpoints follow existing conventions (RBAC scope injection, pagination, rate limiting, audit trail).

#### Health Router Extensions (`/api/v1/health/`)

| Method | Path | Phase | Description |
|---|---|---|---|
| `GET` | `/health/security-posture` | P1 | Security feature enable/disable state per org |
| `GET` | `/health/secret-scanning` | P1 | Secret scanning alert MTTD/MTTR, unresolved aging |
| `GET` | `/health/sso` | P1 | SSO/SAML status per org |
| `GET` | `/health/ip-allowlist` | P1 | IP allowlist status and recent changes |
| `GET` | `/health/privilege-changes` | P1 | Privilege escalation summary |
| `GET` | `/health/code-scanning` | P2 | Code scanning alert MTTR and dismissal rates |
| `GET` | `/health/vulnerabilities` | P2 | Dependabot vulnerability aging |
| `GET` | `/health/app-governance` | P2 | OAuth/GitHub App installation summary |
| `GET` | `/health/workflows` | P3 | Workflow failure rates per repo |
| `GET` | `/health/copilot` | P3 | Copilot seat utilization and policy changes |
| `GET` | `/health/codespaces` | P3 | Codespace active/cost signals |
| `GET` | `/health/runners` | P3 | Self-hosted runner fleet version health |
| `GET` | `/health/branch-protection` | P3 | Branch protection change summary |

#### Query Interface Allowable Tables Extensions

In `query_service.py`, add new views/tables to `ALLOWED_TABLES` as they are created:

```python
ALLOWED_TABLES = frozenset({
    "events",
    "detections",
    "behavioral_baselines",
    "events_hourly",
    "events_daily_actor",
    "detections_daily",
    # Phase 1 additions:
    "system_health_events",
    # Phase 4 additions:
    "threat_intel_domains",
})
```

#### System Health Endpoint

```
GET /api/v1/health/system
```

Returns ingestion gap status, stream integrity, last event ingested per org, and whether any `SYSTEM` health events are active. This endpoint is called by the Dashboard to render the data gap banner.

---

### 8.2 Schema Changes to Existing Endpoints

#### `GET /api/v1/health/summary`

Extend the existing summary response model to include new counts from Phase 1:

```python
class HealthSummaryResponse(BaseModel):
    # Existing
    stale_repos: int
    pat_no_expiry: int
    pat_stale: int
    bypass_offenders: int
    ext_collab_total: int
    ext_collab_elevated: int
    # Phase 1 additions
    secret_scanning_unresolved: int          = 0
    secret_scanning_publicly_leaked: int     = 0
    security_features_disabled_7d: int       = 0
    sso_disabled_orgs: int                   = 0
    ip_allowlist_disabled_orgs: int          = 0
    # Phase 3 additions
    workflow_failure_rate_avg: float         = 0.0
    copilot_unused_seats: int                = 0
    codespace_active_never_suspended: int    = 0
```

This is an additive-only change — all new fields have defaults so existing clients are not broken.

---

## 9. Frontend Changes

### 9.1 Org Health Tab Additions

The existing Org Health page currently shows 5 signals (PAT health, bypass offenders, stale repos, archived repos, external collaborators). Phase 1–3 add:

| Phase | New Card / Section | Data Source |
|---|---|---|
| P1 | **Secret Scanning Alerts** — unresolved count, publicly leaked, MTTR | `/health/secret-scanning` |
| P1 | **Security Posture** — feature coverage heatmap per namespace | `/health/security-posture` |
| P1 | **SSO Status** — per-org SSO enable state | `/health/sso` |
| P1 | **Data Ingestion Health** banner — if gap detected | `/health/system` |
| P2 | **Vulnerability Aging** — open critical/high count, >30d open | `/health/vulnerabilities` |
| P2 | **App Governance** — installed apps, OAuth approvals, revocations | `/health/app-governance` |
| P3 | **Copilot Seats** — assigned vs. utilized, policy summary | `/health/copilot` |
| P3 | **Codespace Costs** — active, never-suspended, large-machine counts | `/health/codespaces` |
| P3 | **Runner Fleet** — version disparities, new registrations | `/health/runners` |

### 9.2 Dashboard Additions

Add to the existing Dashboard stat pills:
- **Unresolved Secret Alerts** (P1) — links to Org Health > Secret Scanning
- **Security Feature Disables (7d)** (P1) — links to Org Health > Security Posture

Add to the Platform Alerts card (WS-2.3 from `plan.md`):
- Secret scanning public leak events (P1)
- SAML disabled events (P1)
- Workflow failure rate trend (P3)

### 9.3 New Frontend Page: Security Posture

**Route:** `/security-posture`  
**Phase:** P2

A dedicated page showing a grid of repositories × security features, colored by current enable state. Inspired by GitHub's own "Security coverage" view in the Security tab, but enriched with detection history and bypass rates.

**Components needed:**
- `SecurityCoverageMatrix.tsx` — grid component
- `SecurityFeatureToggleTimeline.tsx` — per-repo event timeline
- `AlertAging.tsx` — reusable aging bar chart (used for both secret scanning and Dependabot)

### 9.4 Velocity Page Additions (P3)

Add to existing Engineering Velocity page:
- **Workflow Health table** — per-repo failure rate, trend sparkline, top failing workflows (replaces the placeholder in `plan.md` WS-5)
- **Branch Protection Changes** — timeline of weakening events
- **Deployment Environment Risks** — environments with self-review enabled or no approvers

---

## 10. Detection Rule Schemas

### 10.1 New `category` Values

Add the following to the allowed category enum in `app/schemas/detection.py`:

| Category | Description |
|---|---|
| `defense_evasion` | Attempts to reduce monitoring or security control effectiveness |
| `posture_degradation` | Changes that weaken security posture without direct attack |
| `posture_change` | Neutral posture change requiring review (not inherently bad) |
| `supply_chain` | Actions that could compromise the software delivery pipeline |
| `incident_response` | Actions taken in response to a security incident |

Existing categories remain: `data_exfiltration`, `access_control`, `privilege_escalation`, `anomalous_behavior`, `policy_violation`.

### 10.2 New `logic_type` Values

| Type | Phase | Description |
|---|---|---|
| `cross_namespace_sequence` | P4 | Multi-step sequence across different action namespaces |

Existing types remain: `pattern`, `threshold`, `sequence`, `impossible_travel`, `behavioral_baseline`.

### 10.3 `x_config` Reserved Keys

Document standard keys the UI and engine may read from `x_config`:

| Key | Type | Purpose |
|---|---|---|
| `rationale` | string | Human-readable rule rationale for analysts |
| `suppression_guidance` | string | Recommended suppression approach |
| `normalization_required` | boolean | Whether ingest normalization is a prerequisite |
| `note` | string | Implementation notes for rule authors |
| `approved_domains` | list[str] | Domain allowlist (future use, Phase 4 webhook intel) |

---

## 11. Database Migrations

### 11.1 Migration: `0004_phase1_system_health.py`

```sql
-- system_health_events: internal OctoWatch health signals (data gaps, stream issues)
CREATE TABLE system_health_events (
    id            BIGINT GENERATED ALWAYS AS IDENTITY,
    occurred_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    org           TEXT,
    signal_type   TEXT NOT NULL,   -- 'ingestion_gap' | 'stream_disabled' | 'stream_modified'
    severity      TEXT NOT NULL,   -- 'warning' | 'critical'
    detail        JSONB NOT NULL DEFAULT '{}',
    resolved_at   TIMESTAMPTZ,
    PRIMARY KEY (id, occurred_at)
);
SELECT create_hypertable('system_health_events', 'occurred_at');
CREATE INDEX idx_system_health_org ON system_health_events (org, occurred_at DESC);
CREATE INDEX idx_system_health_unresolved ON system_health_events (signal_type, resolved_at)
    WHERE resolved_at IS NULL;
```

### 11.2 Migration: `0005_phase1_detection_rules.py`

Seed 14 detection rules from Phase 1 using the existing `rule_definitions` schema. Reference the YAML specs in §4 for exact `logic_config` values.

### 11.3 Migration: `0006_phase2_detection_rules.py`

Seed 12 detection rules from Phase 2.

### 11.4 Migration: `0007_phase3_detection_rules.py`

Seed 10 detection rules from Phase 3.

### 11.5 Migration: `0008_phase4_chain_rules.py`

Seed 5 threat chain rules from Phase 4. Note: these rules must have `enabled: false` in migration unless the `cross_namespace_sequence` engine enhancement is already deployed.

### 11.6 Migration: `0009_behavioral_baseline_expansion.py`

```sql
ALTER TABLE behavioral_baselines
    ADD COLUMN IF NOT EXISTS push_bypass_hourly_mean    DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS push_bypass_hourly_stddev  DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS alert_dismiss_daily_mean   DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS alert_dismiss_daily_stddev DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS admin_action_daily_mean    DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS admin_action_daily_stddev  DOUBLE PRECISION;
```

### 11.7 Migration: `0010_threat_intel_domains.py`

```sql
CREATE TABLE threat_intel_domains (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    domain       TEXT NOT NULL UNIQUE,
    source       TEXT NOT NULL,          -- e.g., 'manual', 'abuse.ch', 'internal'
    confidence   DOUBLE PRECISION NOT NULL DEFAULT 0.80,
    active       BOOLEAN NOT NULL DEFAULT TRUE,
    added_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    added_by     TEXT NOT NULL,
    expires_at   TIMESTAMPTZ,
    notes        TEXT
);
CREATE INDEX idx_threat_intel_active ON threat_intel_domains (active, domain);
```

---

## 12. Cross-Cutting Concerns

### 12.1 Performance

All new health signal queries must be tested against a representative dataset (>1M events) before merging. Queries that scan full-table ranges without leveraging TimescaleDB chunk pruning will be rejected.

- Every query must include `created_at >= NOW() - INTERVAL 'X days'` to enable chunk pruning
- Every query must include `AND org = ANY(:scoped_orgs)` — both for RBAC and for index leverage
- New queries should use `EXPLAIN (ANALYZE, BUFFERS)` output as part of the PR description

### 12.2 RBAC

No new table or query may return data without passing through the `inject_scope_predicate()` function or equivalent manual predicate. This is enforced by code review checklist.

### 12.3 Ingest Normalization

Phase 3 requires the first structural change to the ingest normalizer. The `secrets_passed` field from `workflows.prepared_workflow_job` must be:
1. Counted → stored as `secrets_passed_count` in the event `data` JSONB
2. Removed from storage — the actual secret names must never be persisted

This is a security requirement, not just an optimization.

### 12.4 False Positive Management

For every new detection rule, the analyst team should review the first 100 events matching the rule against production data before enabling it. Rules marked `status: 'staging'` fire detections with `status: 'staging'` which are hidden from the default threat view but visible in a staging filter. Use this for new rules in review.

### 12.5 Rule Dependency Tracking

Rules that require ingest normalization or engine enhancements must be seeded with `enabled: false` and include a `x_config.depends_on` key listing the prerequisite. A startup check in `main.py` can warn operators about disabled rules with unmet dependencies.

---

## 13. Test Plan

### 13.1 Unit Tests

| Component | Test File | Coverage Required |
|---|---|---|
| New health signal queries | `tests/test_health_signal_service.py` | All new functions, with edge cases (empty data, missing events) |
| Phase 1–3 detection rules | `tests/test_detection_service.py` | Each rule: positive match, negative match, threshold boundary |
| `cross_namespace_sequence` engine | `tests/test_detection_service.py` | Complete sequence, partial sequence (no fire), window expiry |
| `check_ingestion_gaps` task | `tests/test_ingest_worker.py` | Gap detected, no gap, per-org scoping |
| `threat_intel_service` | `tests/test_threat_intel_service.py` | Domain match, no match, wildcard, expired entry |

### 13.2 API Tests

Each new endpoint in §8.1 requires:
- Authenticated request → correct data returned
- Unauthenticated request → 401
- Request with scope insufficient for org → 403 or empty result (not 403, depending on convention)
- Invalid parameters → 400 with error detail

### 13.3 Integration Tests

For Phase 4 chain rules:
- Seed synthetic events in sequence order, then verify detection fires
- Seed partial sequence (steps 1 and 3 only, missing step 2), verify no detection
- Seed sequence outside time window, verify no detection

---

## 14. Definition of Done

### Per Phase

- [ ] All Alembic migrations pass `alembic upgrade head` cleanly from a fresh database
- [ ] All new health signal functions have unit tests with ≥90% coverage
- [ ] All new detection rules have positive and negative test cases
- [ ] All new API endpoints are documented in the API router docstrings
- [ ] Performance: new queries run in <2s on a 10M-event test dataset
- [ ] RBAC: `inject_scope_predicate` confirmed on all new queries
- [ ] Security: no secret names, credentials, or PII persisted during normalization
- [ ] Code review checklist signed off by at least one other maintainer

### Final Acceptance (all 4 phases)

- [ ] All 41 new detection rules seeded and active (Phase 4 chain rules pending engine PR)
- [ ] All 19 new health signal functions deployed and tested
- [ ] All 13 new API endpoints live and returning data from real event streams
- [ ] Dashboard shows ingestion gap banner when data is stale
- [ ] Org Health page covers all major security namespaces
- [ ] Security Posture page deployed and linked from Org Health
- [ ] Velocity page shows workflow health data
- [ ] No audit log namespace with >100K historical events in the existing dataset is unaddressed by at least one signal or rule
