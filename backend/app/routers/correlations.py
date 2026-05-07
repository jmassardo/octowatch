"""Correlations router: investigation chain management and correlation engine."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_db, require_permission, verify_csrf
from app.models.correlation import ChainMembership, CorrelationChain
from app.schemas.correlation import (
    ChainMemberResponse,
    ChainMetrics,
    CorrelationChainListParams,
    CorrelationChainListResponse,
    CorrelationChainResponse,
    CorrelationChainSummary,
    CorrelationRunResponse,
    MergeChainRequest,
    UpdateChainRequest,
)
from app.services.audit_service import log_action
from app.services.correlation_service import CorrelationEngine
from app.utils.client_ip import get_client_ip

router = APIRouter(prefix="/correlations", tags=["correlations"])

_engine = CorrelationEngine()


async def _get_chain_or_404(db: AsyncSession, chain_id: str) -> CorrelationChain:
    """Fetch a chain by ID or raise 404."""
    stmt = select(CorrelationChain).where(CorrelationChain.id == chain_id)
    result = await db.execute(stmt)
    chain = result.scalar_one_or_none()
    if not chain:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chain not found")
    return chain


@router.get("/chains", response_model=CorrelationChainListResponse)
async def list_chains(
    params: CorrelationChainListParams = Depends(),
    current_user: AuthenticatedUser = Depends(require_permission("detections", "view")),
    db: AsyncSession = Depends(get_db),
) -> CorrelationChainListResponse:
    """List investigation chains with filtering and pagination."""
    stmt = select(CorrelationChain).order_by(CorrelationChain.updated_at.desc())

    if params.status:
        stmt = stmt.where(CorrelationChain.status == params.status)
    if params.severity:
        stmt = stmt.where(CorrelationChain.severity == params.severity)
    if params.assignee:
        stmt = stmt.where(CorrelationChain.assignee == params.assignee)

    # Count total matching results
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total: int = (await db.execute(count_stmt)).scalar_one()

    # Pagination
    offset = (params.page - 1) * params.page_size
    stmt = stmt.limit(params.page_size).offset(offset)
    result = await db.execute(stmt)
    chains = result.scalars().all()

    items: list[CorrelationChainSummary] = []
    for chain in chains:
        # Count members
        member_count_stmt = select(func.count()).where(ChainMembership.chain_id == chain.id)
        member_count: int = (await db.execute(member_count_stmt)).scalar_one()

        items.append(
            CorrelationChainSummary(
                chain_id=chain.id,
                title=chain.title,
                status=chain.status,
                severity=chain.severity,
                assignee=chain.assignee,
                created_at=chain.created_at,
                updated_at=chain.updated_at,
                resolved_at=chain.resolved_at,
                detection_count=member_count,
            )
        )

    return CorrelationChainListResponse(
        items=items,
        total=total,
        page=params.page,
        page_size=params.page_size,
        has_next=(params.page * params.page_size < total),
    )


@router.get("/chains/metrics", response_model=ChainMetrics)
async def get_chain_metrics(
    current_user: AuthenticatedUser = Depends(require_permission("detections", "view")),
    db: AsyncSession = Depends(get_db),
) -> ChainMetrics:
    """Get summary metrics for the chains dashboard."""
    # Active chains (open or investigating)
    active_stmt = select(func.count()).where(CorrelationChain.status.in_(["open", "investigating"]))
    active_chains: int = (await db.execute(active_stmt)).scalar_one()

    # Total chains
    total_stmt = select(func.count()).select_from(CorrelationChain)
    total_chains: int = (await db.execute(total_stmt)).scalar_one()

    # Average chain size
    avg_size: float = 0.0
    if total_chains > 0:
        avg_stmt = select(
            func.avg(
                select(func.count())
                .where(ChainMembership.chain_id == CorrelationChain.id)
                .correlate(CorrelationChain)
                .scalar_subquery()
            )
        ).select_from(CorrelationChain)
        avg_result = (await db.execute(avg_stmt)).scalar_one()
        avg_size = float(avg_result) if avg_result else 0.0

    # Chains resolved today
    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    resolved_stmt = select(func.count()).where(
        CorrelationChain.status == "resolved",
        CorrelationChain.resolved_at >= today_start,
    )
    chains_resolved_today: int = (await db.execute(resolved_stmt)).scalar_one()

    return ChainMetrics(
        active_chains=active_chains,
        avg_chain_size=round(avg_size, 1),
        chains_resolved_today=chains_resolved_today,
        total_chains=total_chains,
    )


@router.get("/chains/{chain_id}", response_model=CorrelationChainResponse)
async def get_chain(
    chain_id: str,
    current_user: AuthenticatedUser = Depends(require_permission("detections", "view")),
    db: AsyncSession = Depends(get_db),
) -> CorrelationChainResponse:
    """Get a chain with all member detections."""
    chain_data = await _engine.get_investigation_chain(chain_id, db)
    if chain_data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chain not found")

    members = [
        ChainMemberResponse(
            detection_id=m.detection_id,
            correlation_type=m.correlation_type,
            confidence=m.confidence,
            added_at=m.added_at,
            detection_title=m.detection_title,
            detection_severity=m.detection_severity,
            detection_status=m.detection_status,
            detection_actor=m.detection_actor,
            detection_triggered_at=m.detection_triggered_at,
        )
        for m in chain_data.members
    ]

    return CorrelationChainResponse(
        chain_id=chain_data.chain_id,
        title=chain_data.title,
        status=chain_data.status,
        severity=chain_data.severity,
        assignee=chain_data.assignee,
        notes=chain_data.notes,
        created_at=chain_data.created_at,
        updated_at=chain_data.updated_at,
        resolved_at=chain_data.resolved_at,
        members=members,
        detection_count=len(members),
    )


@router.put(
    "/chains/{chain_id}",
    response_model=CorrelationChainResponse,
    dependencies=[Depends(verify_csrf)],
)
async def update_chain(
    chain_id: str,
    payload: UpdateChainRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(require_permission("detections", "edit")),
    db: AsyncSession = Depends(get_db),
) -> CorrelationChainResponse:
    """Update chain (assign, change status, add notes)."""
    chain = await _get_chain_or_404(db, chain_id)

    if payload.status is not None:
        chain.status = payload.status
        if payload.status == "resolved":
            chain.resolved_at = datetime.now(UTC)
        elif chain.resolved_at is not None and payload.status != "resolved":
            chain.resolved_at = None

    if payload.assignee is not None:
        chain.assignee = payload.assignee

    if payload.title is not None:
        chain.title = payload.title

    if payload.notes is not None:
        chain.notes = payload.notes

    await db.flush()

    ip = get_client_ip(request)
    await log_action(
        db,
        user_login=current_user.github_login,
        user_github_id=current_user.github_id,
        ip_address=ip,
        user_agent=request.headers.get("user-agent"),
        action_type="correlation.chain_update",
        resource_type="correlation_chain",
        resource_id=chain_id,
        parameters={
            "status": payload.status,
            "assignee": payload.assignee,
        },
    )

    return await get_chain(chain_id, current_user, db)


@router.post(
    "/chains/{chain_id}/merge",
    response_model=CorrelationChainResponse,
    dependencies=[Depends(verify_csrf)],
)
async def merge_chain(
    chain_id: str,
    payload: MergeChainRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(require_permission("detections", "edit")),
    db: AsyncSession = Depends(get_db),
) -> CorrelationChainResponse:
    """Merge another chain into this one."""
    # Validate both chains exist
    await _get_chain_or_404(db, chain_id)
    await _get_chain_or_404(db, payload.source_chain_id)

    result_id = await _engine.merge_chains([chain_id, payload.source_chain_id], db)
    if result_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to merge chains",
        )

    ip = get_client_ip(request)
    await log_action(
        db,
        user_login=current_user.github_login,
        user_github_id=current_user.github_id,
        ip_address=ip,
        user_agent=request.headers.get("user-agent"),
        action_type="correlation.chain_merge",
        resource_type="correlation_chain",
        resource_id=chain_id,
        parameters={"source_chain_id": payload.source_chain_id},
    )

    return await get_chain(result_id, current_user, db)


@router.post("/run/{detection_id}", response_model=CorrelationRunResponse)
async def run_correlation(
    detection_id: int,
    current_user: AuthenticatedUser = Depends(require_permission("detections", "edit")),
    db: AsyncSession = Depends(get_db),
) -> CorrelationRunResponse:
    """Manually trigger correlation for a detection."""
    result = await _engine.correlate_detection(detection_id, db)

    return CorrelationRunResponse(
        detection_id=result.detection_id,
        chain_id=result.chain_id,
        match_count=len(result.matches),
        created_new_chain=result.created_new_chain,
    )
