# OctoWatch — Implementation Plan
**Version**: 1.0  
**Date**: 2026-03-28  
**Author**: Strategy & Design Agent  
**Status**: Approved for Architecture Review

---

## 1. Executive Summary

A comprehensive codebase audit of OctoWatch (commit date 2026-03-27) identified **30 issues** spanning four severity tiers. The core finding is a **production UX crisis**: every major feature pane—Copilot Insights, Health sub-tabs, Reports, and Users—renders hardcoded placeholder data that is visible to end-users with no path to live data. This is compounded by three backend crash vectors (ticketing service `NotImplementedError`, silent JSON parse failures in import scripts, and an abstract worker method reachable at runtime) and a completely non-functional E2E test suite.

**Recommended approach**: Deliver in four sequential phases.

| Phase | Theme | Duration Estimate | Issues |
|-------|-------|-------------------|--------|
| P0 | Backend Crash Prevention | Sprint 1 | #2, #3, #4 |
| P1 | Live Data + E2E Infra | Sprints 2–4 | #1, #5–#15, #27 |
| P2 | Config Hardening & UI Completeness | Sprints 5–6 | #16–#24 |
| P3 | Observability, Docs & Roadmap | Sprint 7+ | #25–#30 |

No new technology is required. All work is achievable within the existing FastAPI + React/TypeScript + PostgreSQL + TailwindCSS stack.

---

## 2. Prioritized Epics

### Epic 1 — BE-STABILITY: Backend Crash Prevention
**Priority**: P0 (Critical)  
**Effort**: S (< 3 days)  
**Description**: Eliminate three production crash vectors in the backend before any other work proceeds. The ticketing service `NotImplementedError` will crash any unsupported integration at runtime; the abstract worker `NotImplementedError` can crash the ingestion pipeline; silent JSON failures in import scripts cause undetected data loss.  
**Issues**: #2, #3, #4  
**Rationale**: Crashes in production are deal-breakers regardless of UX state. These are small, surgical fixes with high risk reduction.

---

### Epic 2 — TEST-INFRA: E2E Test Infrastructure
**Priority**: P0 (Critical)  
**Effort**: M (3–5 days)  
**Description**: Unblock the Playwright E2E suite by implementing authenticated `storageState`, re-enabling all commented-out smoke tests, and adding navigation tests. The test suite currently provides zero coverage of authenticated routes—the entire app after login.  
**Issues**: #1, #27  
**Rationale**: Without authenticated E2E tests, every UI change ships without regression coverage. This must be in place before the P1 UI work begins.

---

### Epic 3 — COPILOT-DATA: Copilot Insights Live Data
**Priority**: P1 (High)  
**Effort**: L (1–2 weeks)  
**Description**: Replace all hardcoded/illustrative data in Copilot Insights sub-tabs (Overview, Adoption, Models & Features, Anomalies) with API-driven data. Remove "This data is illustrative" banners and replace with real loading/empty states. Consolidate `COST_PER_SEAT` into a single org-level config.  
**Issues**: #5, #20  
**Rationale**: Copilot cost tracking is a primary value proposition of OctoWatch. Shipping with "illustrative" banners visible to customers destroys trust.

---

### Epic 4 — HEALTH-DATA: Health Pane Live Data
**Priority**: P1 (High)  
**Effort**: L (1–2 weeks)  
**Description**: Replace all static/hardcoded data in the three Health sub-panes (License ghost members, Maintenance fake PRs/workflows, WAF static findings) with API-backed data. Fix the incorrect "sample data" banner shown on panes where real data exists.  
**Issues**: #6, #7, #8, #15  
**Rationale**: Health metrics are the second major value driver. License ghost member detection and WAF findings are only useful if they reflect real org state.

---

### Epic 5 — REPORTS-USERS: Reports & Users Live Data
**Priority**: P1 (High)  
**Effort**: M (3–5 days)  
**Description**: Replace fake report catalog entries (from 2023/2024) and static fake user/session data in the Users page with live API responses. Implement real "last active" timestamps from session records.  
**Issues**: #9, #10  
**Rationale**: An admin viewing fake users (`sarah.chen`, `mike.ross`) will lose confidence in the entire platform's data integrity.

---

### Epic 6 — DASHBOARD-COMPLETE: Dashboard & DORA Completeness
**Priority**: P1 (High)  
**Effort**: L (1–2 weeks)  
**Description**: Implement the two missing stat pills on the dashboard (pipeline success, API calls 24h), build the four DORA metrics charts (deployment frequency, lead time, MTTR, change failure rate), and fix the hardcoded team filter in Developer Activity.  
**Issues**: #11, #12, #13  
**Rationale**: The dashboard is the first screen users see. Missing stat pills and absent DORA charts undermine the engineering velocity story.

---

### Epic 7 — RULES-DETECT: Rule Testing Feature
**Priority**: P1 (High)  
**Effort**: M (3–5 days)  
**Description**: Implement the rule testing feature end-to-end: a "Test rule" button in the Rules UI that sends a sample payload to a new `/api/v1/rules/{id}/test` backend endpoint and displays matched/unmatched results.  
**Issues**: #14  
**Rationale**: Without a test harness, operators cannot safely validate detection rule changes before enabling them in production.

---

### Epic 8 — CONFIG-OBS: Config Hardening & Observability
**Priority**: P2 (Medium)  
**Effort**: M (3–5 days)  
**Description**: Move hardcoded `JWT_TTL_SECONDS` default to env-var documentation (it already reads from env but the default is not documented in `.env.example`), expose OpenAPI/Swagger UI endpoint, add startup warning when GeoIP DB is missing, narrow broad `except Exception` in `database.py`, and convert `print()` in import scripts to structured logger calls.  
**Issues**: #16, #17, #18, #19, #26  
**Rationale**: Config hardening is a security requirement; OpenAPI docs unblock API consumers; GeoIP silence causes invisible enrichment failures.

---

### Epic 9 — UI-COMPLETE: UI Completeness (TopBar, Dev Activity, Integrations)
**Priority**: P2 (Medium)  
**Effort**: L (1–2 weeks)  
**Description**: Implement the org-tab segmented control and "New report" button in the TopBar (WS-1), complete the Developer Activity detail panel (WS-3), wire the Events Explorer search bar (WS-4), and fix the Developer Activity filtering (WS-6).  
**Issues**: #21, #22, #23, #24  
**Rationale**: These are workflow-breaking UI gaps. The Events Explorer search being non-functional means analysts cannot filter events—a core audit use case.

---

### Epic 10 — DOCS-CODE-QUALITY: Code Quality & Documentation
**Priority**: P3 (Low)  
**Effort**: S (< 3 days)  
**Description**: Add docstrings to `query_service.py`, `rbac_service.py`, and `workers/ingestion/base.py`. Configure Playwright `storageState` auth setup file.  
**Issues**: #25, #27  
**Rationale**: Security-critical code without documentation presents onboarding and audit risk. Low effort, high long-term value.

---

### Epic 11 — ROADMAP: Webhook Ingestion, Alerting, Container Scanning
**Priority**: P3 (Low)  
**Effort**: XL (multi-sprint)  
**Description**: Implement GitHub webhook receiver for real-time event ingestion, wire detection engine to Slack/email alerting channels, add Trivy container scanning to CI pipeline.  
**Issues**: #28, #29, #30  
**Rationale**: Net-new features from the public roadmap. Valuable but not blockers for current functionality.

---

## 3. User Stories

> **Notation**: All file paths are relative to the repository root.

---

### US-001 — Fix Silent JSON Parse Errors in Import Scripts

**Epic**: BE-STABILITY  
**Priority**: P0  
**As a** platform operator running bulk data imports,  
**I want** all JSON parse errors to be logged with context (file name, line number, error message),  
**so that** I can diagnose data ingestion failures and know exactly which records were skipped.

**Acceptance Criteria**:

1. **Given** `import_local.py` encounters a line that cannot be parsed as JSON, **when** the line is skipped, **then** a structured log entry at `WARNING` level is emitted containing `file`, `line_number`, `error`, and `raw_line_preview` (first 200 chars).
2. **Given** `import_copilot_usage.py`'s `_parse_stream()` call at L35–37 encounters a malformed line, **when** it is skipped, **then** a `WARNING` log entry is emitted with the same fields (not a bare `print()` to stderr).
3. **Given** `import_copilot_usage.py`'s outer file-level parse failure at L55–58 occurs, **when** the function falls back or aborts, **then** an `ERROR` log entry is emitted with `file`, `error`, and `records_recovered` count.
4. **Given** an import run with 5 malformed lines completes, **when** it finishes, **then** the summary log line includes `parse_errors: 5` alongside `imported` count.
5. **Given** a completely valid file is imported, **when** it finishes, **then** no warning or error log lines are emitted.

**Technical Notes**:
- Files: `backend/import_local.py` (L40–43 `except json.JSONDecodeError: pass`), `backend/import_copilot_usage.py` (L35–37 and L55–58).
- Import scripts use `print()` today; replace with `import structlog; logger = structlog.get_logger()` or the app's existing `logging` setup.
- `parse_errors` counter already accumulates in `import_local.py`; it is never logged — add a final log call.

**Definition of Done**:
- [ ] Both files emit structured WARNING/ERROR logs on parse failures.
- [ ] `parse_errors` summary field present in completion log.
- [ ] Unit tests verify warning is emitted for a malformed line in each script.
- [ ] No bare `pass` blocks remain in JSON parse except-clauses.

---

### US-002 — Handle Unsupported Ticketing Platforms Gracefully

