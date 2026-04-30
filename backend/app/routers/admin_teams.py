"""Admin teams router: CRUD for teams, membership, and team role assignments.

Teams provide a way to group users and assign shared roles. Team-inherited
roles are merged with personal role assignments during permission resolution.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.deps import AuthenticatedUser, get_db, require_permission, verify_csrf
from app.models.team import Team, TeamMembership, TeamRoleAssignment
from app.models.user import RbacRole
from app.schemas.team import (
    TeamCreateRequest,
    TeamDetailResponse,
    TeamMemberAddRequest,
    TeamMemberResponse,
    TeamRoleAssignRequest,
    TeamRoleResponse,
    TeamSummaryResponse,
    TeamUpdateRequest,
)
from app.services.audit_service import log_action
from app.utils.client_ip import get_client_ip

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/admin/teams", tags=["admin-teams"])


def _slugify(name: str) -> str:
    """Convert a team name to a URL-safe slug.

    Lowercases, replaces non-alphanumeric runs with hyphens, and strips
    leading/trailing hyphens.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "team"


# ─── Team CRUD ────────────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=TeamDetailResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_csrf)],
)
async def create_team(
    payload: TeamCreateRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(require_permission("admin_teams", "create")),
    db: AsyncSession = Depends(get_db),
) -> TeamDetailResponse:
    """Create a new team. Requires admin_teams:create permission."""
    slug = _slugify(payload.name)

    # Check for duplicate name or slug
    existing = await db.execute(
        select(Team).where((Team.name == payload.name) | (Team.slug == slug))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Team with name '{payload.name}' or slug '{slug}' already exists",
        )

    team = Team(
        name=payload.name,
        slug=slug,
        description=payload.description,
        github_org=payload.github_org,
        github_team_slug=payload.github_team_slug,
        auto_sync=payload.auto_sync,
        created_by=current_user.github_login,
        created_at=datetime.now(UTC),
    )
    db.add(team)
    await db.flush()
    await db.refresh(team)

    ip = get_client_ip(request)
    await log_action(
        db,
        user_login=current_user.github_login,
        user_github_id=current_user.github_id,
        ip_address=ip,
        user_agent=request.headers.get("user-agent"),
        action_type="team.create",
        resource_type="team",
        resource_id=str(team.id),
        parameters={"name": team.name, "slug": team.slug},
    )

    return TeamDetailResponse(
        id=team.id,
        name=team.name,
        slug=team.slug,
        description=team.description,
        github_org=team.github_org,
        github_team_slug=team.github_team_slug,
        auto_sync=team.auto_sync,
        created_by=team.created_by,
        created_at=team.created_at,
        updated_at=team.updated_at,
        members=[],
        roles=[],
    )


@router.get("", response_model=list[TeamSummaryResponse])
async def list_teams(
    current_user: AuthenticatedUser = Depends(require_permission("admin_teams", "view")),
    db: AsyncSession = Depends(get_db),
) -> list[TeamSummaryResponse]:
    """List all teams with member and role counts."""
    # Subqueries for counts
    member_count_sq = (
        select(
            TeamMembership.team_id,
            func.count().label("member_count"),
        )
        .group_by(TeamMembership.team_id)
        .subquery()
    )
    role_count_sq = (
        select(
            TeamRoleAssignment.team_id,
            func.count().label("role_count"),
        )
        .group_by(TeamRoleAssignment.team_id)
        .subquery()
    )

    stmt = (
        select(
            Team,
            func.coalesce(member_count_sq.c.member_count, 0).label("member_count"),
            func.coalesce(role_count_sq.c.role_count, 0).label("role_count"),
        )
        .outerjoin(member_count_sq, Team.id == member_count_sq.c.team_id)
        .outerjoin(role_count_sq, Team.id == role_count_sq.c.team_id)
        .order_by(Team.name)
    )
    result = await db.execute(stmt)
    rows = result.all()

    return [
        TeamSummaryResponse(
            id=team.id,
            name=team.name,
            slug=team.slug,
            description=team.description,
            member_count=mc,
            role_count=rc,
            auto_sync=team.auto_sync,
            created_by=team.created_by,
            created_at=team.created_at,
        )
        for team, mc, rc in rows
    ]


