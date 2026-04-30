---
title: RBAC & Permissions
description: Configure role-based access control in OctoWatch
---

OctoWatch implements fine-grained role-based access control (RBAC) with organization-scoped permissions. This ensures teams only see data relevant to their organizations.

## Role Hierarchy

| Role | Scope | Capabilities |
|------|-------|-------------|
| **sys_admin** | Global | Full system access, all organizations, user management, system settings |
| **org_admin** | Organization | Manage org settings, users within org, view all org data, run reports |
| **analyst** | Organization | View dashboards, run queries, export data, manage detection rules |
| **viewer** | Organization | Read-only access to dashboards and reports |

## How Roles Are Assigned

### Initial Admin

The `INITIAL_ADMIN_LOGINS` environment variable grants `sys_admin` to specified GitHub usernames on login:

```yaml
backend:
  env:
    INITIAL_ADMIN_LOGINS: "admin-user1,admin-user2"
```

:::caution
Users in `INITIAL_ADMIN_LOGINS` receive `sys_admin` on **every** login. Remove usernames from this list once you've set up proper role assignments, or they cannot be demoted.
:::

### Manual Assignment

As a `sys_admin` or `org_admin`:

1. Navigate to **Settings** → **Users**
2. Find or invite a user
3. Assign their role and organization scope

### API Assignment

```bash
curl -X PUT https://octowatch.yourdomain.com/api/v1/users/{user_id}/role \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"role": "analyst", "organization_id": "org-uuid-here"}'
```

## Organization Scoping

Non-sys_admin roles are scoped to specific organizations:

- A user can have **different roles** in different organizations
- A `viewer` in Org A sees nothing from Org B
- An `org_admin` in Org A cannot manage users in Org B
- `sys_admin` is always global (all organizations)

## Permission Matrix

| Action | sys_admin | org_admin | analyst | viewer |
|--------|:---------:|:---------:|:-------:|:------:|
| View dashboards | ✓ | ✓ | ✓ | ✓ |
| Run queries | ✓ | ✓ | ✓ | ✗ |
| Export data | ✓ | ✓ | ✓ | ✗ |
| Manage detection rules | ✓ | ✓ | ✓ | ✗ |
| Generate reports | ✓ | ✓ | ✓ | ✗ |
| Manage org users | ✓ | ✓ | ✗ | ✗ |
| Manage org settings | ✓ | ✓ | ✗ | ✗ |
| System settings | ✓ | ✗ | ✗ | ✗ |
| Manage all users | ✓ | ✗ | ✗ | ✗ |
| View system health | ✓ | ✗ | ✗ | ✗ |

## Best Practices

1. **Minimize sys_admin accounts** — Only infrastructure/security team leads need this role
2. **Use org_admin for delegation** — Let org owners manage their own team's access
3. **Default to viewer** — Start users with read-only access and promote as needed
4. **Audit role changes** — All RBAC changes are captured in the audit log
5. **Remove INITIAL_ADMIN_LOGINS entries** — After setup, manage roles through the UI/API
