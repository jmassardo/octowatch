---
applyTo: "frontend/**"
---

# Frontend Instructions

## Framework & Patterns
- React 19 with TypeScript (strict mode), built with Vite 8
- TanStack React Query for all server state — no `useEffect` for data fetching
- ECharts via `echarts-for-react` for all charts/graphs
- React Router v7 for navigation

## File Organization
- **API** (`src/api/`): Typed fetch wrappers. Each function returns `Promise<T>` with explicit response types. Use `buildQuery()` helper for query params.
- **Pages** (`src/pages/`): Feature-organized. Each page dir may contain pane components.
- **Components** (`src/components/`): Reusable UI — `charts/` (ECharts wrappers), `common/` (PageHeader, skeletons), `primitives/` (DataTable, Drawer), `widgets/` (dashboard cards).
- **Context** (`src/context/`): React contexts — `OrgContext` (org filter), `AuthContext` (user session).
- **Hooks** (`src/hooks/`): Custom hooks — `useOrg()`, `useFeatures()`, `useDateRange()`.

## Conventions
- Named exports only (no `export default`)
- Include `selectedOrg` in React Query `queryKey` for org-filtered queries
- Use `useOrg()` to get current organization filter; pass as `org: selectedOrg || undefined` to API
- API functions accept optional `org?: string` param — `undefined` is omitted from query string by `buildQuery()`
- Wrap API calls in arrow functions for `queryFn` (don't pass directly — React Query injects context objects)
- Test imports must be explicit: `import { describe, it, expect, vi, beforeEach } from 'vitest'`
- Charts must include accessibility: use sr-only data tables via `chartA11y` utils

## Testing
- Vitest + @testing-library/react
- Use `renderWithProviders()` helper for components needing QueryClient + Router context
- Mock ECharts: `vi.mock('echarts-for-react', ...)`
- Mock API calls: `vi.mock('../api/someApi')`
- Run: `cd frontend && npx vitest run --reporter=verbose`

## Validation
```bash
npx eslint src/ --quiet              # Lint
npx tsc --noEmit                     # Type check (fast)
npx vitest run --reporter=verbose    # Tests
npm run build                        # Full build (tsc -b + vite)
```

## Important: Docker Build
Docker uses `tsc -b` (build mode with project references) which is stricter than `tsc --noEmit`. Always verify with `npm run build` before merging.
