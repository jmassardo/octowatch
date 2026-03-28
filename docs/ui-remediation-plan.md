# OctoWatch UI Remediation Plan

**Generated:** 2026-03-28  
**Scope:** Full UI analysis of all pages and components  
**Methodology:** Static source analysis of `/frontend/src/` — every page, component, data file, and API binding reviewed

---

## Executive Summary

The OctoWatch UI is structurally sound and well-organized, but carries significant surface area of **hardcoded/static mock data** and **non-functional controls** that would confuse or mislead users in a production context. Four areas are especially critical: the entire **Copilot Insights** section, the **Health page** (License, Maintenance, WAF sub-tabs), the **Reports catalog**, and the **Integrations Configure** workflow. Additionally, the **Users page** active-sessions table and parts of the **Dev Activity** team filter use hardcoded fake user names.

Priority tiers:

| Priority | Label | User impact |
|---|---|---|
| **P0** | 🔴 Critical | Actively misleads users with fake data or completely non-functional |
| **P1** | 🟠 High | Core feature blocked; data is missing or wrong |
| **P2** | 🟡 Medium | Degraded experience; partial functionality |
| **P3** | 🟢 Low | Polish, copy, or minor UX improvement |

---

## P0 — Critical: Actively Misleading or Non-Functional

---

### US-001 · Copilot Insights — Replace all static mock data with live API data

**Priority:** P0 🔴  
**Page/Component:** `/pages/Copilot/` — all sub-tabs (Overview, Adoption, Models, Anomalies, License)  
**Source files:**
- `frontend/src/pages/Copilot/copilotData.ts` — 100% hardcoded constants
- `frontend/src/pages/Copilot/OverviewPane.tsx` — consumes hardcoded data, displays "This data is illustrative" banners
- `frontend/src/pages/Copilot/AdoptionPane.tsx`
- `frontend/src/pages/Copilot/AnomaliesPane.tsx`
- `frontend/src/pages/Copilot/ModelsPane.tsx`

**Current behavior:**  
Every metric, chart, and table in the Copilot Insights section displays static fake data. User names shown include: `sarah.chen`, `mike.ross`, `ana.silva`, `james.wu`, `priya.patel`, `tom.jones`, `lisa.park`, `raj.kumar`. All modals in OverviewPane include the warning "This data is illustrative. Connect the Copilot Metrics API for live per-user data." The `AnomaliesPane` displays a `SampleDataBanner`. The data constructs affected are: `ACCEPTANCE_RATE_DAYS`, `ACCEPTANCE_RATE_VALUES`, `LANGUAGES`, `ADOPTION_TIERS`, `POWER_USERS`, `MINIMAL_USERS`, `MODEL_USAGE`, `FEATURE_USAGE`, `EDITORS`, `ANOMALIES`.

**Acceptance Criteria:**
1. Backend exposes a `/api/v1/copilot/metrics` endpoint that integrates with the GitHub Copilot Metrics API (`GET /orgs/{org}/copilot/metrics`).
2. A React Query hook (`useCopilotMetrics`) caches and fetches acceptance rates, language breakdown, editor breakdown, and feature usage.
3. Adoption tier classification (Power / Regular / Minimal / Inactive / Never) is computed server-side from the Copilot Metrics data and returned via `/api/v1/copilot/adoption-summary`.
4. Anomaly detection: server computes statistical deviation from per-team rolling averages; results are persisted and returned via `/api/v1/copilot/anomalies`.
5. All instances of `copilotData.ts` constants are replaced by live query data.
6. When the Copilot Metrics API is not yet connected, the entire Copilot section displays a single "Connect Copilot Metrics API" empty state card with a link to `/integrations`, rather than showing fake data.
7. Remove all "This data is illustrative" inline banners from OverviewPane modals once live data is flowing.
8. `AnomaliesPane` and `OverviewPane` `SampleDataBanner` components are removed once the API is connected.

**Implementation notes:**
- The Copilot Metrics API requires an org-level token with `manage_billing:copilot` or `copilot` scope.
- Consider storing ingested Copilot Metrics snapshots in the DB for trend analysis (the API only returns a rolling window).
- The `LicensePane.tsx` inside Copilot already queries `getSeatUtilizationReport` and `getCopilotSeatsReport` — this pattern should be extended to all Copilot sub-tabs.

---

### US-002 · Integrations — Implement real configuration forms for each integration

**Priority:** P0 🔴  
**Page/Component:** `/pages/Integrations/index.tsx` → `MktCard` → `configTarget` modal  
**Source file:** `frontend/src/pages/Integrations/index.tsx` lines 469–479

