# OctoWatch — Mockup-to-App Gap Fix Plan

> Systematic comparison of mockup/index.html against live app.
> Every screen, control, chart, and interaction catalogued.
> Generated 2026-03-27.

---

## Executive Summary

The mockup defines 11 screens with rich data visualizations, marketplace-style integrations, 
5-tab Copilot insights, DORA metrics with SVG charts, a SQL query explorer, and data import 
drop-zones. The current app has all 11 routes but significant gaps in visual fidelity, 
missing UI elements, incomplete interactivity, and non-functional controls.

---

## WS-1: TopBar — Org Tabs & Controls

**Mockup**: Org segmented-button tabs (acme-corp | globex | + Add org), "New report" button, avatar "JM"  
**Current**: Dark mode toggle, user dropdown menu, no org tabs, no "New report" button

- [ ] 1.1 Add org-tab segmented control component to TopBar
- [ ] 1.2 Wire org-tab selection to global state/context (active org filter)
- [ ] 1.3 Add "+ Add org" tab trigger
- [ ] 1.4 Add "New report" button with + icon
- [ ] 1.5 Show user initials avatar (from auth context)

---

## WS-2: Dashboard — Missing Elements

**Mockup has 5 stat pills**: events today, open threats, pipeline success %, active devs, API calls (24h)  
**Current has 3 stat pills**: events (recent), open threats, active actors

**Mockup has**: Activity heatmap, Activity feed, Open threats by severity, **Platform alerts** card  
**Current**: Has heatmap + feed + severity bars + Recent detections card (not Platform alerts)

- [ ] 2.1 Add "pipeline success" stat pill (needs backend data or derive from events)
- [ ] 2.2 Add "API calls (24h)" stat pill
- [ ] 2.3 Replace "Recent detections" card with "Platform alerts" card per mockup (workflow failure rate ↑, PR cycle time, deploy frequency)
- [ ] 2.4 Ensure severity bar styling matches mockup (dot + label + bar + count layout)

---

## WS-3: Threats — Detail Panel & Interactions

**Mockup**: Split layout with detail panel showing evidence code block, labels, description, action buttons  
**Current**: Has split layout — verify detail panel completeness

- [ ] 3.1 Verify evidence code block renders correctly in detail panel
- [ ] 3.2 Verify action buttons: Suspend user, Acknowledge, Assign 
- [ ] 3.3 Verify severity labels + rule category labels render in detail panel header
- [ ] 3.4 Verify tabs (Open/Closed/Acknowledged/All) work correctly
- [ ] 3.5 Ensure "Filter" and "New rule" buttons exist and match mockup placement

---

## WS-4: Events Explorer — Search, Filters, Table

**Mockup**: Search bar with filter chips (org:acme-corp, action:repo.*, after:2024-01-14), results count, Export CSV / Save query buttons, table with Timestamp/Action/Actor/Repository/IP-Location/Details columns  
**Current**: Has search and chips but free-text search doesn't filter, Export CSV and Save query are not wired

- [ ] 4.1 Wire search bar to actually filter events (parse key:value syntax, send to API)
- [ ] 4.2 Add "+ Add filter" chip button per mockup
- [ ] 4.3 Wire "Export CSV" button to call export endpoint 
- [ ] 4.4 Add IP/Location column to events table (source_ip + geo_country_code)
- [ ] 4.5 Add "Details" button per row that shows raw event

---

## WS-5: Engineering Velocity — Charts & Tables

**Mockup has**:
- DORA tier badge ("★ Elite") top-right
- Info banner about metrics being system behavior
- 8 metric cards (PRs merged, Lead time, PR cycle time, Change failure rate, Deployments, Workflow success, WIP, Planned work ratio)
- Team contribution calendar
- 2×2 chart grid: Lead time chart (median+P90), Change failure rate chart, Workflow success rate chart, Daily deployments bar chart
- "Top failing workflows" table
- "Most active repositories" table

**Current**: Has metric cards, contribution calendar, table of recent workflow failures. Missing: DORA badge, info banner, SVG line/area/bar charts, "Most active repositories" table, some metric cards.