**Epic**: BE-STABILITY  
**Priority**: P0  
**As a** platform operator who may configure an unsupported ticketing integration,  
**I want** the backend to return a structured `422 Unprocessable Entity` error instead of crashing with `NotImplementedError`,  
**so that** the API remains stable and integrators receive a clear, actionable message.

**Acceptance Criteria**:

1. **Given** a detection is created and a ticketing config with `platform = "pagerduty"` (unsupported) is active, **when** the ticketing service is called, **then** the service raises `ValueError` (not `NotImplementedError`) with message `"Unsupported ticketing platform: pagerduty"`.
2. **Given** the router catches this `ValueError`, **when** it returns a response, **then** the HTTP status code is `422` with a JSON body `{"detail": "Unsupported ticketing platform: pagerduty"}`.
3. **Given** `platform` is `"jira"` or `"github"`, **when** the service dispatches, **then** no error is raised and existing behavior is unchanged.
4. **Given** the unsupported-platform path is hit, **when** the error is raised, **then** a `logger.warning("ticketing.unsupported_platform", platform=...)` entry appears in the application log.
5. **Given** the existing router error handler tests in `backend/tests/test_exception_handlers.py`, **when** a `ValueError` is raised from a service, **then** the test suite passes without modification.

**Technical Notes**:
- File: `backend/app/services/ticketing_service.py` L67 (`raise NotImplementedError`).
- Change `raise NotImplementedError(...)` to `raise ValueError(...)`.
- Confirm existing exception handler middleware in `main.py` maps `ValueError` to 422; if not, add a handler.
- The existing `except Exception` in the same function already logs and re-raises — keep that behaviour, just swap the exception type.

**Definition of Done**:
- [ ] `NotImplementedError` removed from `ticketing_service.py`.
- [ ] API returns 422 for unsupported platform, not 500.
- [ ] Unit test added covering unsupported platform path.
- [ ] `logger.warning` present before raising.

---

### US-003 — Guard Abstract Ingestion Worker Against Direct Instantiation

**Epic**: BE-STABILITY  
**Priority**: P0  
**As a** backend engineer developing a new ingestion worker,  
**I want** the abstract base class to fail fast at class definition time if `_normalize_event` is not overridden,  
**so that** an incomplete worker never reaches production and crashes the ingestion pipeline.

**Acceptance Criteria**:

1. **Given** `AbstractIngestWorker` uses Python's `abc.ABC` + `@abstractmethod` decorator on `_normalize_event` (or equivalent), **when** a concrete subclass is defined without implementing `_normalize_event`, **then** Python raises `TypeError` at instantiation time, not at the call site during ingestion.
2. **Given** all existing concrete workers (`LocalFileIngestWorker`, `CopilotUsageIngestWorker`, etc.) implement `_normalize_event`, **when** they are instantiated, **then** no `TypeError` is raised and the pipeline runs normally.
3. **Given** the abstract method is decorated with `@abstractmethod`, **when** `mypy` is run, **then** no new type errors are introduced.
4. **Given** `base.py` L375 previously raised `NotImplementedError` at call time, **when** the fix is applied, **then** that line is replaced with the abstract method mechanism.
5. **Given** a developer adds a new worker and forgets to implement `_normalize_event`, **when** they run tests, **then** instantiation fails with a clear `TypeError: Can't instantiate abstract class ... without an implementation for abstract method '_normalize_event'`.

**Technical Notes**:
- File: `backend/app/workers/ingestion/base.py` L375.
- Add `from abc import ABC, abstractmethod` if not already imported.
- Decorate `_normalize_event` with `@abstractmethod`; mark class as inheriting `ABC`.
- Verify all subclasses in `backend/app/workers/ingestion/` implement the method.

**Definition of Done**:
- [ ] `AbstractIngestWorker` inherits `ABC`.
- [ ] `_normalize_event` decorated with `@abstractmethod`.
- [ ] All concrete worker subclasses verified to implement the method.
- [ ] `mypy` passes with no new errors.
- [ ] Test added that confirms `TypeError` on direct instantiation attempt.

---

### US-004 — Implement Authenticated Playwright E2E Smoke Tests

**Epic**: TEST-INFRA  
**Priority**: P0  
**As a** CI engineer running the test pipeline,  
**I want** Playwright smoke tests to exercise every authenticated route using a saved session state,  
**so that** regressions in any protected page are caught automatically on every pull request.

**Acceptance Criteria**:

1. **Given** `e2e/auth.setup.ts` runs as a Playwright "setup" project, **when** it completes, **then** a valid session state file is saved to `e2e/.auth/user.json` that grants access to all protected routes.
2. **Given** the setup project succeeds, **when** the main smoke test suite runs, **then** all 11 protected routes (dashboard, threats, events, velocity, dev-activity, copilot, reports, query, rules, users, integrations) are visited and their primary heading is visible.
3. **Given** any route returns an HTTP error or redirects to `/login`, **when** the test runs, **then** it fails with a descriptive assertion message.
4. **Given** the `playwright.config.ts` has a `"setup"` project dependency added to the main project, **when** `playwright test` is run from CI, **then** setup runs before smoke tests automatically.
5. **Given** the smoke tests complete, **when** they are all passing, **then** the two existing files (`e2e/smoke.spec.ts`, `e2e/navigation.spec.ts`) have all TODO comments resolved and all `test.skip` / commented-out blocks restored to active tests.

**Technical Notes**:
- Files: `frontend/e2e/smoke.spec.ts`, `frontend/e2e/navigation.spec.ts`, `frontend/playwright.config.ts`.
- Create `frontend/e2e/auth.setup.ts` following Playwright's [auth docs](https://playwright.dev/docs/auth).
- Auth flow: POST credentials to `/auth/login` or trigger GitHub OAuth mock; capture cookie/token; `page.context().storageState({ path: 'e2e/.auth/user.json' })`.
- Add `e2e/.auth/` to `.gitignore`.
- The auth setup file must use a dedicated test user (env vars `E2E_USER` / `E2E_PASS`) not a production credential.

**Definition of Done**:
- [ ] `auth.setup.ts` created and saves session state.
- [ ] `playwright.config.ts` updated with `setup` project.
- [ ] All 11 route smoke tests pass in CI.
- [ ] All TODO / commented-out test blocks removed.
- [ ] `e2e/.auth/` in `.gitignore`.

---

### US-005 — Replace Copilot Overview Pane Illustrative Data with Live API Data

**Epic**: COPILOT-DATA  
**Priority**: P1  
**As an** admin monitoring Copilot adoption,  
**I want** the Copilot Overview pane to show real metrics from the Copilot Metrics API,  
**so that** the seat utilization, acceptance rates, and cost figures reflect my organization's actual usage.

**Acceptance Criteria**:

1. **Given** the Copilot Metrics API has data for an org, **when** the Overview pane loads, **then** all six metric cards (acceptance rate, active seats, total seats, inactive+never, lines accepted, chat turns) are populated from API responses—not hardcoded values.
2. **Given** the API returns data, **when** the pane renders, **then** the "This data is illustrative" banner at `OverviewPane.tsx` L559, L570, and L582 is NOT shown.
3. **Given** the API call is in flight, **when** the pane first renders, **then** a loading skeleton is shown in place of each metric card.
4. **Given** the API returns an error or empty dataset, **when** the pane renders, **then** an empty state message is shown (e.g., "No Copilot usage data available. Import data or connect the API.") and the illustrative banner is NOT shown.
5. **Given** the `COST_PER_SEAT` is configured at the org level (see US-020), **when** the cost calculation runs, **then** it uses the org-level value, not the hardcoded `19` from `copilotData.ts`.

**Technical Notes**:
- Files: `frontend/src/pages/Copilot/OverviewPane.tsx` (L559, L570, L582), `frontend/src/pages/Copilot/copilotData.ts` (L1).
- API endpoint: confirm existing `/api/v1/copilot/metrics` or equivalent; wire via React Query hook.
- Remove `COST_PER_SEAT` export from `copilotData.ts`; read from org config API (see US-020).
- Follow existing query hook patterns in the codebase (e.g., how `useEvents` is structured).

**Definition of Done**:
- [ ] All three "illustrative" banners removed from `OverviewPane.tsx`.
- [ ] Metric cards populated from API.
- [ ] Loading skeleton shown during fetch.
- [ ] Empty state shown when no data.
- [ ] `COST_PER_SEAT` constant removed from `copilotData.ts`.
- [ ] Unit tests verify banner is absent when data is present.

---

### US-006 — Replace Copilot Anomalies Pane Illustrative Data with Live API Data

**Epic**: COPILOT-DATA  
**Priority**: P1  
**As a** security analyst reviewing Copilot usage anomalies,  
**I want** the Anomalies pane to show real anomaly detections from the backend,  
**so that** I can investigate actual unusual Copilot activity in my organization.

**Acceptance Criteria**:

1. **Given** the backend has Copilot anomaly detection results, **when** the Anomalies pane loads, **then** the anomaly list is populated from the `/api/v1/copilot/anomalies` endpoint (or equivalent).
2. **Given** the API returns data, **when** the pane renders, **then** the "This data is illustrative" banner at `AnomaliesPane.tsx` L131 is NOT shown.
3. **Given** zero anomalies are present, **when** the pane renders, **then** an empty state ("No anomalies detected") is shown—not sample anomaly rows.
4. **Given** anomaly data is loading, **when** the pane renders, **then** a loading skeleton is shown.
5. **Given** the Anomalies tab has a badge count, **when** live data is loaded, **then** the badge reflects the actual anomaly count from the API (not a hardcoded "3").

