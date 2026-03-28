"""Rules router: full CRUD for detection rules + version management."""

from __future__ import annotations

from typing import Any

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
    ValidateConfigRequest,
    ValidateConfigResponse,
)
from app.services import rule_service
from app.services.detection_service import _SAFE_DISTINCT_COLUMNS
from app.services.rule_service import invalidate_rule_cache

router = APIRouter(prefix="/rules", tags=["rules"])

# Allowed values for aggregation_key
_VALID_AGGREGATION_KEYS: frozenset[str] = frozenset({"actor", "repo", "org"})

# Allowed values for distinct_count_field
_VALID_DISTINCT_FIELDS: frozenset[str] = frozenset(
    {"actor", "org", "repo", "source_ip", "user_agent", "geo_country_code", "action"}
)

# Allowed operators for field_conditions
_VALID_FIELD_OPERATORS: frozenset[str] = frozenset(
    {
        "eq",
        "ne",
        "gt",
        "gte",
        "lt",
        "lte",
        "in",
        "not_in",
        "contains",
        "not_contains",
        "exists",
        "not_exists",
        "matches_glob",
        "scope_contains",
    }
)


def validate_logic_config(
    logic_type: str,
    config: dict[str, Any],
) -> tuple[list[str], list[str]]:
    """Validate a logic_config dict for the given logic_type.

    Returns a tuple of (errors, warnings).
    """
    errors: list[str] = []
    warnings: list[str] = []

    # ── Common validation: action_filters ──────────────────────────────────
    action_filters = config.get("action_filters")
    if action_filters is not None:
        if not isinstance(action_filters, list):
            errors.append("action_filters must be a list of strings.")
        elif not all(isinstance(a, str) for a in action_filters):
            errors.append("Every element in action_filters must be a string.")

    # ── Common validation: field_conditions ────────────────────────────────
    field_conditions = config.get("field_conditions")
    if field_conditions is not None:
        if not isinstance(field_conditions, list):
            errors.append("field_conditions must be a list of objects.")
        else:
            for idx, cond in enumerate(field_conditions):
                if not isinstance(cond, dict):
                    errors.append(f"field_conditions[{idx}] must be an object.")
                    continue
                for required_key in ("field", "operator", "value"):
                    if required_key not in cond:
                        errors.append(
                            f"field_conditions[{idx}] is missing required key '{required_key}'."
                        )
                op = cond.get("operator")
                if op is not None and op not in _VALID_FIELD_OPERATORS:
                    errors.append(
                        f"field_conditions[{idx}].operator '{op}' is not a valid operator."
                    )

    # ── Common validation: confidence ──────────────────────────────────────
    confidence = config.get("confidence")
    if confidence is not None:
        try:
            conf_val = float(confidence)
            if conf_val < 0 or conf_val > 1:
                errors.append("confidence must be a float between 0 and 1.")
        except (TypeError, ValueError):
            errors.append("confidence must be a float between 0 and 1.")

    # ── Type-specific validation ───────────────────────────────────────────
    if logic_type == "threshold":
        # threshold (required, int > 0)
        threshold = config.get("threshold")
        if threshold is None:
            errors.append("threshold is required for threshold rules.")
        elif not isinstance(threshold, int) or threshold <= 0:
            errors.append("threshold must be an integer greater than 0.")

        # time_window_minutes (required, int > 0)
        twm = config.get("time_window_minutes")
        if twm is None:
            errors.append("time_window_minutes is required for threshold rules.")
        elif not isinstance(twm, int) or twm <= 0:
            errors.append("time_window_minutes must be an integer greater than 0.")

        # aggregation_key (required, must be in allowed set)
        agg_key = config.get("aggregation_key")
        if agg_key is None:
            errors.append("aggregation_key is required for threshold rules.")
        elif agg_key not in _VALID_AGGREGATION_KEYS:
            errors.append(
                f"aggregation_key must be one of {sorted(_VALID_AGGREGATION_KEYS)}, "
                f"got '{agg_key}'."
            )

        # distinct_count_field (optional, must be in allowed set)
        dcf = config.get("distinct_count_field")
        if dcf is not None and dcf not in _VALID_DISTINCT_FIELDS:
            errors.append(
                f"distinct_count_field must be one of {sorted(_VALID_DISTINCT_FIELDS)}, "
                f"got '{dcf}'."
            )

    elif logic_type == "sequence":
        # sequence_steps (required, list of {action, min_count}, min 2 steps)
        steps = config.get("sequence_steps")
        if steps is None:
            errors.append("sequence_steps is required for sequence rules.")
        elif not isinstance(steps, list):
            errors.append("sequence_steps must be a list.")
        elif len(steps) < 2:
            errors.append("sequence_steps must contain at least 2 steps.")
        else:
            for idx, step in enumerate(steps):
                if not isinstance(step, dict):
                    errors.append(f"sequence_steps[{idx}] must be an object.")
                    continue
                if "action" not in step:
                    errors.append(f"sequence_steps[{idx}] is missing required key 'action'.")
                if "min_count" not in step:
                    errors.append(f"sequence_steps[{idx}] is missing required key 'min_count'.")
                elif not isinstance(step["min_count"], int) or step["min_count"] < 1:
                    errors.append(f"sequence_steps[{idx}].min_count must be an integer >= 1.")

        # aggregation_key (required)
        agg_key = config.get("aggregation_key")
        if agg_key is None:
            errors.append("aggregation_key is required for sequence rules.")
        elif agg_key not in _VALID_AGGREGATION_KEYS:
            errors.append(
                f"aggregation_key must be one of {sorted(_VALID_AGGREGATION_KEYS)}, "
                f"got '{agg_key}'."
            )

        # time_window_minutes (required, int > 0)
        twm = config.get("time_window_minutes")
        if twm is None:
            errors.append("time_window_minutes is required for sequence rules.")
        elif not isinstance(twm, int) or twm <= 0:
            errors.append("time_window_minutes must be an integer greater than 0.")

    elif logic_type == "statistical":
        # x_config with engine field (required)
        x_config = config.get("x_config")
        if x_config is None:
            errors.append("x_config is required for statistical rules.")
        elif not isinstance(x_config, dict):
            errors.append("x_config must be an object.")
        elif "engine" not in x_config:
            errors.append("x_config.engine is required for statistical rules.")

    # pattern type has no additional required fields beyond the common ones

    return errors, warnings


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
    # Validate distinct_count_field if present in logic_config (§1.7)
    if (distinct_field := payload.logic_config.get("distinct_count_field")) is not None:
        if distinct_field not in _SAFE_DISTINCT_COLUMNS:
            raise HTTPException(
                status_code=422,
                detail=f"distinct_count_field '{distinct_field}' is not a permitted column.",
            )

    # Check slug uniqueness
    existing = await rule_service.get_rule_by_slug(db, payload.slug)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Rule with slug '{payload.slug}' already exists",
        )
    rule = await rule_service.create_rule(db, payload=payload, created_by=current_user.github_login)
    return RuleResponse.model_validate(rule)


@router.post("/validate-config", response_model=ValidateConfigResponse)
async def validate_config(
    payload: ValidateConfigRequest,
    current_user: AuthenticatedUser = Depends(
        require_role(["analyst", "report_admin", "rule_author", "sys_admin"])
    ),
) -> ValidateConfigResponse:
    """Validate a logic_config structure for a given logic_type.

    Returns validation errors and warnings without persisting anything.
    """
    errs, warns = validate_logic_config(payload.logic_type, payload.logic_config)
    return ValidateConfigResponse(valid=len(errs) == 0, errors=errs, warnings=warns)


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
    # Validate distinct_count_field if present in logic_config (§1.7)
    if (distinct_field := payload.logic_config.get("distinct_count_field")) is not None:
        if distinct_field not in _SAFE_DISTINCT_COLUMNS:
            raise HTTPException(
                status_code=422,
                detail=f"distinct_count_field '{distinct_field}' is not a permitted column.",
            )

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
