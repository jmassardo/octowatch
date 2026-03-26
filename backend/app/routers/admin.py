"""Admin router: user management, retention config, ingestion sources, top-actors."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_db, require_role
from app.models.user import RbacRole, UserRoleAssignment
from app.schemas.integration import (
    IngestionSourceCreate,
    RetentionConfig,
    RoleAssignmentCreate,
    RoleAssignmentResponse,
)
from app.services.report_service import get_top_actors_report

router = APIRouter(prefix="/admin", tags=["admin"])


# ─── Role management ──────────────────────────────────────────────────────────


@router.get("/roles", response_model=list[dict])
async def list_roles(
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """List all available RBAC roles."""
    result = await db.execute(select(RbacRole))
    roles = result.scalars().all()
    return [{"id": r.id, "name": r.name, "description": r.description} for r in roles]


@router.get("/assignments", response_model=list[RoleAssignmentResponse])
async def list_role_assignments(
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> list[RoleAssignmentResponse]:
    """List all user role assignments."""
    result = await db.execute(
        select(UserRoleAssignment).order_by(UserRoleAssignment.created_at.desc())
    )
    assignments = result.scalars().all()
    return [RoleAssignmentResponse.model_validate(a) for a in assignments]


@router.post(
    "/assignments", response_model=RoleAssignmentResponse, status_code=status.HTTP_201_CREATED
)
async def create_role_assignment(
    payload: RoleAssignmentCreate,
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> RoleAssignmentResponse:
    """Assign a role to a user (with optional org/repo scope)."""
    # Validate that role exists
    role_result = await db.execute(select(RbacRole).where(RbacRole.name == payload.role_name))
    role = role_result.scalar_one_or_none()
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Role '{payload.role_name}' not found",
        )

    # Check for duplicate
    existing_result = await db.execute(
        select(UserRoleAssignment).where(
            UserRoleAssignment.github_login == payload.github_login,
            UserRoleAssignment.role_id == role.id,
            UserRoleAssignment.org == payload.org,
        )
    )
    if existing_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Role assignment already exists",
        )

    assignment = UserRoleAssignment(
        github_login=payload.github_login,
        role_id=role.id,
        org=payload.org,
        repo=payload.repo,
        granted_by=current_user.github_login,
    )
    db.add(assignment)
    await db.flush()
    return RoleAssignmentResponse.model_validate(assignment)


@router.delete("/assignments/{assignment_id}")
async def delete_role_assignment(
    assignment_id: int,
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Remove a role assignment."""
    result = await db.execute(
        select(UserRoleAssignment).where(UserRoleAssignment.id == assignment_id)
    )
    assignment = result.scalar_one_or_none()
    if not assignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    await db.delete(assignment)
    await db.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─── Ingestion sources ────────────────────────────────────────────────────────


@router.get("/ingestion-sources", response_model=list[dict])
async def list_ingestion_sources(
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """List configured ingestion sources (cursors)."""
    from app.models.ingestion import IngestionCursor

    result = await db.execute(select(IngestionCursor).order_by(IngestionCursor.updated_at.desc()))
    cursors = result.scalars().all()
    return [
        {
            "id": c.id,
            "source_type": c.source_type,
            "org": c.org,
            "cursor_value": c.cursor_value,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        }
        for c in cursors
    ]


@router.post("/ingestion-sources", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_ingestion_source(
    payload: IngestionSourceCreate,
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Register a new ingestion source."""
    from app.models.ingestion import IngestionCursor

    cursor = IngestionCursor(
        source_type=payload.source_type,
        org=payload.org,
        cursor_value=None,
    )
    db.add(cursor)
    await db.flush()
    return {
        "id": cursor.id,
        "source_type": cursor.source_type,
        "org": cursor.org,
        "message": "Ingestion source registered",
    }


@router.delete("/ingestion-sources/{source_id}")
async def delete_ingestion_source(
    source_id: int,
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Remove an ingestion source cursor."""
    from app.models.ingestion import IngestionCursor

    result = await db.execute(select(IngestionCursor).where(IngestionCursor.id == source_id))
    cursor = result.scalar_one_or_none()
    if not cursor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    await db.delete(cursor)
    await db.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─── Retention configuration ─────────────────────────────────────────────────


@router.get("/retention", response_model=RetentionConfig)
async def get_retention(
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> RetentionConfig:
    """Get current retention policy configuration."""
    # Read from TimescaleDB retention policy metadata
    result = await db.execute(
        text("""
            SELECT hypertable_name, config
            FROM timescaledb_information.jobs
            WHERE proc_name = 'policy_retention'
              AND hypertable_name IN ('events', 'audit_trail')
        """)
    )
    rows = result.fetchall()
    policies = {r.hypertable_name: r.config for r in rows}
    return RetentionConfig(
        events_retention_days=policies.get("events", {}).get("drop_after_days", 90),
        audit_trail_retention_days=policies.get("audit_trail", {}).get("drop_after_days", 365),
    )


@router.put("/retention", response_model=RetentionConfig)
async def update_retention(
    payload: RetentionConfig,
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> RetentionConfig:
    """Update retention policy for events and audit_trail hypertables."""
    # Remove existing policies first, then add new ones
    await db.execute(text("SELECT remove_retention_policy('events', if_exists => true)"))
    await db.execute(text("SELECT remove_retention_policy('audit_trail', if_exists => true)"))
    await db.execute(
        text(
            "SELECT add_retention_policy('events', "
            f"INTERVAL '{payload.events_retention_days} days')"
        )
    )
    await db.execute(
        text(
            "SELECT add_retention_policy('audit_trail', "
            f"INTERVAL '{payload.audit_trail_retention_days} days')"
        )
    )
    return payload


# ─── Analytics helpers ────────────────────────────────────────────────────────


@router.get("/top-actors", response_model=list[dict])
async def get_top_actors(
    window_days: int = 30,
    limit: int = 25,
    org: str | None = None,
    current_user: AuthenticatedUser = Depends(require_role(["report_admin", "sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Return top actors by event count in the window."""
    return await get_top_actors_report(db, window_days=window_days, limit=limit, org=org)


@router.get("/event-trend", response_model=list[dict])
async def get_event_trend(
    window_days: int = 30,
    granularity: str = "hourly",
    org: str | None = None,
    current_user: AuthenticatedUser = Depends(require_role(["report_admin", "sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Return overall event volume trend (uses pre-computed events_hourly if granularity=hourly)."""
    from app.services.report_service import get_event_trend_report

    return await get_event_trend_report(
        db, window_days=window_days, granularity=granularity, org=org
    )


@router.post("/audit-trail/export", response_model=dict)
async def export_audit_trail(
    from_date: str,
    to_date: str,
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Trigger audit trail export (returns count of records in range)."""
    from app.models.audit_trail import AuditTrail

    result = await db.execute(
        select(AuditTrail).where(
            AuditTrail.created_at >= from_date,
            AuditTrail.created_at <= to_date,
        )
    )
    count = len(result.scalars().all())
    return {"record_count": count, "from_date": from_date, "to_date": to_date}
