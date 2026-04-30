---
title: Changelog
description: OctoWatch version history and release notes
---

All notable changes to OctoWatch are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Added
- Public documentation website (GitHub Pages with Astro Starlight)
- Brand identity and visual refresh

### Security
- Mandatory HEC token authentication (previously optional)
- Per-endpoint rate limiting via separate nginx ingress resources
- Reduced proxy body size from 50MB to 5MB

---

## [0.9.0] — 2025-03-15

### Added
- Cross-organization event correlation
- Compliance report builder (SOC 2, HIPAA templates)
- Detection rule management UI
- Health signal monitoring for ingestion pipeline

### Changed
- Migrated session store from Redis to Valkey
- Improved query performance for large event datasets

### Fixed
- RBAC permission check bypass for org-scoped endpoints
- Timezone handling in report date ranges

---

## [0.8.0] — 2025-01-20

### Added
- Organization sync via GitHub App
- Webhook ingestion endpoint
- Role-based access control (RBAC) with 4 roles
- Multi-organization support

### Changed
- Authentication switched from basic auth to GitHub OAuth + JWT
- Database schema migration to support multi-tenancy

---

## [0.7.0] — 2024-11-10

### Added
- Initial HEC endpoint for audit log ingestion
- Basic dashboard with event timeline
- PostgreSQL storage backend
- Docker Compose development setup
- Helm chart for Kubernetes deployment

---

*For the complete commit history, see the [GitHub repository](https://github.com/jmassardo/octowatch/commits/main).*
