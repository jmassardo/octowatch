# OctoWatch — Requirements: Feedback Round 2

**Prepared:** 2026-03-27  
**Status:** Draft — pending stakeholder sign-off  
**Scope:** Items 1–3 and 5 (detection rules + health signals) and Item 4 (MinIO product note)  
**Next step:** Architecture & Security Agent review after stakeholder approval

> **Reading guide.** Each user story includes:
> - Role, want, benefit
> - Acceptance criteria (Given / When / Then)
> - Audit log event sources
> - Implementation classification: **(a)** Detection Rule · **(b)** Org Health signal · **(c)** Both · **(d)** New report endpoint
> - Edge cases and constraints

---

## Baseline / import constraint (applies to all items)

OctoWatch cannot continuously poll GitHub APIs. All signals and rules **must** be powered by one of:

1. **Streamed audit log events** ingested from S3 / Azure Blob / MinIO into the `events` hypertable — the primary data source.
2. **One-time baseline import** seeding repo lists, member rosters, PAT inventory, app installation lists, and collaborator grants at a specific point in time. Drift is detected as new audit events arrive.

Any health signal that relies on "current state" (e.g., token still active, collaborator still present) requires both a baseline seed **and** ongoing audit event reconciliation. This constraint is called out explicitly in each affected story.

---

## Item 1 — Data Exfiltration Risk

### 1-A · Bulk Repository Cloning (Enhancement to existing insider-mass-clone rule)

| Field | Value |
|---|---|
| **ID** | US-1A |
| **Priority** | Must |
| **Category** | `exfiltration` |
| **Classification** | **(c) Both** — Detection Rule + health signal in Repository Health tab |

**User story**  
As a **security analyst**, I want OctoWatch to detect when a single human actor clones an unusually large number of **distinct** repositories within a short time window so that I can identify potential data harvesting before sensitive code leaves the organisation.

> **Important:** An existing rule (`insider-mass-clone`) already fires on raw `git.clone` event count per actor per hour. This story enhances the approach by requiring **distinct-repo counting** as a separate, higher-confidence sibling rule and by surfacing a heat-map health signal so analysts can see cloning patterns without reviewing individual detections.

---

**Acceptance criteria**

*Rule — enhanced distinct-repo threshold:*

- **Given** the detection worker processes a batch of events  
  **When** a single non-bot actor generates `git.clone` events for ≥ 15 **distinct** repositories within any 60-minute rolling window  
  **Then** one Detection is created with severity `High`, rule category `exfiltration`, and `context_data` that includes: `distinct_repo_count`, `total_clone_events`, `window_start`, `window_end`, and the full list of cloned repo names

- **Given** an actor has already triggered the detection within the current window  
  **When** more clone events arrive (same actor, same open window)  
  **Then** the existing open Detection is updated (event IDs extended, `window_end` extended, `distinct_repo_count` refreshed) rather than a duplicate Detection created

- **Given** the actor is flagged `actor_is_bot = true`  
  **When** clone events fire  
  **Then** the rule **does not** trigger (bots executing CI mirror jobs are handled by the existing rule with a separate suppression path)

- **Given** a suppression rule exists for the actor (e.g., known bulk-migration service account)  
  **When** the threshold is crossed  
  **Then** the Detection is suppressed and a suppression log entry is written

*Health signal:*

- **Given** the Org Health → Repository Health tab is loaded  
  **When** the view renders  
  **Then** a "Top cloning actors — last 30 days" summary card is displayed showing the top 10 actors ranked by distinct repos cloned, sourced from `git.clone` events within the 30-day window

- **Given** the summary card is rendered  
  **When** an analyst clicks a row  
  **Then** a detail panel opens listing the actor's clone activity timeline with per-day distinct-repo counts and links to the contributing Detection(s)

**Audit log events**

| Event | Relevant fields |
|---|---|
| `git.clone` | `actor`, `actor_is_bot`, `repo`, `org`, `created_at`, `source_ip` |

**Rule YAML skeleton**
```yaml
id: "insider-mass-clone-distinct-repos"
name: "Mass Repository Clone — Distinct Repo Harvesting"
logic_type: threshold
action_filters:
  - "git.clone"
field_conditions:
  - field: "actor_is_bot"
    operator: "eq"
    value: false
aggregation_key: "actor"
threshold: 15             # distinct repos, not raw events
time_window_minutes: 60
severity: High
confidence: 0.80
category: exfiltration
```
> **Note for rule engine implementation:** The threshold evaluator currently counts raw events per `aggregation_key`. To support distinct-repo counting, the rule will require either (a) a new `distinct_count_field: "repo"` config key that instructs the engine to count unique values of `repo` rather than raw event count, or (b) a dedicated evaluator path for `aggregation_subtype: distinct`. The rule author and engine dev must agree on this before the rule is authored. Flag this as a **backend engine enhancement dependency**.

**Edge cases**

| Scenario | Handling |
|---|---|
| Forking a repo and cloning the fork immediately | Both clone events count; the distinct repos are fork + original — expected behaviour, fork subject to Item 3 logic |
| GitHub Actions workflow that clones multiple repos as part of a monorepo build | Actor is a bot or service account; suppress by actor or by `actor_is_bot = true` |
| Developer doing a legitimate local mirror of all org repos for disaster recovery | Document the suppression path: create a named suppression scoped to actor + `git.clone` action; analysts must explicitly approve and log the justification |
| Clone event missing `repo` field | Exclude events with null `repo` from distinct-repo count; count only events with a resolvable repo name |
| Threshold too sensitive for large engineering orgs | Rule ships as `enabled: false` (draft); each deployment must tune `threshold` and `time_window_minutes` to baseline volume before enabling |

---

### 1-B · Overly Permissive PAT or GitHub App Installation Detection

| Field | Value |
|---|---|
| **ID** | US-1B |
| **Priority** | Must |
| **Category** | `pat_abuse` |
| **Classification** | **(a) Detection Rule** (pattern, fires at creation time) |

**User story**  
As a **security analyst**, I want OctoWatch to immediately flag when a developer creates a classic Personal Access Token with all scopes selected (or a fine-grained PAT with write access across all repositories and no resource constraint), or when a GitHub App is installed with all repository event subscriptions enabled, so that I can enforce the principle of least privilege before such tokens are used.

---

**Acceptance criteria**

*Classic PAT — all-scopes creation:*

- **Given** a `personal_access_token.create` event is ingested  
  **When** `data.scopes` contains `"repo"` **AND** `"admin:org"` **AND** `"admin:enterprise"` (the three top-level super-scopes that together grant near-total access)  
  **Then** a Detection is created with severity `High`, confidence `high` (0.85), category `pat_abuse`, title `"Overly Permissive Classic PAT Created — <actor>"`, and `context_data` including the full scope list and `data.hashed_token`