**Current behavior:**  
Clicking "Configure" on any marketplace card (GitHub Enterprise, Slack, PagerDuty, and any card the user clicks "Install" on) opens a modal containing only three read-only paragraphs:
```
Status: Connected
Description: [card description text]
Configuration settings for {Name} integration. Connect via API key or OAuth flow.
```
There are no form fields, no save buttons, and no actual configuration capability.

**Integrations requiring forms:**

| Integration | Required fields |
|---|---|
| GitHub Enterprise | Hostname/URL, Personal Access Token (scoped), Webhook secret, Org names (multi), TLS verification toggle |
| Slack | Incoming Webhook URL, Default channel, Alert severity threshold (dropdown), Test connection button |
| Microsoft Sentinel | Workspace ID, Primary key, Log Analytics endpoint, Event type filter |
| Splunk | HEC endpoint URL, HEC token, Index name, Source type, TLS skip verify toggle |
| PagerDuty | Integration key (routing key), Severity mapping (critical→P1, high→P2, etc.), Dedup key strategy |
| Jira | Server URL, Project key, API token, Issue type, Assignee field mapping, Auto-create toggle |

**Acceptance Criteria:**
1. Backend implements `POST /api/v1/integrations/{type}/config`, `GET /api/v1/integrations/{type}/config` (with secrets masked), and `DELETE /api/v1/integrations/{type}/config` endpoints for all 6 integration types.
2. Each integration modal renders a form with appropriate input types (text, password, toggle, select).
3. Credentials are masked on retrieval (`*******` placeholder) and only transmitted on explicit Save.
4. Each form has a "Test connection" button that calls `POST /api/v1/integrations/{type}/test` and displays success/error inline.
5. Save button calls the backend API; on success the card status updates to "Connected"; on error, an inline error message is shown.
6. The `configTarget` state and generic modal content are replaced by a per-integration form component (e.g., `GitHubEnterpriseConfigForm`, `SlackConfigForm`, etc.).
7. Integration status (`connected` / `configured` / `not_installed`) is loaded from the backend on page mount via the existing `listTicketingConfigs` / `listNotificationConfigs` APIs — not hardcoded.

---

### US-003 · Integrations — Persist "Install" action to backend

**Priority:** P0 🔴  
**Page/Component:** `/pages/Integrations/index.tsx` → `onInstall` handler  
**Source file:** `frontend/src/pages/Integrations/index.tsx` line 366

**Current behavior:**  
Clicking "Install" on a marketplace card executes:
```js
setStatusOverrides((prev) => ({ ...prev, [integration.name]: 'configured' }))
```
This only mutates local component state. Refreshing the page resets the status back to `not_installed`. Nothing is sent to the backend.

**Acceptance Criteria:**
1. "Install" triggers `POST /api/v1/integrations/{type}/enable`, which records the integration as "configured" in the database.
2. On page load, integration statuses are fetched from the backend and used as the source of truth — the `statusOverrides` local state hack is removed.
3. An appropriate loading indicator is shown during the install mutation.
4. On error, the button reverts and shows an error message.
5. "Install" button navigates the user directly into the Configure form/modal (US-002) so they can enter credentials immediately.

---

### US-004 · Health – License Pane — Replace hardcoded sample data with real API data

**Priority:** P0 🔴  
**Page/Component:** `/pages/Health/LicensePane.tsx`  
**Source files:**
- `frontend/src/pages/Health/healthData.ts` — `LICENSE_SAMPLE`, `GHOST_MEMBERS`, `COPILOT_CROSS_REF`
- `frontend/src/pages/Health/LicensePane.tsx`

**Current behavior:**  
The entire License Health pane uses hardcoded constants:
- **Total seats / Seat limit / Utilization**: `{ totalSeats: 247, seatLimit: 300, utilizationPct: 82 }` (hardcoded)
- **Ghost members table**: 4 rows with fake usernames: `legacy-bot-1`, `contractor-old`, `ex-intern-3`, `svc-old-deploy`, all from 2025
- **Growth forecast**: hardcoded `74d` at `+3.2/month`
- **Copilot cross-reference**: hardcoded `200` total, `62` inactive

The pane does query `getSeatUtilizationReport` and uses real data for the top-level metrics when available (`hasRealSeatData` check), but the ghost members table **always** renders the hardcoded `GHOST_MEMBERS` array regardless of whether real data is present.