@router.get("/{team_id}", response_model=TeamDetailResponse)
async def get_team(
    team_id: int,
    current_user: AuthenticatedUser = Depends(require_permission("admin_teams", "view")),
    db: AsyncSession = Depends(get_db),
) -> TeamDetailResponse:
    """Get team detail with members and role assignments."""
    result = await db.execute(
        select(Team)
        .where(Team.id == team_id)
        .options(
            selectinload(Team.memberships),
            selectinload(Team.role_assignments),
        )
    )
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")

    # Fetch role names for the assignments
    role_ids = [ra.role_id for ra in team.role_assignments]
    role_map: dict[int, RbacRole] = {}
    if role_ids:
        roles_result = await db.execute(select(RbacRole).where(RbacRole.id.in_(role_ids)))
        for role in roles_result.scalars().all():
            role_map[role.id] = role

    members = [
        TeamMemberResponse(
            user_login=m.user_login,
            added_by=m.added_by,
            created_at=m.created_at,
        )
        for m in team.memberships
    ]

    roles = [
        TeamRoleResponse(
            role_id=ra.role_id,
            role_name=role_map[ra.role_id].name if ra.role_id in role_map else "unknown",
            role_display_name=(
                role_map[ra.role_id].display_name if ra.role_id in role_map else "Unknown"
            ),
            org_slug=ra.org_slug,
            repo_slugs=ra.repo_slugs,
            assigned_by=ra.assigned_by,
            created_at=ra.created_at,
        )
        for ra in team.role_assignments
    ]

    return TeamDetailResponse(
        id=team.id,
        name=team.name,
        slug=team.slug,
        description=team.description,
        github_org=team.github_org,
        github_team_slug=team.github_team_slug,
        auto_sync=team.auto_sync,
        created_by=team.created_by,
        created_at=team.created_at,
        updated_at=team.updated_at,
        members=members,
        roles=roles,
    )


@router.patch(
    "/{team_id}",
    response_model=TeamDetailResponse,
    dependencies=[Depends(verify_csrf)],
)
async def update_team(
    team_id: int,
    payload: TeamUpdateRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(require_permission("admin_teams", "edit")),
    db: AsyncSession = Depends(get_db),
) -> TeamDetailResponse:
    """Update a team's metadata."""
    result = await db.execute(
        select(Team)
        .where(Team.id == team_id)
        .options(
            selectinload(Team.memberships),
            selectinload(Team.role_assignments),
        )
    )
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")

    if payload.name is not None:
        new_slug = _slugify(payload.name)
        # Check for duplicate name/slug with other teams
        dup_check = await db.execute(
            select(Team).where(
                (Team.id != team_id) & ((Team.name == payload.name) | (Team.slug == new_slug))
            )
        )
        if dup_check.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Team with name '{payload.name}' or slug '{new_slug}' already exists",
            )
        team.name = payload.name
        team.slug = new_slug
    if payload.description is not None:
        team.description = payload.description
    if payload.github_org is not None:
        team.github_org = payload.github_org
    if payload.github_team_slug is not None:
        team.github_team_slug = payload.github_team_slug
    if payload.auto_sync is not None:
        team.auto_sync = payload.auto_sync
    team.updated_at = datetime.now(UTC)

    await db.flush()
    await db.refresh(team)

    ip = get_client_ip(request)
    await log_action(
        db,
        user_login=current_user.github_login,
        user_github_id=current_user.github_id,
        ip_address=ip,
        user_agent=request.headers.get("user-agent"),
        action_type="team.update",
        resource_type="team",
        resource_id=str(team_id),
        parameters={"name": team.name},
    )

    # Re-fetch with relationships for response
    return await get_team(team_id, current_user, db)