**Technical Notes**:
- File: `frontend/src/pages/Copilot/AnomaliesPane.tsx` L131.
- Confirm whether `GET /api/v1/copilot/anomalies` exists; if not, add it (ticket for backend team).
- Tab badge count in the parent page must read from API response, not a hardcoded constant.

**Definition of Done**:
- [ ] "Illustrative" banner removed.
- [ ] Anomaly list from API.
- [ ] Empty state when no anomalies.
- [ ] Tab badge count from API.
- [ ] Unit test added.

---

### US-007 — Replace Copilot Models Pane Illustrative Data with Live API Data

**Epic**: COPILOT-DATA  
**Priority**: P1  
**As an** engineering manager tracking Copilot model adoption,  
**I want** the Models & Features pane to show real model and editor usage breakdowns,  
**so that** I can identify which AI models and editors my team actually uses.

**Acceptance Criteria**:

1. **Given** Copilot usage data is available, **when** the Models pane loads, **then** the model usage spread (GPT-4o, Claude, o3-mini, etc.) reflects real API data, not static illustrative values.
2. **Given** the API returns data, **when** the pane renders, **then** all three "illustrative" banners at `ModelsPane.tsx` L149, L181, and L213 are NOT shown.
3. **Given** a model appears in the API response, **when** it is rendered, **then** the usage percentage is calculated from real data.
4. **Given** a model does NOT appear in the API response, **when** the pane renders, **then** it is omitted from the display (not shown with a zero or placeholder).
5. **Given** no data is available, **when** the pane renders, **then** an appropriate empty state message is shown.

**Technical Notes**:
- File: `frontend/src/pages/Copilot/ModelsPane.tsx` (L149, L181, L213).
- Model/feature breakdown data source: `/api/v1/copilot/metrics` aggregated by model and editor fields.

**Definition of Done**:
- [ ] All three "illustrative" banners removed.
- [ ] Model, feature, and editor data from API.
- [ ] Empty state when no data.
- [ ] Unit tests updated.

---

### US-008 — Replace Health License Pane Ghost Members with Live Data

**Epic**: HEALTH-DATA  
**Priority**: P1  
**As an** admin managing GitHub license costs,  
**I want** the License sub-pane to show real ghost/inactive member data from my org,  
**so that** I can accurately identify seats to reclaim and reduce license spend.

**Acceptance Criteria**:

1. **Given** the license data API returns ghost member records, **when** the License pane loads, **then** the ghost member rows reflect real usernames from the org—not hardcoded fake values.
2. **Given** `LicensePane.tsx` L61 previously always rendered fake ghost rows, **when** the fix is applied, **then** those rows are only shown when the API returns members matching the ghost/inactive criteria.
3. **Given** the API returns zero ghost members, **when** the pane renders, **then** an empty state ("No ghost members detected") is shown instead of fake rows.
4. **Given** ghost member data is loading, **when** the pane renders, **then** loading skeletons replace the row area.
5. **Given** the `COST_PER_SEAT_DEFAULT` in `healthData.ts` L5 is used, **when** org-level config is available (see US-020), **then** the cost calculation uses the org-configured value.

**Technical Notes**:
- File: `frontend/src/pages/Health/LicensePane.tsx` L61.
- API: confirm `/api/v1/health/license` or equivalent ghost-member endpoint.
- `COST_PER_SEAT_DEFAULT` in `healthData.ts` L5 to be deprecated once US-020 lands.

**Definition of Done**:
- [ ] Hardcoded fake ghost member rows removed from `LicensePane.tsx`.
- [ ] Rows rendered from API data only.
- [ ] Empty state present.
- [ ] Loading state present.
- [ ] Unit tests cover both data and empty states.

---

### US-009 — Replace Health Maintenance Pane Fake PRs/Workflows with Live Data

**Epic**: HEALTH-DATA  
**Priority**: P1  
**As a** platform engineer monitoring repository health,  
**I want** the Maintenance sub-pane to show real stale PRs and failing workflows from my organization,  
**so that** the maintenance signals reflect actual technical debt.

**Acceptance Criteria**:

1. **Given** the maintenance API returns stale PR data, **when** `MaintenancePane.tsx` renders, **then** PR rows show real repo names (not `acme/legacy-payments #48`, `globex/api-v1 #91`) dynamically fetched from the API.
2. **Given** the API returns workflow health data, **when** the pane renders, **then** workflow entries reflect real workflow run outcomes—not hardcoded static values from the previous L190 block.
3. **Given** zero stale PRs are present, **when** the pane renders, **then** an empty state ("No stale PRs detected") is shown.
4. **Given** the API is loading, **when** the pane first renders, **then** skeleton loaders appear in the PR and workflow sections.
5. **Given** a PR row's repository is clicked, **when** the user navigates, **then** the link points to the real GitHub repository URL from the API response.

**Technical Notes**:
- File: `frontend/src/pages/Health/MaintenancePane.tsx` L190 (hardcoded PR rows).
- API: confirm `/api/v1/health/maintenance` or derive from existing events/workflow data.

**Definition of Done**:
- [ ] Hardcoded PR/workflow rows removed from `MaintenancePane.tsx`.
- [ ] Data rendered from API.
- [ ] Empty and loading states.
- [ ] Links use real GitHub URLs.
- [ ] Unit tests.

---

### US-010 — Replace Health WAF Insights Pane Static Findings with Live Data

**Epic**: HEALTH-DATA  
**Priority**: P1  
**As a** security engineer reviewing the Well-Architected Framework assessment,  
**I want** WAF findings to reflect actual analysis of my org's GitHub posture,  
**so that** the assessment is actionable rather than illustrative.

**Acceptance Criteria**:

1. **Given** the WAF assessment API returns findings for an org, **when** `WafInsightsPane.tsx` renders, **then** the findings list is populated from the API, not from a static `WAF_FINDINGS` array.
2. **Given** findings have pillar categories (governance, appsec, architecture, collaboration, productivity), **when** they are rendered, **then** the pillar icons and labels from `PILLAR_META` in `healthData.ts` are correctly applied.
3. **Given** zero WAF findings are returned (fully compliant org), **when** the pane renders, **then** an empty state "No findings — well-architected!" is shown.
4. **Given** WAF data is loading, **when** the pane renders, **then** skeleton loaders are shown.
5. **Given** a finding has a `url` field referencing the WAF library, **when** rendered, **then** the link opens in a new tab with `rel="noopener noreferrer"`.

**Technical Notes**:
- File: `frontend/src/pages/Health/WafInsightsPane.tsx` (static `WAF_FINDINGS` array).
- `PILLAR_META` in `healthData.ts` is correct metadata and should be retained.
- API: confirm `/api/v1/health/waf` endpoint exists or add it.

**Definition of Done**:
- [ ] Static `WAF_FINDINGS` array removed or converted to a fallback.
- [ ] Findings from API.
- [ ] Pillar metadata applied correctly.
- [ ] Empty and loading states.
- [ ] Links use `rel="noopener noreferrer"`.
- [ ] Unit tests.

---

### US-011 — Fix Incorrect Sample Data Banner on Health Panes with Real Data

**Epic**: HEALTH-DATA  
**Priority**: P1  
**As an** admin viewing Health metrics,  
**I want** the "sample data" banner to only appear when demo/illustrative data is being shown,  
**so that** I am not misled about the accuracy of real data being displayed.

**Acceptance Criteria**:

1. **Given** a Health sub-pane is displaying live API data, **when** it renders, **then** NO sample data / illustrative banner is shown.
2. **Given** a Health sub-pane is in demo mode (no API data available and a fallback is in use), **when** it renders, **then** the banner IS shown with clear text explaining how to link real data.
3. **Given** the banner logic uses a boolean prop or context flag, **when** the flag is `false` (live data), **then** all banner elements have `display: none` or are unmounted.
4. **Given** a pane successfully fetches real data and later receives an error refresh, **when** the error occurs, **then** the banner does not reappear; instead, an error toast is shown.
5. **Given** all three Health panes (License, Maintenance, WAF) are fixed, **when** they load with real data, **then** no banner is visible in any of them.

**Technical Notes**:
- Relevant to all Health sub-panes; tracked from issue US-017 in existing docs.
- Introduce a `isLiveData: boolean` prop on each pane; set to `true` when API data is present.
- Consolidate banner component to a single reusable `<SampleDataBanner />`.

**Definition of Done**:
- [ ] Banner absent on all three panes when real data is present.
- [ ] Banner shown only when in fallback/demo mode.
- [ ] Reusable `SampleDataBanner` component created.
- [ ] Unit tests verify banner visibility for both states.

---

### US-012 — Replace Reports Catalog Fake Entries with Live API Data

**Epic**: REPORTS-USERS  
**Priority**: P1  
**As a** compliance officer viewing generated reports,  
**I want** the Reports page to list real, generated reports from the backend,  
**so that** I can download and share actual compliance evidence rather than placeholder entries.

**Acceptance Criteria**:

1. **Given** the reports API returns generated report records, **when** the Reports page loads, **then** the catalog lists real report entries with accurate titles, generation dates, and file sizes.
2. **Given** the `REPORT_CATALOG` array in `frontend/src/pages/Reports/index.tsx` contained four fake reports dated 2023/2024, **when** the fix is applied, **then** that static array is removed and replaced by an API call.
3. **Given** zero reports have been generated, **when** the page loads, **then** an empty state ("No reports generated yet. Create your first report.") is shown with a CTA button.
4. **Given** a report entry is rendered, **when** the user clicks PDF or CSV export, **then** the browser downloads the file from the correct backend URL.
5. **Given** reports are loading, **when** the page renders, **then** skeleton loader cards are shown.

