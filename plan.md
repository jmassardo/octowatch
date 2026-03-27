# OctoWatch — Open Source Launch Plan

> Comprehensive implementation plan for preparing OctoWatch for open-source release.
> Generated from a full codebase audit on 2026-03-27.

---

## Workstream 1: Repository Hygiene (Critical)

These items **must** be completed before the repo goes public.

### 1.1 Add root `.gitignore`

Create `/.gitignore` covering:

```
# Environment
.env
.env.*
!.env.example

# Python
__pycache__/
*.pyc
*.pyo
*.egg-info/
dist/
build/
.venv/
venv/
.mypy_cache/
.ruff_cache/
.pytest_cache/
htmlcov/
.coverage

# Node / Frontend
node_modules/
frontend/dist/

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# OS
.DS_Store
Thumbs.db

# TLS / Secrets
nginx/ssl/*.pem
nginx/ssl/*.key
nginx/ssl/*.crt

# Misc
*.log
```

### 1.2 Remove SSL certificates from repo

- Delete `nginx/ssl/cert.pem` and `nginx/ssl/key.pem` from git tracking
- Run: `git rm --cached nginx/ssl/cert.pem nginx/ssl/key.pem`
- Add a `nginx/ssl/.gitkeep` placeholder
- Add a `nginx/ssl/README.md` explaining how to generate self-signed certs:
  ```
  openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout key.pem -out cert.pem \
    -subj "/CN=localhost"
  ```

### 1.3 Remove dead development files

- Delete `backend/debug_test.py`
- Delete `backend/fix_ann001.py`

### 1.4 Add LICENSE

- Choose license (recommend Apache 2.0 for enterprise-friendly OSS)
- Create `/LICENSE` at repo root

### 1.5 Scrub git history (optional but recommended)

- Verify no secrets exist in git history (the `.env` file appears untracked, but SSL certs may have been committed)
- If certs were committed, consider using `git filter-repo` to remove them from history

---

## Workstream 2: Documentation (Critical)

### 2.1 Create root README.md

Structure:
- **Project name, tagline, badges** (CI, license, version)
- **Screenshot / demo GIF** (use mockup or running instance)
- **What is OctoWatch?** — 2-3 paragraph description
- **Key features** — bullet list
- **Architecture overview** — diagram or brief description
- **Quickstart** — Docker Compose setup in ≤5 commands
- **Configuration** — link to `.env.example` and docs
- **Documentation** — links to `docs/` files
- **Contributing** — link to `CONTRIBUTING.md`
- **License** — link to `LICENSE`

### 2.2 Create CONTRIBUTING.md

Cover:
- Development environment setup (Docker Compose, Python venv, Node)
- Code style (ruff for Python, ESLint for TypeScript)
- Branch naming and PR process
- Commit message conventions
- Testing requirements (backend: pytest ≥80% coverage; frontend: TBD)
- How to run linters, tests, and builds locally
- Issue and PR templates reference
- Code of conduct reference

### 2.3 Create CODE_OF_CONDUCT.md

- Adopt Contributor Covenant v2.1 (industry standard)

### 2.4 Create SECURITY.md

Cover:
- How to report security vulnerabilities (email or GitHub Security Advisories)
- Supported versions
- Security update policy
- Disclosure timeline

### 2.5 Create CHANGELOG.md

- Initialize with current state as v0.1.0
- Document major features implemented so far
- Establish Keep a Changelog format

### 2.6 Fix stale documentation

| File | Issue | Fix |
|------|-------|-----|
| `docs/frontend-architecture-spec.md` | References React 18 / Vite 5.4 | Update to React 19 / Vite 8 |
| `requirements-questionnaire.md` | Says "no polling" | Add note that S3/Azure polling was chosen for v1 reliability |
| `docs/security-and-deployment.md` | Says audit trail logs "every request" | Clarify: mutating methods only, when actor is extractable |
| `docs/architecture.md` | May have version drift | Review against actual implementation |

---

## Workstream 3: GitHub Community Infrastructure (High)

### 3.1 Add issue templates

Create `.github/ISSUE_TEMPLATE/`:
- `bug_report.yml` — structured bug report (steps to reproduce, expected/actual, environment)
- `feature_request.yml` — feature proposal (problem, solution, alternatives)
- `config.yml` — template chooser config

### 3.2 Add PR template

Create `.github/pull_request_template.md`:
- Description of changes
- Related issue(s)
- Type of change (bug fix, feature, breaking change, docs)
- Checklist (tests, docs, lint, changelog)