**Acceptance Criteria:**
1. Backend exposes `/api/v1/health/ghost-members` that returns members inactive ≥ 90 days derived from `org.add_member` / audit event gaps.
2. `LicensePane` queries this endpoint instead of rendering `GHOST_MEMBERS`.
3. The seat limit (`seatLimit`) is removed from hardcoded constants; it is either fetched from the GitHub Enterprise API or made configurable in Health Settings.
4. Growth forecast is computed from event frequency by the backend and returned by a dedicated API (e.g., `/api/v1/health/license-forecast`), not hardcoded.
5. `SampleDataBanner` is removed from `LicensePane` once real data is being shown.
6. Until real data is available, the ghost members table shows an empty state ("No ghost members detected — connect your audit log source") instead of fake rows.
7. `LICENSE_SAMPLE`, `GHOST_MEMBERS`, and `COPILOT_CROSS_REF` constants are deleted from `healthData.ts`.

---

### US-005 · Health – Maintenance Pane — Replace hardcoded sample data with real API data

**Priority:** P0 🔴  
**Page/Component:** `/pages/Health/MaintenancePane.tsx`  
**Source file:** `frontend/src/pages/Health/healthData.ts` — `STALE_PRS`, `UNHEALTHY_WEBHOOKS`, `SKIPPED_WORKFLOWS`

**Current behavior:**  
All three sections display hardcoded fake data:

- **Stale PRs**: `acme/legacy-payments #48`, `globex/api-v1 #91`, `acme/tools-old #12` (fake repos, static dates)
- **Unhealthy webhooks & apps**: `Webhook → api.external-partner.io`, `GitHub App: "old-ci-bot"`, `OAuth App: "legacy-deploy-tool"` (all fictional)
- **Skipped workflows**: `security-scan.yml` / `dependency-review.yml` / `codeql-analysis.yml` on fake repos with hardcoded Feb/Mar 2026 dates

**Acceptance Criteria:**
1. Backend computes stale PR signals from `pull_request.open` / `close` event gaps and exposes them at `/api/v1/health/stale-prs`.
2. Backend detects unhealthy webhooks/apps from `hook.*`, `integration.*`, and `oauth_access.*` events and returns them at `/api/v1/health/unhealthy-hooks`.
3. Backend identifies disabled/skipped workflows from `workflows.disabled_intentionally` and `workflow_run` skipped conclusions, returning them at `/api/v1/health/skipped-workflows`.
4. `MaintenancePane` queries all three endpoints and renders real data.
5. If any section returns empty results, a helpful empty state is shown ("No stale PRs detected in the last 90 days").
6. `SampleDataBanner` is removed once real data is flowing.
7. `STALE_PRS`, `UNHEALTHY_WEBHOOKS`, and `SKIPPED_WORKFLOWS` are deleted from `healthData.ts`.
8. The staleness threshold used for stale PRs matches the configured value in Health Settings (`stalePrDays`).

---

### US-006 · Health – WAF Insights Pane — Replace hardcoded findings with live evaluation

**Priority:** P0 🔴  
**Page/Component:** `/pages/Health/WafInsightsPane.tsx`  
**Source file:** `frontend/src/pages/Health/healthData.ts` — `WAF_FINDINGS`, `PILLAR_META`

**Current behavior:**  
The WAF Insights pane displays findings from a static `WAF_FINDINGS` array defined in `healthData.ts`. These findings are not evaluated against real audit log data — they are pre-populated placeholder assessments.

**Acceptance Criteria:**
1. Backend exposes `/api/v1/health/waf-findings` that evaluates WAF alignment signals against the ingested audit log data.
2. Each finding includes: `id`, `finding`, `pillar`, `severity` (`critical|warning|info`), `evaluated` (bool), `evidence` (array of source events), `status` (`pass|fail|warning`), and `detail`.
3. Unevaluated findings (those marked `API only` — requiring active GitHub API polling) are clearly marked and grouped separately.
4. `WafInsightsPane` queries this endpoint instead of reading `WAF_FINDINGS`.
5. `SampleDataBanner` is removed once real evaluation is available.
6. `WAF_FINDINGS` constant is deleted from `healthData.ts`.
7. The pillar summary cards update dynamically based on real evaluations.

---

### US-007 · Reports — Replace hardcoded report catalog with real generated reports

**Priority:** P0 🔴  
**Page/Component:** `/pages/Reports/index.tsx` — `REPORT_CATALOG`  
**Source file:** `frontend/src/pages/Reports/index.tsx` lines 21–56

**Current behavior:**  
The Reports page displays four hardcoded report entries from 2023/2024 that do not exist:
- "Monthly Security Posture — January 2024" (Generated Jan 15, 2024)
- "Engineering Velocity Q4 2023" (Generated Jan 1, 2024)
- "Access Review — Outside Collaborators and PAT Inventory" (Dec 28, 2023)
- "DORA Metrics — December 2023" (Generated Jan 2, 2024)

Clicking the "PDF" or "CSV" buttons calls `exportReport(r.type, 'pdf'/'csv')` on these fake report types. This will either 404 or return meaningless data.