**Technical Notes**:
- File: `frontend/src/pages/Reports/index.tsx` (static `REPORT_CATALOG` array).
- API: `GET /api/v1/reports` — confirm endpoint exists.
- Plan.md WS-8 tasks (8.1–8.3) apply here; style per mockup alongside this data fix.

**Definition of Done**:
- [ ] Static `REPORT_CATALOG` removed.
- [ ] Reports loaded from API.
- [ ] Empty state present.
- [ ] Loading skeleton present.
- [ ] PDF/CSV download links use real backend URLs.
- [ ] Unit tests.

---

### US-013 — Replace Users Page Fake Sessions with Live Session Data

**Epic**: REPORTS-USERS  
**Priority**: P1  
**As an** admin managing user access,  
**I want** the Users page to show real active user sessions with accurate "last active" timestamps,  
**so that** I can audit who has active sessions and revoke them if needed.

**Acceptance Criteria**:

1. **Given** the sessions API returns active session records, **when** the Users page loads, **then** the active users table shows real usernames and session data — not the hardcoded `ACTIVE_USERS` array with `sarah.chen`, `mike.ross`.
2. **Given** the table is populated from the API, **when** a "last active" timestamp is shown, **then** it is a relative time derived from the session's actual `last_activity_at` field (e.g., "3 minutes ago"), not a static string that never updates.
3. **Given** a row is present for a session, **when** the admin clicks "Revoke session", **then** a `DELETE /api/v1/sessions/{id}` (or equivalent) call is made and the session is removed from the list on success.
4. **Given** zero active sessions exist other than the admin's own, **when** the page loads, **then** the table shows an empty state ("No other active sessions").
5. **Given** the sessions list is loading, **when** the page renders, **then** skeleton rows are shown.

**Technical Notes**:
- File: `frontend/src/pages/Users/index.tsx` (static `ACTIVE_USERS` array).
- API: `GET /api/v1/users/sessions` or `GET /api/v1/sessions` — verify endpoint.
- Relative timestamp: use `date-fns` `formatDistanceToNow()` or equivalent already in project.
- Consider polling interval (30s) to keep "last active" current.

**Definition of Done**:
- [ ] Static `ACTIVE_USERS` array removed.
- [ ] Session data from API.
- [ ] Relative timestamps update correctly.
- [ ] Session revocation works.
- [ ] Empty state shown when no other sessions.
- [ ] Unit tests for both populated and empty states.

---

### US-014 — Implement Dashboard Pipeline Success and API Calls Stat Pills

**Epic**: DASHBOARD-COMPLETE  
**Priority**: P1  
**As a** DevOps engineer monitoring platform health,  
**I want** to see pipeline success rate and API call volume directly on the Dashboard,  
**so that** I can immediately spot degradation in automation health.

**Acceptance Criteria**:

1. **Given** the dashboard loads, **when** the stat pills row renders, **then** a "Pipeline success" pill shows the percentage of successful workflow runs in the last 24 hours.
2. **Given** the dashboard loads, **when** the stat pills row renders, **then** an "API calls (24h)" pill shows the total GitHub API call count for the last 24 hours.
3. **Given** backend data is unavailable for a pill, **when** the pill renders, **then** it shows a `—` placeholder (not a crash or missing element).
4. **Given** the mockup specifies 5 stat pills total, **when** the dashboard renders, **then** all five pills (events today, open threats, pipeline success, active devs, API calls) are visible in the correct order.
5. **Given** the pills auto-refresh on a 60-second interval, **when** the interval fires, **then** values update without a full page reload.

**Technical Notes**:
- Files: Dashboard component in `frontend/src/` (identify exact path, likely `frontend/src/pages/Dashboard/`).
- Plan.md WS-2 tasks 2.1 and 2.2 directly map here.
- Backend: may require a new `/api/v1/metrics/summary` endpoint or derive from existing events queries.
- `pipeline_success_rate` can be derived from `workflow_runs` table: `success_count / total_count * 100` in last 24h.

**Definition of Done**:
- [ ] Both new stat pills present and rendering API data.
- [ ] All five pills present per mockup spec.
- [ ] Fallback `—` for unavailable data.
- [ ] 60-second auto-refresh implemented.
- [ ] Unit tests for each new pill component.

---

### US-015 — Implement DORA Metrics Charts on Engineering Velocity Page

**Epic**: DASHBOARD-COMPLETE  
**Priority**: P1  
**As an** engineering manager assessing delivery performance,  
**I want** to see DORA metrics charts (deployment frequency, lead time for changes, MTTR, change failure rate) on the Engineering Velocity page,  
**so that** I can track our team's software delivery performance against industry benchmarks.

**Acceptance Criteria**:

1. **Given** the Engineering Velocity page loads, **when** the 2×2 chart grid renders, **then** four charts are present: Lead Time for Changes (line/area), Change Failure Rate (area with threshold), Workflow Success Rate (area), and Daily Deployments (bar chart).
2. **Given** chart data is loaded from the API, **when** a data point is hovered, **then** a tooltip shows the exact value and date.
3. **Given** the DORA tier calculation runs, **when** the tier badge renders top-right, **then** it displays one of: "Elite", "High", "Medium", "Low" based on DORA benchmark thresholds.
4. **Given** the "Most active repositories" table is present, **when** it renders, **then** it shows columns: repo, commits, PRs merged, CFR, MTTR, contributors — populated from API data.
5. **Given** chart data is loading, **when** the section renders, **then** skeleton chart placeholders are shown (not blank space).

**Technical Notes**:
- Files: Engineering Velocity page in `frontend/src/pages/` (likely `EngineeringVelocity/` or `Velocity/`).
- Plan.md WS-5 tasks 5.1–5.5 map directly here.
- Chart library: use whatever charting library is already installed (check `package.json`).
- DORA thresholds per official DORA report: Elite = daily deploys, <1h lead time, <5% CFR, <1h MTTR.
- Backend data: derive from `workflow_runs` and events tables.

**Definition of Done**:
- [ ] All four DORA charts present and populated from API.
- [ ] Tooltips working.
- [ ] DORA tier badge component implemented.
- [ ] "Most active repositories" table present.
- [ ] Loading skeletons.
- [ ] Unit tests for chart rendering with mock data.

---

### US-016 — Fix Developer Activity Team Filter to Use API Data

**Epic**: DASHBOARD-COMPLETE  
**Priority**: P1  
**As a** team lead filtering Developer Activity by my team,  
**I want** the team filter buttons to show the actual teams configured in the system,  
**so that** I am not filtering by hardcoded teams that may not exist in my organization.

**Acceptance Criteria**:

1. **Given** the system has teams configured (e.g., "platform-team", "security-team"), **when** the Developer Activity page loads, **then** the team filter buttons reflect the actual teams returned by `GET /api/v1/teams` (or equivalent).
2. **Given** a previously hardcoded team name is not in the API response, **when** the page loads, **then** that team button does NOT appear.
3. **Given** the currently selected team filter changes, **when** the API call is made, **then** it includes the selected team as a query parameter and the developer cards update.
4. **Given** the API returns zero teams, **when** the filter section renders, **then** only the "All teams" button is shown (no error state).
5. **Given** teams are loading, **when** the filter renders, **then** skeleton pill buttons are shown while loading.

**Technical Notes**:
- File: Developer Activity page in `frontend/src/pages/DevActivity/` or equivalent.
- Plan.md WS-6, US-012 in the original docs.
- API: `GET /api/v1/teams` — confirm endpoint or link to RBAC team list endpoint.

**Definition of Done**:
- [ ] Hardcoded team list removed.
- [ ] Teams loaded from API.
- [ ] "All teams" always present.
- [ ] Selected team filters developer cards.
- [ ] Loading skeletons for filter buttons.
- [ ] Unit tests.

---

### US-017 — Implement Rule Testing Feature

**Epic**: RULES-DETECT  
**Priority**: P1  
**As a** security analyst managing detection rules,  
**I want** to test a rule against a sample event payload before enabling it in production,  
**so that** I can validate rule logic without risking false positives or missed detections on live data.

**Acceptance Criteria**:

1. **Given** a rule is open in the Rules editor, **when** the user clicks "Test rule", **then** a modal opens with a JSON payload editor pre-populated with a sample event matching the rule's category.
2. **Given** the user edits the payload and clicks "Run test", **when** the request is sent to `POST /api/v1/rules/{id}/test` with the payload body, **then** the response shows "Matched" or "Unmatched" with the reason.
3. **Given** the rule matches the payload, **when** the result is shown, **then** the matched fields are highlighted and a summary message "Rule would trigger" is displayed in green.
4. **Given** the rule does NOT match the payload, **when** the result shows, **then** the unmatched fields are indicated and the message "Rule would not trigger" is displayed in amber.
5. **Given** the test endpoint receives a request, **when** the rule logic is evaluated, **then** no detection record is created in the database (dry-run only).

**Technical Notes**:
- Frontend: `frontend/src/pages/Rules/` — add "Test rule" button to rule row.
- Backend: add `POST /api/v1/rules/{id}/test` endpoint in `backend/app/routers/rules.py`.
- Backend service: add `test_rule(rule_id, payload) -> TestResult` to `detection_service.py` or new `rule_test_service.py`.
- `TestResult` schema: `{ matched: bool, reason: str, matched_fields: list[str] }`.
- Must be a dry-run — no side effects, no DB writes.

