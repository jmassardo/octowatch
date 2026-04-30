---
title: GitHub App Setup
description: Configure the OctoWatch GitHub App for enhanced integration
---

While OctoWatch can operate with just HEC audit log streaming, installing a GitHub App enables enhanced features like real-time webhook events, organization metadata sync, and repository-level details.

## What the GitHub App Enables

| Feature | Without App | With App |
|---------|-------------|----------|
| Audit log ingestion | ✓ (HEC) | ✓ (HEC + webhooks) |
| Org metadata sync | Manual | Automatic |
| Repository details | Basic | Full (topics, visibility, settings) |
| Team membership | Not available | Full sync |
| Real-time webhooks | Not available | ✓ |

## Creating the GitHub App

### Step 1: Register the App

1. Go to your GitHub organization → **Settings** → **Developer settings** → **GitHub Apps**
2. Click **"New GitHub App"**
3. Fill in the details:

| Field | Value |
|-------|-------|
| **App name** | `OctoWatch - [Your Org]` |
| **Homepage URL** | `https://octowatch.yourdomain.com` |
| **Webhook URL** | `https://octowatch.yourdomain.com/api/v1/ingest/webhook` |
| **Webhook secret** | Generate a strong random string |

### Step 2: Set Permissions

Under **Permissions**, configure:

**Organization permissions:**
- Administration: Read-only
- Members: Read-only
- Audit log: Read-only

**Repository permissions:**
- Metadata: Read-only
- Administration: Read-only

**Account permissions:**
- None required

### Step 3: Subscribe to Events

Under **Subscribe to events**, select:
- Organization
- Repository
- Member
- Team

### Step 4: Generate Private Key

After creating the app:
1. Scroll to **"Private keys"**
2. Click **"Generate a private key"**
3. Save the downloaded `.pem` file securely

### Step 5: Install the App

1. From the app settings, click **"Install App"**
2. Select your organization
3. Choose **"All repositories"** (recommended) or select specific repos

## Configuring OctoWatch

Add the following environment variables to your deployment:

```yaml
# Helm values
backend:
  env:
    GITHUB_APP_ID: "123456"
    GITHUB_APP_PRIVATE_KEY: |
      -----BEGIN RSA PRIVATE KEY-----
      ... your private key content ...
      -----END RSA PRIVATE KEY-----
    GITHUB_APP_CLIENT_ID: "Iv1.abc123"
    GITHUB_APP_CLIENT_SECRET: "your-client-secret"
    GITHUB_WEBHOOK_SECRET: "your-webhook-secret"
```

:::tip
For Kubernetes, store the private key in a Secret rather than directly in values:
```bash
kubectl create secret generic octowatch-github-app \
  --from-file=private-key.pem=./your-app.pem \
  -n octowatch
```
:::

## Verifying the Integration

After configuration:

1. Navigate to **Settings** → **Integrations** in OctoWatch
2. The GitHub App should show as "Connected"
3. Click **"Sync Now"** to trigger an initial metadata sync
4. Verify organizations and repositories appear under **Settings** → **Organizations**

## Webhook Delivery

Monitor webhook delivery in GitHub:

1. Go to your GitHub App settings → **Advanced**
2. View **"Recent deliveries"**
3. All deliveries should show ✓ (200 response)

If you see failures, check:
- Webhook URL is correct and publicly accessible
- Webhook secret matches between GitHub and OctoWatch
- TLS certificate is valid