**Acceptance Criteria:**
1. Backend exposes `GET /api/v1/reports/catalog` that returns a list of previously generated or on-demand-available reports, including: `id`, `type`, `title`, `generated_at`, `page_count`, `tags`, `status` (`ready|generating|failed`).
2. Backend exposes `POST /api/v1/reports/generate` to request a new report, returning a job ID.
3. `ReportsPage` queries `GET /api/v1/reports/catalog` and renders real entries.
4. PDF/CSV export buttons call `GET /api/v1/reports/{id}/export?format=pdf|csv` on real report IDs.
5. A "Generate new report" button allows users to request a new report by selecting a type and date range from a form.
6. While a report is generating, the entry shows a spinner and "Generating..." status.
7. If no reports exist yet, an empty state is shown: "No reports generated yet. Click 'Generate report' to create your first report."
8. The `REPORT_CATALOG` hardcoded constant is removed entirely.

---

## P1 — High: Core Feature Blocked or Data Is Wrong

---

### US-008 · Users Page — Replace hardcoded Active Users table with real session data

**Priority:** P1 🟠  
**Page/Component:** `/pages/Users/index.tsx` — `ACTIVE_USERS`  
**Source file:** `frontend/src/pages/Users/index.tsx` lines 32–37

**Current behavior:**  
The "Active users" section renders a hardcoded `ACTIVE_USERS` array with 4 fake entries including real-seeming usernames, static "last active" relative strings (e.g., "Just now", "12 min ago" — they never change), and hardcoded MFA status and session counts. Clicking on a session count opens a modal that shows the same hardcoded data. Clicking on a username navigates to `/events?actor={username}` which may find no real events for these fake users.

**Acceptance Criteria:**
1. Backend exposes `GET /api/v1/admin/sessions` returning active OctoWatch sessions: `login`, `role`, `last_active_at` (ISO timestamp), `mfa_enabled`, `session_count`.
2. `UsersPage` queries this endpoint and computes relative time using `formatRelativeTime(iso)` (already implemented in the file).
3. The MFA status is sourced from the auth provider or stored in the user profile, not hardcoded.
4. If the backend cannot provide session data, the section is hidden (not shown with fake data).
5. The `ACTIVE_USERS` constant is deleted.
6. Session detail modal shows real IP, user agent, and expiry if available from the backend.

---

### US-009 · Health Settings — Persist settings to backend

**Priority:** P1 🟠  
**Page/Component:** `/pages/Health/HealthSettings.tsx` — `handleSave()`  
**Source file:** `frontend/src/pages/Health/HealthSettings.tsx` lines ~102–107

**Current behavior:**  
The Save button executes:
```js
function handleSave() {
  // No backend endpoint yet — log and show toast
  console.log('Health settings saved:', settings);
  showToast('Settings saved successfully');
}
```
Settings are **not** persisted. On page reload, all values revert to `DEFAULTS`. The configured thresholds (stale repo days, dormant member days, PAT staleness, license utilization alert threshold, etc.) are not applied to any health signal queries.

**Acceptance Criteria:**
1. Backend exposes `GET /api/v1/health/settings` and `PUT /api/v1/health/settings` endpoints.
2. The settings schema matches the `HealthSettingsState` interface: `staleRepoDays`, `stalePrDays`, `unreviewedDependabotDays`, `ciSkippedConsecutive`, `dormantMemberDays`, `patNoExpiryFlag`, `patStaleDays`, `outsideCollabFlag`, `licenseUtilizationPct`, `ghostMemberCost`, `escalateCriticalDays`, `escalateStaleReposDays`, `escalateDormantDays`, `escalationDestination`.
3. `HealthSettingsPage` loads current settings from the API on mount using a React Query `useQuery`.
4. Save button calls `PUT /api/v1/health/settings` via a `useMutation`; loading state is shown on the button during the request.
5. Health signal queries in `LicensePane`, `MaintenancePane`, `AccessIdentityPane`, `RepoHealthPane` pass the configured thresholds as query parameters.
6. `console.log` call is removed.
7. Escalation destination options (`ESCALATION_OPTIONS`) are dynamically populated from connected integrations (i.e., Slack channels are listed only if Slack is connected).

---

### US-010 · Integrations — Remove duplicate Data Import sections

**Priority:** P1 🟠  
**Page/Component:** `/pages/Integrations/index.tsx`

**Current behavior:**  
The Integrations page has **two separate file upload sections** immediately below each other:

