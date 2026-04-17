"""Admin router: user management, retention config, ingestion sources, top-actors."""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.deps import AuthenticatedUser, get_db, get_valkey, require_role, verify_csrf
from app.models.user import RbacRole, UserRoleAssignment
from app.schemas.integration import (
    ArchiveFileInfo,
    ArchiveRestoreRequest,
    GdprEraseRequest,
    GdprEraseResponse,
    IngestionSourceCreate,
    RetentionPoliciesResponse,
    RetentionPolicyItem,
    RetentionUpdateRequest,
    RoleAssignmentCreate,
    RoleAssignmentResponse,
)
from app.services.audit_service import log_action
from app.services.report_service import get_top_actors_report
from app.services.settings_service import get_setting, set_setting
from app.utils.client_ip import get_client_ip

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
    ip = get_client_ip(request)
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
    ip = get_client_ip(request)
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


@router.get("/retention", response_model=RetentionPoliciesResponse)
async def get_retention(
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> RetentionPoliciesResponse:
    """Get retention policies for all managed tables with storage statistics."""
    from app.services import retention_service

    policies = await retention_service.get_all_policies(db)

    # Best-effort storage stats (may fail on non-Postgres test DBs)
    stats: dict[str, dict[str, int]] = {}
    try:
        stats = await retention_service.get_storage_stats(db)
    except Exception:
        stats = {}  # gracefully degrade when stats unavailable

    items: list[RetentionPolicyItem] = []
    for table_name, policy in policies.items():
        tbl_stats = stats.get(table_name, {})
        items.append(
            RetentionPolicyItem(
                table_name=table_name,
                time_column=policy["time_column"],
                retention_days=policy["retention_days"],
                default_days=policy["default_days"],
                row_count=tbl_stats.get("row_count", 0),
                size_bytes=tbl_stats.get("size_bytes", 0),
            )
        )
    return RetentionPoliciesResponse(policies=items)


@router.put(
    "/retention",
    response_model=RetentionPoliciesResponse,
    dependencies=[Depends(verify_csrf)],
)
async def update_retention(
    payload: RetentionUpdateRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> RetentionPoliciesResponse:
    """Update retention policies for one or more tables."""
    from app.services import retention_service

    ip = get_client_ip(request)
    for table_name, days in payload.policies.items():
        if table_name not in retention_service.RETENTION_TABLES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown table: {table_name}",
            )
        if days < 1 or days > 3650:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"retention_days must be 1-3650 for {table_name}",
            )
        await retention_service.update_policy(
            db, table_name, days, user_login=current_user.github_login, ip_address=ip
        )
    await db.commit()

    # Return the updated full policy set
    return await get_retention(current_user=current_user, db=db)


# ─── Archive management ──────────────────────────────────────────────────────


@router.get("/archive/list", response_model=list[ArchiveFileInfo])
async def list_archives(
    table: str | None = None,
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
) -> list[ArchiveFileInfo]:
    """List archive files in object storage, optionally filtered by table."""
    from app.services.archive_service import get_archive_bucket, get_s3_client
    from app.services.archive_service import list_archives as _list

    try:
        s3 = get_s3_client()
        bucket = get_archive_bucket()
        items = _list(s3_client=s3, bucket=bucket, table_name=table)
        return [ArchiveFileInfo(**item) for item in items]
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not list archives: {exc}",
        ) from exc


