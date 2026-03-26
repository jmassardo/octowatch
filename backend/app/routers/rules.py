"""Rules router: full CRUD for detection rules + version management."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_db, get_valkey, require_role
from app.schemas.detection import (
    RuleCreate,
    RuleListResponse,
    RuleResponse,
    RuleStatusUpdate,
    RuleVersionResponse,
    SuppressionCreate,
    SuppressionResponse,
)
from app.services import rule_service
from app.services.rule_service import invalidate_rule_cache

router = APIRouter(prefix="/rules", tags=["rules"])


@router.get("", response_model=RuleListResponse)
async def list_rules(
    enabled: bool | None = None,
    logic_type: str | None = None,
    rule_status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    current_user: AuthenticatedUser = Depends(
        require_role(["analyst", "report_admin", "rule_author", "sys_admin"])
    ),
    db: AsyncSession = Depends(get_db),
) -> RuleListResponse:
    """List detection rules with optional filtering."""
    rules = await rule_service.list_rules(
        db,
        enabled=enabled,
        logic_type=logic_type,
        status=rule_status,
        limit=limit,
        offset=offset,
    )
    return RuleListResponse(
        items=[RuleResponse.model_validate(r) for r in rules],
        total=len(rules),
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=RuleResponse, status_code=status.HTTP_201_CREATED)
async def create_rule(
    payload: RuleCreate,
    current_user: AuthenticatedUser = Depends(require_role(["rule_author", "sys_admin"])),
    db: AsyncSession = Depends(get_db),
    valkey: Redis = Depends(get_valkey),
) -> RuleResponse:
    """Create a new detection rule."""
    # Check slug uniqueness
    existing = await rule_service.get_rule_by_slug(db, payload.slug)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Rule with slug '{payload.slug}' already exists",
        )
    rule = await rule_service.create_rule(db, payload=payload, created_by=current_user.github_login)
    return RuleResponse.model_validate(rule)


@router.get("/{rule_id}", response_model=RuleResponse)
async def get_rule(
    rule_id: int,
    current_user: AuthenticatedUser = Depends(
        require_role(["analyst", "report_admin", "rule_author", "sys_admin"])
    ),
    db: AsyncSession = Depends(get_db),
) -> RuleResponse:
    """Get a single rule by ID."""
    rule = await rule_service.get_rule_by_id(db, rule_id)
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    return RuleResponse.model_validate(rule)


@router.put("/{rule_id}", response_model=RuleResponse)
async def update_rule(
    rule_id: int,
    payload: RuleCreate,
    current_user: AuthenticatedUser = Depends(require_role(["rule_author", "sys_admin"])),
    db: AsyncSession = Depends(get_db),
    valkey: Redis = Depends(get_valkey),
) -> RuleResponse:
    """Update a rule (creates a new version if logic changes)."""
    rule = await rule_service.get_rule_by_id(db, rule_id)
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    updated = await rule_service.update_rule(
        db, rule=rule, payload=payload, updated_by=current_user.github_login
    )
    await invalidate_rule_cache(valkey, rule_id)
    return RuleResponse.model_validate(updated)


@router.patch("/{rule_id}/status", response_model=RuleResponse)
async def update_rule_status(
    rule_id: int,
    payload: RuleStatusUpdate,
    current_user: AuthenticatedUser = Depends(require_role(["rule_author", "sys_admin"])),
    db: AsyncSession = Depends(get_db),
    valkey: Redis = Depends(get_valkey),
) -> RuleResponse:
    """Update rule lifecycle status: draft → active → deprecated."""
    rule = await rule_service.get_rule_by_id(db, rule_id)
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    updated = await rule_service.update_rule_status(
        db, rule=rule, payload=payload, updated_by=current_user.github_login
    )
    await invalidate_rule_cache(valkey, rule_id)
    return RuleResponse.model_validate(updated)


@router.delete("/{rule_id}")
async def delete_rule(
    rule_id: int,
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
    valkey: Redis = Depends(get_valkey),
) -> Response:
    """Soft-delete a rule (marks as deprecated + disabled)."""
    rule = await rule_service.get_rule_by_id(db, rule_id)
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    await rule_service.delete_rule(db, rule=rule, deleted_by=current_user.github_login)
    await invalidate_rule_cache(valkey, rule_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{rule_id}/versions", response_model=list[RuleVersionResponse])
async def get_rule_versions(
    rule_id: int,
    limit: int = 20,
    current_user: AuthenticatedUser = Depends(
        require_role(["analyst", "report_admin", "rule_author", "sys_admin"])
    ),
    db: AsyncSession = Depends(get_db),
) -> list[RuleVersionResponse]:
    """List version history for a rule."""
    rule = await rule_service.get_rule_by_id(db, rule_id)
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    versions = await rule_service.get_rule_versions(db, rule_id=rule_id, limit=limit)
    return [RuleVersionResponse.model_validate(v) for v in versions]


# ─── Suppression sub-resource ─────────────────────────────────────────────────


@router.get("/{rule_id}/suppressions", response_model=list[SuppressionResponse])
async def list_suppressions(
    rule_id: int,
    current_user: AuthenticatedUser = Depends(
        require_role(["analyst", "rule_author", "sys_admin"])
    ),
    db: AsyncSession = Depends(get_db),
) -> list[SuppressionResponse]:
    """List all suppressions for a rule."""
    from sqlalchemy import select

    from app.models.detection import DetectionSuppression

    result = await db.execute(
        select(DetectionSuppression)
        .where(DetectionSuppression.rule_id == rule_id)
        .order_by(DetectionSuppression.created_at.desc())
    )
    suppressions = result.scalars().all()
    return [SuppressionResponse.model_validate(s) for s in suppressions]


@router.post(
    "/{rule_id}/suppressions",
    response_model=SuppressionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_suppression(
    rule_id: int,
    payload: SuppressionCreate,
    current_user: AuthenticatedUser = Depends(require_role(["rule_author", "sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> SuppressionResponse:
    """Create a suppression for a rule."""
    # Verify rule exists
    rule = await rule_service.get_rule_by_id(db, rule_id)
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")

    from app.models.detection import DetectionSuppression

    suppression = DetectionSuppression(
        rule_id=rule_id,
        suppress_actor=payload.suppress_actor,
        suppress_org=payload.suppress_org,
        suppress_repo=payload.suppress_repo,
        expires_at=payload.expires_at,
        active=True,
        created_by=current_user.github_login,
    )
    db.add(suppression)
    await db.flush()
    return SuppressionResponse.model_validate(suppression)


@router.delete("/{rule_id}/suppressions/{suppression_id}")
async def delete_suppression(
    rule_id: int,
    suppression_id: int,
    current_user: AuthenticatedUser = Depends(require_role(["rule_author", "sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Delete (deactivate) a suppression."""
    from sqlalchemy import select

    from app.models.detection import DetectionSuppression

    result = await db.execute(
        select(DetectionSuppression).where(
            DetectionSuppression.id == suppression_id,
            DetectionSuppression.rule_id == rule_id,
        )
    )
    suppression = result.scalar_one_or_none()
    if not suppression:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suppression not found")
    suppression.active = False
    await db.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