1. **"Data Import" section** (lines ~368–401): Contains two `ImportCard` components for "Audit Log Import" and "Copilot Metrics Import" that upload files directly to the client-side `handleFileImport()` function — which fakes a record count using `Math.random()` and stores results in local state only.
2. **"Import Data" section** (lines ~462–464): Contains the `<ManualIngestPanel />` component, which is the real API-backed implementation that calls `uploadFile`, shows real job status via `getIngestJob`, and lists jobs via `listIngestJobs`.

The two sections duplicate the same purpose but only the `ManualIngestPanel` is wired to real backend APIs.

**Acceptance Criteria:**
1. The standalone "Data Import" section containing `ImportCard` components is removed entirely.
2. `ManualIngestPanel` is the sole upload interface on the page.
3. `handleFileImport()` function, `ImportCard` component, `ImportDropZone` component, `LogFileIcon`, `MetricsFileIcon`, `UploadIcon`, and the local `RECENT_IMPORTS` hardcoded constant are all deleted.
4. The `ManualIngestPanel` section heading is renamed to "Data Import" for consistency.
5. The "Import Data" section is repositioned above the SyncPanel section.

---

### US-011 · Integrations — Remove hardcoded Recent Imports history

**Priority:** P1 🟠  
**Page/Component:** `/pages/Integrations/index.tsx` — `RECENT_IMPORTS`  
**Source file:** `frontend/src/pages/Integrations/index.tsx` lines 43–48

**Current behavior:**  
A hardcoded `RECENT_IMPORTS` array lists three fake file imports from May–June 2025:
```js
{ file: 'audit-log-2025-06-01.csv', type: 'Audit Log', size: '14.2 MB', importedAt: '2025-06-01 09:32', records: 48_210, status: 'Completed' },
{ file: 'copilot-metrics-may.json', type: 'Copilot Metrics', size: '2.1 MB', importedAt: '2025-05-28 14:15', records: 1_340, status: 'Completed' },
{ file: 'audit-log-2025-05-15.json', type: 'Audit Log', size: '38.7 MB', importedAt: '2025-05-15 11:04', records: 125_800, status: 'Completed' },
```
These are merged with real `importedFiles` state via `const allImports = [...importedFiles, ...RECENT_IMPORTS]` and displayed in the "Import history" table.

**Acceptance Criteria:**
1. `RECENT_IMPORTS` constant is deleted.
2. Import history is sourced exclusively from `ManualIngestPanel`'s real API (`listIngestJobs`).
3. If `ManualIngestPanel` is being used as the sole import interface (per US-010), this story is resolved as part of that ticket.

---

### US-012 · Dev Activity — Replace hardcoded team filter with real org team data

**Priority:** P1 🟠  
**Page/Component:** `/pages/DevActivity/index.tsx` — `TEAM_MEMBERS`, `TEAM_NAMES`  
**Source file:** `frontend/src/pages/DevActivity/index.tsx` lines 31–38

**Current behavior:**  
The team filter dropdown is populated from a hardcoded `TEAM_MEMBERS` object:
```js
const TEAM_MEMBERS: Record<string, readonly string[]> = {
  'platform-team': ['alice', 'david', 'sarah.chen', 'priya.patel'],
  'backend-team': ['bob', 'mike.ross', 'raj.kumar'],
  'frontend-team': ['carol', 'ana.silva', 'eremin', 'lisa.park'],
};
```
These team names and user assignments are entirely fictional. Selecting a team from the dropdown filters against these fake names, which will typically show zero results for real event data.

**Acceptance Criteria:**
1. Backend exposes `GET /api/v1/health/teams` (or similar) that returns org team memberships derived from `org.add_member` events, `team.add_member` events, and/or the GitHub Enterprise Teams API.
2. `DevActivityPage` uses React Query to load team definitions; the `selectedTeam` filter filters by real actor handles.
3. If no team data is available (org not synced yet), the team filter dropdown is hidden and a tooltip explains why.
4. `TEAM_MEMBERS` and `TEAM_NAMES` constants are deleted.

---

## P2 — Medium: Degraded Experience or Missing Functionality

---

### US-013 · Health – Repo Health Pane — Populate "unknown" table columns

**Priority:** P2 🟡  
**Page/Component:** `/pages/Health/RepoHealthPane.tsx` — `RepoHealthTable`  
**Source file:** `frontend/src/pages/Health/RepoHealthPane.tsx` lines ~115–140

**Current behavior:**  
The `RepoHealthTable` renders a 7-column table. Four columns are permanently `<Label variant="muted">unknown</Label>`:
- **Branch protection** — always "unknown"
- **Secret scanning** — always "unknown"
- **Dependabot alerts** — always "unknown"
- **CI health** — always "unknown"

Only "Last push" and "Overall" have real data.

