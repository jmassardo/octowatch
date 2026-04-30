---
title: Installation
description: Deploy OctoWatch on Kubernetes or Docker Compose
---

OctoWatch can be deployed using Helm on Kubernetes (recommended for production) or Docker Compose (for development and small-scale deployments).

## Option 1: Helm on Kubernetes (Recommended)

### Add the Helm Repository

```bash
helm repo add octowatch https://jmassardo.github.io/octowatch/charts
helm repo update
```

### Create a Values File

Create a `values-custom.yaml` with your base configuration:

```yaml
# values-custom.yaml
global:
  domain: octowatch.yourdomain.com

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

:::note
Sensitive credentials (HEC token, GitHub App keys, OAuth secrets) are configured securely through the **Setup Wizard** after deployment — not in the values file.
:::

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
# Edit .env with your basic settings (domain, database)
```

:::note
Sensitive credentials are configured through the **Setup Wizard** after first login. The `.env` file only needs basic infrastructure settings (database URL, Valkey URL).
:::

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
2. **Complete the Setup Wizard** — Configure credentials, GitHub App, and HEC token securely
3. **Configure audit log streaming** — See the [HEC Configuration](/octowatch/guides/hec-configuration/) guide
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