- [ ] 5.1 Add DORA tier badge component (top-right of page header)
- [ ] 5.2 Add info banner about metrics being system behavior (blue info box)
- [ ] 5.3 Ensure all 8 metric cards are present with correct labels and deltas
- [ ] 5.4 Add 2×2 chart grid using LineAreaChart/BarChart components:
  - Lead time for changes (median + P90 dashed line)
  - Change failure rate (area chart with threshold line)
  - Workflow success rate (area chart)
  - Daily deployments (bar chart)
- [ ] 5.5 Add "Most active repositories" table (repo, commits, PRs merged, CFR, MTTR, contributors)

---

## WS-6: Developer Activity — Work Distribution

**Mockup has**:
- Team filter buttons (All teams, platform-team, security-team, frontend-team)
- "Work distribution — last 30 days" section with context text about bus factor
- PR authorship share card (horizontal bars per developer)
- Review concentration card (with warning: "@alice performs 44% of all reviews")
- Developer cards grid

**Current**: Has team filter buttons, developer cards grid. Need to verify PR authorship/review concentration cards.

- [ ] 6.1 Add "Work distribution" section title with context text
- [ ] 6.2 Add PR authorship share card with per-developer horizontal bars
- [ ] 6.3 Add Review concentration card with warning threshold highlighting
- [ ] 6.4 Verify developer cards match mockup (avatar, name, handle, team, mini-bars, stats with flag badge)

---

## WS-7: Copilot Insights — 5 Sub-tabs (MAJOR)

**Mockup has 5 tabs**: Overview, Adoption, Models & Features, License Optimization, Anomalies (with badge "3")  
**Current**: Has a single page with some metrics. Missing most sub-tab content.

### 7a — Overview tab
- [ ] 7a.1 Seat waste alert banner (red, shows $ waste, inactive + never-used count)
- [ ] 7a.2 6 metric cards: acceptance rate, active/total seats, inactive+never, lines accepted, chat turns, PR summaries
- [ ] 7a.3 Acceptance rate chart (7-day rolling avg with "25% good" threshold line)
- [ ] 7a.4 Seat utilization trend chart (3 series: active, inactive 30d+, never used)
- [ ] 7a.5 Acceptance rate by language card (horizontal bars: TypeScript, Python, Go, Java, C++, Rust)
- [ ] 7a.6 Correlation insight card (acceptance ↑ + cycle time ↓, active ≠ effective)
- [ ] 7a.7 Inactive seats table (user, seat assigned, last activity, last editor, days inactive, monthly cost, Revoke button)

### 7b — Adoption tab
- [ ] 7b.1 5-tier adoption cards (Power Users, Regular, Minimal, Inactive, Never Used) with counts
- [ ] 7b.2 Stacked horizontal progress bar showing tier proportions
- [ ] 7b.3 Daily power users table (champion candidates: user, team, streak, accept rate)
- [ ] 7b.4 Feature adoption gaps card (IDE completions, IDE chat, github.com chat, PR summaries, CLI, Knowledge bases)
- [ ] 7b.5 CCR impact comparison panel (Repos WITH vs WITHOUT CCR — median PR review time, % faster)
- [ ] 7b.6 Minimal users table (user, team, uses 30d, accepted, last feature, Schedule onboarding button)

### 7c — Models & Features tab
- [ ] 7c.1 Model usage spread card (GPT-4o, Claude 3.7, o3-mini, custom model, GPT-4o-mini)
- [ ] 7c.2 Feature usage spread card (IDE completions, IDE chat, github.com chat, PR summaries, CLI, Knowledge bases)
- [ ] 7c.3 Editor breakdown cards (VS Code, JetBrains, Neovim, Xcode, Other — 5-column grid)

### 7d — License Optimization tab
- [ ] 7d.1 License optimization dashboard content (cost analysis, recommendations)

### 7e — Anomalies tab
- [ ] 7e.1 Anomalies list/dashboard with badge count
- [ ] 7e.2 Tab navigation with active state and red badge

---

## WS-8: Reports — Catalog Styling

**Mockup**: Report catalog as "release-item" cards with title, date/pages, tag labels, PDF/CSV buttons  
**Current**: Has reports list — verify styling matches mockup

- [ ] 8.1 Style report items as release cards (title, generated date, page count)
- [ ] 8.2 Add finding-count labels (e.g., "14 critical findings", "8 medium")
- [ ] 8.3 Ensure PDF/CSV export buttons work

---

## WS-9: Query Explorer — Styling & Behavior

