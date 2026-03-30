"""Detections router: CRUD for detections, status management, and assignment."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_db, require_role
from app.models.detection import Detection
from app.schemas.detection import (
    AssignDetectionRequest,
    DetectionListParams,
    DetectionListResponse,
    DetectionResponse,
    UpdateDetectionStatusRequest,
)
from app.services.rbac_service import get_user_scope

router = APIRouter(prefix="/detections", tags=["detections"])


async def _get_detection_or_404(
    db: AsyncSession, detection_id: int, scope_orgs: list[str] | None = None
) -> Detection:
    stmt = select(Detection).where(Detection.id == detection_id)
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
    current_user: AuthenticatedUser = Depends(
        require_role(["analyst", "report_admin", "rule_author", "sys_admin"])
    ),
    db: AsyncSession = Depends(get_db),
) -> DetectionListResponse:
    """List detections with filtering and pagination."""
    scope = await get_user_scope(db, current_user.github_login, current_user.roles)

    stmt = select(Detection).order_by(Detection.triggered_at.desc())

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
    current_user: AuthenticatedUser = Depends(
        require_role(["analyst", "report_admin", "rule_author", "sys_admin"])
    ),
    db: AsyncSession = Depends(get_db),
) -> DetectionResponse:
    """Get a single detection by ID."""
    scope = await get_user_scope(db, current_user.github_login, current_user.roles)
    detection = await _get_detection_or_404(db, detection_id, scope.scoped_orgs)
    return DetectionResponse.model_validate(detection)


@router.patch("/{detection_id}/status", response_model=DetectionResponse)
async def update_detection_status(
    detection_id: int,
    payload: UpdateDetectionStatusRequest,
    current_user: AuthenticatedUser = Depends(require_role(["analyst", "sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> DetectionResponse:
    """Update the status of a detection (e.g. open → investigating → closed)."""
    scope = await get_user_scope(db, current_user.github_login)
    detection = await _get_detection_or_404(db, detection_id, scope.org_allowlist)

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

    detection.status = payload.status
    if payload.resolution_note:
        detection.resolution_note = payload.resolution_note
    await db.flush()

    return DetectionResponse.model_validate(detection)


@router.patch("/{detection_id}/assign", response_model=DetectionResponse)
async def assign_detection(
    detection_id: int,
    payload: AssignDetectionRequest,
    current_user: AuthenticatedUser = Depends(require_role(["analyst", "sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> DetectionResponse:
    """Assign a detection to a user."""
    scope = await get_user_scope(db, current_user.github_login)
    detection = await _get_detection_or_404(db, detection_id, scope.org_allowlist)

    detection.assigned_to = payload.assigned_to
    await db.flush()
    return DetectionResponse.model_validate(detection)


@router.post("/{detection_id}/suppress", response_model=dict)
async def suppress_from_detection(
    detection_id: int,
    current_user: AuthenticatedUser = Depends(require_role(["rule_author", "sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a suppression rule scoped to the actor/org of this detection."""
    scope = await get_user_scope(db, current_user.github_login)
    detection = await _get_detection_or_404(db, detection_id, scope.org_allowlist)

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


@router.delete("/{detection_id}")
async def delete_detection(
    detection_id: int,
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Delete a detection record (sys_admin only)."""
    scope = await get_user_scope(db, current_user.github_login, current_user.roles)
    detection = await _get_detection_or_404(db, detection_id, scope.scoped_orgs)
    await db.delete(detection)
    await db.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
