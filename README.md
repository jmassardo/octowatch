# OctoWatch

**Security analytics for GitHub audit logs — threat detection, compliance visibility, and operational insights.**

[![CI](https://github.com/octowatch/octowatch/actions/workflows/ci.yml/badge.svg)](https://github.com/octowatch/octowatch/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.1.0-green.svg)](CHANGELOG.md)

## What is OctoWatch?

OctoWatch is an open-source security analytics platform that ingests GitHub Enterprise Cloud audit log streams and transforms them into actionable security intelligence. It continuously monitors audit events from S3, Azure Blob Storage, or MinIO for signs of insider threats, account compromise, privilege escalation, and policy violations — giving security teams and GitHub administrators the visibility they need to protect their organization.

Beyond threat detection, OctoWatch provides operational dashboards covering monthly active users, license seat utilization, Copilot adoption, GitHub Actions usage, and personal access token lifecycle — all queryable through a self-service SQL interface. Role-based access control ensures that repository owners see only their own data while security teams retain full visibility.

OctoWatch is designed for self-hosted deployment. It ships as Docker containers with a Helm chart for Kubernetes, so your audit data never leaves your infrastructure.

## Key Features

- **Audit Event Ingestion** — Poll and ingest audit log streams from Amazon S3, Azure Blob Storage, and MinIO with automatic cursor tracking
- **Threat Detection Engine** — Behavioral baselines, impossible travel detection, sequence-based rules, and tunable severity classification with detection lifecycle management
- **Role-Based Access Control** — GitHub team-based role assignments with scope injection (org/repo/global), ensuring data isolation at every query
- **Self-Service Query Engine** — Run SQL queries against audit events with allowlist validation, row caps, and query cost controls
- **Dashboards & Reports** — Pre-built views for MAU, seat utilization, Copilot metrics, Actions run volume, PAT counts, and more — with drill-down to raw events
- **Ticketing Integration** — Create and link findings to Jira issues or GitHub Issues, manually or automatically
- **Notifications** — Deliver alerts and digests via Slack and SMTP email
- **IdP Enrichment** — Enrich actor events with user metadata from Okta, Entra ID, and Google Workspace
- **GeoIP Enrichment** — Resolve IP addresses to geographic locations using MaxMind for impossible travel and geo-anomaly detection
- **Full Audit Trail** — Every state-changing operation within OctoWatch itself is logged with before/after snapshots for accountability

## Architecture

```
                         ┌─────────────────────────────┐
                         │        nginx (TLS)          │
                         │    reverse proxy :443       │
                         └──────────┬──────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
             ┌──────┴──────┐                 ┌──────┴──────┐
             │  Frontend   │                 │ Backend API │
             │  React/Vite │                 │   FastAPI   │
             │  :5173      │                 │   :8000     │
             └─────────────┘                 └──────┬──────┘
                                                    │
                          ┌─────────────────────────┼─────────────────────────┐
                          │                         │                         │
                   ┌──────┴──────┐          ┌───────┴───────┐         ┌───────┴───────┐
                   │ TimescaleDB │          │    Valkey     │         │     MinIO     │
                   │ (PostgreSQL)│          │(Redis-compat) │         │ (S3-compat)   │
                   │   :5432     │          │    :6379      │         │   :9000       │
                   └─────────────┘          └───────────────┘         └───────────────┘

             ┌──────────────────────────────────────────────────────────┐
             │                    Celery Workers                       │
             │  ingestion · detection · enrichment · notifications     │
             │                   (via Valkey broker)                   │
             └──────────────────────────────────────────────────────────┘
```

## Quickstart

1. **Clone the repository:**

   ```bash
   git clone https://github.com/octowatch/octowatch.git
   cd octowatch
   ```

2. **Generate environment configuration:**

   ```bash
   python scripts/gen_env.py
   ```

   This creates a `.env` file with sensible defaults. Review and customize as needed.

3. **Generate TLS certificates:**

   See [`nginx/ssl/README.md`](nginx/ssl/README.md) for instructions on generating self-signed certificates for local development.

4. **Start all services:**

   ```bash
   docker compose up -d
   ```

5. **Open OctoWatch:**

   Visit [https://localhost](https://localhost) in your browser.

## Local Development

For working on individual components without Docker:

**Prerequisites:** Python 3.12+, Node.js 20+

```bash
# Backend
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest

# Frontend (in a separate terminal)
cd frontend
npm install
npm run dev
```

The backend requires TimescaleDB, Valkey, and MinIO — start just the infrastructure with:

```bash
docker compose up -d db valkey minio
```

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the full development guide including linting, testing, and pre-commit hooks.

## Configuration

OctoWatch is configured through environment variables. See [`backend/.env.example`](backend/.env.example) for a complete reference of all available settings.

For production deployment, security hardening, and Kubernetes configuration, see [`docs/security-and-deployment.md`](docs/security-and-deployment.md).

## Documentation

| Document | Description |
|----------|-------------|
| [`docs/architecture.md`](docs/architecture.md) | System architecture and design decisions |
| [`docs/api-and-detection-design.md`](docs/api-and-detection-design.md) | API design and threat detection engine |
| [`docs/frontend-architecture-spec.md`](docs/frontend-architecture-spec.md) | Frontend architecture and component design |
| [`docs/security-and-deployment.md`](docs/security-and-deployment.md) | Security controls, deployment, and operations |
| [`docs/runbook.md`](docs/runbook.md) | Operational runbook for troubleshooting |
| [`docs/api-versioning.md`](docs/api-versioning.md) | API versioning strategy and deprecation policy |

## Contributing

We welcome contributions! Please see [`CONTRIBUTING.md`](CONTRIBUTING.md) for guidelines on how to get started, development setup, code style, and the pull request process.

## Security

To report a security vulnerability, please see [`SECURITY.md`](SECURITY.md). **Do not open public issues for security vulnerabilities.**

## License

OctoWatch is licensed under the [Apache License 2.0](LICENSE).

```
Copyright 2026 OctoWatch Contributors

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
```
