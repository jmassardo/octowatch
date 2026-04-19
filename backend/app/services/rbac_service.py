"""RBAC service: GitHub team → role resolution and org/repo scope injection.

All scope decisions come from the database (user_role_assignments), never from
user-supplied request data. Client-provided org/repo params are narrowing
filters only and can never expand the RBAC scope.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, runtime_checkable

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import RbacRole, UserRoleAssignment

if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)

# Role names that can be derived from GitHub team memberships
ROLE_NAMES = ("analyst", "report_admin", "rule_author", "sys_admin")


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


async def get_user_scope(
    session: AsyncSession,
    github_login: str,
    roles: list[str],
) -> OrgRepoScope:
    """Return the org/repo scope for a user.

    sys_admin gets global scope. Others get scope from user_role_assignments.
    """
    if "sys_admin" in roles:
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
    """
    from sqlalchemy import or_

    if scope.is_global:
        return stmt

    # Narrow by permitted orgs
    if scope.scoped_orgs:
        stmt = stmt.where(org_col.in_(scope.scoped_orgs))  # type: ignore[union-attr]

    # Narrow by permitted repos if repo-scoped
    if repo_col is not None and scope.scoped_repos and not scope.scoped_orgs:
        stmt = stmt.where(  # type: ignore[union-attr]
            or_(repo_col.is_(None), repo_col.in_(scope.scoped_repos))
        )

    return stmt


async def get_scoped_orgs(
    session: AsyncSession,
    user: _ScopedUser,
) -> list[str]:
    """Return the explicit list of orgs the user may query.

    For scoped users the list comes from their role assignments.  For
    ``sys_admin`` / global-scope users the function queries all distinct
    orgs present in the ``events`` table so that downstream SQL can
    always use ``org = ANY(:scoped_orgs)`` without a wildcard.

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
