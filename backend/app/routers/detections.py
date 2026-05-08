"""Detections router: CRUD for detections, status management, and assignment."""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.deps import AuthenticatedUser, get_db, require_permission, verify_csrf
from app.models.audit_event import AuditEvent
from app.models.detection import Detection
from app.schemas.actor import DetectionTimeline, TimelineEvent
from app.schemas.detection import (
    AssignDetectionRequest,
    DetectionListParams,
    DetectionListResponse,
    DetectionResponse,
    UpdateDetectionStatusRequest,
)
from app.services.audit_service import log_action
from app.services.rbac_service import get_user_scope
from app.utils.client_ip import get_client_ip

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/detections", tags=["detections"])


async def _get_detection_or_404(
    db: AsyncSession, detection_id: int, scope_orgs: list[str] | None = None
) -> Detection:
    stmt = (
        select(Detection).options(selectinload(Detection.rule)).where(Detection.id == detection_id)
    )
    if scope_orgs:
        stmt = stmt.where(Detection.org.in_(scope_orgs))
    result = await db.execute(stmt)
    detection = result.scalar_one_or_none()
    if not detection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Detection not found")
    return detection


@router.get("", response_model=DetectionListResponse)
async def list_detections(
    params: DetectionListParams = Depends(),
    current_user: AuthenticatedUser = Depends(require_permission("detections", "view")),
    db: AsyncSession = Depends(get_db),
) -> DetectionListResponse:
    """List detections with filtering and pagination."""
    scope = await get_user_scope(db, current_user.github_login, current_user.roles)

    stmt = (
        select(Detection)
        .options(selectinload(Detection.rule))
        .order_by(Detection.triggered_at.desc())
    )

    if params.status:
        stmt = stmt.where(Detection.status == params.status)
    if params.severity:
        stmt = stmt.where(Detection.severity == params.severity)
    if params.rule_id:
        stmt = stmt.where(Detection.rule_id == params.rule_id)
    if params.actor:
        stmt = stmt.where(Detection.actor == params.actor)
    if params.org:
        stmt = stmt.where(Detection.org == params.org)
    if params.repo:
        safe_repo = params.repo.replace("%", r"\%").replace("_", r"\_")
        stmt = stmt.where(Detection.repo.ilike(f"%{safe_repo}%"))
    if params.since:
        stmt = stmt.where(Detection.triggered_at >= params.since)
    if params.until:
        stmt = stmt.where(Detection.triggered_at <= params.until)

    # Scope enforcement: inject org allowlist
    if scope.scoped_orgs:
        stmt = stmt.where(Detection.org.in_(scope.scoped_orgs))

    # Count total matching results
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total: int = (await db.execute(count_stmt)).scalar_one()

    # Pagination
    offset = (params.page - 1) * params.page_size
    stmt = stmt.limit(params.page_size).offset(offset)
    result = await db.execute(stmt)
    detections = result.scalars().all()

    return DetectionListResponse(
        items=[DetectionResponse.model_validate(d) for d in detections],
        total=total,
        page=params.page,
        page_size=params.page_size,
        has_next=(params.page * params.page_size < total),
    )


@router.get("/{detection_id}", response_model=DetectionResponse)
async def get_detection(
    detection_id: int,
    current_user: AuthenticatedUser = Depends(require_permission("detections", "view")),
    db: AsyncSession = Depends(get_db),
) -> DetectionResponse:
    """Get a single detection by ID."""
    scope = await get_user_scope(db, current_user.github_login, current_user.roles)
    detection = await _get_detection_or_404(db, detection_id, scope.scoped_orgs)
    return DetectionResponse.model_validate(detection)


@router.patch(
    "/{detection_id}/status", response_model=DetectionResponse, dependencies=[Depends(verify_csrf)]
)
async def update_detection_status(
    detection_id: int,
    payload: UpdateDetectionStatusRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(require_permission("detections", "edit")),
    db: AsyncSession = Depends(get_db),
) -> DetectionResponse:
    """Update the status of a detection (e.g. open → investigating → closed)."""
    scope = await get_user_scope(db, current_user.github_login, current_user.roles)
    detection = await _get_detection_or_404(db, detection_id, scope.scoped_orgs)

    valid_transitions = {
        "open": {"investigating", "resolved", "false_positive"},
        "investigating": {"open", "resolved", "false_positive"},
        "resolved": {"open"},
        "false_positive": {"open"},
    }
    if payload.status not in valid_transitions.get(detection.status, set()):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Cannot transition from '{detection.status}' to '{payload.status}'",
        )

    previous_status = detection.status
    detection.status = payload.status
    if payload.status == "resolved":
        detection.resolved_at = datetime.now(UTC)
        detection.resolved_by = current_user.github_login
    elif previous_status == "resolved" and payload.status != "resolved":
        detection.resolved_at = None
        detection.resolved_by = None

    if payload.resolution_note:
        detection.resolution_note = payload.resolution_note
    await db.flush()

    if payload.status == "resolved":
        try:
            import redis.asyncio as aioredis

            from app.config import settings
            from app.services.pagerduty_service import resolve_detection_incident

            valkey = aioredis.from_url(settings.VALKEY_URL, decode_responses=True)
            try:
                await resolve_detection_incident(db, valkey, detection_id)
            finally:
                await valkey.aclose()
        except Exception as exc:
            logger.warning(
                "detection.pagerduty_auto_resolve_failed",
                detection_id=detection_id,
                error=str(exc),
            )

    ip = get_client_ip(request)
    await log_action(
        db,
        user_login=current_user.github_login,
        user_github_id=current_user.github_id,
        ip_address=ip,
        user_agent=request.headers.get("user-agent"),
        action_type="detection.status_change",
        resource_type="detection",
        resource_id=str(detection_id),
        parameters={"new_status": payload.status},
    )

    return DetectionResponse.model_validate(detection)


