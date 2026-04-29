"""RBAC service: GitHub team → role resolution and org/repo scope injection.

All scope decisions come from the database (user_role_assignments), never from
user-supplied request data. Client-provided org/repo params are narrowing
filters only and can never expand the RBAC scope.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, runtime_checkable

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import RbacRole, UserRoleAssignment

if TYPE_CHECKING:
    import redis.asyncio as aioredis

logger = structlog.get_logger(__name__)

# Legacy role names preserved for backward compatibility
ROLE_NAMES = ("analyst", "report_admin", "rule_author", "sys_admin")

# New role names for the enhanced RBAC model
SYSTEM_ROLES = (
    "super_admin",
    "security_analyst",
    "security_engineer",
    "compliance_officer",
    "engineering_leader",
    "copilot_admin",
    "viewer",
)

# Mapping from old role names to new role names
ROLE_MIGRATION_MAP: dict[str, str] = {
    "sys_admin": "super_admin",
    "report_admin": "compliance_officer",
    "rule_author": "security_engineer",
    "analyst": "security_analyst",
}

# All valid resources in the permission model
VALID_RESOURCES = frozenset(
    {
        "dashboard",
        "detections",
        "events",
        "queries",
        "posture",
        "advanced_security",
        "velocity",
        "dev_activity",
        "cross_org",
        "copilot",
        "org_health",
        "workflow_security",
        "workflow_health",
        "reports",
        "rules",
        "admin_settings",
        "admin_users",
        "admin_roles",
        "admin_teams",
        "audit_log",
        "playbooks",
    }
)

# All valid actions in the permission model
VALID_ACTIONS = frozenset(
    {
        "view",
        "create",
        "edit",
        "delete",
        "export",
        "share",
        "assign",
        "dismiss",
        "execute",
        "admin",
    }
)

# Predefined system role permissions
SYSTEM_ROLE_PERMISSIONS: dict[str, list[str]] = {
    "super_admin": ["*:*"],
    "security_analyst": [
        "detections:*",
        "events:*",
        "queries:execute",
        "reports:view",
        "dashboard:view",
        "rules:view",
        "posture:view",
        "cross_org:view",
        "workflow_security:view",
        "copilot:view",
        "org_health:view",
        "playbooks:view",
        "playbooks:execute",
    ],
    "security_engineer": [
        "detections:*",
        "events:*",
        "queries:execute",
        "reports:view",
        "dashboard:view",
        "rules:*",
        "playbooks:*",
        "posture:view",
        "cross_org:view",
        "workflow_security:view",
        "copilot:view",
        "org_health:view",
    ],
    "compliance_officer": [
        "posture:*",
        "reports:*",
        "audit_log:view",
        "events:view",
        "dashboard:view",
        "detections:view",
        "queries:execute",
        "rules:view",
        "cross_org:view",
        "workflow_security:view",
        "copilot:view",
        "org_health:view",
        "playbooks:view",
    ],
    "engineering_leader": [
        "velocity:*",
        "dev_activity:*",
        "workflow_health:*",
        "copilot:view",
        "dashboard:view",
    ],
    "copilot_admin": [
        "copilot:*",
        "dashboard:view",
    ],
    "viewer": [
        "dashboard:view",
        "events:view",
        "detections:view",
    ],
    # Legacy role mappings (backward compatibility during transition)
    "sys_admin": ["*:*"],
    "analyst": [
        "detections:*",
        "events:*",
        "queries:execute",
        "reports:view",
        "dashboard:view",
        "rules:view",
        "posture:view",
        "cross_org:view",
        "workflow_security:view",
        "copilot:view",
        "org_health:view",
        "playbooks:view",
        "playbooks:execute",
    ],
    "rule_author": [
        "detections:*",
        "events:*",
        "queries:execute",
        "reports:view",
        "dashboard:view",
        "rules:*",
        "playbooks:*",
        "posture:view",
        "cross_org:view",
        "workflow_security:view",
        "copilot:view",
        "org_health:view",
    ],
    "report_admin": [
        "posture:*",
        "reports:*",
        "audit_log:view",
        "events:view",
        "dashboard:view",
        "queries:execute",
        "detections:*",
        "rules:view",
        "cross_org:view",
        "workflow_security:view",
        "copilot:view",
        "org_health:view",
        "playbooks:view",
    ],
}


@runtime_checkable
class _ScopedUser(Protocol):
    """Structural type for any object carrying RBAC scope attributes."""

    github_login: str
    roles: list[str]
    scoped_orgs: list[str]
    scope_type: str


@dataclass
class OrgRepoScope:
    """Resolved RBAC scope for a user at request time."""

    scoped_orgs: list[str] = field(default_factory=list)
    scoped_repos: list[str] = field(default_factory=list)
    scope_type: str = "org"  # "global" | "org" | "repo"

    @property
    def is_global(self) -> bool:
        return self.scope_type == "global"


async def resolve_roles(
    session: AsyncSession,
    github_login: str,
) -> list[str]:
    """Return the list of role names active for a GitHub user.

    Checks both direct user assignments and returns all active, non-expired roles.
    """
    stmt = (
        select(RbacRole.name)
        .join(UserRoleAssignment, UserRoleAssignment.role_id == RbacRole.id)
        .where(
            UserRoleAssignment.github_login == github_login,
            UserRoleAssignment.active.is_(True),
            # Exclude expired assignments
            (UserRoleAssignment.expires_at.is_(None))
            | (UserRoleAssignment.expires_at > text("NOW()")),
        )
    )
    result = await session.execute(stmt)
    roles = [row[0] for row in result.fetchall()]

    return list(set(roles))  # deduplicate


async def resolve_permissions(
    session: AsyncSession,
    github_login: str,
    *,
    valkey: aioredis.Redis | None = None,
) -> list[str]:
    """Return the full list of permission strings for a user from all their roles.

    Optionally caches in Valkey with the configured refresh interval TTL.
    """
    # Check cache first
    if valkey is not None:
        cache_key = f"rbac:permissions:{github_login}"
        cached = await valkey.get(cache_key)
        if cached:
            cached_perms: list[str] = json.loads(cached)
            return cached_perms

    stmt = (
        select(RbacRole.permissions)
        .join(UserRoleAssignment, UserRoleAssignment.role_id == RbacRole.id)
        .where(
            UserRoleAssignment.github_login == github_login,
            UserRoleAssignment.active.is_(True),
            (UserRoleAssignment.expires_at.is_(None))
            | (UserRoleAssignment.expires_at > text("NOW()")),
        )
    )
    db_result = await session.execute(stmt)
    all_perms: set[str] = set()
    for (perms,) in db_result.fetchall():
        if isinstance(perms, list):
            all_perms.update(perms)

    permissions = sorted(all_perms)

    # Store in cache
    if valkey is not None:
        from app.config import settings

        ttl = settings.AUTH.ROLE_REFRESH_INTERVAL_SECONDS
        await valkey.setex(cache_key, ttl, json.dumps(permissions))

    return permissions


async def check_permission(
    session: AsyncSession,
    github_login: str,
    resource: str,
    action: str,
    *,
    roles: list[str] | None = None,
    valkey: aioredis.Redis | None = None,
) -> bool:
    """Check if a user has the specific permission via any of their roles.

    Checks for:
    1. Exact match: resource:action
    2. Resource wildcard: resource:*
    3. Global wildcard: *:*
    4. super_admin role always grants all permissions

    Parameters
    ----------
    session:
        Async SQLAlchemy session.
    github_login:
        The GitHub login of the user.
    resource:
        The resource being accessed (e.g., "detections").
    action:
        The action being performed (e.g., "view").
    roles:
        Pre-resolved roles (avoids re-querying). If None, resolved from DB.
    valkey:
        Optional Valkey client for permission caching.

    Returns
    -------
    True if the user has the permission, False otherwise.
    """
    # super_admin always has all permissions
    if roles and ("super_admin" in roles or "sys_admin" in roles):
        return True

    # Resolve roles if not provided
    if roles is None:
        roles = await resolve_roles(session, github_login)
        if "super_admin" in roles or "sys_admin" in roles:
            return True

    # Fast path: check SYSTEM_ROLE_PERMISSIONS for known role names
    # This avoids a DB round-trip when all roles are system roles with
    # statically defined permissions.
    required = f"{resource}:{action}"
    known_perms: set[str] = set()
    all_roles_known = True
    for role_name in roles:
        if role_name in SYSTEM_ROLE_PERMISSIONS:
            known_perms.update(SYSTEM_ROLE_PERMISSIONS[role_name])
        else:
            all_roles_known = False

    if all_roles_known and known_perms:
        for perm in known_perms:
            if perm == "*:*":
                return True
            if perm == required:
                return True
            if perm == f"{resource}:*":
                return True
        return False

    # Slow path: resolve permissions from DB (for custom roles or mixed)
    permissions = await resolve_permissions(session, github_login, valkey=valkey)

    for perm in permissions:
        if perm == "*:*":
            return True
        if perm == required:
            return True
        if perm == f"{resource}:*":
            return True

    return False


async def invalidate_permission_cache(
    valkey: aioredis.Redis,
    github_login: str,
) -> None:
    """Invalidate the cached permissions for a user.

    Call this when roles or assignments change.
    """
    cache_key = f"rbac:permissions:{github_login}"
    await valkey.delete(cache_key)


async def get_user_scope(
    session: AsyncSession,
    github_login: str,
    roles: list[str],
) -> OrgRepoScope:
    """Return the org/repo scope for a user.

    super_admin (or legacy sys_admin) gets global scope.
    Others get scope from user_role_assignments.
    """
    if "sys_admin" in roles or "super_admin" in roles:
        return OrgRepoScope(scoped_orgs=[], scoped_repos=[], scope_type="global")

    stmt = select(UserRoleAssignment).where(
        UserRoleAssignment.github_login == github_login,
        UserRoleAssignment.active.is_(True),
        (UserRoleAssignment.expires_at.is_(None)) | (UserRoleAssignment.expires_at > text("NOW()")),
    )
    result = await session.execute(stmt)
    assignments = result.scalars().all()

    orgs: list[str] = []
    repos: list[str] = []
    has_global = False
    scope_types = set()

    for assignment in assignments:
        scope_types.add(assignment.scope_type)
        if assignment.scope_type == "global":
            has_global = True
        elif assignment.scope_type == "org" and assignment.scope_value:
            orgs.append(assignment.scope_value)
        elif assignment.scope_type == "repo" and assignment.scope_value:
            repos.append(assignment.scope_value)

    if has_global:
        return OrgRepoScope(scoped_orgs=[], scoped_repos=[], scope_type="global")

    return OrgRepoScope(
        scoped_orgs=list(set(orgs)),
        scoped_repos=list(set(repos)),
        scope_type="org" if orgs else "repo",
    )


def inject_scope_predicate(
    stmt: object,
    scope: OrgRepoScope,
    org_col: object,
    repo_col: object | None = None,
) -> object:
    """Append mandatory RBAC scope WHERE clauses to a SQLAlchemy SELECT.

    Parameters
    ----------
    stmt:
        A SQLAlchemy Select statement.
    scope:
        The resolved OrgRepoScope for the current user.
    org_col:
        The `org` column of the table being queried.
    repo_col:
        Optional `repo` column; if provided, also scopes by repo.

    Returns
    -------
    The same stmt with additional WHERE predicates appended.

    Scoping rules:
    - Global (super_admin): no WHERE clause added
    - Org-scoped: WHERE org IN (...)
    - Repo-scoped: WHERE repo IN (...) — narrower than org, takes precedence
    - When both org and repo scopes exist: repo takes precedence (narrower wins)
    """
    from sqlalchemy import or_

    if scope.is_global:
        return stmt

    # When repo scopes exist, they take precedence (narrower wins)
    if repo_col is not None and scope.scoped_repos:
        stmt = stmt.where(  # type: ignore[union-attr]
            or_(repo_col.is_(None), repo_col.in_(scope.scoped_repos))
        )
        return stmt

    # Narrow by permitted orgs
    if scope.scoped_orgs:
        stmt = stmt.where(org_col.in_(scope.scoped_orgs))  # type: ignore[union-attr]

    return stmt


async def get_scoped_orgs(
    session: AsyncSession,
    user: _ScopedUser,
) -> list[str]:
    """Return the explicit list of orgs the user may query.

    For scoped users the list comes from their role assignments.  For
    ``super_admin`` / ``sys_admin`` / global-scope users the function queries
    all distinct orgs present in the ``events`` table so that downstream SQL
    can always use ``org = ANY(:scoped_orgs)`` without a wildcard.

    Parameters
    ----------
    session:
        An async SQLAlchemy session.
    user:
        An ``AuthenticatedUser`` instance (or any object exposing
        ``github_login``, ``roles``, ``scoped_orgs`` and ``scope_type``).

    Returns
    -------
    A (possibly empty) list of org name strings.
    """
    # Fast path: scoped users already carry org names from session data
    if user.scope_type != "global" and user.scoped_orgs:
        return list(user.scoped_orgs)

    # Resolve scope from DB for correctness
    scope = await get_user_scope(
        session,
        user.github_login,
        user.roles,
    )

    if scope.is_global:
        # Primary source: distinct orgs from the events table
        result = await session.execute(
            text("SELECT DISTINCT org FROM events WHERE org IS NOT NULL LIMIT 1000")
        )
        orgs = [row[0] for row in result.fetchall()]
        if orgs:
            return orgs

        # Fallback: synced orgs from enterprise_orgs / github_app_configs
        # (covers fresh installs where sync has run but no audit events yet)
        for fallback_query in (
            "SELECT DISTINCT org_login FROM enterprise_orgs WHERE org_login IS NOT NULL",
            (
                "SELECT DISTINCT org_login FROM github_app_configs"
                " WHERE enabled = true AND org_login IS NOT NULL"
            ),
        ):
            try:
                fb = await session.execute(text(fallback_query))
                orgs = [row[0] for row in fb.fetchall()]
                if orgs:
                    return orgs
            except Exception:  # noqa: BLE001
                logger.debug("rbac_service.fallback_query_failed", query=fallback_query[:60])
                continue

        return []

    return scope.scoped_orgs


def apply_client_filters(
    stmt: object,
    scope: OrgRepoScope,
    client_org: str | None,
    client_repo: str | None,
    org_col: object,
    repo_col: object | None = None,
) -> object:
    """Apply client-supplied org/repo as additional narrowing filters.

    These can only narrow the RBAC scope, never expand it. Silently ignored if
    they refer to orgs/repos not in the user's scope.
    """
    if client_org:
        # Only allow if within RBAC scope
        if scope.is_global or client_org in scope.scoped_orgs:
            stmt = stmt.where(org_col == client_org)  # type: ignore[union-attr]

    if repo_col is not None and client_repo:
        if scope.is_global or client_repo in scope.scoped_repos or scope.scoped_orgs:
            stmt = stmt.where(repo_col == client_repo)  # type: ignore[union-attr]

    return stmt
