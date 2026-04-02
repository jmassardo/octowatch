"""Admin router: user management, retention config, ingestion sources, top-actors."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.deps import AuthenticatedUser, get_db, require_role, verify_csrf
from app.models.user import RbacRole, UserRoleAssignment
from app.schemas.integration import (
    IngestionSourceCreate,
    RetentionConfig,
    RoleAssignmentCreate,
    RoleAssignmentResponse,
)
from app.services.audit_service import log_action
from app.services.report_service import get_top_actors_report
from app.services.settings_service import get_setting, set_setting

router = APIRouter(prefix="/admin", tags=["admin"])

# Role priority for determining a user's primary (highest-privilege) role.
_ROLE_PRIORITY: list[str] = ["sys_admin", "report_admin", "rule_author", "analyst", "viewer"]


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
        select(UserRoleAssignment)
        .options(selectinload(UserRoleAssignment.role))
        .order_by(UserRoleAssignment.granted_at.desc())
    )
    assignments = result.scalars().all()
    return [
        RoleAssignmentResponse(
            id=a.id,
            github_login=a.github_login,
            github_team_slug=a.github_team_slug,
            role_id=a.role_id,
            role_name=a.role.name if a.role else "unknown",
            scope_type=a.scope_type,
            scope_value=a.scope_value,
            granted_by=a.granted_by,
            granted_at=a.granted_at,
            expires_at=a.expires_at,
            active=a.active,
        )
        for a in assignments
    ]


@router.post(
    "/assignments",
    response_model=RoleAssignmentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_csrf)],
)
async def create_role_assignment(
    payload: RoleAssignmentCreate,
    request: Request,
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
            UserRoleAssignment.scope_type == payload.scope_type,
        )
    )
    if existing_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Role assignment already exists",
        )

    assignment = UserRoleAssignment(
        github_login=payload.github_login,
        github_team_id=payload.github_team_id,
        github_team_slug=payload.github_team_slug,
        saml_subject=payload.saml_subject,
        role_id=role.id,
        scope_type=payload.scope_type,
        scope_value=payload.scope_value,
        granted_by=current_user.github_login,
    )
    db.add(assignment)
    await db.flush()

    # Eagerly load the role relationship for the response
    await db.refresh(assignment, attribute_names=["role"])
    forwarded = request.headers.get("x-forwarded-for")
    ip = (
        forwarded.split(",")[0].strip()
        if forwarded
        else (request.client.host if request.client else None)
    )
    await log_action(
        db,
        user_login=current_user.github_login,
        user_github_id=current_user.github_id,
        ip_address=ip,
        user_agent=request.headers.get("user-agent"),
        action_type="role_assignment.create",
        resource_type="role_assignment",
        resource_id=str(assignment.id),
        parameters={"login": payload.github_login, "role": payload.role_name},
    )
    return RoleAssignmentResponse(
        id=assignment.id,
        github_login=assignment.github_login,
        github_team_slug=assignment.github_team_slug,
        role_id=assignment.role_id,
        role_name=assignment.role.name if assignment.role else payload.role_name,
        scope_type=assignment.scope_type,
        scope_value=assignment.scope_value,
        granted_by=assignment.granted_by,
        granted_at=assignment.granted_at,
        expires_at=assignment.expires_at,
        active=assignment.active,
    )


@router.delete("/assignments/{assignment_id}", dependencies=[Depends(verify_csrf)])
async def delete_role_assignment(
    assignment_id: int,
    request: Request,
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
    assignment_login = assignment.github_login
    assignment_role_id = assignment.role_id
    await db.delete(assignment)
    await db.flush()
    forwarded = request.headers.get("x-forwarded-for")
    ip = (
        forwarded.split(",")[0].strip()
        if forwarded
        else (request.client.host if request.client else None)
    )
    await log_action(
        db,
        user_login=current_user.github_login,
        user_github_id=current_user.github_id,
        ip_address=ip,
        user_agent=request.headers.get("user-agent"),
        action_type="role_assignment.delete",
        resource_type="role_assignment",
        resource_id=str(assignment_id),
        parameters={"login": assignment_login, "role_id": assignment_role_id},
    )
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


@router.post(
    "/ingestion-sources",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_csrf)],
)
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


@router.delete("/ingestion-sources/{source_id}", dependencies=[Depends(verify_csrf)])
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


@router.put("/retention", response_model=RetentionConfig, dependencies=[Depends(verify_csrf)])
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


@router.post("/audit-trail/export", response_model=dict, dependencies=[Depends(verify_csrf)])
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


# ─── Active sessions ─────────────────────────────────────────────────────────


@router.get("/sessions", response_model=list[dict[str, Any]])
async def list_active_sessions(
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Return active OctoWatch sessions from audit trail (last 24 hours)."""
    result = await db.execute(
        text("""
            SELECT
                user_login,
                MAX(timestamp) AS last_active_at,
                COUNT(*) AS session_count
            FROM audit_trail
            WHERE timestamp >= NOW() - INTERVAL '24 hours'
              AND user_login IS NOT NULL
            GROUP BY user_login
            ORDER BY last_active_at DESC
            LIMIT 50
        """)
    )
    rows = result.fetchall()
    if not rows:
        return []

    # Resolve actual RBAC roles for all active users
    logins = [row.user_login for row in rows]
    role_result = await db.execute(
        select(UserRoleAssignment.github_login, RbacRole.name)
        .join(RbacRole, UserRoleAssignment.role_id == RbacRole.id)
        .where(
            UserRoleAssignment.github_login.in_(logins),
            UserRoleAssignment.active.is_(True),
            (UserRoleAssignment.expires_at.is_(None))
            | (UserRoleAssignment.expires_at > text("NOW()")),
        )
    )

    # Build login → set of role names
    login_roles: dict[str, set[str]] = {}
    for login, role_name in role_result.fetchall():
        login_roles.setdefault(login, set()).add(role_name)

    # Grant sys_admin to bootstrap admin logins
    for login in logins:
        if login.lower() in settings.initial_admin_logins:
            login_roles.setdefault(login, set()).add("sys_admin")

    def _primary_role(login: str) -> str:
        """Return the highest-privilege role for a user."""
        roles = login_roles.get(login, set())
        for r in _ROLE_PRIORITY:
            if r in roles:
                return r
        return "viewer"

    sessions: list[dict[str, Any]] = []
    for row in rows:
        sessions.append(
            {
                "login": row.user_login,
                "last_active_at": (row.last_active_at.isoformat() if row.last_active_at else None),
                "session_count": row.session_count,
                "role": _primary_role(row.user_login),
                "mfa_enabled": True,
            }
        )
    return sessions