**Acceptance Criteria:**
1. Backend `getRepoHealth` API is extended to return `branch_protection_enabled`, `secret_scanning_enabled`, `dependabot_alerts_count` (or `dependabot_enabled`) per repo, derived from `branch_protection_rule.*`, `repository.enable_vulnerability_alerts`, and `dependabot_alert.*` audit events.
2. `RepoHealthPane` renders these values with appropriate label variants (e.g., branch protection: `success` / `danger`).
3. If a field genuinely cannot be derived from available audit log events, the column is removed from the table rather than showing "unknown".
4. A source note below the table documents which audit events each column is derived from.

---

### US-014 · Threats — Add filter by actor / repository / rule

**Priority:** P2 🟡  
**Page/Component:** `/pages/Threats/index.tsx`

**Current behavior:**  
The Threats page has a "Filter" toggle that reveals only a `<select>` for severity filtering. There is no way to filter by actor (e.g., show all detections for `@suspicious-user`), or by repository, or by specific rule. The severity filter `<select>` uses an inline `style` rather than the app's component system.

**Acceptance Criteria:**
1. The filter bar expands to show three filter controls: **Severity** (existing), **Actor** (text input with debounce), **Rule** (select populated from `listRules`).
2. All three filter parameters are passed to `listDetections()` as query params.
3. Active filters are reflected in the URL as search params so they can be bookmarked/shared.
4. A "Clear filters" button appears when any filter is active.
5. The existing inline `style` on the severity `<select>` is replaced with a shared `styles.filterSelect` CSS class.

---

### US-015 · Rules — Add "Test rule" against sample events

**Priority:** P2 🟡  
**Page/Component:** `/pages/Rules/index.tsx`, `editor/`

**Current behavior:**  
The Rules page creates, edits, enables/disables, and deletes detection rules. There is no mechanism to test a rule against historical event data before publishing it. Users cannot tell if a new rule will produce false positives or whether the pattern/threshold config is correct.

**Acceptance Criteria:**
1. Rule creation/edit form has a "Test rule" button that calls `POST /api/v1/rules/test` with the rule's `logic_type` and `logic_config`.
2. The API returns a list of events from the last 7 days that would have matched this rule.
3. A modal displays the test results: number of matching events, list of up to 20 sample matches with actor, action, repo, and timestamp.
4. A "0 matches" result shows a warning ("This rule would not have triggered on the last 7 days of data — verify your pattern filters").

---

### US-016 · Reports — Fix PDF/CSV export for real report types

**Priority:** P2 🟡  
**Page/Component:** `/pages/Reports/index.tsx`

**Current behavior:**  
The data summary section at the top (MAU, Actions, Seat utilization, Copilot seat buckets) correctly shows real metric counts and clicking them opens a drill-down modal with real data. However, the "PDF" and "CSV" export buttons in the report catalog call `exportReport(r.type, 'pdf'/'csv')` where `r.type` is one of `'security_posture'`, `'engineering_velocity'`, `'access_review'`, `'dora_metrics'` — types that may not be implemented on the backend.

**Acceptance Criteria:** *(Dependent on US-007)*
1. Once the real report catalog (US-007) is implemented, PDF/CSV buttons call `GET /api/v1/reports/{id}/export?format=pdf|csv` and trigger a file download.
2. Button shows loading state while the export is generating.
3. If export fails, an inline error message is shown.
4. The data summary drill-down modal (already working) is preserved as-is.

---

### US-017 · Health – AppGovernance Pane — Remove SampleDataBanner that is not needed

**Priority:** P2 🟡  
**Page/Component:** `/pages/Health/AppGovernancePane.tsx`

**Current behavior:**  
`AppGovernancePane` shows a `SampleDataBanner` stating "App governance signals are derived from audit log events." However, the pane already queries real API endpoints (`getAppGovernance`, `getCodeScanning`, `getVulnerabilities`) and renders real data. The banner is misleading — this data is *not* sample data.

**Acceptance Criteria:**
1. `SampleDataBanner` is removed from `AppGovernancePane`.
2. If any specific metric in the pane cannot be derived from audit logs (similar to the "API only" WAF findings pattern), that metric shows a targeted empty-state note rather than a page-level banner.

---

### US-018 · Login — Correct misleading footer copy

**Priority:** P2 🟡  
**Page/Component:** `/pages/LoginPage.tsx`

**Current behavior:**  
The login page footer reads: "By signing in you agree to OctoWatch being installed in your organization."  
OctoWatch is a monitoring platform — it is not a GitHub App that gets "installed" into an organization. This copy implies a GitHub App OAuth installation flow that doesn't exist.

**Acceptance Criteria:**
1. Footer copy is updated to: "By signing in, you authorize OctoWatch to access your organization's audit log data."
2. A link to the privacy policy or terms of service is added if one exists.