- **Given** a `personal_access_token.create` event with `data.scopes` containing only `"repo"` (no admin scopes)  
  **When** the event is processed  
  **Then** no Detection is created (repo-only PATs are broad but accepted practice; this is a health signal concern, not an immediate detection)

*Fine-grained PAT — all-repository write grant:*

- **Given** a `personal_access_token.create` event is ingested where `data.token_type` indicates a fine-grained token  
  **When** `data.resource` is `"all_repositories"` **AND** `data.permissions` contains any combination of write-level permissions (e.g., `repository:write`, `contents:write`)  
  **Then** a Detection is created with severity `Medium`, confidence `medium` (0.65), category `pat_abuse`, and `context_data` including `data.resource`, `data.permissions`, and `data.hashed_token`

*GitHub App installation — broad permissions:*

- **Given** an `integration_installation.create` event is ingested  
  **When** `data.permissions` grants `write` on `contents` **AND** `write` on `administration` on `data.repository_selection = "all"`  
  **Then** a Detection is created with severity `High`, confidence `medium` (0.70), category `supply_chain`, and `context_data` including the app name, permissions object, and installing actor's login

- **Given** a detection is already open for the same `data.hashed_token` within the last 7 days (e.g., the token was rotated and recreated with same scopes)  
  **When** a new event fires  
  **Then** a new Detection is still created (each new token creation event is a distinct security decision; deduplication does not apply across token hashes)

**Audit log events**

| Event | Relevant fields |
|---|---|
| `personal_access_token.create` | `actor`, `org`, `data.scopes`, `data.token_type`, `data.resource`, `data.permissions`, `data.hashed_token`, `data.token_expires_at` |
| `integration_installation.create` | `actor`, `org`, `data.app_id`, `data.app_name`, `data.permissions`, `data.repository_selection` |

**Rule YAML skeletons**
```yaml
# Rule 1B-i: Classic PAT with super-scopes
id: "pat-all-scopes-classic"
name: "Overly Permissive Classic PAT — All Super-Scopes"
logic_type: pattern
action_filters:
  - "personal_access_token.create"
field_conditions:
  - field: "data.scopes"
    operator: "contains"
    value: "repo"
  - field: "data.scopes"
    operator: "contains"
    value: "admin:org"
  - field: "data.scopes"
    operator: "contains"
    value: "admin:enterprise"
severity: High
confidence: 0.85
category: pat_abuse
```
```yaml
# Rule 1B-ii: Fine-grained PAT with all-repos write
id: "pat-fine-grained-all-repos-write"
name: "Fine-Grained PAT — All Repositories Write Access"
logic_type: pattern
action_filters:
  - "personal_access_token.create"
field_conditions:
  - field: "data.token_type"
    operator: "eq"
    value: "fine_grained"
  - field: "data.resource"
    operator: "eq"
    value: "all_repositories"
  - field: "data.permissions"
    operator: "contains"
    value: "write"
severity: Medium
confidence: 0.65
category: pat_abuse
```

**Edge cases**

| Scenario | Handling |
|---|---|
| GitHub Enterprise's built-in `github-actions` bot creates tokens automatically | Suppress by `actor = "github-actions[bot]"` and `actor_is_bot = true` |
| Organisation administrators who legitimately need broad PATs | Document the suppression path: create a suppression scoped to actor + org; require `rule_author` sign-off with a ticket reference |
| Classic PATs created before OctoWatch was deployed | Not detectable via streaming events; must be surface via health signal (see US-1C) |
| `data.scopes` field format varies between GitHub Enterprise versions | The field `data.scopes` may be a comma-separated string or a JSON array depending on GHES version; detection service field_condition evaluation must normalise to array before applying `contains` |
| Fine-grained PAT event fields are not available on older GHES versions | Guard with an `org`-level or `business`-level version check; ship rule as `enabled: false` until GHES version is confirmed |

---

### 1-C · Token Age Health Signal

| Field | Value |
|---|---|
| **ID** | US-1C |
| **Priority** | Must |
| **Category** | PAT hygiene |
| **Classification** | **(b) Org Health signal** — Access & Identity tab → "PAT health snapshot" card (card already exists in v2 mockup) |

**User story**  
As a **security engineer**, I want the Org Health screen to show me which PATs are still active but were created more than a configurable age threshold ago (default: 365 days) so that I can prioritise token rotation before long-lived secrets are exploited.

---

**Acceptance criteria**

- **Given** the Access & Identity tab is loaded  
  **When** the "PAT health snapshot" card renders  
  **Then** the card displays three age-band rows:
  - **No expiry** — count of PATs with `data.token_expires_at` null (never expire)
  - **Expiring within 30 days** — count where `token_expires_at` is within the next 30 days
  - **Stale (not used in 90+ days)** — count where no event carrying the token's `data.hashed_token` has been seen in 90 days (see constraint note below)

- **Given** a `personal_access_token.create` event was ingested more than 365 days ago and no corresponding `personal_access_token.revoke` or `personal_access_token.delete` event has been ingested  
  **When** the PAT health card computes the "aged tokens" subcategory  
  **Then** the token appears in an "Aged tokens (>365 days)" drill-down table with columns: **Actor**, **Org**, **Token fingerprint** (`hashed_token`, truncated), **Days since creation**, **Last seen in events**, **Recommended action**

- **Given** the operator configures a custom age threshold (e.g., 180 days) via the Org Health Settings panel  
  **When** the PAT health signal re-computes  
  **Then** the aged-tokens count and table refresh to reflect the new threshold, without a new baseline import being required

- **Given** a baseline import has been run that includes the active PAT inventory  
  **When** the baseline row is present but no corresponding `personal_access_token.create` audit event exists (e.g., the token predates audit log streaming)  
  **Then** the token appears in the health signal with `created_at: unknown (pre-baseline)` and an age of `≥ baseline import date`; it is always treated as aged

- **Given** a PAT appears in the aged-tokens table  
  **When** a `personal_access_token.revoke` or `personal_access_token.delete` event is subsequently ingested for that `hashed_token`  
  **Then** the row is removed from the signal on the next health signal refresh

**Audit log events**

| Event | Relevant fields |
|---|---|
| `personal_access_token.create` | `actor`, `org`, `created_at`, `data.hashed_token`, `data.token_expires_at`, `data.scopes` |
| `personal_access_token.revoke` / `.delete` | `actor`, `org`, `data.hashed_token` |
| Any API-call event (for "last seen") | `data.hashed_token` — used to derive the most recent activity timestamp per token |

**Constraint note:** "Last seen" computation requires a table-scan or BRIN-index scan for events carrying a matching `hashed_token`. This should be implemented as a **materialised view or pre-computed cache** (refreshed every 6 hours) rather than a live query at page load, given the hypertable volume.

**Edge cases**

