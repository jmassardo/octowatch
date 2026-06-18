# OctoWatch — Copilot Instructions

## Project Overview

OctoWatch is a security analytics platform for GitHub Enterprise Cloud audit logs. It ingests audit events (via Splunk HEC, S3, Azure Blob, or GitHub webhooks), detects threats, and provides operational dashboards for security teams and GitHub administrators.

## Tech Stack

### Backend
- **Language**: Python 3.12+
- **Framework**: FastAPI with async/await
- **ORM**: SQLAlchemy 2.x with `AsyncSession`, `Mapped[]` type annotations
- **Database**: TimescaleDB (PostgreSQL extension) — hypertables for time-series event data
- **Cache/Broker**: Valkey (Redis-compatible) — used as Celery broker and result backend
- **Task Queue**: Celery with multiple dedicated queues (ingestion, detection, baseline, notification, sync, enrichment)
- **Logging**: structlog (structured JSON logging)
- **Linting**: ruff (lint + format)
- **Type Checking**: mypy
- **Testing**: pytest with async support (`pytest-asyncio`)

### Frontend
- **Language**: TypeScript (strict mode)
- **Framework**: React 19 with Vite 8
- **State**: TanStack React Query for server state
- **Charts**: ECharts via `echarts-for-react`
- **Routing**: React Router v7
- **Testing**: Vitest + @testing-library/react
- **Linting**: ESLint + Prettier

### Infrastructure
- **Cloud**: Azure (VMs, networking, storage, DNS)
- **Orchestration**: Self-managed kubeadm Kubernetes cluster (3 nodes + management VM)
- **IaC**: Terraform (Azure provider)
- **Packaging**: Helm chart for K8s deployment, Docker Compose for development
- **CI/CD**: GitHub Actions → GHCR → Helm upgrade on self-hosted runner
- **TLS**: cert-manager with Let's Encrypt

## Project Structure

```
backend/
├── app/
│   ├── main.py              # FastAPI app factory, middleware, router registration
│   ├── config.py             # Pydantic settings (env-based configuration)
│   ├── deps.py               # Dependency injection (db sessions, auth, permissions)
│   ├── models/               # SQLAlchemy ORM models
│   ├── routers/              # FastAPI route handlers (~50 routers)
│   ├── services/             # Business logic layer
│   ├── workers/              # Celery task definitions
│   │   └── ingestion/        # Audit log ingestion pipeline
│   └── celery_app.py         # Celery configuration and beat schedule
├── alembic/                  # Database migrations (sequential 0001–00XX numbering)
├── tests/                    # pytest test suite
└── Dockerfile

frontend/
├── src/
│   ├── App.tsx               # Router definition
│   ├── api/                  # API client functions (typed fetch wrappers)
│   ├── components/           # Reusable UI components
│   │   ├── charts/           # ECharts wrapper components
│   │   ├── common/           # PageHeader, SkeletonCard, etc.
│   │   ├── primitives/       # DataTable, Drawer, Label, etc.
│   │   └── widgets/          # Dashboard widget components
│   ├── context/              # React contexts (OrgContext, AuthContext)
│   ├── hooks/                # Custom hooks (useOrg, useFeatures, etc.)
│   └── pages/                # Page components organized by feature
├── Dockerfile
└── tsconfig.app.json         # TypeScript config (strict, bundler mode)

terraform/                    # Azure infrastructure (VMs, networking, K8s cluster)
helm/                         # Kubernetes Helm chart
docs/                         # Documentation, ADRs, runbooks
scripts/                      # Operational scripts (backup, restore, deploy)
```

## Coding Conventions

### Backend (Python)
- Use `from __future__ import annotations` in all files
- Use `Mapped[]` and `mapped_column()` for SQLAlchemy models (not `Column()`)
- Use `AsyncSession` for all database operations
- Use `text()` for raw SQL queries with named parameters (`:param_name`)
- Use `structlog.get_logger(__name__)` for logging
- Service functions return `dict[str, Any]` (not Pydantic models for API responses)
- Router endpoints use `Depends(require_permission("resource", "action"))` for auth
- Alembic migrations use sequential numbering: `0001_`, `0002_`, etc.
- All public service functions start with `await _check_feature_enabled(db)` guard

### Frontend (TypeScript)
- Use named exports (not default exports) for components
- Use `useQuery` from TanStack React Query for data fetching
- Include `selectedOrg` in `queryKey` arrays for org-filtered queries
- Use `useOrg()` hook to get the current organization filter
- API functions live in `frontend/src/api/` and return typed Promises
- Test files use explicit imports: `import { describe, it, expect, vi } from 'vitest'`
- ECharts components use `ReactECharts` from `echarts-for-react`
- Accessibility: charts include sr-only tables via `chartA11y` utils

## Build & Test Commands

### Backend
```bash
cd backend
ruff check .                    # Lint
ruff format --check .           # Format check
mypy .                          # Type check
pytest tests/ -x -q             # Run tests
alembic upgrade head            # Run migrations
```

### Frontend
```bash
cd frontend
npx eslint src/ --quiet         # Lint
npx tsc --noEmit                # Type check (fast, no build)
npx tsc -b                      # Type check (build mode, used by Docker)
npm run build                   # Full build (tsc -b && vite build)
npx vitest run --reporter=verbose  # Run tests
```

### Full Validation
```bash
# Backend
cd backend && ruff check . && ruff format --check . && pytest tests/ -x -q

# Frontend
cd frontend && npx eslint src/ --quiet && npx tsc --noEmit && npx vitest run --reporter=verbose && npm run build
```

## Infrastructure

### Kubernetes Cluster
- 3-node kubeadm cluster: 1 control plane + 2 workers
- Management VM serves as bastion, CI runner, and kubectl entry point
- K8s nodes have NO public IPs — all admin traffic flows through the mgmt subnet
- SSH to mgmt VM: `ssh octowatch@<mgmt-public-ip>`
- SSH to K8s nodes: `ssh -J octowatch@<mgmt-ip> octowatch@<node-ip>`

### Deployment
- CI builds Docker images → pushes to GHCR
- Self-hosted GitHub Actions runner on mgmt VM pulls and deploys via `helm upgrade`
- Helm chart at `helm/` defines all K8s resources
- Terraform at `terraform/` manages Azure infrastructure

## Key Architectural Patterns

### Authentication & Authorization
- GitHub OAuth for user login
- RBAC with `require_permission("resource", "action")` dependency injection
- Org-scoped data isolation via `useOrg()` hook (frontend) and `org` query params (backend)

### Data Ingestion Pipeline
- Events flow: Source (HEC/S3/Webhook) → Celery worker → dedup → normalize → DB insert
- Webhook endpoint validates HMAC-SHA256 signatures
- Each ingestion source produces normalized `AuditEvent` records

### Organization Filter
- TopBar has org selector dropdown
- All API functions accept optional `org` parameter
- Backend endpoints accept `org: str | None = Query(None)` and filter queries
- Frontend panes use `useOrg()` hook and include `orgParam` in `queryKey`

### Event Processing
- Celery workers process events asynchronously across dedicated queues
- Beat scheduler runs periodic tasks (baselines, classification, retention, reports)
- Detection engine evaluates rules against incoming events