# ─── Synced teams ─────────────────────────────────────────────────────────────


@router.get("/teams", response_model=list[dict[str, Any]])
async def list_synced_teams(
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """List GitHub teams from the latest enterprise sync.

    Returns teams from the ``org_teams`` table so the frontend can display
    team names in role assignment forms and validate team slugs.
    """
    from app.models.github_sync import OrgTeam

    result = await db.execute(select(OrgTeam).order_by(OrgTeam.org, OrgTeam.team_slug).limit(500))
    teams = result.scalars().all()
    return [
        {
            "org": t.org,
            "team_slug": t.team_slug,
            "name": t.name,
            "privacy": t.privacy,
            "synced_at": t.synced_at.isoformat() if t.synced_at else None,
        }
        for t in teams
    ]


# ─── Ingest job stubs ─────────────────────────────────────────────────────────


@router.get("/ingest/jobs")
async def list_ingest_jobs(
    page: int = 1,
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List recent file ingestion jobs from audit trail."""
    per_page = 20
    offset = (page - 1) * per_page
    result = await db.execute(
        text("""
            SELECT id, timestamp, parameters, outcome
            FROM audit_trail
            WHERE action_type = 'ingest.upload'
            ORDER BY timestamp DESC
            LIMIT :limit OFFSET :offset
        """),
        {"limit": per_page, "offset": offset},
    )
    rows = result.fetchall()
    count_result = await db.execute(
        text("SELECT COUNT(*) FROM audit_trail WHERE action_type = 'ingest.upload'")
    )
    total = count_result.scalar() or 0
    items = [
        {
            "id": str(r.id),
            "created_at": r.timestamp.isoformat(),
            "status": r.outcome or "success",
            "file_name": (r.parameters or {}).get("file_name", "unknown"),
            "file_type": (r.parameters or {}).get("type", "unknown"),
            "events_processed": (r.parameters or {}).get("events_processed", 0),
        }
        for r in rows
    ]
    return {"items": items, "total": total}


@router.get("/ingest/jobs/{job_id}")
async def get_ingest_job(
    job_id: str,
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get a specific ingest job by audit trail ID."""
    result = await db.execute(
        text("SELECT id, timestamp, parameters, outcome FROM audit_trail WHERE id = :id"),
        {"id": int(job_id)},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "id": str(row.id),
        "created_at": row.timestamp.isoformat(),
        "status": row.outcome or "success",
        "file_name": (row.parameters or {}).get("file_name", "unknown"),
        "file_type": (row.parameters or {}).get("type", "unknown"),
        "events_processed": (row.parameters or {}).get("events_processed", 0),
    }


@router.get("/audit-stream/config")
async def get_audit_stream_config(
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get current audit log streaming configuration."""
    stream_user = await get_setting(db, "minio_stream_user")
    stream_password = await get_setting(db, "minio_stream_password")

    base_url = settings.AUTH.APP_BASE_URL
    bucket = settings.MINIO.MINIO_AUDIT_BUCKET

    return {
        "configured": bool(stream_user and stream_password),
        "stream_user": stream_user or "",
        "s3_endpoint": f"{base_url}/s3",
        "bucket": bucket,
        "region": "us-east-1",
        "instructions": {
            "step_1": "Go to GitHub Enterprise → Settings → Audit Log → Log Streaming",
            "step_2": "Select 'Amazon S3' as the provider",
            "step_3": f"S3 Endpoint: {base_url}/s3",
            "step_4": f"Bucket: {bucket}",
            "step_5": f"Access Key ID: {stream_user or '<configure first>'}",
            "step_6": "Secret Access Key: <use the password configured in the vault>",
            "step_7": "Region: us-east-1",
        },
    }


@router.put("/audit-stream/config", dependencies=[Depends(verify_csrf)])
async def update_audit_stream_config(
    payload: dict[str, str],
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Update audit log streaming credentials in the vault."""
    stream_user = payload.get("stream_user", "").strip()
    stream_password = payload.get("stream_password", "").strip()

    if not stream_user or not stream_password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Both stream_user and stream_password are required",
        )
    if len(stream_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="stream_password must be at least 8 characters (MinIO requirement)",
        )

    await set_setting(
        db,
        "minio_stream_user",
        stream_user,
        category="audit_stream",
        sensitivity="sensitive",
        description="MinIO streaming service account username",
        changed_by=current_user.github_login,
    )
    await set_setting(
        db,
        "minio_stream_password",
        stream_password,
        category="audit_stream",
        sensitivity="critical",
        description="MinIO streaming service account password",
        changed_by=current_user.github_login,
    )

    return {
        "status": "ok",
        "message": (
            "Streaming credentials updated. Restart minio-setup to provision the user in MinIO."
        ),
    }