| Scenario | Handling |
|---|---|
| Token created by one actor and used by another (delegated token) | The `hashed_token` field is consistent regardless of actor; last-seen reflects any event carrying the token, not only the creator's events |
| `data.token_expires_at` field absent (older GHES versions) | Treat as "no expiry" in the health signal |
| Same `hashed_token` appears on both a create and a subsequent revoke, then a new create | State machine: created → active; revoked → inactive; re-created → new token (different hash); tokens should not be matched by hash across distinct creation events |
| Very large PAT inventory (enterprises with thousands of service account tokens) | Paginate drill-down table (50 rows/page); health card shows counts only, not raw list |

---

### 1-D · Dormant / Unused Token Health Signal

| Field | Value |
|---|---|
| **ID** | US-1D |
| **Priority** | Should |
| **Category** | PAT hygiene |
| **Classification** | **(b) Org Health signal** — Access & Identity tab → PAT health snapshot, "Stale" row (already in mockup) |

**User story**  
As a **security engineer**, I want OctoWatch to identify PATs that were created but have never been used (or have not been used in 90+ days) so that I can revoke dormant tokens before they become an attack vector.

---

**Acceptance criteria**

- **Given** a `personal_access_token.create` event exists for a given `hashed_token`  
  **When** no subsequent audit log event carrying that same `hashed_token` has been ingested within 30 days of token creation  
  **Then** the token is flagged as **never-used** in the PAT health snapshot

- **Given** a token was previously active (matching `hashed_token` appeared in at least one event)  
  **When** 90 consecutive days pass with no event carrying that `hashed_token`  
  **Then** the token is flagged as **dormant (90+ days)** in the PAT health snapshot

- **Given** a token is classified as never-used or dormant  
  **When** a new event carrying that `hashed_token` is ingested  
  **Then** the token is immediately reclassified as active and removed from the stale list on the next health signal refresh

- **Given** the Access & Identity tab is loaded  
  **When** an analyst clicks the stale tokens row  
  **Then** a drill-down table appears with columns: **Actor**, **Org**, **Token fingerprint**, **Days since creation**, **Days since last use**, **Last event type** (the most recent action this token was used for), **Recommended action**

- **Given** a grace period configuration exists (default: 30 days from creation before flagging as never-used)  
  **When** a token has been created fewer than 30 days ago and has no usage events  
  **Then** the token is **not** included in the never-used count (onboarding grace period)

**Audit log events**

Same as US-1C. The signal is derived by correlating `personal_access_token.create` events against `data.hashed_token` presence across all other events.

**Edge cases**

| Scenario | Handling |
|---|---|
| Service account tokens used only for internal automation that doesn't generate audit events | These are indistinguishable from truly unused tokens via audit log alone; operators should suppress by actor or annotate in the health signal |
| Token rotated (old revoked, new created same day) | The old token hash disappears from events; the new token hash starts fresh — treat separately |
| Audit log streaming has gaps (downtime, missed events) | Do not reset the dormancy clock based on a streaming gap; use the most recent ingested event timestamp for that token's last-seen |

---

## Item 2 — Branch Protection & Push Protection Bypass Repeat Offenders

### 2-A · Single-Event Push Protection Bypass Detection (General)

| Field | Value |
|---|---|
| **ID** | US-2A |
| **Priority** | Must |
| **Category** | `branch_protection_bypass` |
| **Classification** | **(a) Detection Rule** (pattern) |

**User story**  
As a **security analyst**, I want OctoWatch to create a Detection every time any actor bypasses secret scanning push protection **or** overrides a branch protection rule (not limited to publicly-leaked secrets) so that I have a complete audit trail of every bypass event to feed into the repeat-offender correlation.

> **Context:** An existing rule (`secret-leakage-push-protection-bypass-public`) fires only when `data.publicly_leaked = true`. This story adds two more pattern rules to capture **all** push protection bypasses and **all** `protected_branch.policy_override` events.

---

**Acceptance criteria**

*Push protection bypass (all variants):*

- **Given** a `secret_scanning_push_protection.bypass` event is ingested  
  **When** `data.publicly_leaked` is `false` or absent  
  **Then** a Detection is created with severity `Medium`, confidence `medium` (0.60), category `branch_protection_bypass`, title `"Push Protection Bypassed — <actor> on <repo>"`, and `context_data` including `data.secret_type`, `data.bypass_reason`, `data.multi_repo`, `data.publicly_leaked`

- **Given** an existing rule fires with `data.publicly_leaked = true`  
  **When** this general bypass rule also evaluates the same event  
  **Then** the general bypass rule is **suppressed** for that event; the publicly-leaked rule (higher severity) takes precedence (implemented via rule suppression or `field_condition: publicly_leaked eq false`)

*Branch protection policy override:*

- **Given** a `protected_branch.policy_override` event is ingested  
  **When** the event is processed  
  **Then** a Detection is created with severity `Medium`, confidence `medium` (0.60), category `branch_protection_bypass`, title `"Branch Protection Override — <actor> on <repo> branch <branch>"`, and `context_data` including `data.protected_branch`, `data.override_type`, `data.repo`

- **Given** the same actor triggers both a `secret_scanning_push_protection.bypass` **and** a `protected_branch.policy_override` on the same repo within 10 minutes  
  **When** both Detections are created  
  **Then** both are independent Detections; the correlation between them is handled by the threshold rule in US-2B (not collapsed here)

**Audit log events**

| Event | Relevant fields |
|---|---|
| `secret_scanning_push_protection.bypass` | `actor`, `org`, `repo`, `data.secret_type`, `data.publicly_leaked`, `data.multi_repo`, `data.bypass_reason` |
| `protected_branch.policy_override` | `actor`, `org`, `repo`, `data.protected_branch`, `data.override_type` |

**Rule YAML skeletons**
```yaml
# Rule 2A-i: Push protection bypass (non-public-leaked)
id: "push-protection-bypass-general"
name: "Push Protection Bypassed (Non-Public Secret)"
logic_type: pattern
action_filters:
  - "secret_scanning_push_protection.bypass"
field_conditions:
  - field: "data.publicly_leaked"
    operator: "ne"
    value: true
severity: Medium
confidence: 0.60
category: branch_protection_bypass
```
```yaml
# Rule 2A-ii: Branch protection policy override
id: "branch-protection-policy-override"
name: "Branch Protection Policy Override"
logic_type: pattern
action_filters:
  - "protected_branch.policy_override"
field_conditions: []
severity: Medium
confidence: 0.60
category: branch_protection_bypass
```

**Edge cases**

| Scenario | Handling |
|---|---|
| Repository owner bypasses during an incident / hotfix with documented justification | `data.bypass_reason` is captured in `context_data`; suppression by actor+repo can be applied for known incident windows using time-bounded suppressions |
| Force-push to a protected branch that generates a `push` event but not a `policy_override` event | `push` events are not currently classified as bypass events; this is a known audit log coverage gap. Document in rule as a known limitation. |
| `protected_branch.policy_override` events without a `data.protected_branch` field (GHES version differences) | Accept the event; populate `protected_branch: "unknown"` in `context_data` |

