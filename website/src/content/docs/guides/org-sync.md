---
title: Organization Sync
description: Configure and manage organization synchronization
---

OctoWatch synchronizes metadata from your GitHub organizations to provide rich context for audit events. This guide covers how org sync works and how to configure it.

## How Sync Works

Organization sync pulls the following data from GitHub:

- **Organizations** — Name, description, settings, plan
- **Repositories** — Name, visibility, topics, archived status
- **Teams** — Name, description, membership, permissions
- **Members** — Username, role (owner/member), 2FA status

This metadata enriches audit log events, enabling queries like "show all events from public repositories" or "alert when an owner's account is compromised."

## Sync Modes

| Mode | Trigger | Use Case |
|------|---------|----------|
| **Scheduled** | Cron (default: every 6 hours) | Keep metadata fresh automatically |
| **Manual** | Admin action in UI | Immediate refresh after changes |

## Configuring Scheduled Sync

Set the sync interval via environment variable:

```yaml
backend:
  env:
    ORG_SYNC_INTERVAL_HOURS: "6"  # Default: 6 hours
```

## Adding Organizations

### Via the UI

1. Navigate to **Settings** → **Organizations**
2. Click **"Add Organization"**
3. Enter the organization login name (e.g., `my-company`)
4. Click **"Sync"**

### Via the API

```bash
curl -X POST https://octowatch.yourdomain.com/api/v1/organizations \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"login": "my-company"}'
```

## Sync Status

Monitor sync health in **Settings** → **Organizations**:

| Status | Meaning |
|--------|---------|
| ✓ Synced | Last sync completed successfully |
| ⟳ Syncing | Sync currently in progress |
| ⚠ Stale | Last sync was >24 hours ago |
| ✗ Error | Last sync failed (check logs) |

## Permissions Required

For sync to work, OctoWatch needs:

- **GitHub App** (recommended): Organization read access (automatic via app installation)
- **Personal Access Token** (alternative): `read:org`, `repo` scopes with org owner access

## Troubleshooting

### Sync shows "Error"

Check backend logs:
```bash
kubectl logs -n octowatch deployment/octowatch-backend | grep "org_sync"
```

Common causes:
- GitHub API rate limiting (check `X-RateLimit-Remaining` headers)
- Token/App permissions insufficient
- Organization name misspelled

### Missing repositories or teams

- Ensure the GitHub App is installed on the organization with **"All repositories"** access
- Private repositories require explicit permission grants
- Archived repositories are synced but flagged as archived