---

## P3 — Low: Polish, UX, and Minor Improvements

---

### US-019 · Copilot – LicensePane — Improve empty state when no Copilot seat data is available

**Priority:** P3 🟢  
**Page/Component:** `/pages/Copilot/LicensePane.tsx`

**Current behavior:**  
When the Copilot Seats API returns no data, all four metric cards show `"—"` (dashes) with no explanation. The page renders an empty recommendations section with only the generic "Consider just-in-time provisioning" bullet.

**Acceptance Criteria:**
1. When `seatBuckets.length === 0`, the pane shows an empty state card: "No Copilot seat data available. Import a Copilot Metrics file on the Integrations page, or connect the Copilot Metrics API."
2. The empty state includes a link to `/integrations`.
3. Metric cards are not rendered when there is no data to display.

---

### US-020 · Dashboard — Add organization indicator and last-synced timestamp

**Priority:** P3 🟢  
**Page/Component:** `/pages/Dashboard/index.tsx`

**Current behavior:**  
The dashboard does not visibly indicate which GitHub organization's data is being shown, nor when the data was last synced. Users with multi-org setups may not know which org is active.

**Acceptance Criteria:**
1. The dashboard header shows the currently selected org name from `useOrg()` context (already available via the org switcher in the app shell).
2. A "Last synced: X minutes ago" subtitle is shown below the org name, derived from the system health endpoint data already fetched by the dashboard (`getSystemHealth`).
3. When org is "All orgs" (empty string), the header shows "All organizations".

---

### US-021 · Health – RepoHealth Pane — Remove hardcoded "private" repo visibility

**Priority:** P3 🟢  
**Page/Component:** `/pages/Health/RepoHealthPane.tsx` line ~118

**Current behavior:**  
Every row in the repository table renders a subtitle: `{r.org} · private` — the visibility is hardcoded as "private" regardless of the actual repo visibility.

**Acceptance Criteria:**
1. The `StaleRepo` type returned by `getRepoHealth` includes a `visibility` field (`'public' | 'private' | 'internal'`).
2. The repo row renders the actual visibility.
3. If visibility cannot be determined from audit log events, the subtitle shows only the org name (no "· private").

---

### US-022 · Threats — Improve empty state for "no detections" with actionable guidance

**Priority:** P3 🟢  
**Page/Component:** `/pages/Threats/index.tsx`

**Current behavior:**  
When no detections are found, the threat list shows only `<div className={styles.emptyRow}>No detections found</div>`.

**Acceptance Criteria:**
1. On the **Open** tab with 0 detections, show: "No open threats detected — all clear." with a green checkmark icon.
2. On the **Closed** tab with 0 detections, show: "No closed detections. Resolved detections will appear here."
3. If the threats list is empty because no audit log data has been imported yet, a link to `/integrations` is included.

---

### US-023 · Health – Maintenance Pane — Make stale PR threshold link to Health Settings

**Priority:** P3 🟢  
**Page/Component:** `/pages/Health/MaintenancePane.tsx`

**Current behavior:**  
The "Stale PRs" card header includes a note "open > configured threshold" but there is no link to the threshold configuration and the threshold is not displayed.

**Acceptance Criteria:**
1. The stale PR threshold (from Health Settings, `stalePrDays`) is displayed in the section header: `open > {stalePrDays} days`.
2. The threshold value is a clickable link that navigates to `/health/settings`.

---

### US-024 · Reports — Show org filter context on report entries

**Priority:** P3 🟢  
**Page/Component:** `/pages/Reports/index.tsx`

**Current behavior:**  
Each catalog entry in the report list appends `<Label variant="muted">{selectedOrg || 'All orgs'}</Label>`. This is already in the code and works correctly, but the org selector for generating new reports (once US-007 is implemented) should be part of the "Generate report" form.

**Acceptance Criteria:**
1. *(Dependent on US-007)* The "Generate report" form includes an org selector pre-populated from `useOrg()`.
2. Reports generated for a specific org clearly show the org name in the entry.

---

## Summary Table