---

### 2-B · Repeat Bypass Offender — Threshold Detection Rule

| Field | Value |
|---|---|
| **ID** | US-2B |
| **Priority** | Must |
| **Category** | `branch_protection_bypass` |
| **Classification** | **(a) Detection Rule** (threshold, long-window) |

**User story**  
As a **security analyst**, I want OctoWatch to automatically escalate from a low-severity single-bypass Detection to a high-severity "repeat offender" Detection when the same actor accumulates 3 or more bypass events (push protection or branch protection combined) within a 7-day rolling window so that serial bypass behaviour is surfaced before it becomes habitual.

---

**Acceptance criteria**

- **Given** the detection worker evaluates a batch of events  
  **When** a single actor has triggered combined `secret_scanning_push_protection.bypass` **and/or** `protected_branch.policy_override` events ≥ 3 times within a 7-day window  
  **Then** a single repeat-offender Detection is created with severity `High`, confidence `high` (0.80), category `branch_protection_bypass`, title `"Repeat Bypass Offender — <actor>"`, and `context_data` including: `bypass_count`, `distinct_repos_affected`, `bypass_types` (list of action types observed), `window_start`, `window_end`, and the list of contributing Detection IDs

- **Given** a repeat-offender Detection is open for actor `X`  
  **When** actor `X` triggers another bypass within the same open window  
  **Then** the existing Detection is updated (bypass count incremented, event IDs extended, `window_end` extended) — no duplicate Detection

- **Given** a repeat-offender Detection has been resolved (status `resolved` or `acknowledged`) by an analyst  
  **When** the actor immediately triggers another bypass (within the still-open 7-day window)  
  **Then** a **new** Detection is opened (the analyst resolved the previous finding; new behaviour creates a fresh finding)

- **Given** the actor is a repository `admin` role (i.e., `data.actor_is_org_admin` or enterprise owner)  
  **When** the threshold is crossed  
  **Then** the Detection severity is **escalated to `Critical`** (admin repeat bypasses are a higher-risk signal)

- **Given** the first bypass is already captured by the single-event rules in US-2A  
  **When** the repeat-offender threshold rule later fires for the same actor  
  **Then** the repeat-offender Detection links the contributing single-event Detection IDs in `context_data.prior_detection_ids` (analyst can cross-reference)

**Audit log events**

| Event | Relevant fields |
|---|---|
| `secret_scanning_push_protection.bypass` | `actor`, `org`, `repo` |
| `protected_branch.policy_override` | `actor`, `org`, `repo` |

**Rule YAML skeleton**
```yaml
id: "repeat-bypass-offender"
name: "Repeat Bypass Offender — Branch and Push Protection"
description: |
  Actor has bypassed push protection or branch protection ≥ 3 times within
  7 days. Serial bypass behaviour indicates either deliberate circumvention
  of controls or a developer who needs re-training on security policies.
logic_type: threshold
action_filters:
  - "secret_scanning_push_protection.bypass"
  - "protected_branch.policy_override"
field_conditions: []
aggregation_key: "actor"
threshold: 3
time_window_minutes: 10080    # 7 days
severity: High
confidence: 0.80
category: branch_protection_bypass
tags: ["branch-protection-bypass", "insider-threat", "repeat-offender"]
```

**Edge cases**

| Scenario | Handling |
|---|---|
| CI pipeline service account that legitimately bypasses push protection as part of secret-rotation automation | Suppress by `actor` or by `actor_is_bot = true`; document in suppression note |
| 3 bypasses across 3 different orgs in a multi-org enterprise | The rule fires per `actor` globally; `context_data.distinct_repos` should include org prefix (`org/repo`) so analysts know cross-org exposure |
| The threshold of 3 is too sensitive for a principal engineer who manages branch protection policy for many repos | Rule ships with configurable threshold in `logic_config`; administrators must tune per deployment |
| Bypass events arrive out of order (e.g., MinIO delivery delays) | The 7-day window uses `created_at` (the original event timestamp), not `ingested_at`, so order of ingestion does not affect correctness |

---

### 2-C · Repeat Bypass Offender Health Signal

| Field | Value |
|---|---|
| **ID** | US-2C |
| **Priority** | Should |
| **Category** | PAT hygiene / Access controls |
| **Classification** | **(b) Org Health signal** — Access & Identity tab |

**User story**  
As a **security engineer**, I want the Org Health → Access & Identity tab to show me a ranked table of actors who have accumulated the most bypass events over the last 90 days so that I can proactively counsel or escalate to frequent offenders before a formal detection fires.

---

**Acceptance criteria**

- **Given** the Access & Identity tab is loaded  
  **When** the page renders  
  **Then** a "Branch & push protection bypasses — top offenders (90 days)" table is visible, sorted descending by total bypass count, showing columns: **Actor**, **Org(s)**, **Total bypasses**, **Push protection bypasses**, **Branch policy overrides**, **Distinct repos affected**, **Last bypass date**, **View detections** (link)

- **Given** the table is rendered  
  **When** an analyst clicks **View detections** for an actor  
  **Then** the Threats screen opens pre-filtered to open Detections for that actor from category `branch_protection_bypass`

- **Given** an actor has 0 bypass events in the 90-day window  
  **When** the table computes  
  **Then** the actor does not appear in the table (zero-value rows are omitted)

- **Given** the org-selector in the top navigation bar is set to a specific org  
  **When** the table re-computes  
  **Then** only bypass events within that org's scope are counted in that view

**Audit log events** — same as US-2A/2B.

**Edge cases**

| Scenario | Handling |
|---|---|
| Actor removed from the org mid-window | Show actor with a `(deprovisioned)` badge; do not remove historical bypass counts |
| Very long tail of low-frequency offenders | Default view shows top 25 actors; pagination available |

---

## Item 3 — Identifying Repositories That Should Be Deleted

### 3-A · Stale and Abandoned Repository Health Signal

| Field | Value |
|---|---|
| **ID** | US-3A |
| **Priority** | Must |
| **Category** | Repository hygiene |
| **Classification** | **(b) Org Health signal** — Repository Health tab (extends existing "Stale repository trend" section already in v2 mockup) |

**User story**  
As a **security engineer or IT manager**, I want the Org Health → Repository Health tab to surface a list of repositories that have had no push activity, pull request activity, or issue creation for longer than a configurable threshold (default: 90 days) so that I can identify candidates for archiving or deletion to reduce the org's attack surface and license overhead.

---

**Acceptance criteria**

*Signal computation:*

- **Given** a repository exists in the baseline-imported repo list  
  **When** the health signal engine computes staleness  
  **Then** a repo is classified as **stale** if the most recent `git.push`, `pull_request.create`, `pull_request.merge`, or `issues.create` event timestamp for that `repo` is older than the configured staleness threshold (default: 90 days)