**Definition of Done**:
- [ ] "Test rule" button in Rules UI.
- [ ] Test payload modal with pre-populated sample.
- [ ] `POST /api/v1/rules/{id}/test` endpoint implemented.
- [ ] Matched/unmatched result display.
- [ ] No DB writes on test.
- [ ] Unit tests for backend endpoint.
- [ ] E2E test for modal open/close and result display.

---

### US-018 — Make JWT TTL Configurable via Environment Variable

**Epic**: CONFIG-OBS  
**Priority**: P2  
**As a** security engineer deploying OctoWatch,  
**I want** the JWT session TTL to be configurable via an environment variable,  
**so that** I can enforce stricter or longer session policies without modifying code.

**Acceptance Criteria**:

1. **Given** `JWT_TTL_SECONDS` has a default of `3600` in `AuthSettings`, **when** the env var `JWT_TTL_SECONDS=7200` is set, **then** `settings.JWT_TTL_SECONDS` returns `7200`.
2. **Given** `JWT_TTL_SECONDS` is not set in the environment, **when** the app starts, **then** it uses the default of `3600` and logs `auth.jwt_ttl_seconds_default` at INFO level on startup.
3. **Given** the `.env.example` file exists, **when** updated, **then** it includes `JWT_TTL_SECONDS=3600  # JWT and session TTL in seconds` with an explanatory comment.
4. **Given** the `AuthSettings.JWT_TTL_SECONDS` field at `config.py` L70 has `default=3600`, **when** a value is set via env, **then** pydantic-settings picks it up without code changes.
5. **Given** the test suite in `backend/tests/test_config.py`, **when** it runs with `JWT_TTL_SECONDS=1800` set in the test environment, **then** `settings.JWT_TTL_SECONDS == 1800`.

**Technical Notes**:
- File: `backend/app/config.py` L70 — the field already supports env var override via pydantic-settings. The issue is documentation and a missing startup log.
- Add startup log in `app/main.py` lifespan: `logger.info("auth.config", jwt_ttl_seconds=settings.JWT_TTL_SECONDS)`.
- Update `backend/.env.example` with the `JWT_TTL_SECONDS` entry.

**Definition of Done**:
- [ ] `.env.example` documents `JWT_TTL_SECONDS`.
- [ ] Startup log emitted showing configured TTL.
- [ ] Test confirms env var override works.
- [ ] `config.py` field description updated to note it is configurable.

---

### US-019 — Expose OpenAPI/Swagger UI Documentation Endpoint

**Epic**: CONFIG-OBS  
**Priority**: P2  
**As an** integration developer consuming the OctoWatch API,  
**I want** an interactive Swagger UI available at `/docs` and a ReDoc view at `/redoc`,  
**so that** I can explore the API, understand request/response schemas, and test endpoints without reading source code.

**Acceptance Criteria**:

1. **Given** the FastAPI app runs, **when** a browser navigates to `/docs`, **then** the Swagger UI renders with all registered API routes and their schemas.
2. **Given** a user navigates to `/redoc`, **when** the page loads, **then** ReDoc renders the full API spec.
3. **Given** the app runs in production mode (`ENV=production`), **when** accessing `/docs`, **then** the endpoint requires authentication (authenticated user with `admin` role or restricted by IP allowlist config) — docs must not be publicly accessible.
4. **Given** the API spec is generated, **when** `/openapi.json` is fetched, **then** all routers' endpoints appear with correct tags, summary text, and response models.
5. **Given** the Swagger UI is open, **when** the user clicks "Authorize" and provides a JWT token, **then** authenticated endpoints can be tested directly from the browser.

**Technical Notes**:
- File: `backend/app/main.py` — FastAPI enables `/docs` and `/redoc` by default unless `docs_url=None`. Confirm current setting.
- If disabled, re-enable with `app = FastAPI(docs_url="/docs", redoc_url="/redoc")`.
- For production auth protection: add a dependency on `/docs` using `Depends(require_admin)` or restrict via nginx (preferred — see `nginx/nginx.conf`).
- Ensure all routers have meaningful `tags=` and `summary=` on routes for useful docs.

**Definition of Done**:
- [ ] `/docs` renders Swagger UI in development.
- [ ] `/redoc` renders ReDoc in development.
- [ ] Production mode protects `/docs` (auth or IP restriction).
- [ ] All router tags updated for organized docs display.
- [ ] Runbook updated with reference to `/docs`.

---

### US-020 — Add Startup Warning When GeoIP Database is Missing

**Epic**: CONFIG-OBS  
**Priority**: P2  
**As a** platform operator deploying OctoWatch,  
**I want** the application to emit a clear startup warning when the GeoIP database is not found,  
**so that** I am not silently running without IP enrichment without realising it.

**Acceptance Criteria**:

1. **Given** `GEOIP_DB_PATH` is set but the file does not exist at that path, **when** the app starts, **then** a `WARNING` log is emitted: `"geoip.db_not_found path=<path> — IP enrichment disabled"`.
2. **Given** the GeoIP DB is found and readable, **when** the app starts, **then** an `INFO` log is emitted: `"geoip.db_loaded path=<path>"`.
3. **Given** the warning is emitted, **when** the app continues to run, **then** ingestion proceeds normally (enrichment is best-effort), but all events have null geo fields.
4. **Given** `MAXMIND_LICENSE_KEY` is set, **when** the GeoIP DB is missing, **then** the startup warning also includes a hint: `"Set GEOIP_DB_PATH or place the mmdb file at the default location"`.
5. **Given** the app is running in a container without the GeoIP file mounted, **when** it starts, **then** the warning is clearly visible in container logs (not buried in DEBUG output).

**Technical Notes**:
- File: `backend/app/services/geoip_service.py` — add startup check, or hook into `app/main.py` lifespan startup.
- Pattern: `if not Path(settings.GEOIP_DB_PATH).exists(): logger.warning("geoip.db_not_found", ...)`.
- Also update `docs/runbook.md` to mention the GeoIP DB setup step.

**Definition of Done**:
- [ ] Startup WARNING emitted when DB missing.
- [ ] Startup INFO emitted when DB loaded.
- [ ] Warning includes actionable hint text.
- [ ] Runbook updated with GeoIP setup instructions.
- [ ] Unit test mocking file absence verifies warning call.

---

### US-021 — Narrow Broad Exception Handler in database.py

**Epic**: CONFIG-OBS  
**Priority**: P2  
**As a** backend engineer debugging database issues,  
**I want** the database connection handler to catch only specific, expected exceptions,  
**so that** unexpected errors surface immediately rather than being swallowed silently.

**Acceptance Criteria**:

1. **Given** `database.py` L66–71 has a broad `except Exception` block, **when** refactored, **then** it catches only `sqlalchemy.exc.SQLAlchemyError` (and appropriate subclasses) rather than all exceptions.
2. **Given** a `KeyboardInterrupt` or `SystemExit` is raised during DB initialization, **when** the broad handler is removed, **then** these signals propagate correctly and are not swallowed.
3. **Given** a `SQLAlchemyError` is caught, **when** it is logged, **then** the log entry includes `error_type`, `error_message`, and (if applicable) `pgcode`.
4. **Given** the existing tests in `backend/tests/` pass before the change, **when** after the change, **then** all existing tests still pass.
5. **Given** the narrowed handler is in place, **when** an unexpected non-DB exception occurs, **then** it propagates to the FastAPI exception handlers normally.

**Technical Notes**:
- File: `backend/app/database.py` L66–71.
- Import: `from sqlalchemy.exc import SQLAlchemyError, OperationalError`.
- Replace `except Exception` with `except (SQLAlchemyError, ConnectionRefusedError)` as appropriate for the context.

**Definition of Done**:
- [ ] `except Exception` removed from `database.py`.
- [ ] Specific exception types listed.
- [ ] `KeyboardInterrupt`/`SystemExit` not swallowed.
- [ ] Existing test suite passes.
- [ ] Code review confirms no other broad handlers in `database.py`.

---

### US-022 — Consolidate COST_PER_SEAT into Org-Level Configuration

**Epic**: CONFIG-OBS  
**Priority**: P2  
**As an** admin configuring OctoWatch for my organization,  
**I want** the Copilot seat cost to be configurable per organization in the UI,  
**so that** cost calculations across all panes reflect our actual contracted price.

**Acceptance Criteria**:

1. **Given** two hardcoded definitions exist — `COST_PER_SEAT = 19` in `copilotData.ts` L1 and `COST_PER_SEAT_DEFAULT = 19` in `healthData.ts` L5 — **when** this story is complete, **then** both are replaced by a value fetched from `GET /api/v1/orgs/{org}/config`.
2. **Given** an admin navigates to org settings, **when** they update the "Copilot seat cost" field and save, **then** `PATCH /api/v1/orgs/{org}/config` persists the new value.
3. **Given** the per-org cost is set to `39`, **when** any pane calculates seat waste or cost, **then** it uses `39`, not `19`.
4. **Given** no org-specific cost is configured, **when** cost is calculated, **then** the system falls back to a global default (`19`) defined only in backend config.
5. **Given** the org config endpoint is called, **when** RBAC is checked, **then** only users with `admin` or `owner` role for that org can read or write the cost field.

**Technical Notes**:
- Frontend: `frontend/src/pages/Copilot/copilotData.ts` (L1), `frontend/src/pages/Health/healthData.ts` (L5).
- Backend: add `copilot_cost_per_seat: float` to org config model/table.
- New API: `GET /api/v1/orgs/{org}/config`, `PATCH /api/v1/orgs/{org}/config`.
- RBAC: enforce `admin`/`owner` role check on write path.

