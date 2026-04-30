---
title: Installation
description: Deploy OctoWatch on Kubernetes or Docker Compose
---

# Installation

OctoWatch can be deployed using Helm on Kubernetes (recommended for production) or Docker Compose (for development and small-scale deployments).

## Option 1: Helm on Kubernetes (Recommended)

### Add the Helm Repository

```bash
helm repo add octowatch https://jmassardo.github.io/octowatch/charts
helm repo update
```

### Create a Values File

Create a `values-custom.yaml` with your configuration:

```yaml
# values-custom.yaml
global:
  domain: octowatch.yourdomain.com

backend:
  env:
    DATABASE_URL: "postgresql://octowatch:yourpassword@postgres:5432/octowatch"
    VALKEY_URL: "redis://valkey:6379/0"
    JWT_SECRET: "your-jwt-secret-here"
    HEC_TOKEN: "your-hec-token-here"
    INITIAL_ADMIN_LOGINS: "your-github-username"

ingress:
  enabled: true
  className: nginx
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
  tls:
    - secretName: octowatch-tls
      hosts:
        - octowatch.yourdomain.com

postgresql:
  auth:
    password: "yourpassword"
    database: octowatch

valkey:
  auth:
    enabled: false
```

### Install the Chart

```bash
# Create namespace
kubectl create namespace octowatch

# Install
helm install octowatch octowatch/octowatch \
  --namespace octowatch \
  --values values-custom.yaml
```

### Verify the Deployment

```bash
# Check pods are running
kubectl get pods -n octowatch

# Check the ingress
kubectl get ingress -n octowatch
```

## Option 2: Docker Compose (Development)

### Clone the Repository

```bash
git clone https://github.com/jmassardo/octowatch.git
cd octowatch
```

### Configure Environment

```bash
cp .env.example .env
# Edit .env with your settings
```

Key environment variables to set:

```bash
# .env
DATABASE_URL=postgresql://octowatch:localdev@postgres:5432/octowatch
VALKEY_URL=redis://valkey:6379/0
JWT_SECRET=change-me-in-production
HEC_TOKEN=your-hec-token
INITIAL_ADMIN_LOGINS=your-github-username
```

### Start Services

```bash
docker compose up -d
```

### Verify

```bash
# Check services are healthy
docker compose ps

# Test the API
curl -s http://localhost:8000/health | jq .
```

## Post-Installation

After deployment, you should:

1. **Access the UI** — Navigate to your configured domain (or `http://localhost:3000` for Docker Compose)
2. **Log in** — Use the GitHub account specified in `INITIAL_ADMIN_LOGINS`
3. **Configure HEC streaming** — See the [HEC Configuration](/octowatch/guides/hec-configuration/) guide
4. **Set up org sync** — See the [Organization Sync](/octowatch/guides/org-sync/) guide

## Upgrading

### Helm

```bash
helm repo update
helm upgrade octowatch octowatch/octowatch \
  --namespace octowatch \
  --values values-custom.yaml
```

### Docker Compose

```bash
git pull
docker compose pull
docker compose up -d
```

## Next Steps

Proceed to [First Login](/octowatch/getting-started/first-login/) to complete initial setup.
