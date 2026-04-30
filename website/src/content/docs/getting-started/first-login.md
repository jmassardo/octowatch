---
title: First Login
description: Complete your initial OctoWatch setup
---

After deploying OctoWatch, follow these steps to complete the initial setup.

## Accessing OctoWatch

Navigate to your OctoWatch instance:

- **Kubernetes**: `https://octowatch.yourdomain.com`
- **Docker Compose**: `http://localhost:3000`

## Authentication

OctoWatch uses GitHub OAuth for authentication. On your first visit:

1. Click **"Sign in with GitHub"**
2. Authorize the OctoWatch application
3. You'll be redirected back to the OctoWatch dashboard

:::note
The user(s) specified in the `INITIAL_ADMIN_LOGINS` environment variable are automatically granted the `sys_admin` role. This should be your GitHub username.
:::

## Initial Setup Wizard

On first login as an admin, you'll be guided through:

### 1. Verify HEC Endpoint

The setup wizard confirms your HEC endpoint is accessible:

```
✓ HEC endpoint responding at /services/collector
✓ Token authentication verified
```

### 2. Connect Your First Organization

- Enter your GitHub organization name
- OctoWatch will verify API access
- Initial sync pulls organization metadata (repos, teams, members)

### 3. Configure Audit Log Streaming

Follow the guided setup to configure GitHub's audit log streaming:

1. Go to your GitHub organization → **Settings** → **Audit log** → **Log streaming**
2. Click **"Set up a stream"**
3. Select **"Splunk"** as the stream type
4. Enter your OctoWatch HEC endpoint URL: `https://octowatch.yourdomain.com/services/collector`
5. Enter your HEC token
6. Click **"Check endpoint"** then **"Save"**

### 4. Verify Data Flow

Within a few minutes of configuring streaming, you should see:

- Events appearing in the **Activity** dashboard
- Organization metadata populated in **Settings** → **Organizations**
- The health indicator showing "Receiving data"

## Setting Up Additional Admins

As a `sys_admin`, you can invite additional administrators:

1. Navigate to **Settings** → **Users**
2. Click **"Add User"**
3. Enter their GitHub username
4. Assign the appropriate role (`sys_admin`, `org_admin`, or `viewer`)

## Troubleshooting First Login

### "Access Denied" after GitHub OAuth

Ensure your GitHub username is listed in the `INITIAL_ADMIN_LOGINS` environment variable. This value is case-sensitive.

### HEC endpoint not receiving data

1. Verify the endpoint is publicly accessible from GitHub's IP ranges
2. Check that TLS certificates are valid (GitHub requires HTTPS)
3. Confirm the HEC token matches between GitHub's streaming config and OctoWatch's `HEC_TOKEN` environment variable

### Organization sync failing

1. Verify you have **Owner** access to the GitHub organization
2. Check that the GitHub App (if used) is installed on the organization
3. Review backend logs: `kubectl logs -n octowatch deployment/octowatch-backend`

## Next Steps

- [HEC Configuration](/octowatch/guides/hec-configuration/) — Advanced HEC endpoint settings
- [GitHub App Setup](/octowatch/guides/github-app-setup/) — Enhanced integration with GitHub
- [RBAC & Permissions](/octowatch/guides/rbac/) — Configure access control for your team