@router.delete("/{team_id}", dependencies=[Depends(verify_csrf)])
async def delete_team(
    team_id: int,
    request: Request,
    current_user: AuthenticatedUser = Depends(require_permission("admin_teams", "delete")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Delete a team and all its memberships and role assignments."""
    result = await db.execute(select(Team).where(Team.id == team_id))
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")

    team_name = team.name

    # Delete memberships and role assignments first (cascade handles this, but be explicit)
    await db.execute(delete(TeamMembership).where(TeamMembership.team_id == team_id))
    await db.execute(delete(TeamRoleAssignment).where(TeamRoleAssignment.team_id == team_id))
    await db.delete(team)
    await db.flush()

    ip = get_client_ip(request)
    await log_action(
        db,
        user_login=current_user.github_login,
        user_github_id=current_user.github_id,
        ip_address=ip,
        user_agent=request.headers.get("user-agent"),
        action_type="team.delete",
        resource_type="team",
        resource_id=str(team_id),
        parameters={"name": team_name},
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─── Membership Management ───────────────────────────────────────────────────


@router.post(
    "/{team_id}/members",
    response_model=TeamMemberResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_csrf)],
)
async def add_member(
    team_id: int,
    payload: TeamMemberAddRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(require_permission("admin_teams", "edit")),
    db: AsyncSession = Depends(get_db),
) -> TeamMemberResponse:
    """Add a member to a team."""
    # Verify team exists
    team_result = await db.execute(select(Team).where(Team.id == team_id))
    if not team_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")

    # Check if already a member
    existing = await db.execute(
        select(TeamMembership).where(
            TeamMembership.team_id == team_id,
            TeamMembership.user_login == payload.user_login,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"User '{payload.user_login}' is already a member of this team",
        )

    membership = TeamMembership(
        team_id=team_id,
        user_login=payload.user_login,
        added_by=current_user.github_login,
        created_at=datetime.now(UTC),
    )
    db.add(membership)
    await db.flush()
    await db.refresh(membership)

    ip = get_client_ip(request)
    await log_action(
        db,
        user_login=current_user.github_login,
        user_github_id=current_user.github_id,
        ip_address=ip,
        user_agent=request.headers.get("user-agent"),
        action_type="team.member_add",
        resource_type="team_membership",
        resource_id=str(team_id),
        parameters={"user_login": payload.user_login},
    )

    return TeamMemberResponse(
        user_login=membership.user_login,
        added_by=membership.added_by,
        created_at=membership.created_at,
    )


@router.delete(
    "/{team_id}/members/{login}",
    dependencies=[Depends(verify_csrf)],
)
async def remove_member(
    team_id: int,
    login: str,
    request: Request,
    current_user: AuthenticatedUser = Depends(require_permission("admin_teams", "edit")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Remove a member from a team."""
    result = await db.execute(
        select(TeamMembership).where(
            TeamMembership.team_id == team_id,
            TeamMembership.user_login == login,
        )
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Membership not found",
        )

    await db.delete(membership)
    await db.flush()

    ip = get_client_ip(request)
    await log_action(
        db,
        user_login=current_user.github_login,
        user_github_id=current_user.github_id,
        ip_address=ip,
        user_agent=request.headers.get("user-agent"),
        action_type="team.member_remove",
        resource_type="team_membership",
        resource_id=str(team_id),
        parameters={"user_login": login},
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─── Team Role Assignment ────────────────────────────────────────────────────


@router.post(
    "/{team_id}/roles",
    response_model=TeamRoleResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_csrf)],
)
async def assign_team_role(
    team_id: int,
    payload: TeamRoleAssignRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(require_permission("admin_teams", "edit")),
    db: AsyncSession = Depends(get_db),
) -> TeamRoleResponse:
    """Assign a role to a team."""
    # Verify team exists
    team_result = await db.execute(select(Team).where(Team.id == team_id))
    if not team_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")

    # Verify role exists
    role_result = await db.execute(select(RbacRole).where(RbacRole.id == payload.role_id))
    role = role_result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")

    # Check for duplicate assignment
    existing = await db.execute(
        select(TeamRoleAssignment).where(
            TeamRoleAssignment.team_id == team_id,
            TeamRoleAssignment.role_id == payload.role_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This role is already assigned to this team",
        )

    assignment = TeamRoleAssignment(
        team_id=team_id,
        role_id=payload.role_id,
        org_slug=payload.org_slug,
        repo_slugs=payload.repo_slugs,
        assigned_by=current_user.github_login,
        created_at=datetime.now(UTC),
    )
    db.add(assignment)
    await db.flush()
    await db.refresh(assignment)

    ip = get_client_ip(request)
    await log_action(
        db,
        user_login=current_user.github_login,
        user_github_id=current_user.github_id,
        ip_address=ip,
        user_agent=request.headers.get("user-agent"),
        action_type="team.role_assign",
        resource_type="team_role_assignment",
        resource_id=str(team_id),
        parameters={"role_id": payload.role_id, "role_name": role.name},
    )

    return TeamRoleResponse(
        role_id=assignment.role_id,
        role_name=role.name,
        role_display_name=role.display_name,
        org_slug=assignment.org_slug,
        repo_slugs=assignment.repo_slugs,
        assigned_by=assignment.assigned_by,
        created_at=assignment.created_at,
    )


@router.delete(
    "/{team_id}/roles/{role_id}",
    dependencies=[Depends(verify_csrf)],
)
async def remove_team_role(
    team_id: int,
    role_id: int,
    request: Request,
    current_user: AuthenticatedUser = Depends(require_permission("admin_teams", "edit")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Remove a role assignment from a team."""
    result = await db.execute(
        select(TeamRoleAssignment).where(
            TeamRoleAssignment.team_id == team_id,
            TeamRoleAssignment.role_id == role_id,
        )
    )
    assignment = result.scalar_one_or_none()
    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team role assignment not found",
        )

    await db.delete(assignment)
    await db.flush()

    ip = get_client_ip(request)
    await log_action(
        db,
        user_login=current_user.github_login,
        user_github_id=current_user.github_id,
        ip_address=ip,
        user_agent=request.headers.get("user-agent"),
        action_type="team.role_remove",
        resource_type="team_role_assignment",
        resource_id=str(team_id),
        parameters={"role_id": role_id},
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
