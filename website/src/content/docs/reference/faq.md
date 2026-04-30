---
title: FAQ
description: Frequently asked questions about OctoWatch
---

## General

### What is OctoWatch?

OctoWatch is a self-hosted security monitoring platform that ingests GitHub Enterprise audit logs, applies real-time threat detection, and provides compliance reporting. It gives security teams visibility into activity across their GitHub organizations.

### Who is OctoWatch for?

OctoWatch is designed for:
- **Security teams** monitoring GitHub Enterprise environments
- **Compliance teams** generating audit evidence
- **Platform engineers** managing multi-org GitHub deployments
- **CISOs** needing visibility into developer platform security

### Is OctoWatch open source?

Yes. OctoWatch is available at [github.com/jmassardo/octowatch](https://github.com/jmassardo/octowatch) under an open source license.

### Does OctoWatch work with GitHub.com (Free/Pro/Team)?

OctoWatch requires **GitHub Enterprise Cloud** for audit log streaming. GitHub Free, Pro, and Team plans do not support the audit log streaming feature that OctoWatch relies on for real-time ingestion.

---

## Deployment

### Where does OctoWatch run?

OctoWatch is self-hosted — you deploy it on your own infrastructure. It supports:
- Kubernetes (via Helm chart) — recommended for production
- Docker Compose — suitable for development or small deployments

### What are the infrastructure requirements?

See the [Prerequisites](/octowatch/getting-started/prerequisites/) page for detailed requirements. Minimum: 2 Kubernetes nodes with 4 vCPU/8GB RAM each.

### Does OctoWatch send data externally?

No. OctoWatch is entirely self-contained. Your audit log data never leaves your infrastructure. The only outbound connections are to GitHub's API (for org sync and authentication).

### Can I run OctoWatch on AWS/GCP/on-premise?

Yes. While our primary deployment guide focuses on Azure AKS, OctoWatch runs on any Kubernetes cluster (EKS, GKE, on-premise, etc.) or any host with Docker.

---

## Security & Compliance

### What compliance frameworks does OctoWatch support?

OctoWatch can generate reports aligned with:
- SOC 2 Type II
- HIPAA
- Custom frameworks (configurable)

### How is data encrypted?

- **In transit**: All traffic uses TLS 1.2+
- **At rest**: Depends on your storage layer (use encrypted persistent volumes)
- **Authentication tokens**: Stored as bcrypt hashes

### How does RBAC work?

OctoWatch implements organization-scoped role-based access control. Users can have different roles per organization. See the [RBAC guide](/octowatch/guides/rbac/) for details.

---

## Operations

### How much storage does OctoWatch need?

Storage depends on your audit log volume. As a guideline:
- Small org (< 100 users): ~1GB/month
- Medium org (100-1000 users): ~5-10GB/month
- Large org (1000+ users): ~20-50GB/month

### Can I configure data retention?

Yes. OctoWatch supports configurable retention policies. Events older than the retention period are automatically purged.

### How do I upgrade OctoWatch?

For Helm deployments: `helm upgrade` with the new chart version. For Docker Compose: `git pull && docker compose up -d`. See the [Installation](/octowatch/getting-started/installation/) guide for details.

### Does OctoWatch support high availability?

Yes. The backend and frontend are stateless and can run multiple replicas behind a load balancer. PostgreSQL HA requires external solutions (e.g., CloudNativePG, RDS, or Azure Database for PostgreSQL).

---

## Troubleshooting

### Events are not appearing in the dashboard

1. Check GitHub streaming status (org settings → Audit log → Log streaming)
2. Verify HEC endpoint is reachable from GitHub's IP ranges
3. Confirm HEC token matches between GitHub and OctoWatch
4. Check backend logs for errors

### Login is failing

1. Verify GitHub OAuth App credentials are correct
2. Check callback URL matches your deployment domain
3. Ensure the user's GitHub account is not restricted

### Reports are timing out

Large reports covering many events may time out. Try:
1. Narrow the date range
2. Filter to specific organizations
3. Check PostgreSQL query performance (add indexes if needed)