### 3.3 Add GitHub repository metadata

Prepare for when the repo is created/configured:
- Description, topics, homepage URL
- Enable Discussions
- Branch protection rules for `main`
- Required status checks

---

## Workstream 4: CI/CD Pipeline Updates (High)

### 4.1 Update `ci.yml` for frontend

Add frontend CI jobs:
- `frontend-lint`: `cd frontend && npm ci && npm run lint`
- `frontend-typecheck`: `cd frontend && npm ci && npx tsc --noEmit`
- `frontend-build`: `cd frontend && npm ci && npm run build`
- `frontend-test`: `cd frontend && npm ci && npm test` (after tests are added)

Remove stale comments about "frontend source is absent."

### 4.2 Update `release.yml`

- Ensure frontend image build is no longer conditional
- Verify frontend Dockerfile is included in the build

### 4.3 Add CI for plan validation (optional)

- Markdown link checking
- YAML validation for Helm charts

---

## Workstream 5: Frontend Testing (High)

### 5.1 Set up testing infrastructure

Install and configure:
- `vitest` — test runner (Vite-native)
- `@testing-library/react` — component testing
- `@testing-library/jest-dom` — DOM matchers
- `@testing-library/user-event` — user interaction simulation
- `jsdom` — DOM environment
- `msw` (Mock Service Worker) — API mocking

Add to `frontend/package.json`:
```json
{
  "scripts": {
    "test": "vitest run",
    "test:watch": "vitest",
    "test:coverage": "vitest run --coverage"
  }
}
```

Create `frontend/vitest.config.ts` and `frontend/src/test/setup.ts`.

### 5.2 Write priority component tests

Minimum coverage targets for launch:
- `AuthGuard` — redirect logic
- `AppShell` — renders sidebar, topbar, outlet
- `Sidebar` — navigation links, active state, threat badge
- `Modal` — open/close, escape key, click outside
- `ErrorBanner` — renders error, retry button
- `api/client.ts` — fetch wrapper, CSRF handling, 401 redirect

### 5.3 Write priority page tests

- `Login` — renders, redirects when authenticated
- `Dashboard` — renders metrics, handles loading/error states
- `Events` — renders table, filters work
- `Query` — SQL input, execution, results display

---

## Workstream 6: Code Quality Tooling (High)

### 6.1 Add pre-commit hooks

Create `.pre-commit-config.yaml`:
```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: https://github.com/pre-commit/mirrors-eslint
    hooks:
      - id: eslint
  - repo: https://github.com/pre-commit/pre-commit-hooks
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
      - id: no-commit-to-branch
        args: [--branch, main]
```

Document in CONTRIBUTING.md: `pre-commit install`

### 6.2 Add `.editorconfig`

```ini
root = true

[*]
indent_style = space
indent_size = 4
end_of_line = lf
charset = utf-8
trim_trailing_whitespace = true
insert_final_newline = true

[*.{ts,tsx,js,jsx,json,css,yml,yaml,md}]
indent_size = 2

[Makefile]
indent_style = tab
```

### 6.3 Add Prettier for frontend

Install `prettier` as dev dependency. Create `.prettierrc`:
```json
{
  "semi": true,
  "singleQuote": true,
  "trailingComma": "all",
  "printWidth": 100,
  "tabWidth": 2
}
```

Add `format` and `format:check` scripts to `frontend/package.json`.

---

## Workstream 7: Backend Improvements (Medium)

### 7.1 Add global exception handler

In `backend/app/main.py`, register a global exception handler:
- Catch unhandled exceptions
- Return consistent JSON error envelope: `{ "error": { "code": "...", "message": "..." } }`
- Log structured error with request ID
- Never leak stack traces in production

### 7.2 Review and harden error responses

Audit all routers for consistent error response format:
- Ensure all `HTTPException` uses follow the same envelope pattern
- Add validation error formatting for Pydantic errors

### 7.3 Add API versioning documentation

Create `docs/api-versioning.md`:
- Current version: v1
- Versioning strategy (URL path prefix)
- Deprecation policy
- Backwards compatibility guarantees

---

## Workstream 8: Frontend Improvements (Medium)

### 8.1 Accessibility pass