| Story | Title | Priority | Page | Type |
|---|---|---|---|---|
| US-001 | Copilot Insights — Replace all static mock data | P0 🔴 | Copilot | Mock data |
| US-002 | Integrations — Implement real configuration forms | P0 🔴 | Integrations | Non-functional control |
| US-003 | Integrations — Persist "Install" action to backend | P0 🔴 | Integrations | Non-functional control |
| US-004 | Health License Pane — Replace hardcoded sample data | P0 🔴 | Health | Mock data |
| US-005 | Health Maintenance Pane — Replace hardcoded sample data | P0 🔴 | Health | Mock data |
| US-006 | Health WAF Insights — Replace hardcoded findings | P0 🔴 | Health | Mock data |
| US-007 | Reports — Replace hardcoded report catalog | P0 🔴 | Reports | Mock data |
| US-008 | Users — Replace hardcoded Active Users table | P1 🟠 | Users | Mock data |
| US-009 | Health Settings — Persist settings to backend | P1 🟠 | Health | Non-functional control |
| US-010 | Integrations — Remove duplicate Data Import sections | P1 🟠 | Integrations | Duplicate UI |
| US-011 | Integrations — Remove hardcoded Recent Imports history | P1 🟠 | Integrations | Mock data |
| US-012 | Dev Activity — Replace hardcoded team filter | P1 🟠 | Dev Activity | Mock data |
| US-013 | Repo Health Pane — Populate "unknown" columns | P2 🟡 | Health | Missing data |
| US-014 | Threats — Add actor/repo/rule filter | P2 🟡 | Threats | Missing feature |
| US-015 | Rules — Add "Test rule" functionality | P2 🟡 | Rules | Missing feature |
| US-016 | Reports — Fix PDF/CSV export | P2 🟡 | Reports | Non-functional control |
| US-017 | Health AppGovernance — Remove incorrect SampleDataBanner | P2 🟡 | Health | UX |
| US-018 | Login — Correct misleading footer copy | P2 🟡 | Login | Copy |
| US-019 | Copilot LicensePane — Improve empty state | P3 🟢 | Copilot | UX |
| US-020 | Dashboard — Add org indicator & last-synced timestamp | P3 🟢 | Dashboard | UX |
| US-021 | Repo Health — Remove hardcoded "private" visibility | P3 🟢 | Health | Mock data |
| US-022 | Threats — Improve empty state with actionable guidance | P3 🟢 | Threats | UX |
| US-023 | Maintenance Pane — Link threshold to Health Settings | P3 🟢 | Health | UX |
| US-024 | Reports — Org filter on report generation form | P3 🟢 | Reports | UX |

---

## Pages with No Significant Issues Found

The following pages are substantially properly connected to real APIs and have no major mock data or non-functional controls:

| Page | Status |
|---|---|
| **Login** (`/login`) | ✅ Functional — minor copy issue only (US-018) |
| **Dashboard** (`/dashboard`) | ✅ Live data from detections, events, health, actions APIs |
| **Threats** (`/threats`) | ✅ Live data — filter enhancement is improvement (US-014) |
| **Events** (`/events`) | ✅ Live data — search, pagination, CSV export all functional |
| **Velocity** (`/velocity`) | ✅ Live data from events and actions volume APIs |
| **Dev Activity** (`/devactivity`) | ⚠️ Live data foundations, but team filter is hardcoded (US-012) |
| **Query** (`/query`) | ✅ Live data — run, save, load templates all functional |
| **Rules** (`/rules`) | ✅ Live CRUD — test functionality missing (US-015) |
| **Health → Ops Health** | ✅ Live data from workflow and runner health signals |
| **Health → Security Posture** | ✅ Live data from SSO, secret scanning, privilege change signals |
| **Health → Access & Identity** | ✅ Live data from PAT health, bypass, external collaborators |
| **Health → App Governance** | ✅ Live data — incorrect banner (US-017) |
| **Health → Repo Health** | ⚠️ Live data for staleness, but 4 columns always show "unknown" (US-013) |
| **Users** (`/users`) | ⚠️ RBAC management is live, but Active Users table is hardcoded (US-008) |

---

## Recommended Implementation Order

Given the dependencies between stories, the recommended sprint order is:

**Sprint 1 (Foundation):**
- US-010 + US-011 (clean up duplicate import sections — quick win, removes confusion)
- US-018 (login copy — 5 minute fix)
- US-003 (persist Install to backend — enables US-002)
- US-009 (Health Settings backend — enables US-004, US-005, US-008)

**Sprint 2 (Health data):**
- US-004 (License Pane real data)
- US-005 (Maintenance Pane real data)
- US-006 (WAF Insights real evaluation)
- US-013 (Repo Health unknown columns)
- US-017 (remove incorrect AppGovernance banner)

**Sprint 3 (Copilot & Reports):**
- US-001 (Copilot backend API + frontend)
- US-007 (Reports catalog backend)
- US-016 (Reports export)

**Sprint 4 (Users, Integrations, Dev Activity):**
- US-002 (Integration config forms — largest story, needs per-integration backend work)
- US-008 (Users active sessions)
- US-012 (Dev Activity real teams)

**Sprint 5 (Polish):**
- US-014 (Threats advanced filters)
- US-015 (Rules test functionality)
- US-019 through US-024 (UX polish)