@router.patch(
    "/{detection_id}/assign", response_model=DetectionResponse, dependencies=[Depends(verify_csrf)]
)
async def assign_detection(
    detection_id: int,
    payload: AssignDetectionRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(require_permission("detections", "edit")),
    db: AsyncSession = Depends(get_db),
) -> DetectionResponse:
    """Assign a detection to a user."""
    scope = await get_user_scope(db, current_user.github_login, current_user.roles)
    detection = await _get_detection_or_404(db, detection_id, scope.scoped_orgs)

    detection.assigned_to = payload.assigned_to
    await db.flush()
    ip = get_client_ip(request)
    await log_action(
        db,
        user_login=current_user.github_login,
        user_github_id=current_user.github_id,
        ip_address=ip,
        user_agent=request.headers.get("user-agent"),
        action_type="detection.assign",
        resource_type="detection",
        resource_id=str(detection_id),
        parameters={"assigned_to": payload.assigned_to},
    )
    return DetectionResponse.model_validate(detection)


@router.post("/{detection_id}/suppress", response_model=dict, dependencies=[Depends(verify_csrf)])
async def suppress_from_detection(
    detection_id: int,
    current_user: AuthenticatedUser = Depends(require_permission("rules", "create")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a suppression rule scoped to the actor/org of this detection."""
    scope = await get_user_scope(db, current_user.github_login, current_user.roles)
    detection = await _get_detection_or_404(db, detection_id, scope.scoped_orgs)

    from app.models.detection import DetectionSuppression

    suppression = DetectionSuppression(
        rule_id=detection.rule_id,
        suppress_actor=detection.actor,
        suppress_org=detection.org,
        active=True,
        created_by=current_user.github_login,
    )
    db.add(suppression)
    await db.flush()

    return {"suppression_id": suppression.id, "detection_id": detection_id}


@router.delete("/{detection_id}", dependencies=[Depends(verify_csrf)])
async def delete_detection(
    detection_id: int,
    request: Request,
    current_user: AuthenticatedUser = Depends(require_permission("detections", "delete")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Delete a detection record (sys_admin only)."""
    scope = await get_user_scope(db, current_user.github_login, current_user.roles)
    detection = await _get_detection_or_404(db, detection_id, scope.scoped_orgs)
    await db.delete(detection)
    await db.flush()
    ip = get_client_ip(request)
    await log_action(
        db,
        user_login=current_user.github_login,
        user_github_id=current_user.github_id,
        ip_address=ip,
        user_agent=request.headers.get("user-agent"),
        action_type="detection.delete",
        resource_type="detection",
        resource_id=str(detection_id),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{detection_id}/timeline", response_model=DetectionTimeline)
async def get_detection_timeline(
    detection_id: int,
    current_user: AuthenticatedUser = Depends(require_permission("detections", "view")),
    db: AsyncSession = Depends(get_db),
) -> DetectionTimeline:
    """Build a chronological investigation timeline for a detection.

    Fetches all events referenced by the detection's event_ids and annotates
    sequence steps from context_data when available.
    """
    scope = await get_user_scope(db, current_user.github_login, current_user.roles)
    detection = await _get_detection_or_404(db, detection_id, scope.scoped_orgs)

    events: list[TimelineEvent] = []
    sequence_actions: list[str] = []

    # Extract sequence steps from context_data (for sequence-type detections)
    context = detection.context_data or {}
    if "sequence" in context:
        sequence_actions = [
            step.get("action", "") for step in context["sequence"] if isinstance(step, dict)
        ]
    elif "steps" in context:
        sequence_actions = [
            step.get("action", "") for step in context["steps"] if isinstance(step, dict)
        ]

    # Fetch events by IDs
    if detection.event_ids:
        stmt = (
            select(AuditEvent)
            .where(AuditEvent.id.in_(detection.event_ids))
            .order_by(AuditEvent.created_at.asc())
        )
        result = await db.execute(stmt)
        db_events = result.scalars().all()

        for event in db_events:
            is_step = event.action in sequence_actions
            step_idx = sequence_actions.index(event.action) if is_step else None
            events.append(
                TimelineEvent(
                    id=event.id,
                    created_at=event.created_at,
                    action=event.action,
                    actor=event.actor,
                    org=event.org,
                    repo=event.repo,
                    source_ip=str(event.source_ip) if event.source_ip else None,
                    geo_country_code=event.geo_country_code,
                    geo_city=event.geo_city,
                    geo_latitude=event.geo_latitude,
                    geo_longitude=event.geo_longitude,
                    data=event.data,
                    is_sequence_step=is_step,
                    sequence_index=step_idx,
                )
            )

    category = detection.rule.category if detection.rule else None

    return DetectionTimeline(
        detection_id=detection.id,
        detection_title=detection.title,
        detection_severity=detection.severity,
        detection_category=category,
        events=events,
        sequence_steps=sequence_actions,
        context_data=context,
    )