**Definition of Done**:
- [ ] Both hardcoded constants removed from frontend.
- [ ] Value fetched from org config API.
- [ ] Admin can update cost via UI and it persists.
- [ ] Fallback to global default when not configured.
- [ ] RBAC enforced on write.
- [ ] Unit tests for API endpoints.

---

### US-023 — Implement TopBar Org Tabs and New Report Button

**Epic**: UI-COMPLETE  
**Priority**: P2  
**As an** admin managing multiple GitHub organizations,  
**I want** org selector tabs in the TopBar and a "New report" button,  
**so that** I can quickly switch between orgs and initiate reports from any screen.

**Acceptance Criteria**:

1. **Given** the user has access to multiple orgs, **when** the TopBar renders, **then** a segmented-button tab control shows each org name with the active org highlighted.
2. **Given** the user clicks a different org tab, **when** the selection changes, **then** the global org filter context updates and all data-loading pages re-fetch for the newly selected org.
3. **Given** a "+ Add org" tab is present, **when** the user clicks it, **then** a modal opens to configure a new org connection.
4. **Given** the user is on any page, **when** they click "New report", **then** a report creation modal opens (or the Reports page opens with the creation modal pre-opened).
5. **Given** the user has only one org configured, **when** the TopBar renders, **then** org tabs are shown with a single tab (no clutter) or a simplified single-org label.

**Technical Notes**:
- Files: TopBar component in `frontend/src/` (confirm exact path).
- Plan.md WS-1 tasks 1.1–1.5 map here.
- Global org state: use existing `OrgContext` or React Query global state — do not create a new state system.
- User initial avatar: derive from `useAuth()` user object `login` field.

**Definition of Done**:
- [ ] Org tabs present in TopBar.
- [ ] Tab selection updates global org filter.
- [ ] "+ Add org" button opens modal.
- [ ] "New report" button present and functional.
- [ ] User initials avatar from auth context.
- [ ] Unit tests for tab switching.

---

### US-024 — Complete Developer Activity Detail Panel

**Epic**: UI-COMPLETE  
**Priority**: P2  
**As a** team lead reviewing individual developer contributions,  
**I want** the Developer Activity detail panel to show complete information when a developer card is clicked,  
**so that** I can assess individual contribution patterns, flag concerns, and take action.

**Acceptance Criteria**:

1. **Given** the user clicks on a developer card, **when** the detail panel opens, **then** it shows: avatar, name, handle, team, contribution stats (commits, PRs authored, reviews, comments), and a recent activity timeline.
2. **Given** the detail panel is open, **when** it renders, **then** all sections are populated from API data — not placeholders or empty sections.
3. **Given** the detail panel has action buttons (per mockup), **when** they are rendered, **then** at minimum "View GitHub profile" and "Schedule onboarding" are functional links/actions.
4. **Given** the panel is open on a small viewport (mobile), **when** it renders, **then** it overlays the developer grid as a full-width drawer rather than a side panel.
5. **Given** the panel is open, **when** the user presses Escape or clicks outside, **then** the panel closes.

**Technical Notes**:
- File: Developer Activity page component (confirm path in `frontend/src/pages/`).
- Plan.md WS-3 (detail panel) and WS-6 tasks apply.
- API: `GET /api/v1/developers/{login}/activity` — confirm exists.
- Keyboard accessibility: Escape key must close panel; focus trapped inside when open.

**Definition of Done**:
- [ ] Detail panel complete with all sections populated from API.
- [ ] Action buttons present and wired.
- [ ] Mobile drawer behavior.
- [ ] Escape-to-close and focus trap.
- [ ] Accessibility: `role="dialog"`, `aria-labelledby`.
- [ ] Unit tests.

---

### US-025 — Wire Events Explorer Search Bar to API

**Epic**: UI-COMPLETE  
**Priority**: P2  
**As a** security analyst querying audit events,  
**I want** the Events Explorer search bar to actually filter results,  
**so that** I can find specific events by actor, action, or repository without manually scanning the full log.

**Acceptance Criteria**:

1. **Given** the user types `action:repo.*` into the search bar, **when** the input is parsed, **then** a filter chip is created and the events table re-fetches from `GET /api/v1/events?action=repo.*`.
2. **Given** the user adds multiple filters (e.g., `org:acme-corp` and `action:repo.*`), **when** both chips are active, **then** the API call includes both as query params and results are AND-filtered.
3. **Given** the user clicks "Export CSV", **when** the button is clicked, **then** `GET /api/v1/events/export?format=csv&<filters>` is called and the browser downloads the file.
4. **Given** the user clicks "Save query", **when** activated, **then** a modal prompts for a query name and `POST /api/v1/query-templates` saves it.
5. **Given** a filter chip is present, **when** the user clicks the × on the chip, **then** the filter is removed and the table re-fetches without that filter.

**Technical Notes**:
- File: Events Explorer page (confirm path in `frontend/src/pages/Events/` or similar).
- Plan.md WS-4 tasks 4.1–4.5 map here.
- Search parsing: `key:value` syntax tokenizer — reuse or build a small `parseFilterChips(query: string)` utility.
- Export: confirm `GET /api/v1/events/export` endpoint exists in backend routers.

**Definition of Done**:
- [ ] Search bar creates filter chips from `key:value` input.
- [ ] Chips passed as query params to events API.
- [ ] Multi-filter AND logic works.
- [ ] "Export CSV" downloads file.
- [ ] "Save query" persists template.
- [ ] Chip removal triggers re-fetch.
- [ ] Unit tests for filter parsing utility.

---

### US-026 — Fix Developer Activity Filtering

**Epic**: UI-COMPLETE  
**Priority**: P2  
**As a** team lead viewing Developer Activity,  
**I want** filter controls (team, date range, activity type) to actually filter the displayed developer cards,  
**so that** I can focus on the subset of developers relevant to my analysis.

**Acceptance Criteria**:

1. **Given** a team filter is selected, **when** the filter is applied, **then** only developer cards belonging to that team are shown; others are hidden or not fetched.
2. **Given** a date range filter is applied, **when** the API is called, **then** the `from` and `to` date params are included and the activity stats reflect that period.
3. **Given** an activity type filter (e.g., "PRs authored") is selected, **when** applied, **then** the developer cards' primary metric displays the selected activity dimension.
4. **Given** all filters are cleared, **when** the page re-renders, **then** all developers in the selected org are shown.
5. **Given** no developers match the active filters, **when** the page renders, **then** an empty state ("No developers match the current filters") is shown.

**Technical Notes**:
- File: Developer Activity page (confirm path).
- Plan.md WS-6 items 6.1–6.4 and US-024 overlap.
- Ensure filter state is in URL query params for shareability (`useSearchParams`).

**Definition of Done**:
- [ ] Team filter hides non-matching cards.
- [ ] Date range passed to API.
- [ ] Activity type filter changes displayed metric.
- [ ] Clear-all resets to full list.
- [ ] Filters reflected in URL query params.
- [ ] Unit tests.

---

### US-027 — Add Docstrings to Security-Critical Service Files

**Epic**: DOCS-CODE-QUALITY  
**Priority**: P3  
**As a** backend engineer onboarding to OctoWatch,  
**I want** `query_service.py`, `rbac_service.py`, and `workers/ingestion/base.py` to have module-level and function-level docstrings,  
**so that** I can understand the intent and security implications of complex code without reading the implementation in full.

**Acceptance Criteria**:

1. **Given** `query_service.py` lacks docstrings on public methods, **when** updated, **then** each public method has a Google-style docstring describing: purpose, params, return value, and any security note (e.g., "User input is parameterized; never interpolated into SQL").
2. **Given** `rbac_service.py` has permission-checking functions, **when** updated, **then** each function documents what role is required and what happens if access is denied.
3. **Given** `workers/ingestion/base.py` has a complex abstract base class, **when** updated, **then** the class docstring describes the template method pattern, expected subclass contract, and deduplication logic.
4. **Given** docstrings are added, **when** `pydoc` or any doc generator is run, **then** they render without syntax errors.
5. **Given** no logic is changed, **when** the test suite runs after adding docstrings, **then** all tests pass without modification.

**Technical Notes**:
- Files: `backend/app/services/query_service.py`, `backend/app/services/rbac_service.py`, `backend/app/workers/ingestion/base.py`.
- Style: Google-style docstrings (as used elsewhere in the project, if a standard exists; otherwise establish one).
- Security notes especially important for: SQL construction in `query_service.py`, role hierarchy in `rbac_service.py`.

**Definition of Done**:
- [ ] All three files have module-level docstrings.
- [ ] All public methods/functions have docstrings.
- [ ] Security notes present where relevant.
- [ ] No logic changes.
- [ ] Test suite still passes.

---

### US-028 — Replace print() in Import Scripts with Structured Logger

**Epic**: DOCS-CODE-QUALITY  
**Priority**: P3  
**As a** platform operator monitoring import job health via log aggregation,  
**I want** import scripts to emit structured JSON log entries instead of `print()` to stderr,  
**so that** import job telemetry appears in my centralized logging system alongside other application logs.

**Acceptance Criteria**:

1. **Given** `import_local.py` uses `print()` for status output, **when** updated, **then** all `print()` calls are replaced with `structlog` (or `logging`) calls at appropriate levels (INFO for progress, WARNING for parse issues, ERROR for failures).
2. **Given** `import_copilot_usage.py` uses `print()` similarly, **when** updated, **then** all `print()` calls are replaced in the same manner.
3. **Given** the scripts are run, **when** logging is configured for JSON output (e.g., `LOG_FORMAT=json`), **then** log entries are valid JSON objects.
4. **Given** a successful import completes, **when** logs are viewed, **then** an `INFO` entry includes `records_imported`, `parse_errors`, `source_file`, and `duration_seconds`.
5. **Given** an operator redirects stderr to `/dev/null`, **when** the script runs, **then** progress information is not lost (because it now goes to the structured logger, which routes to stdout/file per config).

