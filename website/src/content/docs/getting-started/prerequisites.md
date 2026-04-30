---
title: Prerequisites
description: What you need before deploying OctoWatch
---

# Prerequisites

Before deploying OctoWatch, ensure you have the following requirements in place.

## GitHub Requirements

| Requirement | Details |
|------------|---------|
| **GitHub Enterprise Cloud** | Required for audit log streaming |
| **Organization Owner** access | Needed to configure audit log streaming and install GitHub Apps |
| **GitHub App** (optional) | For enhanced org sync and webhook-based ingestion |

:::note
OctoWatch works with GitHub Enterprise Cloud. GitHub Enterprise Server (GHES) support is planned for a future release.
:::

## Infrastructure Requirements

### For Kubernetes Deployment (Recommended)

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| **Kubernetes** | v1.26+ | v1.28+ |
| **Helm** | v3.12+ | v3.14+ |
| **Nodes** | 2 nodes, 4 vCPU / 8GB each | 3 nodes, 4 vCPU / 16GB each |
| **Storage** | 50GB persistent volume | 200GB+ SSD persistent volume |
| **Ingress Controller** | nginx-ingress or equivalent | nginx-ingress with TLS |

### For Docker Compose (Development/Small Scale)

| Component | Minimum |
|-----------|---------|
| **Docker** | v24+ |
| **Docker Compose** | v2.20+ |
| **RAM** | 8GB available |
| **Disk** | 20GB free |

## Network Requirements

| Port/Protocol | Purpose |
|--------------|---------|
| **443/TCP inbound** | HEC endpoint (audit log streaming from GitHub) |
| **443/TCP inbound** | Web UI and API access |
| **443/TCP outbound** | GitHub API access (api.github.com) |
| **5432/TCP internal** | PostgreSQL database |
| **6379/TCP internal** | Valkey (Redis-compatible) cache |

:::caution
The HEC endpoint **must** be reachable from GitHub's IP ranges. See [GitHub's meta API](https://api.github.com/meta) for current IP ranges used by audit log streaming.
:::

## Required Credentials

Before starting installation, gather the following:

1. **HEC Token** — A strong random token for authenticating audit log streams
2. **JWT Secret** — Secret key for signing authentication tokens
3. **Database credentials** — PostgreSQL username and password
4. **GitHub App credentials** (if using GitHub App integration):
   - App ID
   - Private key (PEM file)
   - Client ID and secret
   - Webhook secret

## Supported Browsers

The OctoWatch web interface supports:

- Chrome/Chromium 90+
- Firefox 90+
- Safari 15+
- Edge 90+

## Next Steps

Once you've confirmed all prerequisites are met, proceed to the [Installation](/octowatch/getting-started/installation/) guide.
