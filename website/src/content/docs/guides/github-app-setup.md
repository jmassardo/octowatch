---
title: GitHub App Setup
description: Configure the OctoWatch GitHub App for enhanced integration
---

While OctoWatch can operate with just HEC audit log streaming, installing a GitHub App enables enhanced organization metadata sync and repository-level details.

## What the GitHub App Enables

| Feature | Without App | With App |
|---------|-------------|----------|
| Audit log ingestion | ✓ (HEC) | ✓ (HEC) |
| Org metadata sync | Manual | Automatic |
| Repository details | Basic | Full (topics, visibility, settings) |
| Team membership | Not available | Full sync |

## Creating the GitHub App

### Step 1: Register the App

1. Go to your GitHub organization → **Settings** → **Developer settings** → **GitHub Apps**
2. Click **"New GitHub App"**
3. Fill in the details:

| Field | Value |
|-------|-------|
| **App name** | `OctoWatch - [Your Org]` |
| **Homepage URL** | `https://octowatch.yourdomain.com` |

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

### Step 3: Generate Private Key

After creating the app:
1. Scroll to **"Private keys"**
2. Click **"Generate a private key"**
3. Save the downloaded `.pem` file securely — the app uses this to sign JWTs for GitHub API communication

### Step 4: Install the App

1. From the app settings, click **"Install App"**
2. Select your organization
3. Choose **"All repositories"** (recommended) or select specific repos

## Configuring OctoWatch

The GitHub App credentials are configured through the **Setup Wizard** during initial setup. You'll need:

- **App ID** — Found on the app's settings page
- **Private Key** (PEM file) — Downloaded in Step 3
- **Enterprise slug** — Your GitHub Enterprise account name

The wizard securely stores these credentials and validates connectivity.

## Verifying the Integration

After configuration:

1. Navigate to **Settings** → **Integrations** in OctoWatch
2. The GitHub App should show as "Connected"
3. Click **"Sync Now"** to trigger an initial metadata sync
4. Verify organizations and repositories appear under **Settings** → **Organizations**