**Technical Notes**:
- Files: `backend/import_local.py`, `backend/import_copilot_usage.py`.
- Use the same logger setup as `backend/app/` (import `structlog` or the app's configured `logging`).
- Replace `print(..., file=sys.stderr)` patterns throughout.
- This partially overlaps with US-001 (which addresses the missing logging on parse errors specifically).

**Definition of Done**:
- [ ] All `print()` calls removed from both import scripts.
- [ ] Structured log calls at appropriate levels.
- [ ] JSON log format works when `LOG_FORMAT=json` is set.
- [ ] Summary log entry with import stats.
- [ ] Manual smoke test verifying log output format.

---

### US-029 — Configure Playwright Auth Setup File

**Epic**: DOCS-CODE-QUALITY  
**Priority**: P3  
**As a** CI engineer maintaining the test pipeline,  
**I want** Playwright's `storageState` auth setup to be fully documented and runnable without manual steps,  
**so that** any developer can run the full authenticated E2E suite locally with a single command.

**Acceptance Criteria**:

1. **Given** `frontend/e2e/auth.setup.ts` exists (created in US-004), **when** `playwright test --project=setup` is run, **then** it completes successfully and creates `e2e/.auth/user.json`.
2. **Given** the test user credentials are stored in `.env.test` (not committed), **when** `auth.setup.ts` reads them, **then** it uses `process.env.E2E_USER` and `process.env.E2E_PASS`.
3. **Given** the `playwright.config.ts` has the setup project dependency configured, **when** `playwright test` is run without `--project=setup`, **then** setup runs automatically first.
4. **Given** a developer has no `.env.test` file, **when** they run E2E tests, **then** an error message explains the missing variables and points to the setup guide.
5. **Given** the `CONTRIBUTING.md` or `frontend/README.md` is updated, **when** a developer reads it, **then** the E2E setup steps are clearly documented (create `.env.test`, run setup, run tests).

**Technical Notes**:
- Files: `frontend/playwright.config.ts`, `frontend/e2e/auth.setup.ts` (create), `frontend/.env.test.example` (create).
- Also update `CONTRIBUTING.md` with E2E setup section.
- Note: US-004 is the primary delivery vehicle; this story ensures the auth config is documented and resilient.

**Definition of Done**:
- [ ] `auth.setup.ts` runnable locally.
- [ ] Credentials from env vars.
- [ ] `playwright.config.ts` auto-runs setup.
- [ ] Clear error when env vars missing.
- [ ] `CONTRIBUTING.md` updated with setup steps.

---

### US-030 — Implement GitHub Webhook Receiver for Real-Time Event Ingestion

**Epic**: ROADMAP  
**Priority**: P3  
**As a** security engineer monitoring GitHub in real time,  
**I want** OctoWatch to receive GitHub audit log events via webhook push,  
**so that** security events appear within seconds of occurrence rather than waiting for the next scheduled import.

**Acceptance Criteria**:

1. **Given** a GitHub org has the OctoWatch webhook URL configured, **when** a GitHub audit event is sent as a webhook POST, **then** OctoWatch responds with HTTP 200 within 500ms.
2. **Given** the webhook request arrives, **when** the signature is verified using `X-Hub-Signature-256` against `WEBHOOK_SECRET`, **then** only valid-signature payloads are processed; invalid signatures return 401.
3. **Given** a valid webhook payload is received, **when** it is queued, **then** a Celery/background task processes and ingests it through the existing `AbstractIngestWorker` pipeline within 5 seconds.
4. **Given** the webhook endpoint receives a duplicate event (same `_document_id`), **when** processed, **then** the deduplication layer prevents a duplicate DB row.
5. **Given** the webhook service is not reachable or errors occur, **when** GitHub retries the webhook, **then** OctoWatch idempotently handles re-delivery.

**Technical Notes**:
- New file: `backend/app/routers/webhooks.py` — `POST /api/v1/webhooks/github`.
- HMAC signature verification: `hmac.compare_digest` — must be timing-safe.
- Enqueue via existing Celery workers in `backend/app/workers/`.
- Reuse `AbstractIngestWorker` and dedup logic.
- Add `WEBHOOK_SECRET` to `config.py` as a required env var when webhook is enabled.
- Security: reject payloads > 25MB; use constant-time HMAC comparison.

**Definition of Done**:
- [ ] `POST /api/v1/webhooks/github` endpoint implemented.
- [ ] HMAC signature verification with constant-time comparison.
- [ ] Payload enqueued to Celery worker.
- [ ] Deduplication works for re-delivered events.
- [ ] `WEBHOOK_SECRET` in `config.py` and `.env.example`.
- [ ] Unit tests for: valid signature, invalid signature (401), duplicate event.
- [ ] Load test: 100 webhook calls/second without issue.

---

### US-031 — Implement Slack and Email Alerting on Detection Events

**Epic**: ROADMAP  
**Priority**: P3  
**As a** security analyst on call,  
**I want** to receive Slack messages and email notifications when a detection rule fires,  
**so that** I can respond to threats immediately rather than checking the dashboard periodically.

**Acceptance Criteria**:

1. **Given** a detection is created with severity `critical` or `high`, **when** the detection is persisted, **then** a Slack message is sent to the configured channel within 30 seconds.
2. **Given** a user has email alerts enabled for their account, **when** a detection in their watched orgs fires, **then** an email is sent to their verified address within 2 minutes.
3. **Given** Slack is not configured (`SLACK_WEBHOOK_URL` absent), **when** a detection fires, **then** no error is raised; the platform logs `alerting.slack_not_configured` at DEBUG level.
4. **Given** the Slack message is sent, **when** received in Slack, **then** it includes: severity emoji, detection title, affected org/repo, link to the detection detail page in OctoWatch.
5. **Given** an alert delivery fails (Slack API error), **when** the failure occurs, **then** it is logged at `ERROR` level with `alert_id`, `channel`, and `error`; a retry is attempted up to 3 times with exponential backoff.

**Technical Notes**:
- The existing `ticketing_service.py` demonstrates the integration pattern; follow it for `alerting_service.py`.
- New file: `backend/app/services/alerting_service.py`.
- Enqueue via Celery so detection endpoint returns fast.
- `SLACK_WEBHOOK_URL` and `ALERT_EMAIL_FROM` in `config.py`.
- Email delivery: use existing SMTP config or add `SMTP_HOST/PORT/USER/PASS`.

**Definition of Done**:
- [ ] Slack alerting for critical/high detections.
- [ ] Email alerting per user preference.
- [ ] Graceful no-op when services not configured.
- [ ] Retry with exponential backoff.
- [ ] Unit tests with mocked Slack/SMTP.
- [ ] Integration test stub.

---

### US-032 — Add Trivy Container Scanning to CI Pipeline

**Epic**: ROADMAP  
**Priority**: P3  
**As a** security engineer responsible for OctoWatch's supply chain,  
**I want** container images to be scanned for known CVEs on every build,  
**so that** vulnerable base images or dependencies are caught before deployment.

**Acceptance Criteria**:

1. **Given** a pull request is opened, **when** the CI pipeline runs, **then** a Trivy scan of the built Docker images (`backend/Dockerfile`, `frontend/Dockerfile`) is included.
2. **Given** Trivy finds a CRITICAL or HIGH CVE, **when** the scan completes, **then** the CI step fails and the PR cannot be merged.
3. **Given** Trivy finds only MEDIUM or lower CVEs, **when** the scan completes, **then** the CI step passes with a warning comment on the PR listing the findings.
4. **Given** the scan completes, **when** results are available, **then** they are uploaded as a SARIF artifact visible in the GitHub Security tab.
5. **Given** a base image is updated to patch a CVE, **when** the next CI run triggers, **then** the scan passes without changing Trivy config.

**Technical Notes**:
- Add Trivy scan step to existing CI (confirm whether GitHub Actions or another CI platform is used — check `.github/` or CI config files).
- Use `aquasecurity/trivy-action@v0` for GitHub Actions.
- SARIF upload: `github/codeql-action/upload-sarif`.
- Exit code: `--exit-code 1` for CRITICAL/HIGH, `--exit-code 0` for lower.

**Definition of Done**:
- [ ] Trivy scan step in CI pipeline for both Dockerfiles.
- [ ] CRITICAL/HIGH CVEs fail CI.
- [ ] SARIF uploaded to GitHub Security tab.
- [ ] Makefile target `make scan` for local scan.
- [ ] `SECURITY.md` updated with CVE response policy.

---

## 4. Implementation Sequence

### Dependency Graph

```
US-001  ──────────────────────────────────────────┐
US-002  ──────────────────────────────────────────┤
US-003  ──────────────────────────────────────────┤── Phase 0 (P0 Crash Prevention)
US-004  ──────────────────────────────────────────┘   No dependencies; run in parallel
         │
         ▼
US-018  ──── No blockers; run in parallel with Phase 1   (Config)
US-019  ──── No blockers; run in parallel with Phase 1   (OpenAPI)
US-020  ──── No blockers; separate startup concern       (GeoIP)
US-021  ──── No blockers; surgical DB fix                (Exception)

         ▼ Phase 1
US-022  ─────── Blocked by: US-005, US-008 (COST_PER_SEAT consumers must exist to validate)
US-005  ─────── Can start after US-001 (logging); no backend blockers if API exists
US-006  ─────── No blockers (API exists)
US-007  ─────── No blockers (API exists)
US-008  ─────── No blockers
US-009  ─────── No blockers
US-010  ─────── No blockers
US-011  ─────── Blocked by: US-008, US-009, US-010 (needs panes to exist with live data)
US-012  ─────── No blockers
US-013  ─────── No blockers
US-014  ─────── May require new backend endpoint (parallel backend/frontend work)
US-015  ─────── May require new backend endpoint (parallel backend/frontend work)
US-016  ─────── No blockers (uses existing teams API)
US-017  ─────── Needs new backend endpoint POST /rules/{id}/test

         ▼ Phase 2
US-023  ─────── Blocked by: global org context must be stable (from US-016 work)
US-024  ─────── No blockers
US-025  ─────── No backend blocker if export endpoint exists
US-026  ─────── No blockers

         ▼ Phase 3
US-027  ─────── No blockers (docs only)
US-028  ─────── No blockers; completes US-001 work
US-029  ─────── Blocked by: US-004 (auth setup file must exist)

         ▼ Future
US-030  ─────── Blocked by: US-003 (worker abstract method), stable ingestion pipeline
US-031  ─────── Blocked by: US-002 (ticketing service pattern), detection pipeline stable
US-032  ─────── No blockers (CI-only)
```

### Recommended Sprint Allocation

| Sprint | Stories | Theme |
|--------|---------|-------|
| Sprint 1 | US-001, US-002, US-003, US-004 | P0: Crash prevention + E2E infra |
| Sprint 2 | US-005, US-006, US-007, US-018, US-019 | Copilot live data + Config |
| Sprint 3 | US-008, US-009, US-010, US-011, US-020, US-021 | Health live data + Observability |
| Sprint 4 | US-012, US-013, US-014, US-015, US-016 | Reports/Users + Dashboard + Rules |
| Sprint 5 | US-017, US-022, US-023, US-024 | DORA charts + TopBar + Detail panel |
| Sprint 6 | US-025, US-026, US-027, US-028, US-029 | Events search + DX + Docs |
| Sprint 7+ | US-030, US-031, US-032 | Roadmap features |

---

## 5. Risk Register

### Risk 1 — Backend API Gaps for Mock Data Replacement
**Description**: Several frontend panes are showing mock data because the corresponding backend API endpoints may not exist yet (health/license, health/maintenance, health/waf, developer activity). Replacing mock data in the frontend assumes these endpoints are available.  
**Probability**: Medium  
**Impact**: High — if endpoints are missing, P1 frontend stories are blocked.  
**Mitigation**:
1. Immediately audit all `/api/v1/` routes against the mock-data replacement stories (US-005 through US-016).
2. For any missing endpoint, create a backend sub-task (not a separate story) within the same sprint.
3. Frontend engineers can proceed with API hook stubs and mock service workers; unblock when backend is ready.
4. Acceptance criteria in each story explicitly requires backend availability before story is "Done".

---

### Risk 2 — E2E Test Auth Setup Complexity
**Description**: `auth.setup.ts` requires a working login flow. GitHub OAuth in test environments typically requires a real OAuth app or a mock. SAML adds further complexity. If the test environment cannot perform real OAuth, auth setup may need a dedicated test credential bypass endpoint.  
**Probability**: High  
**Impact**: Medium — delays US-004 and all subsequent E2E coverage.  
**Mitigation**:
1. Evaluate whether a "test mode" JWT bypass endpoint can be added to FastAPI for E2E tests only (gated by `TEST_MODE=true` env var, disabled in production).
2. Alternatively, pre-generate a long-lived JWT for the test user and persist it via `storageState` manually — acceptable for CI.
3. Document the chosen approach in `CONTRIBUTING.md` before Sprint 1 ends.

---

### Risk 3 — Copilot Metrics API Access Requirements
**Description**: The Copilot Metrics API (GitHub Enterprise Cloud) requires specific OAuth scopes (`manage_billing:copilot`, `read:enterprise`) and an Enterprise account. Many self-hosted or GitHub Free/Team orgs will not have access. If the API is unavailable, Copilot Insights panes must fall back gracefully without breaking the app.  
**Probability**: High (likely affects some user segments)  
**Impact**: Medium — if not handled, removing mock data leaves panes blank for many users.  
**Mitigation**:
1. US-005 through US-007 acceptance criteria explicitly require an empty state when no API data is available.
2. Add a Copilot integration health check to the platform status page.
3. Consider a "demo mode" toggle in Settings that restores illustrative data for evaluation purposes only — clearly labeled as demo.

---

### Risk 4 — Abstract Worker Refactor Breaks Existing Subclasses
**Description**: US-003 requires `AbstractIngestWorker` to use `abc.ABC` and `@abstractmethod`. If any subclass does not implement `_normalize_event` (even indirectly via mixin or late binding), the app will fail to start.  
**Probability**: Low  
**Impact**: High — production ingestion pipeline down.  
**Mitigation**:
1. Before merging, run `pylint --disable=all --enable=W0223` (abstract-method check) against all workers.
2. `mypy` strict mode should catch this; confirm `mypy` CI check is enforced.
3. Add a test that instantiates all concrete workers to confirm no `TypeError`.
4. Deploy as a hotfix in a staging environment first; verify all workers start.

---

### Risk 5 — Org Config API (COST_PER_SEAT) Requires Schema Migration
**Description**: US-022 adds `copilot_cost_per_seat` to an org config table. This requires a new Alembic migration. If `alembic upgrade head` is not run during deployment, the new column is absent and the API returns 500.  
**Probability**: Medium  
**Impact**: Medium — cost calculations broken until migration runs.  
**Mitigation**:
1. Add a Pydantic validator that catches `ProgrammingError` (missing column) and returns a sensible fallback value rather than a 500.
2. Include migration in the deployment runbook as a mandatory pre-deployment step.
3. Add a startup health check that verifies the `org_configs` table schema includes `copilot_cost_per_seat`; log a warning if not.
4. Alembic migration should be additive (not rename/drop) to be zero-downtime-safe.

---

## Appendix A — Requirements Traceability Matrix

| US-ID | Audit Finding # | Epic | Priority | Sprint |
|-------|----------------|------|----------|--------|
| US-001 | #2 | BE-STABILITY | P0 | 1 |
| US-002 | #3 | BE-STABILITY | P0 | 1 |
| US-003 | #4 | BE-STABILITY | P0 | 1 |
| US-004 | #1 | TEST-INFRA | P0 | 1 |
| US-005 | #5 | COPILOT-DATA | P1 | 2 |
| US-006 | #5 | COPILOT-DATA | P1 | 2 |
| US-007 | #5 | COPILOT-DATA | P1 | 2 |
| US-008 | #6 | HEALTH-DATA | P1 | 3 |
| US-009 | #7 | HEALTH-DATA | P1 | 3 |
| US-010 | #8 | HEALTH-DATA | P1 | 3 |
| US-011 | #15 | HEALTH-DATA | P1 | 3 |
| US-012 | #9 | REPORTS-USERS | P1 | 4 |
| US-013 | #10 | REPORTS-USERS | P1 | 4 |
| US-014 | #11 | DASHBOARD-COMPLETE | P1 | 4 |
| US-015 | #12 | DASHBOARD-COMPLETE | P1 | 5 |
| US-016 | #13 | DASHBOARD-COMPLETE | P1 | 4 |
| US-017 | #14 | RULES-DETECT | P1 | 5 |
| US-018 | #16 | CONFIG-OBS | P2 | 2 |
| US-019 | #17 | CONFIG-OBS | P2 | 2 |
| US-020 | #18 | CONFIG-OBS | P2 | 3 |
| US-021 | #19 | CONFIG-OBS | P2 | 3 |
| US-022 | #20 | CONFIG-OBS | P2 | 5 |
| US-023 | #21 | UI-COMPLETE | P2 | 5 |
| US-024 | #22 | UI-COMPLETE | P2 | 5 |
| US-025 | #23 | UI-COMPLETE | P2 | 6 |
| US-026 | #24 | UI-COMPLETE | P2 | 6 |
| US-027 | #25 | DOCS-CODE-QUALITY | P3 | 6 |
| US-028 | #26 | DOCS-CODE-QUALITY | P3 | 6 |
| US-029 | #27 | DOCS-CODE-QUALITY | P3 | 6 |
| US-030 | #28 | ROADMAP | P3 | 7+ |
| US-031 | #29 | ROADMAP | P3 | 7+ |
| US-032 | #30 | ROADMAP | P3 | 7+ |

---

## Appendix B — Non-Functional Requirements

| Requirement | Metric | Applies To |
|------------|--------|-----------|
| API response time | p95 < 200ms for read endpoints | All US replacing mock data |
| API response time | p95 < 500ms for write/complex queries | US-017, US-022 |
| E2E test run time | Total suite < 5 minutes in CI | US-004, US-029 |
| Accessibility | WCAG 2.1 AA | All UI stories (US-005–US-026) |
| RBAC enforcement | All new endpoints covered by role checks | US-017, US-019, US-022, US-030 |
| Security | No new CVEs introduced (CRITICAL/HIGH) | All stories |
| Backwards compatibility | Alembic migrations additive only | US-022, US-030 |
| Log format | Structured JSON when `LOG_FORMAT=json` | US-001, US-028 |

---

*This document is approved for handoff to the Architecture & Security Agent. All user stories meet INVEST criteria, all acceptance criteria are specific and testable, and all edge cases are documented.*
