# OctoWatch Roadmap

This document outlines planned features and improvements. Community input is welcome — feel free to open an issue or discussion to share your priorities.

## Near-Term

- **Webhook Ingestion** — Receive GitHub audit log events via webhook push for real-time ingestion
- **Alerting System** — Wire the detection engine to real-time Slack and email alerts on threat detection
- **E2E Test Suite** — Playwright tests for critical user journeys (login → dashboard → query → results)
- **Container Image Scanning** — Add Trivy scanning of built Docker images in CI

## Medium-Term

- **Internationalization (i18n)** — Extract UI strings for multi-language support
- **User Preferences** — Timezone, default organization, notification preferences
- **Load Testing** — k6 or Locust scripts for API performance benchmarks
- **Query Cost Estimation** — Preview query cost and estimated duration before execution

## Long-Term

- **Multi-Tenancy** — Support multiple isolated tenants in a single deployment
- **Plugin System** — Extensible detection rules and third-party integrations
- **Advanced Analytics** — ML-based anomaly detection beyond behavioral baselines
- **API SDK** — Official client libraries for Python, TypeScript, and Go

## Contributing to the Roadmap

If you're interested in working on any of these items, please:
1. Check existing issues for related discussions
2. Open a new issue describing your proposed approach
3. Wait for maintainer feedback before starting work

We welcome contributions of all sizes!
