# OctoWatch — Frontend Architecture Specification

**Version**: 1.0  
**Date**: 2026-03-26  
**Author**: Architecture & Security Agent  
**Status**: Ready for Development  

---

## Table of Contents

1. [Tech Stack Decisions](#1-tech-stack-decisions)
2. [Project Structure](#2-project-structure)
3. [TypeScript API Types](#3-typescript-api-types)
4. [API Client Design](#4-api-client-design)
5. [Routing Structure](#5-routing-structure)
6. [Component Architecture](#6-component-architecture)
7. [State Management](#7-state-management)
8. [CSS Architecture](#8-css-architecture)
9. [Vite Configuration](#9-vite-configuration)
10. [Security Controls](#10-security-controls)
11. [Package.json](#11-packagejson)
12. [Development Runbook](#12-development-runbook)

---

## 1. Tech Stack Decisions

| Role | Package | Exact Version | Rationale |
|------|---------|---------------|-----------|
| Build tool | `vite` | `5.4.8` | Fast HMR, first-class TypeScript, Vite proxy for dev API |
| UI framework | `react` | `18.3.1` | Established stack |
| DOM renderer | `react-dom` | `18.3.1` | Pair with React |
| Language | `typescript` | `5.5.4` | Strict mode throughout |
| Routing | `react-router-dom` | `6.26.2` | v6 data router, declarative route guard |
| Server state | `@tanstack/react-query` | `5.56.2` | Cache-first fetching, automatic background refresh |
| Charts | `echarts` | `5.5.1` | Established stack; used for line/bar/area; **not** a UI component library |
| React ECharts | `echarts-for-react` | `3.0.2` | Thin React wrapper with resize observer |
| Vite React plugin | `@vitejs/plugin-react` | `4.3.1` | Babel fast refresh |
| Types — React | `@types/react` | `18.3.5` | |
| Types — ReactDOM | `@types/react-dom` | `18.3.0` | |

**Explicitly excluded:**
- No TailwindCSS (use CSS Modules + global design tokens instead)
- No MUI / Ant Design / Radix / shadcn (all components are custom)
- No Redux / Zustand (React Query handles server state; `useState`/`useContext` for UI state)
- No Axios (native `fetch` with credentials)
- No `date-fns` / `dayjs` — use `Intl.DateTimeFormat` for all date formatting

---

## 2. Project Structure

All files live under `/Users/jmassardo/code/audit-log-analyzer/frontend/`.

```
frontend/
├── index.html                        # Vite entry point
├── vite.config.ts                    # Vite config (proxy, aliases)
├── tsconfig.json                     # TypeScript config (strict)
├── tsconfig.node.json                # tsconfig for vite.config.ts itself
├── package.json
│
├── public/
│   └── favicon.svg                   # OctoWatch logo SVG (from mockup)
│
└── src/
    ├── main.tsx                      # ReactDOM.createRoot, QueryClientProvider, RouterProvider
    ├── App.tsx                       # createBrowserRouter definition (routes + guards)
    │
    ├── styles/
    │   ├── tokens.css                # :root { --canvas: ...; } — all CSS variables from mockup
    │   ├── reset.css                 # box-sizing reset, html/body height:100%, base font
    │   └── global.css                # @import tokens + reset; imported once in main.tsx
    │
    ├── api/
    │   ├── client.ts                 # fetch wrapper: credentials, CSRF, 401 redirect, error throw
    │   ├── auth.ts                   # auth endpoint functions
    │   ├── events.ts                 # events endpoint functions
    │   ├── detections.ts             # detections endpoint functions
    │   ├── reports.ts                # reports endpoint functions
    │   ├── query.ts                  # query endpoint functions
    │   ├── rules.ts                  # rules endpoint functions
    │   ├── admin.ts                  # admin endpoint functions
    │   └── integrations.ts           # integrations endpoint functions
    │
    ├── types/
    │   ├── auth.ts                   # MeResponse, etc.
    │   ├── events.ts                 # EventResponse, EventListResponse, EventListParams
    │   ├── detections.ts             # DetectionResponse, DetectionListResponse, Rule*, etc.
    │   ├── reports.ts                # ReportEnvelope, all bucket types
    │   ├── query.ts                  # QueryRunRequest, QueryRunResponse, QueryTemplate
    │   ├── admin.ts                  # RoleAssignment, IngestionSource, RetentionPolicy, TopActor
    │   └── integrations.ts           # TicketingConfig, NotificationConfig, IdpEnrichment
    │
    ├── hooks/
    │   ├── useCurrentUser.ts         # useQuery → GET /auth/me; exports CurrentUser | null
    │   ├── useOrg.ts                 # useContext for selected org (from topbar tabs)
    │   ├── useCSRF.ts                # module-level CSRF token store + updater
    │   └── useDebounce.ts            # generic debounce hook (for search inputs)
    │
    ├── context/
    │   └── OrgContext.tsx            # OrgContext: selected org string + setter
    │
    ├── components/
    │   ├── layout/
    │   │   ├── AppShell.tsx          # <Sidebar> + <TopBar> + <Outlet> — rendered by all auth'd routes
    │   │   ├── AppShell.module.css
    │   │   ├── Sidebar.tsx           # nav-section groups, nav-items, active state via useMatch
    │   │   ├── Sidebar.module.css
    │   │   ├── TopBar.tsx            # org tabs (from useCurrentUser.scoped_orgs), avatar, "New report" btn
    │   │   └── TopBar.module.css
    │   │
    │   ├── primitives/
    │   │   ├── Button.tsx            # variant: 'default'|'primary'|'danger'; size: 'sm'|'md'
    │   │   ├── Button.module.css
    │   │   ├── Label.tsx             # variant: 'danger'|'attention'|'success'|'done'|'muted'|'accent'|'severe'
    │   │   ├── Label.module.css
    │   │   ├── Pill.tsx              # stat pill (value + label + variant)
    │   │   ├── Pill.module.css
    │   │   ├── Card.tsx              # card wrapper with optional header
    │   │   ├── Card.module.css
    │   │   ├── MetricCard.tsx        # large value + label + delta (up/down/neutral)
    │   │   ├── MetricCard.module.css
    │   │   ├── SeverityDot.tsx       # color dot: critical|high|medium|low
    │   │   ├── SeverityDot.module.css
    │   │   ├── Spinner.tsx           # CSS-only loading spinner
    │   │   ├── Spinner.module.css
    │   │   ├── ErrorBanner.tsx       # full-width error message with retry button
    │   │   ├── ErrorBanner.module.css
    │   │   ├── CodeBlock.tsx         # pre/code with canvas-inset bg
    │   │   ├── CodeBlock.module.css
    │   │   ├── Avatar.tsx            # initials avatar (color seeded from username)
    │   │   ├── Avatar.module.css
    │   │   ├── Modal.tsx             # generic portal modal with backdrop
    │   │   ├── Modal.module.css
    │   │   ├── ConfirmDialog.tsx     # wraps Modal; "Are you sure?" pattern
    │   │   └── ConfirmDialog.module.css
    │   │
    │   ├── data/
    │   │   ├── DataTable.tsx         # generic <table> with thead/tbody, sortable cols, empty state
    │   │   ├── DataTable.module.css
    │   │   ├── Pagination.tsx        # prev/next buttons + "Page N of M"
    │   │   ├── Pagination.module.css
    │   │   ├── SearchBar.tsx         # search input + filter chips
    │   │   ├── SearchBar.module.css
    │   │   ├── FilterChip.tsx        # individual removable chip
    │   │   └── FilterChip.module.css
    │   │
    │   └── charts/
    │       ├── LineAreaChart.tsx     # ECharts line+area; props: series[], xAxisData[], title
    │       ├── BarChart.tsx          # ECharts bar; props: series[], xAxisData[], title
    │       ├── ContributionCalendar.tsx  # pure SVG heatmap (same grid as GitHub calendar)
    │       ├── ContributionCalendar.module.css
    │       ├── MiniBarChart.tsx      # tiny inline bars (dev cards); pure SVG; no ECharts
    │       └── MiniBarChart.module.css
    │
    └── pages/
        ├── LoginPage.tsx             # Full-page login (GitHub OAuth button)
        ├── LoginPage.module.css
        ├── Dashboard/
        │   ├── index.tsx             # DashboardPage — assembles sub-components
        │   ├── Dashboard.module.css
        │   ├── ActivityFeed.tsx      # timeline feed
        │   ├── ActivityFeed.module.css
        │   ├── ThreatPills.tsx       # stat pills row (open detections by severity)
        │   └── ThreatPills.module.css
        ├── Threats/
        │   ├── index.tsx             # ThreatsPage — split layout
        │   ├── Threats.module.css
        │   ├── DetectionList.tsx     # issue-list with filter tabs
        │   ├── DetectionList.module.css
        │   ├── DetectionListRow.tsx  # single row: sev-dot, title, meta, time
        │   ├── DetectionListRow.module.css
        │   ├── DetectionPanel.tsx    # 480px sliding detail panel
        │   └── DetectionPanel.module.css
        ├── Events/
        │   ├── index.tsx             # EventsPage
        │   ├── Events.module.css
        │   ├── EventFilters.tsx      # search bar + filter chips
        │   ├── EventFilters.module.css
        │   ├── EventTable.tsx        # paginated event table
        │   ├── EventTable.module.css
        │   ├── EventDetailPanel.tsx  # sliding detail + raw JSON
        │   └── EventDetailPanel.module.css
        ├── Velocity/
        │   ├── index.tsx             # VelocityPage
        │   ├── Velocity.module.css
        │   ├── DoraTierBadge.tsx     # Elite/High/Medium/Low badge
        │   ├── DoraTierBadge.module.css
        │   ├── VelocityMetricStrip.tsx  # 8-metric grid
        │   ├── RepoTable.tsx         # repo × CFR/MTTR table
        │   └── RepoTable.module.css
        ├── DevActivity/
        │   ├── index.tsx             # DevActivityPage
        │   ├── DevActivity.module.css
        │   ├── WorkDistribution.tsx  # horizontal bar charts
        │   ├── WorkDistribution.module.css
        │   ├── BusFactor.tsx         # warning banner + concentration chart
        │   ├── BusFactor.module.css
        │   ├── DeveloperGrid.tsx     # auto-fill card grid
        │   ├── DeveloperCard.tsx     # avatar + mini bars + stats
        │   └── DeveloperCard.module.css
        ├── Copilot/
        │   ├── index.tsx             # CopilotPage
        │   ├── Copilot.module.css
        │   ├── CopilotMetricStrip.tsx
        │   ├── SeatWasteAlert.tsx    # attention banner
        │   ├── SeatWasteAlert.module.css
        │   ├── InactiveSeatsTable.tsx
        │   └── InactiveSeatsTable.module.css
        ├── Reports/
        │   ├── index.tsx             # ReportsPage
        │   ├── Reports.module.css
        │   ├── ReportCard.tsx        # report name + description + Export button
        │   └── ReportCard.module.css
        ├── Query/
        │   ├── index.tsx             # QueryPage
        │   ├── Query.module.css
        │   ├── SchemaTree.tsx        # collapsible table + col list
        │   ├── SchemaTree.module.css
        │   ├── SqlEditor.tsx         # textarea with line numbers (no external editor dep)
        │   ├── SqlEditor.module.css
        │   ├── QueryResults.tsx      # columns + rows table
        │   ├── QueryResults.module.css
        │   ├── TemplatePicker.tsx    # dropdown list of saved templates
        │   └── TemplatePicker.module.css
        ├── Rules/
        │   ├── index.tsx             # RulesPage
        │   ├── Rules.module.css
        │   ├── RulesTable.tsx        # sortable table with status toggle + delete
        │   ├── RulesTable.module.css
        │   ├── RuleForm.tsx          # create/edit form in a Modal
        │   └── RuleForm.module.css
        ├── Users/
        │   ├── index.tsx             # UsersPage
        │   ├── Users.module.css
        │   ├── RoleAssignmentsTable.tsx
        │   └── RoleAssignmentsTable.module.css
        └── Integrations/
            ├── index.tsx             # IntegrationsPage
            ├── Integrations.module.css
            ├── TicketingCards.tsx
            ├── NotificationCards.tsx
            └── IntegrationCard.module.css
```

---

## 3. TypeScript API Types

Each file under `src/types/` declares interfaces that map directly to the Pydantic schemas. Use `readonly` everywhere to enforce immutability at compile time.

### `src/types/auth.ts`

```typescript
export interface MeResponse {
  readonly github_login: string;
  readonly github_id: number;
  readonly roles: readonly string[];
  readonly scoped_orgs: readonly string[];
  readonly scoped_repos: readonly string[];
  readonly scope_type: string;
  readonly session_expires_at: string;
}
```

### `src/types/events.ts`

```typescript
export interface EventResponse {
  readonly id: number;
  readonly document_id: string;
  readonly created_at: string;       // ISO 8601
  readonly ingested_at: string;
  readonly action: string;
  readonly namespace: string;
  readonly actor: string | null;
  readonly actor_id: number | null;
  readonly actor_is_bot: boolean;
  readonly org: string | null;
  readonly org_id: number | null;
  readonly repo: string | null;
  readonly repo_id: number | null;
  readonly business: string | null;
  readonly source_ip: string | null;
  readonly user_agent: string | null;
  readonly geo_country_code: string | null;
  readonly geo_city: string | null;
  readonly geo_is_proxy: boolean | null;
  readonly data: Record<string, unknown>;
  readonly ingestion_source: string;
  readonly source_file_path: string;
}

export interface EventListResponse {
  readonly items: readonly EventResponse[];
  readonly total: number;
  readonly page: number;
  readonly page_size: number;
  readonly has_next: boolean;
}

export interface EventListParams {
  org?: string;
  repo?: string;
  actor?: string;
  action?: string;
  namespace?: string;
  source_ip?: string;
  since?: string;           // ISO 8601
  until?: string;
  actor_is_bot?: boolean;
  geo_country_code?: string;
  sort?: 'created_at_desc' | 'created_at_asc';
  page?: number;
  page_size?: number;
}
```

### `src/types/detections.ts`

```typescript
export type DetectionStatus = 'investigating' | 'resolved' | 'false_positive';
export type DetectionSeverity = 'critical' | 'high' | 'medium' | 'low';

export interface TicketSummary {
  readonly id: number;
  readonly external_id: string;
  readonly external_url: string;
  readonly provider: string;
  readonly external_status: string | null;
}

export interface DetectionResponse {
  readonly id: number;
  readonly rule_id: number;
  readonly rule_name: string | null;
  readonly rule_version: number;
  readonly severity: DetectionSeverity;
  readonly confidence: string;
  readonly confidence_score: number;
  readonly status: DetectionStatus;
  readonly title: string;
  readonly description: string;
  readonly actor: string | null;
  readonly org: string | null;
  readonly repo: string | null;
  readonly source_ip: string | null;
  readonly window_start: string | null;
  readonly window_end: string | null;
  readonly event_ids: readonly number[];
  readonly context_data: Record<string, unknown>;
  readonly triggered_at: string;
  readonly assigned_to: string | null;
  readonly resolved_at: string | null;
  readonly resolution_note: string | null;
  readonly tickets: readonly TicketSummary[];
}

export interface DetectionListResponse {
  readonly items: readonly DetectionResponse[];
  readonly total: number;
  readonly page: number;
  readonly page_size: number;
  readonly has_next: boolean;
}

export interface UpdateDetectionStatusRequest {
  status: DetectionStatus;
  resolution_note?: string;
}

export interface AssignDetectionRequest {
  assigned_to: string;
}

/** Rule types */
export type RuleCategory =
  | 'exfiltration' | 'account_compromise' | 'privilege_escalation'
  | 'secret_leakage' | 'supply_chain' | 'branch_protection_bypass'
  | 'pat_abuse' | 'impossible_travel' | 'off_hours_anomaly' | 'other';

export interface RuleResponse {
  readonly id: number;
  readonly name: string;
  readonly slug: string;
  readonly description: string | null;
  readonly category: RuleCategory;
  readonly severity: DetectionSeverity;
  readonly enabled: boolean;
  readonly version: number;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface RuleCreate {
  name: string;
  slug: string;
  description?: string;
  category: RuleCategory;
  severity: DetectionSeverity;
  enabled?: boolean;
}
```

### `src/types/reports.ts`

```typescript
export interface ReportEnvelope {
  readonly org: string | null;
  readonly granularity: string;
  readonly window: string;
  readonly generated_at: string;
  readonly data: readonly Record<string, unknown>[];
}

export interface MAUBucket {
  readonly bucket: string;
  readonly unique_actor_count: number;
  readonly unique_bot_actor_count: number;
  readonly new_actor_count: number;
}

export interface SeatUtilizationBucket {
  readonly bucket: string;
  readonly active_seat_count: number;
  readonly provisioned_seat_count: number;
  readonly utilization_pct: number;
}

export interface ActionsVolumeBucket {
  readonly bucket: string;
  readonly workflow_runs_total: number;
  readonly workflow_runs_succeeded: number;
  readonly workflow_runs_failed: number;
  readonly success_rate_pct: number;
  readonly unique_workflows: number;
}

export interface CopilotSeatsBucket {
  readonly bucket: string;
  readonly seats_assigned: number;
  readonly seats_revoked: number;
  readonly seats_net: number;
  readonly policy_change_count: number;
}

export interface PATCountsBucket {
  readonly bucket: string;
  readonly pats_created: number;
  readonly pats_deleted: number;
  readonly pats_expired: number;
  readonly fine_grained_pats: number;
  readonly classic_pats: number;
  readonly high_access_pats: number;
}

export interface WebhookCountsBucket {
  readonly bucket: string;
  readonly webhooks_created: number;
  readonly webhooks_deleted: number;
  readonly app_installs: number;
  readonly app_uninstalls: number;
  readonly unique_webhook_targets: number;
}

export type ReportWindow = '30d' | '60d' | '90d';
export type ReportGranularity = 'daily' | 'weekly' | 'monthly';

export interface ReportParams {
  org?: string;
  granularity?: ReportGranularity;
  window?: ReportWindow;
}
```

### `src/types/query.ts`

```typescript
export interface QueryRunRequest {
  sql: string;
  org?: string;
  format?: 'json' | 'csv';
}

export interface QueryRunResponse {
  readonly columns: readonly string[];
  readonly rows: readonly (readonly unknown[])[];
  readonly row_count: number;
  readonly truncated: boolean;
  readonly execution_ms: number;
  readonly query_id: string;
}

export interface QueryTemplate {
  readonly id: number;
  readonly name: string;
  readonly description: string | null;
  readonly sql: string;
  readonly created_by: string;
  readonly created_at: string;
}

export interface QueryTemplateCreate {
  name: string;
  description?: string;
  sql: string;
}
```

### `src/types/admin.ts`

```typescript
export interface RoleDefinition {
  readonly name: string;
  readonly permissions: readonly string[];
}

export interface RoleAssignment {
  readonly id: number;
  readonly github_login: string;
  readonly role: string;
  readonly assigned_by: string;
  readonly assigned_at: string;
}

export interface RoleAssignmentCreate {
  github_login: string;
  role: string;
}

export interface IngestionSource {
  readonly id: number;
  readonly source_type: string;
  readonly display_name: string;
  readonly enabled: boolean;
  readonly created_at: string;
}

export interface RetentionPolicy {
  readonly hot_days: number;
  readonly warm_days: number;
  readonly cold_days: number;
}

export interface TopActor {
  readonly actor: string;
  readonly event_count: number;
  readonly action_types: readonly string[];
}
```

### `src/types/integrations.ts`

```typescript
export interface TicketingConfigResponse {
  readonly id: number;
  readonly provider: 'jira' | 'github_issues';
  readonly display_name: string;
  readonly target: string;
  readonly project_key: string | null;
  readonly default_issue_type: string;
  readonly auto_create: boolean;
  readonly auto_create_severities: readonly string[];
  readonly enabled: boolean;
  readonly created_by: string;
  readonly created_at: string;
}

export interface TicketingConfigCreate {
  provider: 'jira' | 'github_issues';
  display_name: string;
  target: string;
  project_key?: string;
  default_issue_type?: string;
  auto_create?: boolean;
  auto_create_severities?: string[];
  credential_env_var: string;
  enabled?: boolean;
}

export interface NotificationConfigResponse {
  readonly id: number;
  readonly channel_type: 'slack' | 'email';
  readonly display_name: string;
  readonly target: string;
  readonly notify_severities: readonly string[];
  readonly cooldown_seconds: number;
  readonly enabled: boolean;
  readonly created_by: string;
  readonly created_at: string;
}

export interface NotificationConfigCreate {
  channel_type: 'slack' | 'email';
  display_name: string;
  target: string;
  credential_env_var?: string;
  notify_severities?: string[];
  cooldown_seconds?: number;
  enabled?: boolean;
}

export interface IdpEnrichmentResponse {
  readonly github_login: string;
  readonly idp_provider: string;
  readonly idp_user_id: string | null;
  readonly email: string | null;
  readonly display_name: string | null;
  readonly department: string | null;
  readonly title: string | null;
  readonly employment_status: string | null;
}
```

---

## 4. API Client Design

### `src/api/client.ts`

This is the **single HTTP primitive** used by every API module. It enforces:
- `credentials: 'include'` on every request (sends the httponly JWT cookie)
- CSRF token capture from response headers and injection on mutating requests
- 401 → redirect to `/login`
- Non-2xx → throw `ApiError`

```typescript
// src/api/client.ts

/** Module-level CSRF token store. Updated on every response that carries X-CSRF-Token. */
let csrfToken: string | null = null;

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: unknown,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

const MUTATING_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

/**
 * Core fetch wrapper. All API modules MUST use this function.
 * Never call `fetch` directly in feature code.
 */
export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const method = (options.method ?? 'GET').toUpperCase();

  const headers = new Headers(options.headers);

  // Always request JSON back
  headers.set('Accept', 'application/json');

  // Set Content-Type for bodies (don't override if caller sets multipart, etc.)
  if (!headers.has('Content-Type') && options.body != null) {
    headers.set('Content-Type', 'application/json');
  }

  // Inject CSRF token on all mutating requests
  if (MUTATING_METHODS.has(method) && csrfToken !== null) {
    headers.set('X-CSRF-Token', csrfToken);
  }

  const response = await fetch(`/api/v1${path}`, {
    ...options,
    method,
    headers,
    credentials: 'include',   // send the httponly JWT cookie
  });

  // Capture CSRF token from any response (backend may rotate it)
  const newCsrf = response.headers.get('X-CSRF-Token');
  if (newCsrf !== null) {
    csrfToken = newCsrf;
  }

  // Unauthenticated → redirect to login
  if (response.status === 401) {
    window.location.replace('/login');
    // Return a never-resolving promise so callers don't process a null body
    return new Promise(() => {});
  }

  // No-content success (204)
  if (response.status === 204) {
    return undefined as T;
  }

  // Parse body before deciding success/error
  let body: unknown;
  const contentType = response.headers.get('Content-Type') ?? '';
  if (contentType.includes('application/json')) {
    body = await response.json();
  } else {
    body = await response.text();
  }

  if (!response.ok) {
    throw new ApiError(
      response.status,
      body,
      `API ${method} ${path} failed with status ${response.status}`,
    );
  }

  return body as T;
}

/** Convenience helpers — used by API modules */
export const api = {
  get: <T>(path: string, params?: Record<string, string | number | boolean | undefined>) => {
    const url = params ? `${path}?${buildQuery(params)}` : path;
    return apiFetch<T>(url);
  },
  post: <T>(path: string, body?: unknown) =>
    apiFetch<T>(path, { method: 'POST', body: body !== undefined ? JSON.stringify(body) : undefined }),
  put: <T>(path: string, body?: unknown) =>
    apiFetch<T>(path, { method: 'PUT', body: body !== undefined ? JSON.stringify(body) : undefined }),
  patch: <T>(path: string, body?: unknown) =>
    apiFetch<T>(path, { method: 'PATCH', body: body !== undefined ? JSON.stringify(body) : undefined }),
  delete: <T>(path: string) =>
    apiFetch<T>(path, { method: 'DELETE' }),
};

/** Build URL query string from a params object, skipping undefined values */
function buildQuery(params: Record<string, string | number | boolean | undefined>): string {
  const p = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) {
      p.set(key, String(value));
    }
  }
  return p.toString();
}
```

### `src/api/auth.ts`

```typescript
import { api } from './client';
import type { MeResponse } from '../types/auth';

export const authApi = {
  getMe: () => api.get<MeResponse>('/auth/me'),
  logout: () => api.post<{ status: string }>('/auth/logout'),
  // GitHub OAuth: navigate the browser directly — not a fetch call
  loginWithGitHub: () => { window.location.href = '/api/v1/auth/github/login'; },
};
```

### `src/api/events.ts`

```typescript
import { api } from './client';
import type { EventListResponse, EventResponse, EventListParams } from '../types/events';

export const eventsApi = {
  list: (params: EventListParams) =>
    api.get<EventListResponse>('/events', params as Record<string, string | number | boolean | undefined>),
  get: (id: number) => api.get<EventResponse>(`/events/${id}`),
  getRaw: (id: number) => api.get<unknown>(`/events/${id}/raw`),
};
```

### `src/api/detections.ts`

```typescript
import { api } from './client';
import type {
  DetectionListResponse, DetectionResponse,
  UpdateDetectionStatusRequest, AssignDetectionRequest,
} from '../types/detections';

export const detectionsApi = {
  list: (params?: Record<string, string | number | undefined>) =>
    api.get<DetectionListResponse>('/detections', params),
  get: (id: number) => api.get<DetectionResponse>(`/detections/${id}`),
  updateStatus: (id: number, body: UpdateDetectionStatusRequest) =>
    api.patch<DetectionResponse>(`/detections/${id}/status`, body),
  assign: (id: number, body: AssignDetectionRequest) =>
    api.patch<DetectionResponse>(`/detections/${id}/assign`, body),
  suppress: (id: number) => api.post<void>(`/detections/${id}/suppress`),
  delete: (id: number) => api.delete<void>(`/detections/${id}`),
};
```

### `src/api/reports.ts`

```typescript
import { api } from './client';
import type { ReportEnvelope, ReportParams } from '../types/reports';

const reportsApi = (endpoint: string) => (params?: ReportParams) =>
  api.get<ReportEnvelope>(`/reports/${endpoint}`, params as Record<string, string | undefined>);

export const reportsApiMap = {
  mau: reportsApi('mau'),
  seatUtilization: reportsApi('seat-utilization'),
  copilotSeats: reportsApi('copilot-seats'),
  actionsVolume: reportsApi('actions-volume'),
  repoCreationRate: reportsApi('repo-creation-rate'),
  codespaceHours: reportsApi('codespace-hours'),
  patCounts: reportsApi('pat-counts'),
  webhookCounts: reportsApi('webhook-counts'),
  exportUrl: (reportType: string, params?: ReportParams) => {
    const p = new URLSearchParams(params as Record<string, string>);
    return `/api/v1/reports/export/${reportType}?${p.toString()}`;
  },
};
```

### `src/api/query.ts`

```typescript
import { api } from './client';
import type {
  QueryRunRequest, QueryRunResponse,
  QueryTemplate, QueryTemplateCreate,
} from '../types/query';

export const queryApi = {
  run: (body: QueryRunRequest) => api.post<QueryRunResponse>('/query/run', body),
  validate: (sql: string) => api.post<{ valid: boolean; error?: string }>('/query/validate', { sql }),
  getTemplates: () => api.get<QueryTemplate[]>('/query/templates'),
  createTemplate: (body: QueryTemplateCreate) => api.post<QueryTemplate>('/query/templates', body),
  deleteTemplate: (id: number) => api.delete<void>(`/query/templates/${id}`),
  runTemplate: (id: number) => api.post<QueryRunResponse>(`/query/templates/${id}/run`),
};
```

### `src/api/rules.ts`

```typescript
import { api } from './client';
import type { RuleResponse, RuleCreate } from '../types/detections';

export const rulesApi = {
  list: () => api.get<RuleResponse[]>('/rules'),
  get: (id: number) => api.get<RuleResponse>(`/rules/${id}`),
  create: (body: RuleCreate) => api.post<RuleResponse>('/rules', body),
  update: (id: number, body: RuleCreate) => api.put<RuleResponse>(`/rules/${id}`, body),
  setStatus: (id: number, enabled: boolean) =>
    api.patch<RuleResponse>(`/rules/${id}/status`, { enabled }),
  delete: (id: number) => api.delete<void>(`/rules/${id}`),
  getVersions: (id: number) => api.get<unknown[]>(`/rules/${id}/versions`),
};
```

### `src/api/admin.ts`

```typescript
import { api } from './client';
import type { RoleDefinition, RoleAssignment, RoleAssignmentCreate, IngestionSource, RetentionPolicy, TopActor } from '../types/admin';

export const adminApi = {
  getRoles: () => api.get<RoleDefinition[]>('/admin/roles'),
  getAssignments: () => api.get<RoleAssignment[]>('/admin/assignments'),
  createAssignment: (body: RoleAssignmentCreate) => api.post<RoleAssignment>('/admin/assignments', body),
  deleteAssignment: (id: number) => api.delete<void>(`/admin/assignments/${id}`),
  getIngestionSources: () => api.get<IngestionSource[]>('/admin/ingestion-sources'),
  createIngestionSource: (body: unknown) => api.post<IngestionSource>('/admin/ingestion-sources', body),
  deleteIngestionSource: (id: number) => api.delete<void>(`/admin/ingestion-sources/${id}`),
  getRetention: () => api.get<RetentionPolicy>('/admin/retention'),
  updateRetention: (body: RetentionPolicy) => api.put<RetentionPolicy>('/admin/retention', body),
  getTopActors: () => api.get<TopActor[]>('/admin/top-actors'),
};
```

### `src/api/integrations.ts`

```typescript
import { api } from './client';
import type {
  TicketingConfigResponse, TicketingConfigCreate,
  NotificationConfigResponse, NotificationConfigCreate,
  IdpEnrichmentResponse,
} from '../types/integrations';

export const integrationsApi = {
  getTicketing: () => api.get<TicketingConfigResponse[]>('/integrations/ticketing'),
  createTicketing: (body: TicketingConfigCreate) => api.post<TicketingConfigResponse>('/integrations/ticketing', body),
  deleteTicketing: (id: number) => api.delete<void>(`/integrations/ticketing/${id}`),
  getNotifications: () => api.get<NotificationConfigResponse[]>('/integrations/notifications'),
  createNotification: (body: NotificationConfigCreate) => api.post<NotificationConfigResponse>('/integrations/notifications', body),
  deleteNotification: (id: number) => api.delete<void>(`/integrations/notifications/${id}`),
  getIdpUser: (login: string) => api.get<IdpEnrichmentResponse>(`/integrations/idp/${login}`),
  refreshIdpUser: (login: string) => api.post<IdpEnrichmentResponse>(`/integrations/idp/${login}/refresh`),
};
```

---

## 5. Routing Structure

### `src/App.tsx`

```typescript
import { createBrowserRouter, RouterProvider, Navigate, Outlet } from 'react-router-dom';
import { useCurrentUser } from './hooks/useCurrentUser';
import { AppShell } from './components/layout/AppShell';
import LoginPage from './pages/LoginPage';
import DashboardPage from './pages/Dashboard';
import ThreatsPage from './pages/Threats';
import EventsPage from './pages/Events';
import VelocityPage from './pages/Velocity';
import DevActivityPage from './pages/DevActivity';
import CopilotPage from './pages/Copilot';
import ReportsPage from './pages/Reports';
import QueryPage from './pages/Query';
import RulesPage from './pages/Rules';
import UsersPage from './pages/Users';
import IntegrationsPage from './pages/Integrations';

/** 
 * AuthGuard: renders children only when /auth/me succeeds.
 * On 401 the api client redirects to /login automatically.
 * While loading, renders a full-page spinner.
 */
function AuthGuard() {
  const { data: user, isLoading, isError } = useCurrentUser();
  if (isLoading) return <FullPageSpinner />;
  if (isError || !user) return <Navigate to="/login" replace />;
  return <Outlet />;
}

const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  {
    element: <AuthGuard />,
    children: [
      {
        element: <AppShell />,
        children: [
          { index: true, element: <Navigate to="/dashboard" replace /> },
          { path: '/dashboard', element: <DashboardPage /> },
          { path: '/threats', element: <ThreatsPage /> },
          { path: '/events', element: <EventsPage /> },
          { path: '/velocity', element: <VelocityPage /> },
          { path: '/dev-activity', element: <DevActivityPage /> },
          { path: '/copilot', element: <CopilotPage /> },
          { path: '/reports', element: <ReportsPage /> },
          { path: '/query', element: <QueryPage /> },
          { path: '/rules', element: <RulesPage /> },
          { path: '/users', element: <UsersPage /> },
          { path: '/integrations', element: <IntegrationsPage /> },
        ],
      },
    ],
  },
]);

export default function App() {
  return <RouterProvider router={router} />;
}
```

**Route → Screen mapping:**

| Path | Screen | Nav Label |
|---|---|---|
| `/login` | LoginPage | — |
| `/dashboard` | DashboardPage | Dashboard |
| `/threats` | ThreatsPage | Threat Detections |
| `/events` | EventsPage | Events Explorer |
| `/velocity` | VelocityPage | Engineering Velocity |
| `/dev-activity` | DevActivityPage | Developer Activity |
| `/copilot` | CopilotPage | Copilot Insights |
| `/reports` | ReportsPage | Reports |
| `/query` | QueryPage | Query Explorer |
| `/rules` | RulesPage | Detection Rules |
| `/users` | UsersPage | Users & Roles |
| `/integrations` | IntegrationsPage | Integrations |

---

## 6. Component Architecture

### Layout Components

#### `AppShell.tsx`
```typescript
// Props: none — reads user from useCurrentUser()
// Renders:
//   <OrgContext.Provider value={...}>
//     <div className={styles.layout}>
//       <Sidebar />
//       <div className={styles.main}>
//         <TopBar />
//         <Outlet />   ← page content
//       </div>
//     </div>
//   </OrgContext.Provider>
//
// Local state: selectedOrg (string), setSelectedOrg
// Passes selectedOrg + setSelectedOrg into OrgContext
```

#### `Sidebar.tsx`
```typescript
// Props: none — reads useLocation() for active highlighting
// Nav sections:
//   - (root): Dashboard
//   - Security: Threat Detections (with live count badge), Events Explorer
//   - Platform Intelligence: Engineering Velocity, Developer Activity, Copilot Insights
//   - Analytics: Reports, Query Explorer
//   - Settings: Detection Rules, Users & Roles, Integrations
//
// The Threat Detections count badge: useQuery to GET /detections?status=investigating&page_size=1
//   → display `.total` as the nav-count badge
//   → refetchInterval: 60_000 (60 seconds)
//
// Active state: compare useLocation().pathname to each route's path
```

#### `TopBar.tsx`
```typescript
// Props: none — reads from useCurrentUser() and OrgContext
//
// Left side: org tabs
//   - Renders one tab per scoped_orgs from MeResponse
//   - Clicking a tab calls setSelectedOrg(orgName)
//   - Active tab = selectedOrg from OrgContext
//   - "+ Add org" tab is display-only at this stage (no backend endpoint)
//
// Right side:
//   - "New report" button → navigates to /reports
//   - Avatar: initials from github_login (first 2 chars, uppercase)
//   - Avatar onClick: dropdown with "Sign out" → calls authApi.logout() then navigate('/login')
```

### Primitive Components

#### `Button.tsx`
```typescript
interface ButtonProps {
  variant?: 'default' | 'primary' | 'danger';
  size?: 'sm' | 'md';
  onClick?: () => void;
  disabled?: boolean;
  type?: 'button' | 'submit';
  children: React.ReactNode;
}
// CSS module classes: .btn, .btnPrimary, .btnDanger, .btnSm
// Maps to mockup: .btn, .btn-primary, .btn-danger, .btn-sm
```

#### `Label.tsx`
```typescript
interface LabelProps {
  variant: 'danger' | 'attention' | 'success' | 'done' | 'muted' | 'accent' | 'severe';
  children: React.ReactNode;
}
// Renders <span className={...}>
// Maps to mockup: .label-danger, .label-attention, etc.
```

#### `MetricCard.tsx`
```typescript
interface MetricCardProps {
  value: string | number;
  label: string;
  delta?: string;
  deltaDirection?: 'up' | 'down' | 'neutral';
}
// Renders the .metric card: large value, small label, optional delta
```

#### `DataTable.tsx`
```typescript
interface Column<T> {
  key: string;
  header: string;
  render: (row: T) => React.ReactNode;
  width?: string;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  rows: T[];
  onRowClick?: (row: T) => void;
  selectedId?: number | string;
  emptyMessage?: string;
  isLoading?: boolean;
}
// Renders <table> with thead/tbody
// isLoading: show skeleton rows (3 rows, columns with animated shimmer via CSS animation)
// emptyMessage: center-aligned "No data" message in tbody
// onRowClick + selectedId: applies .il-row.selected class
```

#### `Modal.tsx`
```typescript
interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}
// Uses ReactDOM.createPortal to render into document.body
// Backdrop: fixed full-screen div with rgba(1,4,9,0.8) background
// Closes on backdrop click and Escape key
// Focus trap: keep focus inside modal while open
```

### Page Components

#### `DashboardPage` (`pages/Dashboard/index.tsx`)
```typescript
// Layout: screen-scroll > 
//   <ThreatPills />               ← stat pills row
//   <div className="grid-2">
//     <ActivityFeed />            ← timeline feed (last 20 events from GET /events?page_size=20)
//     <Card title="Platform Alerts">  ← top 5 open detections (GET /detections?status=investigating&page_size=5)
//       <DetectionList mini />
//     </Card>
//   </div>
//   <ContributionCalendar />      ← GET /events aggregated by day (compute client-side from response)
//
// Data fetched on this page:
//   - useQuery(['events', 'feed', selectedOrg], () => eventsApi.list({org, page_size: 20}))
//   - useQuery(['detections', 'open', selectedOrg], () => detectionsApi.list({status:'investigating', org, page_size:5}))
```

#### `ThreatsPage` (`pages/Threats/index.tsx`)
```typescript
// Layout: split-layout (flex, overflow:hidden)
//   Left: DetectionList (flex:1, overflow-y:auto, padding:24px)
//   Right: DetectionPanel (width:480px, open when selectedId !== null)
//
// Local state:
//   selectedId: number | null
//   statusFilter: 'all' | 'investigating' | 'resolved' | 'false_positive'
//   severityFilter: 'all' | 'critical' | 'high' | 'medium' | 'low'
//   page: number
//
// Query key: ['detections', {statusFilter, severityFilter, page, org}]
// Query fn: detectionsApi.list({status, severity, org, page, page_size: 50})
//
// Mutations:
//   updateStatus → useMutation, invalidates ['detections'] on success
//   assign → useMutation, invalidates ['detections', id] on success
//   suppress → useMutation + ConfirmDialog
//   delete → useMutation + ConfirmDialog
```

#### `EventsPage` (`pages/Events/index.tsx`)
```typescript
// Layout: screen-scroll >
//   <EventFilters />
//   <EventTable />
//   <EventDetailPanel open={selectedId !== null} />
//
// Local state:
//   filters: EventListParams (org, actor, action, since, until, etc.)
//   page: number
//   selectedId: number | null
//
// Query key: ['events', filters, page, org]
// Query fn: eventsApi.list({...filters, org, page, page_size: 50})
//
// Filter inputs are debounced 400ms before updating query key
```

#### `VelocityPage` (`pages/Velocity/index.tsx`)
```typescript
// Layout: screen-scroll >
//   <DoraTierBadge tier="elite" />     ← computed from actionsVolume data
//   <VelocityMetricStrip />            ← 8 MetricCards
//   <div className="grid-2">
//     <LineAreaChart ... />            ← Lead time (actionsVolume data)
//     <LineAreaChart ... />            ← CFR trend
//   </div>
//   <div className="grid-2">
//     <LineAreaChart ... />            ← Workflow success rate
//     <BarChart ... />                 ← Daily deployments
//   </div>
//   <RepoTable />                      ← repo-creation-rate data
//
// Data fetched:
//   useQuery(['reports','actionsVolume',params], () => reportsApiMap.actionsVolume(params))
//   useQuery(['reports','repoCreation',params], () => reportsApiMap.repoCreationRate(params))
//
// Window selector: local state windowDays: ReportWindow = '30d'
// Granularity: derived from window (30d→daily, 90d→weekly)
```

#### `DevActivityPage` (`pages/DevActivity/index.tsx`)
```typescript
// Data source: GET /admin/top-actors (top 20)
// Layout: screen-scroll >
//   <WorkDistribution />     ← horizontal bar chart: commits vs PRs vs reviews
//   <BusFactor />            ← warning if top actor > 40% of events
//   <DeveloperGrid />        ← grid of DeveloperCards
//
// useQuery(['admin','topActors'], () => adminApi.getTopActors())
// Requires role: admin or analyst (enforced by backend RBAC, frontend shows empty state)
```

#### `CopilotPage` (`pages/Copilot/index.tsx`)
```typescript
// Data: reportsApiMap.copilotSeats(params) + reportsApiMap.seatUtilization(params)
// Layout: screen-scroll >
//   <SeatWasteAlert />        ← shown if utilization_pct < 60%
//   <CopilotMetricStrip />    ← 6 MetricCards (from latest bucket)
//   <div className="grid-2">
//     <LineAreaChart />       ← acceptance rate 7d rolling (mocked from seats_net buckets)
//     <BarChart />            ← seat utilization timeline
//   </div>
//   <InactiveSeatsTable />    ← seats_revoked entries from last bucket
```

#### `ReportsPage` (`pages/Reports/index.tsx`)
```typescript
// Static list of report definitions (no query needed for the cards themselves)
// Each card has: title, description, export button
// Export button: window.open(reportsApiMap.exportUrl(type, {org}), '_blank')
//
// Report definitions:
const REPORTS = [
  { type: 'mau', title: 'Monthly Active Users', description: 'Unique actors per day/week/month' },
  { type: 'seat-utilization', title: 'Seat Utilization', description: 'Active vs provisioned seats over time' },
  { type: 'copilot-seats', title: 'Copilot Seats', description: 'Seat assignments, revocations, and policy changes' },
  { type: 'actions-volume', title: 'Actions Volume', description: 'Workflow run success/failure rates' },
  { type: 'repo-creation-rate', title: 'Repo Creation Rate', description: 'Repository lifecycle events' },
  { type: 'codespace-hours', title: 'Codespace Hours', description: 'Codespace create/delete and unique actors' },
  { type: 'pat-counts', title: 'PAT Counts', description: 'Personal Access Token lifecycle and risk' },
  { type: 'webhook-counts', title: 'Webhook Counts', description: 'Webhook and app installation activity' },
];
```

#### `QueryPage` (`pages/Query/index.tsx`)
```typescript
// Layout: query-layout (flex, gap:16px)
//   Left: <SchemaTree />  (220px fixed)
//   Right: flex column
//           <TemplatePicker />
//           <SqlEditor />         ← controlled textarea with line numbers
//           <div> Run + Validate buttons </div>
//           <QueryResults />      ← shown after successful run
//
// Local state:
//   sql: string
//   results: QueryRunResponse | null
//   isRunning: boolean
//   validationResult: { valid: boolean; error?: string } | null
//
// Mutations (useMutation, not useQuery — user-triggered):
//   runQuery: queryApi.run
//   validateQuery: queryApi.validate
//
// Note: SQL editor is a plain <textarea> styled to look like the mockup's code editor.
// Do NOT use Monaco or CodeMirror. Line numbers computed from sql.split('\n').length.
```

#### `RulesPage` (`pages/Rules/index.tsx`)
```typescript
// Layout: screen-scroll >
//   <div> page title + "New Rule" button </div>
//   <RulesTable />
//   <RuleForm open={...} rule={editingRule} onClose={...} />
//
// Local state:
//   showForm: boolean
//   editingRule: RuleResponse | null
//
// useQuery(['rules'], () => rulesApi.list())
// useMutation for create/update/delete/toggleStatus
// All mutations invalidate ['rules'] on success
```

#### `UsersPage` (`pages/Users/index.tsx`)
```typescript
// Layout: screen-scroll >
//   <section> Role definitions display (read-only table from GET /admin/roles) </section>
//   <section> 
//     <RoleAssignmentsTable /> 
//     <Button onClick={() => setShowAdd(true)}>Add Assignment</Button>
//   </section>
//
// useQuery(['admin','roles'], () => adminApi.getRoles())
// useQuery(['admin','assignments'], () => adminApi.getAssignments())
// useMutation for createAssignment + deleteAssignment
```

#### `IntegrationsPage` (`pages/Integrations/index.tsx`)
```typescript
// Layout: screen-scroll >
//   <section title="Ticketing">
//     <div className="mkt-grid">
//       <TicketingCards />     ← existing configs + "Add Jira" + "Add GitHub Issues" cards
//     </div>
//   </section>
//   <section title="Notifications">
//     <div className="mkt-grid">
//       <NotificationCards />  ← existing configs + "Add Slack" + "Add Email" cards
//     </div>
//   </section>
//
// useQuery(['integrations','ticketing'], () => integrationsApi.getTicketing())
// useQuery(['integrations','notifications'], () => integrationsApi.getNotifications())
```

---

## 7. State Management

### Principle: Server State vs UI State

**React Query manages all server state.** `useState` manages all pure UI state. No global store needed.

| Data | Type | Location |
|---|---|---|
| Current user (`/auth/me`) | Server state | `useCurrentUser` hook → React Query |
| Detections list | Server state | `ThreatsPage` → React Query |
| Selected detection ID | UI state | `ThreatsPage` → `useState` |
| Events list | Server state | `EventsPage` → React Query |
| Active event filter values | UI state | `EventsPage` → `useState` |
| Selected org | UI state | `OrgContext` → passed to all queries |
| SQL editor content | UI state | `QueryPage` → `useState` |
| Query results | Server state | `useMutation` result (not `useQuery`) |
| Rules list | Server state | `RulesPage` → React Query |
| Modal open/close state | UI state | parent page → `useState` |
| Report window selector | UI state | page component → `useState` |

### `src/context/OrgContext.tsx`

```typescript
import { createContext, useContext, useState } from 'react';

interface OrgContextValue {
  selectedOrg: string | undefined;
  setSelectedOrg: (org: string | undefined) => void;
}

export const OrgContext = createContext<OrgContextValue>({
  selectedOrg: undefined,
  setSelectedOrg: () => {},
});

export function useOrg() {
  return useContext(OrgContext);
}
```

### `src/hooks/useCurrentUser.ts`

```typescript
import { useQuery } from '@tanstack/react-query';
import { authApi } from '../api/auth';

export function useCurrentUser() {
  return useQuery({
    queryKey: ['auth', 'me'],
    queryFn: authApi.getMe,
    staleTime: 5 * 60 * 1000,   // 5 minutes
    retry: false,                 // Don't retry on 401 — api client handles the redirect
  });
}
```

### React Query Client Config (`src/main.tsx`)

```typescript
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,          // 30 seconds default
      refetchOnWindowFocus: true,
      retry: (failureCount, error) => {
        if (error instanceof ApiError && error.status < 500) return false;
        return failureCount < 2;
      },
    },
    mutations: {
      onError: (error) => {
        // Global mutation error handler — show a toast or ErrorBanner
        // Each page can override with its own onError
      },
    },
  },
});
```

---

## 8. CSS Architecture

### Design System Files

#### `src/styles/tokens.css`
Declares all CSS custom properties on `:root`. Maps directly from the mockup's `:root` block:

```css
:root {
  --canvas: #0d1117;
  --canvas-subtle: #161b22;
  --canvas-inset: #010409;
  --border: #30363d;
  --border-muted: #21262d;
  --fg: #e6edf3;
  --fg-muted: #8b949e;
  --fg-subtle: #6e7681;
  --accent: #58a6ff;
  --accent-bg: #1f6feb;
  --success: #3fb950;
  --danger: #f85149;
  --attention: #d29922;
  --severe: #db6d28;
  --done: #bc8cff;
  --sidebar-w: 240px;
  --topbar-h: 48px;
  --font-mono: ui-monospace, SFMono-Regular, "SF Mono", Consolas, monospace;
  --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", Helvetica, Arial, sans-serif;
  --radius: 6px;
}
```

#### `src/styles/reset.css`
```css
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html, body { height: 100%; }
body {
  background: var(--canvas);
  color: var(--fg);
  font-family: var(--font-sans);
  font-size: 14px;
  line-height: 1.5;
}
a { color: var(--accent); text-decoration: none; }
```

#### `src/styles/global.css`
```css
@import './tokens.css';
@import './reset.css';
/* Any truly global utility classes (e.g. .sr-only for accessibility) */
.sr-only {
  position: absolute; width: 1px; height: 1px;
  padding: 0; margin: -1px; overflow: hidden;
  clip: rect(0,0,0,0); white-space: nowrap; border-width: 0;
}
```

### CSS Modules Pattern

Every component has a paired `.module.css` file. CSS custom properties from `tokens.css` are available in every module because `global.css` is imported once in `main.tsx`, which sets them on `:root`.

**Example — `Button.module.css`:**
```css
.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  font-size: 13px;
  font-weight: 500;
  border-radius: var(--radius);
  cursor: pointer;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--fg);
  line-height: 20px;
  font-family: inherit;
}
.btn:hover { background: rgba(177, 186, 196, 0.08); }
.btnPrimary { background: #238636; border-color: rgba(240,246,252,0.1); color: #fff; }
.btnPrimary:hover { background: #2ea043; }
.btnDanger { background: var(--danger); border-color: rgba(240,246,252,0.1); color: #fff; }
.btnSm { padding: 3px 8px; font-size: 12px; }
```

**Rule: No inline styles on components.** Every visual property lives in the `.module.css` file. The only exception is ECharts `option` objects — those are JS objects, not CSS.

### CSS Naming Convention

Use camelCase for CSS module class names (CSSModules transforms them). Match the mockup's semantic names where possible:

| Mockup class | CSS module key |
|---|---|
| `.btn` | `.btn` |
| `.btn-primary` | `.btnPrimary` |
| `.nav-item` | `.navItem` |
| `.nav-item.active` | `.navItem.active` or compose with `:global(.active)` |
| `.cal-cell[data-level="3"]` | attribute selector kept as-is in module |

---

## 9. Vite Configuration

### `frontend/vite.config.ts`

```typescript
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],

  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },

  css: {
    modules: {
      // camelCase class names: styles.myClass instead of styles['my-class']
      localsConvention: 'camelCase',
    },
  },

  server: {
    port: 3000,
    proxy: {
      // All /api/ requests proxied to the FastAPI backend during development
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        // Do NOT rewrite path — backend expects /api/v1/...
      },
    },
  },

  build: {
    outDir: 'dist',
    sourcemap: false,    // disabled in production for security
    rollupOptions: {
      output: {
        // Split vendor chunks for better caching
        manualChunks: {
          'react-vendor': ['react', 'react-dom', 'react-router-dom'],
          'query-vendor': ['@tanstack/react-query'],
          'echarts-vendor': ['echarts', 'echarts-for-react'],
        },
      },
    },
  },
});
```

### `frontend/tsconfig.json`

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "baseUrl": ".",
    "paths": {
      "@/*": ["src/*"]
    }
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

### `frontend/tsconfig.node.json`

```json
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true
  },
  "include": ["vite.config.ts"]
}
```

---

## 10. Security Controls

### CSRF Token Lifecycle

The backend sets `X-CSRF-Token` header on **every response** (including GET responses used for page load). The flow is:

1. App loads → `useCurrentUser` fires GET `/auth/me` → backend sets `X-CSRF-Token: <token>` in response header → `apiFetch` captures it into `csrfToken` module variable.
2. User triggers a mutation → `apiFetch` reads `csrfToken` → sets `X-CSRF-Token: <token>` in request header.
3. If backend rotates the token, it sends a new `X-CSRF-Token` on the mutation response → `apiFetch` captures the new value.
4. If `csrfToken` is `null` when a mutation fires (edge case: user navigates directly to a mutation without first loading any data), the app **must not proceed** — the backend will reject the request with 403.

**Implementation detail in `client.ts`:** The `csrfToken` is a module-level variable (not React state, not localStorage). It lives in memory only, which is correct — it never needs to survive a page refresh (page refresh re-fetches `/auth/me` which refreshes the token).

### Auth Guard

- `AuthGuard` wraps all authenticated routes
- It calls `useCurrentUser()` which calls `GET /auth/me`
- If the cookie is expired, the backend returns 401 → `apiFetch` calls `window.location.replace('/login')` → browser redirects
- No JWT token is ever visible to JavaScript (httponly cookie)
- No auth data is ever stored in `localStorage` or `sessionStorage`

### Content Security Policy

The backend already sets CSP headers. The frontend must not break them:
- **No inline styles** on components (use CSS modules)
- **No `eval()`** or dynamic code execution
- ECharts renders to canvas — no SVG injection that would bypass nonce-based CSP
- All API calls go to same-origin (`/api/v1/...`) — no cross-origin fetches

### Input Sanitization

- SQL editor (`QueryPage`): the textarea value is sent verbatim — no client-side escaping needed because the backend uses pglast AST validation and a readonly DB role
- All user-supplied strings in filter inputs are passed as URL search params via `URLSearchParams` — automatic percent-encoding prevents injection in the URL
- No `dangerouslySetInnerHTML` anywhere in the codebase

### Sensitive Data

- No user PII, access tokens, or session data in component state that gets serialized
- React Query's cache lives in memory only — clears on page refresh
- The only persistent browser storage allowed: nothing. No localStorage, no sessionStorage, no IndexedDB.

---

## 11. Package.json

### `frontend/package.json`

```json
{
  "name": "octowatch-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc --noEmit && vite build",
    "preview": "vite preview",
    "lint": "eslint src --ext ts,tsx --report-unused-disable-directives --max-warnings 0",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "@tanstack/react-query": "5.56.2",
    "echarts": "5.5.1",
    "echarts-for-react": "3.0.2",
    "react": "18.3.1",
    "react-dom": "18.3.1",
    "react-router-dom": "6.26.2"
  },
  "devDependencies": {
    "@types/react": "18.3.5",
    "@types/react-dom": "18.3.0",
    "@typescript-eslint/eslint-plugin": "8.4.0",
    "@typescript-eslint/parser": "8.4.0",
    "@vitejs/plugin-react": "4.3.1",
    "eslint": "9.9.1",
    "eslint-plugin-react-hooks": "5.1.0-rc.0",
    "eslint-plugin-react-refresh": "0.4.11",
    "typescript": "5.5.4",
    "vite": "5.4.8"
  }
}
```

### ESLint Config (`.eslintrc.cjs`)

```javascript
module.exports = {
  root: true,
  env: { browser: true, es2020: true },
  extends: [
    'eslint:recommended',
    'plugin:@typescript-eslint/strict',
    'plugin:react-hooks/recommended',
  ],
  parser: '@typescript-eslint/parser',
  parserOptions: { ecmaVersion: 'latest', sourceType: 'module', project: './tsconfig.json' },
  plugins: ['@typescript-eslint', 'react-refresh'],
  rules: {
    'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
    '@typescript-eslint/no-explicit-any': 'error',
    '@typescript-eslint/consistent-type-imports': 'error',
    'no-console': ['warn', { allow: ['warn', 'error'] }],
  },
};
```

---

## 12. Development Runbook

### First-time setup

```bash
cd frontend
npm install
```

### Dev server (with hot reload)

Requires backend running at `http://localhost:8000`:

```bash
npm run dev
# → http://localhost:3000
# All /api/ requests proxy to http://localhost:8000
```

### Type-check only (no build)

```bash
npm run typecheck
```

### Production build

```bash
npm run build
# Output: frontend/dist/
```

The nginx config in `/nginx/nginx.conf` should serve the `dist/` directory for non-`/api` requests and proxy `/api/` to the FastAPI backend. The Development Agent must update `nginx.conf` to add:

```nginx
root /usr/share/nginx/html;
try_files $uri $uri/ /index.html;  # SPA fallback for React Router
```

### `src/main.tsx` (entry point)

```typescript
import React from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClientProvider, QueryClient } from '@tanstack/react-query';
import App from './App';
import { ApiError } from './api/client';
import './styles/global.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: true,
      retry: (failureCount, error) => {
        if (error instanceof ApiError && error.status < 500) return false;
        return failureCount < 2;
      },
    },
  },
});

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
);
```

### `index.html` (Vite entry)

```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>OctoWatch</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

---

## Appendix A: Query Keys Convention

All React Query keys must follow a consistent hierarchy to enable targeted cache invalidation:

```
['auth', 'me']
['detections', filters_object]            // list
['detections', 'detail', id]              // single
['events', filters_object]
['events', 'detail', id]
['events', 'raw', id]
['reports', report_type, params_object]
['rules']
['rules', 'detail', id]
['query', 'templates']
['admin', 'roles']
['admin', 'assignments']
['admin', 'top-actors']
['admin', 'retention']
['admin', 'ingestion-sources']
['integrations', 'ticketing']
['integrations', 'notifications']
```

On mutation success, invalidate with the minimal prefix. For example:
- After `deleteAssignment`: `queryClient.invalidateQueries({ queryKey: ['admin', 'assignments'] })`
- After `updateStatus` on a detection: `queryClient.invalidateQueries({ queryKey: ['detections'] })` (invalidates list AND detail)

---

## Appendix B: ECharts Usage Pattern

All ECharts components live in `src/components/charts/`. They receive pure data props and construct the ECharts `option` object internally.

```typescript
// src/components/charts/LineAreaChart.tsx
import ReactECharts from 'echarts-for-react';

interface LineAreaChartProps {
  title?: string;
  xData: string[];
  series: Array<{
    name: string;
    data: number[];
    color: string;
    areaOpacity?: number;
  }>;
  height?: number;
}

export function LineAreaChart({ title, xData, series, height = 110 }: LineAreaChartProps) {
  const option = {
    backgroundColor: 'transparent',
    grid: { top: title ? 28 : 8, bottom: 20, left: 8, right: 8, containLabel: true },
    tooltip: { trigger: 'axis', backgroundColor: '#161b22', borderColor: '#30363d', textStyle: { color: '#e6edf3' } },
    xAxis: { type: 'category', data: xData, axisLine: { lineStyle: { color: '#30363d' } }, axisLabel: { color: '#6e7681', fontSize: 9 }, splitLine: { show: false } },
    yAxis: { type: 'value', axisLine: { show: false }, axisLabel: { color: '#6e7681', fontSize: 9 }, splitLine: { lineStyle: { color: '#21262d' } } },
    series: series.map(s => ({
      name: s.name, type: 'line', smooth: false,
      data: s.data,
      lineStyle: { color: s.color, width: 2 },
      itemStyle: { color: s.color },
      symbol: 'none',
      areaStyle: s.areaOpacity !== undefined ? { color: s.color, opacity: s.areaOpacity } : undefined,
    })),
  };

  return (
    <div className={/* chart-wrap module class */}>
      {title && <div className={/* chart-title */}>{title}</div>}
      <ReactECharts option={option} style={{ height }} notMerge />
    </div>
  );
}
```

---

## Appendix C: RBAC-Aware UI

The backend enforces RBAC — the frontend should hide controls that the current user lacks permission to use. Role checks are defensive UI only (backend is authoritative).

Available roles from `GET /admin/roles`:
- `admin` — full access
- `analyst` — read + detection management
- `viewer` — read only

```typescript
// src/hooks/useCurrentUser.ts — add role helpers
export function useIsAdmin() {
  const { data } = useCurrentUser();
  return data?.roles.includes('admin') ?? false;
}

export function useIsAtLeastAnalyst() {
  const { data } = useCurrentUser();
  return data?.roles.some(r => ['admin', 'analyst'].includes(r)) ?? false;
}
```

Apply in components:
```typescript
const isAdmin = useIsAdmin();
// ...
{isAdmin && <Button variant="danger" onClick={...}>Delete</Button>}
```

Pages where RBAC matters:
- **Detection actions** (assign, suppress, delete): analyst+
- **Detection Rules CRUD**: admin only
- **Users & Roles page**: admin only
- **Admin Ingestion Sources / Retention**: admin only
- **Query Explorer**: analyst+

---

## Appendix D: Accessible Markup Requirements

All interactive components must meet WCAG 2.1 AA:

- Every `<button>` has visible focus style: `outline: 2px solid var(--accent); outline-offset: 2px`
- All icon-only buttons have `aria-label`
- `<Modal>` sets `role="dialog"`, `aria-modal="true"`, `aria-labelledby` pointing to title `id`
- `<DataTable>` uses semantic `<table>`, `<thead>`, `<th scope="col">`, `<tbody>`
- `<SeverityDot>` has `aria-label="severity: critical"` etc.
- Color is never the only indicator of state (labels have text + color)
- `ContributionCalendar` cells have `aria-label="MM DD: N events"` tooltip via `title` attribute
- Loading spinners have `role="status"` and `aria-label="Loading..."`
