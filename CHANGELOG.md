# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **HEC ingestion endpoint** — Splunk HEC-compatible receiver at `POST /services/collector`; supports single JSON, NDJSON, and concatenated JSON payloads; auth via `Authorization: Splunk <HEC_TOKEN>` with constant-time comparison
- **Workflow failure / timeout metrics** — new `/api/v1/workflow-metrics` endpoint surfacing always-failing and always-timing-out workflows; results cached in Valkey for 5 minutes
- **"Metrics That Matter" executive dashboard** — high-level security posture summary for non-technical stakeholders
- **Detection service** — 8-step detection pipeline with confidence scoring (`DETECTION_CONFIDENCE_THRESHOLD` configurable)
- **Suggestions endpoint** — RBAC-scoped typeahead for actions, fields, and actors at `/api/v1/suggestions`
- **Workflow security scanner** — Celery worker that detects security anti-patterns in `workflows.*` audit events without requiring GitHub API calls; runs on the `baseline` queue
- Enterprise GitHub sync with GraphQL-based org discovery and delta sync
- Security Posture page with enterprise/org/repo drill-down
- Posture assessment detection system
- WAF insights with 21 signals, interactive findings, and evidence drill-down
- DataTable component with sort/filter adopted across all pages
- Pagination across all major pages
- Feature toggle system for optional platform features
- Query explorer with AST-based validation, intellisense autocomplete, and audit logging
- Sync log viewer with indeterminate progress bar and post-processing status
- Setup wizard with initial hydration sync and scheduling
- Report generation with persisted query templates and real audit export
- Terraform infrastructure and CD deployment workflow (later replaced by GHCR publish)
- GitHub IP allowlist and audit stream configuration UI
- Playwright E2E tests wired into CI with DB integration tests
- Comprehensive deployment guide

### Changed
- **`INGESTION_MODE` default changed from `minio` to `hec`**; valid values are now `hec`, `webhook`, `s3`, `azure_blob`
- **`events.ingestion_source` and `ingestion_cursors.source_type`** CHECK constraints updated: `minio` removed, `hec` and `webhook` added
- **`events.source_file_path`** is now nullable (null for push-based modes `hec`/`webhook`)
- Moved integrations section to Settings with real settings controls
- Replaced org tabs with filterable dropdown across all pages
- Stat cards and metric chips are now clickable with drill-down
- Converted Copilot, Health, and Settings tabs to URL-based subpages
- Renamed project from audit-log-analyzer to OctoWatch
- Auto-formatted entire codebase with ruff and prettier
- Updated architecture docs to reflect React 19 and Vite 8
- Aligned coverage threshold to 60% across CI, Makefile, and docs

### Removed
- **MinIO ingestion backend** — removed due to EOL of the embedded single-node configuration and AGPL-3.0 license concerns (see [ADR-001](docs/adr/ADR-001-hec-ingestion.md))
- `MINIO_ROOT_PASSWORD`, `MINIO_ROOT_USER`, `MINIO_INGEST_PASSWORD`, `MINIO_INGEST_USER`, `MINIO_AUDIT_BUCKET`, `MINIO_ENDPOINT_URL` environment variables
- `minio_data` Docker volume and associated Helm PersistentVolumeClaim
- `minio-setup` sidecar container

### Fixed
- Security hardening: SAML CSRF protection, XFF spoofing prevention, configurable role refresh
- Resolved 6 critical, 14 high, and 20 medium severity issues from security review
- Patched 15 dependency vulnerabilities and updated pinned versions
- Fixed detection status consistency between frontend and backend
- Fixed sync deadlocks, stale run expiration, and duplicate post-sync pipelines
- Fixed query explorer edge cases (comments, semicolons, aborted transactions)
- Eliminated phantom branch protection records
- Fixed container startup issues and Docker image build targets

### Removed
- Unused Codecov upload step from CI
- Internal planning files (plan.md, requirements-questionnaire.md)
- One-off patch scripts and internal E2E audit suite

## [0.1.0] - 2026-03-27

### Added
- Core audit event ingestion from S3, Azure Blob Storage, and MinIO
- Threat detection engine with behavioral baselines and impossible travel detection
- RBAC with GitHub team-based role assignments and scope injection
- Self-service SQL query engine with allowlist validation
- Dashboard with key metrics (MAU, seat utilization, Copilot, Actions, PAT counts)
- GitHub OAuth and SAML 2.0 authentication
- Jira and GitHub Issues ticketing integration
- Slack and SMTP notification delivery
- IdP enrichment (Okta, Entra ID, Google Workspace)
- GeoIP enrichment with MaxMind
- Full application audit trail
- Docker Compose development environment
- Helm chart for Kubernetes deployment
- CI/CD with GitHub Actions
- Comprehensive backend test suite (pytest, 60% coverage threshold)