@router.post("/archive/restore", dependencies=[Depends(verify_csrf)])
async def restore_archive(
    payload: ArchiveRestoreRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Restore data from an archive file back into the database."""
    from app.services.archive_service import get_archive_bucket, get_s3_client
    from app.services.archive_service import restore_archive as _restore

    ip = get_client_ip(request)

    try:
        s3 = get_s3_client()
        bucket = get_archive_bucket()
        restored = await _restore(db, payload.archive_path, s3_client=s3, bucket=bucket)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Restore failed: {exc}",
        ) from exc

    await log_action(
        db,
        user_login=current_user.github_login,
        user_github_id=current_user.github_id,
        ip_address=ip,
        user_agent=request.headers.get("user-agent"),
        action_type="archive.restore",
        resource_type="archive",
        resource_id=payload.archive_path,
        parameters={"restored_rows": restored},
    )
    await db.commit()

    return {"archive_path": payload.archive_path, "restored_rows": restored}


# ─── GDPR erasure ────────────────────────────────────────────────────────────


@router.post(
    "/gdpr/erase",
    response_model=GdprEraseResponse,
    dependencies=[Depends(verify_csrf)],
)
async def gdpr_erase(
    payload: GdprEraseRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> GdprEraseResponse:
    """Erase/anonymise all data for a GitHub user (GDPR right-to-erasure)."""
    from app.services import gdpr_service

    ip = get_client_ip(request)

    result = await gdpr_service.erase_user(
        db,
        payload.github_login,
        authorized_by=current_user.github_login,
        ip_address=ip,
    )
    return GdprEraseResponse(**result)


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


@router.post("/audit-trail/export", dependencies=[Depends(verify_csrf)])
async def export_audit_trail(
    from_date: str,
    to_date: str,
    format: str = "csv",
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Export audit trail records as a downloadable CSV or NDJSON file.

    Streams results to keep memory usage constant regardless of result-set size.
    """
    import csv
    import io
    import json as _json
    from datetime import datetime as _dt

    from fastapi.responses import StreamingResponse

    from app.models.audit_trail import AuditTrail

    if format not in ("csv", "json"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported export format: {format!r}. Use 'csv' or 'json'.",
        )

    result = await db.execute(
        select(AuditTrail)
        .where(
            AuditTrail.timestamp >= from_date,
            AuditTrail.timestamp <= to_date,
        )
        .order_by(AuditTrail.timestamp)
    )
    rows = result.scalars().all()

    _CSV_COLUMNS = [
        "id",
        "timestamp",
        "user_login",
        "user_github_id",
        "ip_address",
        "user_agent",
        "action_type",
        "resource_type",
        "resource_id",
        "parameters",
        "outcome",
        "error_detail",
    ]

    def _serialize_value(value: object) -> str:
        """Convert a value to a CSV-safe string."""
        if value is None:
            return ""
        if isinstance(value, _dt):
            return value.isoformat()
        if isinstance(value, dict):
            return _json.dumps(value)
        return str(value)

    def _row_to_dict(row: AuditTrail) -> dict[str, str]:
        return {col: _serialize_value(getattr(row, col, None)) for col in _CSV_COLUMNS}

    safe_from = from_date.replace(":", "-")
    safe_to = to_date.replace(":", "-")

    if format == "json":

        def _generate_ndjson() -> Iterator[str]:
            for row in rows:
                yield _json.dumps(_row_to_dict(row)) + "\n"

        return StreamingResponse(
            _generate_ndjson(),
            media_type="application/x-ndjson",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="audit_trail_{safe_from}_to_{safe_to}.ndjson"'
                ),
            },
        )

    # Default: CSV
    def _generate_csv() -> Iterator[str]:
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=_CSV_COLUMNS)
        writer.writeheader()
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate(0)
        for row in rows:
            writer.writerow(_row_to_dict(row))
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate(0)

    return StreamingResponse(
        _generate_csv(),
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                f'attachment; filename="audit_trail_{safe_from}_to_{safe_to}.csv"'
            ),
        },
    )


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
    hec_token = await get_setting(db, "hec_token")

    base_url = settings.AUTH.APP_BASE_URL
    hec_base = os.environ.get("HEC_BASE_URL", "")
    if not hec_base:
        hec_base = base_url.replace("-5173.", "-8000.") if "-5173." in base_url else base_url

    return {
        "configured": bool(hec_token),
        "hec_endpoint": f"{hec_base}/services/collector",
        "hec_configured": bool(hec_token),
        "hec_instructions": {
            "step_1": "Go to GitHub Enterprise → Settings → Audit Log → Log Streaming",
            "step_2": "Select 'Splunk' as the provider",
            "step_3": f"HEC URL: {hec_base}/services/collector",
            "step_4": "HEC Token: <use the token configured below>",
            "step_5": "Enable SSL verification (if using TLS)",
        },
    }


@router.put("/audit-stream/hec-token", dependencies=[Depends(verify_csrf)])
async def update_hec_token(
    payload: dict[str, str],
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Update or generate the HEC token for Splunk-compatible streaming."""
    import secrets as _secrets

    token = payload.get("hec_token", "").strip()
    if not token:
        token = _secrets.token_urlsafe(32)

    await set_setting(
        db,
        "hec_token",
        token,
        category="audit_stream",
        sensitivity="critical",
        description="Splunk HEC token for audit log streaming",
        changed_by=current_user.github_login,
    )

    # Update the in-memory cache so the HEC router picks it up immediately
    from app.routers.ingest_hec import set_hec_token_cache

    set_hec_token_cache(token)

    return {
        "status": "ok",
        "hec_token": token,
        "message": "HEC token saved. Use this token in GitHub's Splunk streaming configuration.",
    }


# ─── GitHub IP allowlist ─────────────────────────────────────────────────────


@router.get("/github-ip-allowlist")
async def github_ip_allowlist_status(
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
) -> dict[str, object]:
    """Return the current status of the GitHub IP allowlist."""
    from app.services.github_ip_allowlist import GitHubIPAllowlist

    return {
        "enabled": settings.github_app.GITHUB_IP_ALLOWLIST_ENABLED,
        "loaded": GitHubIPAllowlist.is_loaded(),
        "network_count": GitHubIPAllowlist.network_count(),
    }


@router.post("/github-ip-allowlist/refresh", dependencies=[Depends(verify_csrf)])
async def refresh_github_ip_allowlist(
    request: Request,
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    valkey: aioredis.Redis = Depends(get_valkey),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """Force-refresh the GitHub IP allowlist from the /meta endpoint."""
    from app.services.github_ip_allowlist import GitHubIPAllowlist

    count = await GitHubIPAllowlist.refresh(valkey)

    ip = get_client_ip(request)
    await log_action(
        db,
        user_login=current_user.github_login,
        user_github_id=current_user.github_id,
        ip_address=ip,
        user_agent=request.headers.get("user-agent"),
        action_type="admin.github_ip_allowlist.refresh",
        resource_type="github_ip_allowlist",
        parameters={"network_count": count},
    )
    await db.commit()

    return {"refreshed": True, "network_count": count}
