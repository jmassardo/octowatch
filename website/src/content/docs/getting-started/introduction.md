---
title: Introduction
description: What is OctoWatch and why you need it
---

# What is OctoWatch?

OctoWatch is a **security monitoring and intelligence platform** purpose-built for GitHub Enterprise environments. It ingests GitHub audit logs in real-time, applies automated detection rules, and provides comprehensive dashboards for security teams to monitor, investigate, and report on activity across their GitHub organizations.

## The Problem

GitHub Enterprise generates rich audit logs covering every significant action — repository access, permission changes, secret scanning events, and more. But these logs are:

- **Ephemeral** — GitHub retains audit logs for a limited time
- **Scattered** — Each organization has its own log stream
- **Raw** — No built-in threat detection or anomaly analysis
- **Siloed** — No cross-organization correlation or unified view

Security teams are left piecing together information from multiple sources, often discovering issues days or weeks after they occur.

## The Solution

OctoWatch solves this by providing:

| Capability | Description |
|-----------|-------------|
| **Real-time Ingestion** | HEC (HTTP Event Collector) endpoint receives audit log streams as they happen |
| **Automated Detection** | Configurable rules identify threats, policy violations, and anomalies |
| **Cross-Org Visibility** | Single pane of glass across all your GitHub organizations |
| **Compliance Reporting** | Generate SOC 2, HIPAA, and custom compliance reports on demand |
| **RBAC** | Organization-scoped, role-based access control for multi-tenant environments |
| **Self-Hosted** | Deploy on your infrastructure — data never leaves your environment |

## Key Use Cases

### Security Monitoring
- Detect unauthorized permission escalations
- Monitor repository visibility changes (private → public)
- Track unusual access patterns and login anomalies
- Alert on secret exposure events

### Compliance & Audit
- Prove access controls are enforced
- Generate evidence for auditor requests
- Track data retention and log completeness
- Report on policy adherence across organizations

### Incident Response
- Search and correlate events across time and organizations
- Timeline reconstruction for security investigations
- Identify affected scope during an incident
- Export evidence packages for legal/HR review

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    GitHub Enterprise Cloud                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                      │
│  │  Org A   │  │  Org B   │  │  Org C   │  ...                 │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘                      │
│       │              │              │                             │
│       └──────────────┼──────────────┘                            │
│                      │ Audit Log Streaming                        │
└──────────────────────┼───────────────────────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│                        OctoWatch                                  │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐  │
│  │ HEC Ingest  │→ │  Detection   │→ │  Dashboards & Reports  │  │
│  │  Endpoint   │  │   Engine     │  │   (React Frontend)     │  │
│  └─────────────┘  └──────────────┘  └────────────────────────┘  │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐  │
│  │  PostgreSQL │  │    Valkey    │  │   FastAPI Backend      │  │
│  │  (Storage)  │  │   (Cache)    │  │   (REST API)           │  │
│  └─────────────┘  └──────────────┘  └────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

## Next Steps

Ready to get started? Head to the [Prerequisites](/octowatch/getting-started/prerequisites/) page to check what you need, then follow the [Installation](/octowatch/getting-started/installation/) guide.