- **Given** a repo has never had any of the above event types ingested (i.e., it existed before OctoWatch's audit log coverage began)  
  **When** the signal computes  
  **Then** the repo is classified as **stale — no events since baseline**, and `last_activity: unknown (pre-baseline)` is recorded

- **Given** a repo was `repo.archived` (an archive event was ingested) but no `repo.destroy` event was subsequently ingested  
  **When** the signal computes  
  **Then** the repo is listed in a separate **Archived (still present)** sub-category, distinct from merely stale repos

- **Given** operator has configured a custom staleness threshold (e.g., 180 days) in Org Health Settings  
  **When** the signal refreshes  
  **Then** the staleness classification updates without a new baseline import

*Display requirements:*

- **Given** the Repository Health tab is loaded  
  **When** the stale repo section renders  
  **Then** a summary card shows: **Stale repos (>90 days)** count, **Archived (still present)** count, **Abandoned forks** count (from US-3C), and a bar-chart trend for each over the last 90 days (using `git.push` absence derived from events)

- **Given** the count card is rendered  
  **When** an analyst clicks the stale count  
  **Then** a drill-down table opens with columns: **Repository**, **Org**, **Last push**, **Last PR**, **Archived?**, **Forked from**, **Default branch protection**, **Secret scanning enabled**, **Recommended action** (Archive / Delete / Keep)

- **Given** a repo appears in the stale list  
  **When** a new `git.push` or `pull_request.create` event is ingested for that repo after a period of inactivity  
  **Then** the repo is removed from the stale list on the next signal refresh (health signal is drift-based, not static)

**Audit log events**

| Event | Relevant fields |
|---|---|
| `git.push` | `repo`, `org`, `created_at` |
| `pull_request.create` | `repo`, `org`, `created_at` |
| `pull_request.merge` | `repo`, `org`, `created_at` |
| `issues.create` | `repo`, `org`, `created_at` |
| `repo.archived` | `repo`, `org`, `created_at` |
| `repo.destroy` | `repo`, `org`, `created_at` |
| `repo.create` | `repo`, `org`, `created_at`, `data.visibility` |
| Baseline import | repo list, `archived_at`, `fork`, `fork_parent` |

**Edge cases**

| Scenario | Handling |
|---|---|
| Read-only reference repo intentionally kept dormant (e.g., archived third-party dependency mirror) | Operator can suppress by repo name or prefix; present a "Mark as intentionally dormant" action in the drill-down table that removes the repo from the signal without triggering a baseline re-import |
| Repo with only wiki edits or GitHub Discussions activity | Wiki and Discussions events are not in the standard audit log stream; these repos will appear stale even if content is being maintained. Document this known gap in the signal's data source footnote. |
| Repo deleted since the baseline import (`repo.destroy` event received) | Remove from stale signal immediately on ingestion of the destroy event |
| Multi-org enterprise where the same repo name exists in multiple orgs | Always use `org/repo` as the canonical identifier in the drill-down table |
| Staleness threshold of 0 days is configured | Validate: minimum staleness threshold is 7 days; the UI must enforce this constraint |

---

### 3-B · Archived Repository Hygiene Signal

| Field | Value |
|---|---|
| **ID** | US-3B |
| **Priority** | Should |
| **Category** | Repository hygiene |
| **Classification** | **(b) Org Health signal** — Repository Health tab, as a sub-section of US-3A's drill-down |

**User story**  
As a **security engineer**, I want OctoWatch to separately surface repositories that have been archived (either before ingestion started or via a `repo.archived` event) but have not yet been destroyed, so that I can decide whether archived repos should be deleted to reduce the org's standing attack surface.

---

**Acceptance criteria**

- **Given** a `repo.archived` event is ingested  
  **When** the Repository Health signal refreshes  
  **Then** the repo appears in the **Archived (still present)** sub-category with: `archived_since` derived from the event timestamp, `days_archived`, `last_push_before_archive` (derived from most recent `git.push` before archive), `has_open_issues`, `has_active_webhook` (any `hook.*` events after the archive date indicate the archive is not cleanly frozen)

- **Given** a repo was archived per the baseline import (no corresponding `repo.archived` event exists)  
  **When** the signal renders  
  **Then** the repo appears in the sub-category with `archived_since: unknown (pre-baseline)` and a `baseline` label

- **Given** an archived repo subsequently receives a `git.push` or `repo.restore` event (un-archived)  
  **When** the event is ingested  
  **Then** the repo is removed from the archived sub-category and re-evaluated against the staleness rules in US-3A

- **Given** a `hook.create` or `hook.destroy` event references an archived repo  
  **When** the signal renders  
  **Then** a **webhook still active** warning badge is shown on that repo's row (active webhooks on archived repos are a security concern — they may still deliver events to external endpoints)

**Audit log events**

| Event | Relevant fields |
|---|---|
| `repo.archived` | `repo`, `org`, `created_at` |
| `repo.destroy` | `repo`, `org` |
| `hook.create` / `hook.destroy` | `repo`, `org` |
| Baseline import | `archived_at`, `fork`, `visibility` |

**Edge cases**

| Scenario | Handling |
|---|---|
| Repo archived as part of an org-wide cleanup — all repos archived in the same hour | Bulk archive events should not trigger a flood of individual Detections; this is a health signal only (no detection rule fires for `repo.archived`) |
| Archived repo with a GitHub Actions workflow that still runs on schedule | Schedule-triggered workflow runs do not appear in the standard audit log; this gap is known and documented alongside the signal |

---

### 3-C · Abandoned Fork Health Signal

| Field | Value |
|---|---|
| **ID** | US-3C |
| **Priority** | Could |
| **Category** | Repository hygiene |
| **Classification** | **(b) Org Health signal** — Repository Health tab |

**User story**  
As an **IT manager**, I want OctoWatch to identify forks within the organisation that have received no push activity since they were forked, so that I can identify forks that were created for exploration or testing and were never developed further, and can be safely deleted.

---

**Acceptance criteria**

- **Given** a `repo.fork` event is ingested  
  **When** the health signal evaluates that fork  
  **Then** the fork repository is tracked; if no `git.push` event for that repo is ingested within 30 days of the fork creation date, the repo is classified as an **abandoned fork**

- **Given** an abandoned fork is identified  
  **When** the Repository Health tab renders  
  **Then** the fork appears in a "Abandoned forks" count widget and in the drill-down table with columns: **Repository**, **Forked from**, **Forked by**, **Days since fork**, **Push count since fork** (0), **Recommended action** (Delete)

- **Given** an abandoned fork subsequently receives a `git.push` event  
  **When** the event is ingested  
  **Then** the fork is reclassified as active and removed from the abandoned list

- **Given** the org has many forks (> 100) with no push activity  
  **When** the signal renders  
  **Then** the table is paginated (50 rows/page) and sortable by days-since-fork descending

**Constraint:** Fork-with-no-divergence detection (detecting whether a fork's tree has diverged from its parent) is **not** achievable from audit log events alone — this would require GitHub API calls to compare commit SHAs, which violates the no-continuous-polling constraint. The signal is therefore limited to "forked but never pushed to", which is the most reliable and actionable subset of the concept.

**Audit log events**

| Event | Relevant fields |
|---|---|
| `repo.fork` | `repo` (fork name), `org`, `actor`, `data.forkee` (parent), `created_at` |
| `git.push` | `repo`, `org`, `created_at` |
| `repo.destroy` | `repo`, `org` |

**Edge cases**

| Scenario | Handling |
|---|---|
| Fork used only for reading / raising a PR upstream with no local push | No push events exist; fork correctly classified as abandoned. If the analyst confirms this is intentional, they can dismiss via "Mark as intentionally dormant" |
| Fork created before OctoWatch's audit log coverage (in baseline) | Track from baseline; if no push events seen since baseline import date, classify as abandoned |
| Fork destroyed (`repo.destroy`) before the signal evaluates | Remove from abandoned list on destruction event ingestion |

---

## Item 4 — MinIO Deprecation (Product Note / Roadmap Entry)

> **Classification:** Not a user story or detection rule. Product roadmap entry only.

### Background

The current ingestion pipeline supports three delivery sources, constrained by the `ingestion_source` column check constraint: `s3`, `azure_blob`, `minio`. MinIO was included as a self-hosted S3-compatible alternative for evaluations and air-gapped deployments. Customer feedback and operational experience indicate that MinIO adds deployment complexity (additional stateful service, object lifecycle management, a separate access-key rotation surface) while providing value primarily in environments where direct streaming to S3/Azure is not possible.

The team's preferred long-term direction is **direct streaming ingestion** — a webhook receiver that accepts GitHub audit log events in real time, eliminating object storage from the delivery path entirely. The Roadmap already lists **Webhook Ingestion** as a near-term item.

### Proposed roadmap entry

---

**Deprecate MinIO Ingestion Source (Medium-Term)**

*Context:* MinIO is currently supported as an ingestion delivery mechanism alongside Amazon S3 and Azure Blob Storage. As the platform matures toward real-time webhook-based ingestion, the MinIO path adds operational overhead without providing capabilities that S3 or direct streaming cannot satisfy.

*Proposed deprecation sequence:*
1. **Near-term (alongside Webhook Ingestion):** Mark the MinIO ingestion source as **deprecated** in the UI (an orange "deprecated" badge on the MinIO integration tile in the Integrations screen). Existing MinIO pipelines continue to function with no change.
2. **Medium-term:** After Webhook Ingestion reaches GA status, release a migration guide for transitioning from MinIO to direct webhook delivery or S3 export. Add a banner to the MinIO integration tile: *"MinIO ingestion will be removed in a future release. Migrate to webhook streaming or S3."*
3. **Long-term (next major version):** Remove the `minio` option from the `ingestion_source` check constraint, remove MinIO-specific polling worker code, and update the Helm chart to remove the optional MinIO sub-chart. Any existing rows with `ingestion_source = 'minio'` are retained as historical data (no migration of stored events required).

*Impact:*
- **New deployments:** Should default to S3 or, once available, webhook streaming.
- **Existing MinIO deployments:** Will have a minimum one-major-version deprecation window (no forced migration). Operators who require MinIO for air-gapped environments can pin to the last supported version.
- **Schema change:** The `CHECK (ingestion_source IN ('s3', 'azure_blob', 'minio'))` constraint removal requires an Alembic migration. No data migration needed since stored event rows are unaffected.

*No user stories are required for this item at this time.* Architecture review should assess the webhook ingestion design separately (already on the roadmap).

---

## Item 5 — External Collaborators

### 5-A · Elevated-Permission External Collaborator Addition Detection

| Field | Value |
|---|---|
| **ID** | US-5A |
| **Priority** | Must |
| **Category** | `privilege_escalation` |
| **Classification** | **(a) Detection Rule** (pattern) |

**User story**  
As a **security analyst**, I want OctoWatch to immediately flag when an outside collaborator (or, in EMU enterprises, a guest collaborator) is granted `admin` or `maintain` level access to any repository so that I can verify that elevated external access was intentionally authorised before the collaborator can make destructive changes.

---

**Acceptance criteria**

- **Given** a `repo.add_member` event is ingested  
  **When** `data.permission` is `admin` **AND** `data.member_type` is `outside_collaborator` (or `data.user_type` is `guest` for EMU enterprises)  
  **Then** a Detection is created with severity `High`, confidence `high` (0.85), category `privilege_escalation`, title `"External Collaborator Granted Admin — <actor> on <repo>"`, and `context_data` including `data.collaborator` (the collaborator's login), `data.permission`, `repo`, `org`

- **Given** a `repo.add_member` event is ingested  
  **When** `data.permission` is `maintain` **AND** `data.member_type` is `outside_collaborator`  
  **Then** a Detection is created with severity `Medium`, confidence `medium` (0.65), same category

- **Given** a `org.add_outside_collaborator` event is ingested (org-level collaborator grants)  
  **When** the event is processed  
  **Then** a **separate** Detection is created with severity `Medium`, confidence `medium` (0.60), category `privilege_escalation`, title `"Outside Collaborator Added to Org — <actor>"`, and `context_data` including the collaborator's login, org, and `data.permission`

- **Given** an outside collaborator is added with only `read` or `triage` level access  
  **When** the event is processed  
  **Then** **no** Detection is created (read-only external access is a health signal concern, not an immediate detection)

- **Given** an outside collaborator is immediately removed (`org.remove_outside_collaborator` or `repo.remove_member`) within 60 minutes of the add event  
  **When** a detection from the add event is open  
  **Then** the Detection is **not** auto-resolved (it remains open for analyst review; the quick removal may indicate the addition was noticed and reversed, which is itself interesting)

**Audit log events**

| Event | Relevant fields |
|---|---|
| `repo.add_member` | `actor`, `org`, `repo`, `data.collaborator`, `data.permission`, `data.member_type` |
| `org.add_outside_collaborator` | `actor`, `org`, `data.user`, `data.permission` |
| `business.add_outside_collaborator` | `actor`, `business`, `data.user`, `data.permission` |
| `org.remove_outside_collaborator` | `actor`, `org`, `data.user` |

**Rule YAML skeleton**
```yaml
id: "external-collaborator-admin-grant"
name: "External Collaborator Granted Admin/Maintain Access"
logic_type: pattern
action_filters:
  - "repo.add_member"
field_conditions:
  - field: "data.member_type"
    operator: "in"
    value: ["outside_collaborator", "guest"]
  - field: "data.permission"
    operator: "in"
    value: ["admin", "maintain"]
severity: High
confidence: 0.85
category: privilege_escalation
tags: ["privilege-escalation", "external-access", "compliance"]
```

**Edge cases**

| Scenario | Handling |
|---|---|
| Auditing firms temporarily granted admin access to a dedicated audit repo (standard practice) | Suppression by `repo + actor + time window`; suppression note must include the business justification and expected end date |
| EMU enterprise guest collaborators — `data.member_type` may differ from standard `outside_collaborator` string | Rule `field_conditions` uses `in` operator to cover both; validate exact field values against deployed GHES version before enabling |
| `repo.add_member` event for an internal member who happens to be in a different org of the same enterprise | The `data.member_type` check prevents false positives; only `outside_collaborator` or `guest` types trigger the rule |
| Business-level `business.add_outside_collaborator` events (enterprise-wide grants) — require a separate rule? | Yes — a third rule targeting `business.add_outside_collaborator` with the same permission filter should be authored separately; flag as a follow-on rule after the repo/org-scoped rules are validated |

---

### 5-B · External Collaborator Registry Health Signal

| Field | Value |
|---|---|
| **ID** | US-5B |
| **Priority** | Must |
| **Category** | External access |
| **Classification** | **(b) Org Health signal** — Access & Identity tab (extends existing "Outside collaborators with write/admin access" table in v2 mockup) |

**User story**  
As a **security engineer**, I want the Org Health → Access & Identity tab to maintain a persistent registry of all current outside (and guest) collaborators across all monitored orgs — including when they were added, their current permission level, and their org-grant vs. repo-grant scope — so that I can audit external access holistically across the enterprise without querying each org separately.

---

**Acceptance criteria**

*Registry construction:*

- **Given** a baseline import has been run  
  **When** the baseline includes outside collaborator grants  
  **Then** those collaborators are seeded into the external collaborator registry with `source: baseline` and their known permissions

- **Given** an `org.add_outside_collaborator` or `repo.add_member` (with `member_type = outside_collaborator`) event is ingested  
  **When** the event is processed  
  **Then** the collaborator is added to (or their record is updated in) the registry with: `collaborator_login`, `org`, `repo` (if repo-scoped), `permission`, `added_by`, `added_at`, `scope` (`repo` or `org`), `source` (`audit_event`)

- **Given** an `org.remove_outside_collaborator` or `repo.remove_member` event is ingested for a known collaborator  
  **When** the event is processed  
  **Then** the collaborator's registry record is marked `removed_at` and moved to inactive status; they are no longer shown in the active collaborator table

- **Given** the permission on an existing collaborator entry changes (`repo.update_member` event)  
  **When** the event is ingested  
  **Then** the registry record is updated to reflect the new permission level; a permission change history entry is appended

*Display requirements:*

- **Given** the Access & Identity tab is loaded  
  **When** the "Outside collaborators with write/admin access" table renders  
  **Then** it shows all currently active outside collaborators with `write`, `maintain`, or `admin` permission, with columns: **Collaborator**, **Org(s)**, **Repos** (count + expandable list), **Highest permission**, **Scope** (repo-level / org-level), **Added**, **Added by**, **Last active** (most recent event timestamp for this actor), **Risk** badge

- **Given** the org-selector filters to a specific org  
  **When** the table refreshes  
  **Then** only collaborators with grants in that org are shown

- **Given** an analyst needs a full view of all collaborators including read-only  
  **When** they toggle "Show all permissions"  
  **Then** `read` and `triage` collaborators also appear in the table with a `read` permission label

**Audit log events** — same as US-5A plus:

| Event | Relevant fields |
|---|---|
| `repo.update_member` | `repo`, `org`, `data.collaborator`, `data.old_permission`, `data.permission` |

**Edge cases**

| Scenario | Handling |
|---|---|
| Collaborator exists in the baseline but the `repo.add_member` event predates audit log streaming | Shown in registry with `added: unknown (pre-baseline)`; permission reflects baseline-imported value |
| Same collaborator granted access to multiple repos across multiple orgs | Show a consolidated row with `Repos: 4 repos across 2 orgs` (expandable) and highlight the highest permission level across all grants |
| Collaborator's GitHub account is deleted / suspended after they are added | No `org.remove_outside_collaborator` event is generated for account deletion; the registry entry remains active until an operator manually resolves it or a future GitHub API enrichment confirms removal |
| `repo.update_member` event has missing `data.old_permission` field | Accept the event; permission is set to `data.permission`; old permission recorded as `unknown` in history |

---

### 5-C · Dormant External Collaborator Detection

| Field | Value |
|---|---|
| **ID** | US-5C |
| **Priority** | Must |
| **Category** | External access / `privilege_escalation` |
| **Classification** | **(c) Both** — Threshold Detection Rule + Health signal in Access & Identity tab |

**User story**  
As a **security analyst**, I want OctoWatch to flag outside collaborators who have been granted access but have shown no activity (no audit log events from that actor in any of the monitored orgs) for 60+ days so that I can identify stale external access grants that should be revoked to reduce the standing attack surface.

---

**Acceptance criteria**

*Detection rule — dormant collaborator:*

- **Given** an outside collaborator is in the registry (from US-5B) with an `added_at` more than 30 days ago  
  **When** no audit log event from that `actor` (across any action type) has been ingested for ≥ 60 days  
  **Then** a Detection is created with severity `Medium`, confidence `medium` (0.65), category `privilege_escalation`, title `"Dormant External Collaborator — <collaborator>"`, and `context_data` including `days_since_last_activity`, `permission`, `repos_with_access` (list), `org`

- **Given** a dormant collaborator Detection is open  
  **When** a new audit log event from that actor is ingested  
  **Then** the Detection is **automatically resolved** with `resolution_note: "Actor activity observed"` (the collaborator is no longer dormant)

- **Given** a dormant external collaborator is removed (`org.remove_outside_collaborator`)  
  **When** the event is ingested  
  **Then** the open Detection is auto-resolved with `resolution_note: "Collaborator removed"`

- **Given** an outside collaborator has `read` or `triage` only permission  
  **When** they cross the dormancy threshold  
  **Then** the Detection severity is `Low` rather than `Medium` (read-only dormant access is a hygiene concern, not an immediate risk)

*Health signal — dormant collaborators list (Access & Identity tab):*

- **Given** the Access & Identity tab renders  
  **When** the "Dormant members" table is displayed  
  **Then** outside collaborators inactive for 60+ days appear with a distinct `outside collaborator` role badge (matching the role badge visible in the v2 mockup's dormant members table), alongside internal members — not in a separate section, so analysts see a unified view of all dormant access

- **Given** an external collaborator's dormancy is resolved (activity observed or access revoked)  
  **When** the signal refreshes  
  **Then** the row is removed from the dormant table

**Rule YAML skeleton**

> Note: This rule is **not a standard threshold rule** against real-time events — it requires evaluating the *absence* of events over a time window. This is a **scheduled/periodic evaluation** pattern, not a streaming pattern. The detection worker must run a scheduled job (e.g., nightly) that queries the database for collaborators whose `last_activity_at` (derived from the event table) is older than the threshold. This is a new evaluation mode and should be flagged as a **backend engine enhancement requirement**.

```yaml
id: "dormant-external-collaborator"
name: "Dormant External Collaborator"
logic_type: threshold          # NOTE: scheduled absence check; see implementation note above
action_filters: ["*"]          # All events — last-event-by-actor lookback
field_conditions:
  - field: "actor_is_bot"
    operator: "eq"
    value: false
aggregation_key: "actor"
threshold: 0                   # Zero events triggers — i.e., no activity observed
time_window_minutes: 86400     # 60 days (60 × 1440)
# x_config:
#   engine: "absence_check"
#   subject_registry: "external_collaborator_registry"
#   grace_period_days: 30
severity: Medium
confidence: 0.65
category: privilege_escalation
```

**Edge cases**

| Scenario | Handling |
|---|---|
| External collaborator with access to a repo but who interacts only via GitHub.com UI (no push/PR events) | UI interactions such as issue comments, PR reviews do generate audit log events (`issue_comment.create`, `pull_request_review.submit`); these events reset the dormancy clock |
| Collaborator who interacts exclusively with a private repo wiki (wiki events not in audit log) | This is a known audit log gap; accepted limitation; document in signal footnote |
| Long-term contractor on a sabbatical (60+ days intentionally) | Analyst can dismiss the dormancy Detection for N days via the existing Detection snooze mechanism; registry record should support an `expected_dormant_until` annotation |
| Enterprise has hundreds of external collaborators — rule fires for many simultaneously on first deployment | Suppress by creating a bulk suppression grace window on initial deployment; after first run, the dormancy clock operates continuously |

---

## Summary table

| ID | Title | Classification | Severity | Priority |
|---|---|---|---|---|
| US-1A | Bulk clone / distinct-repo harvesting | Rule + health signal | High | Must |
| US-1B | Overly permissive PAT / App creation | Rule (pattern) | High / Medium | Must |
| US-1C | Token age health signal | Health signal | N/A | Must |
| US-1D | Dormant / unused token health signal | Health signal | N/A | Should |
| US-2A | Single-event push/branch protection bypass | Rule (pattern) | Medium | Must |
| US-2B | Repeat bypass offender threshold rule | Rule (threshold) | High → Critical | Must |
| US-2C | Repeat bypass offender health signal | Health signal | N/A | Should |
| US-3A | Stale / abandoned repo health signal | Health signal | N/A | Must |
| US-3B | Archived repo hygiene signal | Health signal | N/A | Should |
| US-3C | Abandoned fork health signal | Health signal | N/A | Could |
| US-5A | Elevated-permission external collab detection | Rule (pattern) | High / Medium | Must |
| US-5B | External collaborator registry | Health signal | N/A | Must |
| US-5C | Dormant external collaborator | Rule + health signal | Medium | Must |
| — | MinIO deprecation | Product / roadmap note | N/A | Medium-term |

---

## Backend engine enhancement dependencies

The following capabilities do not currently exist in the detection engine and must be scoped before the relevant rules can be implemented:

| Dependency | Required by | Description |
|---|---|---|
| **Distinct-value aggregation** (`distinct_count_field`) | US-1A | Threshold evaluator currently counts raw events; needs a mode to count unique values of a specified field (e.g., `repo`) per aggregation key |
| **Absent-event / absence-check engine** | US-5C, US-1D (partial) | Scheduled evaluation of "actors with zero events" for a given subject registry; requires a periodic Celery beat task rather than streaming evaluation |
| **Token last-seen materialised view** | US-1C, US-1D | Efficient pre-computed last-seen timestamp per `hashed_token`; must be a materialised view or cached aggregate to avoid full hypertable scans at page load |
| **External collaborator registry table** | US-5B, US-5C | A new table (or materialised view) that maintains the current state of outside collaborators, seeded by baseline and updated by audit events; does not exist yet |

These dependencies require discussion between the rule engine developer and architecture review before implementation begins.

---

## Non-functional requirements

| Requirement | Specification |
|---|---|
| Health signal refresh latency | All Org Health signals must reflect new audit log events within ≤ 15 minutes of ingestion (eventual consistency; not real-time) |
| Health signal query performance | Signal queries against the `events` hypertable must complete within < 5 seconds at p95 for a 90-day lookback window over up to 50M events; use materialised views or TimescaleDB continuous aggregates where needed |
| Detection rule evaluation latency | New detection rules must be evaluated against incoming events within ≤ 2 minutes of event ingestion (existing SLA; new rules must not degrade this) |
| Role-based access | Health signals and detection lists must respect RBAC scope injection: org-scoped analysts see only their org's data; `sys_admin` sees all orgs |
| Health signal configurability | Staleness threshold (Item 3), token age threshold (Item 1-C), dormancy window (Items 1-D, 5-C) must be configurable per-deployment via the Org Health Settings panel; defaults specified in each story |
| Accessibility | All new UI components in the Org Health screen must meet WCAG 2.1 AA: sufficient colour contrast for status labels (danger / attention / success), keyboard-navigable tables, ARIA labels on icon-only buttons, screen-reader-friendly status badges |
| Multi-org support | All signals and rules must operate correctly across all monitored orgs in a GitHub Enterprise; org-level filtering must be consistent with the top-nav org selector |
| Audit trail | Any analyst action on a Detection (resolve, assign, suppress) must be recorded in the existing `audit_trail` hypertable |

---

## Open questions for architecture review

1. **Distinct-repo threshold:** The simplest implementation is a `COUNT(DISTINCT repo)` SQL subquery per actor per time window. Confirm whether the TimescaleDB continuous aggregate infrastructure can support this efficiently, or whether a specialised materialized view is needed.

2. **Absence-check scheduling:** For US-1D and US-5C, should the scheduled absence check be a new Celery beat task (periodic) or a new logic_type in the detection engine driven by a cron-style trigger? Recommend defining a `logic_type: absence` with a scheduled evaluator in the detection worker.

3. **External collaborator registry persistence:** Should the collaborator registry be a new table in the application database, or can it be derived on-the-fly from `events` at query time (with appropriate caching)? Given the need for baseline seeding and permission history, a dedicated table is recommended.

4. **EMU vs. standard enterprise field parity:** Several rules reference `data.member_type` and `data.user_type` fields that may differ between standard GitHub Enterprise and EMU configurations. A field normalisation pass over US-5A and US-5B field conditions is required once the team has confirmed which GHES/EMU versions are in scope for the initial deployment.

5. **PAT `data.scopes` field format:** Confirm whether `data.scopes` is a comma-separated string or a JSON array in the GHES version(s) in production. The `contains` operator in the detection engine should be tested against both formats, or a normalisation step added to the event ingestion pipeline.