**Mockup**: Schema tree, SQL editor with syntax highlighting (keyword/function/column/literal/comment colors), line numbers, Run/Save/History toolbar, results table  
**Current**: Has these elements — verify Save and History work

- [ ] 9.1 Add SQL syntax highlighting in editor (color-code keywords, functions, strings, comments)
- [ ] 9.2 Wire "Save" button to create template
- [ ] 9.3 Wire "History" button to show recent queries
- [ ] 9.4 Verify schema tree lists correct tables (audit_events, detections, workflow_runs)

---

## WS-10: Detection Rules — Table Columns

**Mockup**: Table columns: Status, Rule name, Logic, Severity, Detections (30d), Version, Edit  
**Mockup also has**: "Sync from GitHub" button next to "New rule"  
**Current**: Table has Name, Category, Severity, Enabled toggle, Created, Edit/Delete buttons

- [ ] 10.1 Add Status column (active/draft label)
- [ ] 10.2 Add Logic column (threshold/exact-match/ml-assisted label)
- [ ] 10.3 Add "Detections (30d)" column with count
- [ ] 10.4 Add Version column (e.g., v1.3.0)
- [ ] 10.5 Add "Sync from GitHub" button

---

## WS-11: Users & Roles — Table Structure

**Mockup has 2 tables**:
1. Team mappings: GitHub team, OctoWatch role, Mapped by, Last synced, Edit
2. Active users: User, Role, Last active, MFA status, Sessions

**Current**: Has role assignments table and add-mapping modal

- [ ] 11.1 Style team mappings table per mockup (monospace team names, role labels)
- [ ] 11.2 Add "Active users" section/table below team mappings
- [ ] 11.3 Add MFA status column with enabled/pending labels
- [ ] 11.4 Add Sessions count column

---

## WS-12: Integrations — Marketplace Cards & Data Import

**Mockup has**:
- Marketplace-style cards: GitHub Enterprise (connected), Slack (connected), Microsoft Sentinel (not installed), Splunk (not installed), PagerDuty (configured), Jira (not installed)
- Each with icon, name, description, status label, Configure/Install button
- Data Import section with Audit Log Import + Copilot Metrics Import drop zones
- Recent imports table

**Current**: Has Jira/GitHub Issues/Slack/Email cards but NOT marketplace-style. Missing Sentinel, Splunk, PagerDuty. Missing data import section entirely.

- [ ] 12.1 Redesign integration cards to marketplace-style with SVG icons
- [ ] 12.2 Add Microsoft Sentinel, Splunk, PagerDuty cards
- [ ] 12.3 Add GitHub Enterprise as primary integration card
- [ ] 12.4 Add "Data Import" section with drag-and-drop file upload areas
- [ ] 12.5 Add Audit Log Import drop zone (accepts .csv, .json, max 500MB)
- [ ] 12.6 Add Copilot Metrics Import drop zone (accepts .json)
- [ ] 12.7 Add "Recent imports" table (file, type, size, imported at, records, status)
- [ ] 12.8 Wire file uploads to backend ingestion endpoints

---

## WS-13: Playwright E2E Tests

- [ ] 13.1 Set up Playwright config (playwright.config.ts)
- [ ] 13.2 Write smoke tests for all 11 routes (navigate + verify page title)
- [ ] 13.3 Write visual regression tests comparing each screen to mockup layout
- [ ] 13.4 Test all interactive controls: sidebar nav, org tabs, buttons, modals
- [ ] 13.5 Test Copilot sub-tab switching
- [ ] 13.6 Test Threats detail panel open/close
- [ ] 13.7 Test Events search and filter chips
- [ ] 13.8 Test Rules CRUD (create, edit, toggle, delete)
- [ ] 13.9 Test Query editor run
- [ ] 13.10 Test responsive layout (sidebar + main)

---

## Execution Order

1. **Phase A** (Foundation): WS-1 TopBar, WS-13 Playwright setup — parallel
2. **Phase B** (Core screens): WS-2 Dashboard, WS-3 Threats, WS-4 Events, WS-5 Velocity — parallel
3. **Phase C** (Detail screens): WS-6 DevActivity, WS-7 Copilot, WS-8 Reports — parallel
4. **Phase D** (Settings screens): WS-9 Query, WS-10 Rules, WS-11 Users, WS-12 Integrations — parallel
5. **Phase E** (Validation): WS-13 full E2E test suite, fix regressions