Priority fixes:
- `AppShell.tsx` — use `<header>`, `<main>`, `<aside>` instead of `<div>`
- `Sidebar.tsx` — add `role="navigation"`, `aria-current="page"` for active links
- `TopBar.tsx` — use `<header>` element
- Add skip-navigation link at top of `AppShell`
- Add `scope="col"` to all table header cells across pages
- Ensure all interactive elements are keyboard-focusable
- Add `aria-live="polite"` to dynamic content areas (threat count badge, loading states)

### 8.2 Remove static/demo content

Audit these pages for hardcoded demo data and either:
- Replace with empty states showing helpful messages
- Wire to real API calls
- Clearly mark as "sample data" with a banner

Pages to audit:
- Dashboard
- Velocity
- Dev Activity
- Copilot
- Reports

### 8.3 Add dark mode toggle

- Add a theme toggle button to `TopBar`
- Store preference in `localStorage`
- Use `data-theme` attribute on `<html>` element
- Update `tokens.css` to use `[data-theme="dark"]` selector alongside `prefers-color-scheme`

### 8.4 Add loading skeletons

Replace spinner-only loading states with skeleton placeholders for better perceived performance on:
- Dashboard metric cards
- Event tables
- Detection lists

---

## Workstream 9: Infrastructure & DevEx (Medium)

### 9.1 Add Makefile

```makefile
.PHONY: help dev build test lint clean

help:           ## Show this help
dev:            ## Start full dev stack
build:          ## Build all Docker images
test:           ## Run all tests
test-backend:   ## Run backend tests
test-frontend:  ## Run frontend tests
lint:           ## Run all linters
lint-backend:   ## Run backend linters
lint-frontend:  ## Run frontend linters
migrate:        ## Run database migrations
gen-env:        ## Generate .env from template
clean:          ## Stop and remove containers
```

### 9.2 Improve `scripts/gen_env.py`

- Add interactive mode (prompt for GitHub OAuth credentials)
- Add `--non-interactive` flag for CI
- Add SSL cert generation step
- Print next-steps instructions after generation

### 9.3 Add Docker healthcheck for frontend

The frontend `Dockerfile` exists but verify it has:
- `HEALTHCHECK` instruction
- Proper multi-stage build (build → nginx/serve)

### 9.4 Document Helm secret management

Add to `docs/security-and-deployment.md`:
- External Secrets Operator integration example
- Sealed Secrets alternative
- Step-by-step for each approach

---

## Workstream 10: Future Roadmap (Low / Post-Launch)

These items should be documented in a `ROADMAP.md` or in GitHub Discussions, but are **not blockers** for launch:

- [ ] **Webhook ingestion** — receive GitHub audit log events via webhook push
- [ ] **Alerting system** — wire detection engine to real-time Slack/email alerts
- [ ] **E2E tests** — Playwright test suite for critical user journeys
- [ ] **Internationalization** — extract strings, add react-intl
- [ ] **User preferences** — timezone, default org, notification settings
- [ ] **Container image scanning** — add Trivy scan of built images in CI
- [ ] **Load testing** — k6 or Locust scripts for API performance benchmarks
- [ ] **Query cost estimation** — preview query cost before execution
- [ ] **Multi-tenancy** — support multiple isolated tenants
- [ ] **Plugin system** — extensible detection rules and integrations

---

## Execution Order

Recommended order for implementation (dependencies noted):

| Phase | Workstreams | Rationale |
|-------|------------|-----------|
| **Phase A** | WS1 (Repo Hygiene) | Foundation — must be done first |
| **Phase B** | WS2 (Docs) + WS3 (GitHub Infra) | Can be done in parallel |
| **Phase C** | WS4 (CI/CD) + WS6 (Code Quality) | Enable quality gates for subsequent work |
| **Phase D** | WS5 (Frontend Tests) + WS7 (Backend Improvements) | Code quality improvements |
| **Phase E** | WS8 (Frontend Improvements) + WS9 (DevEx) | Polish and developer experience |
| **Phase F** | WS10 (Roadmap doc only) | Document future direction |

---

## Success Criteria

The repo is ready for open-source launch when:

1. ✅ All critical items (WS1) are resolved
2. ✅ LICENSE, README, CONTRIBUTING, CODE_OF_CONDUCT, SECURITY exist
3. ✅ CI passes for both backend and frontend
4. ✅ Frontend has ≥60% test coverage on critical components
5. ✅ Backend maintains ≥80% test coverage
6. ✅ No secrets in git history
7. ✅ All docs are accurate and current
8. ✅ Pre-commit hooks are configured
9. ✅ Accessibility basics are addressed
10. ✅ Static/demo content is removed or clearly labeled
