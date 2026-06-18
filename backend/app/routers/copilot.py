"""Copilot metrics router — endpoints for the frontend Copilot panes.

Provides overview, adoption, models, anomalies, teams, blockers,
policy changes, and ROI report data.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_db, require_permission
from app.services import copilot_metrics_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/copilot", tags=["copilot"])


@router.get("/overview", response_model=dict[str, Any])
async def copilot_overview(
    org: str | None = Query(None, description="Filter to a specific org"),
    current_user: AuthenticatedUser = Depends(require_permission("copilot", "view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Overview pane: acceptance rates, language breakdown, user counts."""
    try:
        return await copilot_metrics_service.get_copilot_overview(db, org=org)
    except Exception:
        logger.error("copilot.overview_failed")
        return JSONResponse(  # type: ignore[return-value]
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"},
        )


@router.get("/adoption", response_model=dict[str, Any])
async def copilot_adoption(
    org: str | None = Query(None, description="Filter to a specific org"),
    current_user: AuthenticatedUser = Depends(require_permission("copilot", "view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Adoption pane: user tiers, feature adoption rates, per-user data."""
    try:
        return await copilot_metrics_service.get_copilot_adoption(db, org=org)
    except Exception:
        logger.error("copilot.adoption_failed")
        return JSONResponse(  # type: ignore[return-value]
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"},
        )


@router.get("/models", response_model=dict[str, Any])
async def copilot_models(
    org: str | None = Query(None, description="Filter to a specific org"),
    current_user: AuthenticatedUser = Depends(require_permission("copilot", "view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Models pane: model usage, feature counts, editors."""
    try:
        return await copilot_metrics_service.get_copilot_models(db, org=org)
    except Exception:
        logger.error("copilot.models_failed")
        return JSONResponse(  # type: ignore[return-value]
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"},
        )


@router.get("/model-users", response_model=dict[str, Any])
async def copilot_model_users(
    org: str | None = Query(None, description="Filter to a specific org"),
    current_user: AuthenticatedUser = Depends(require_permission("copilot", "view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Per-user Copilot usage breakdown by feature category (28 days)."""
    try:
        return await copilot_metrics_service.get_copilot_model_users(db, org=org)
    except Exception:
        logger.error("copilot.model_users_failed")
        return JSONResponse(  # type: ignore[return-value]
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"},
        )


@router.get("/anomalies", response_model=dict[str, Any])
async def copilot_anomalies(
    org: str | None = Query(None, description="Filter to a specific org"),
    current_user: AuthenticatedUser = Depends(require_permission("copilot", "view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Anomalies pane: detected metric deviations."""
    try:
        return await copilot_metrics_service.get_copilot_anomalies(db, org=org)
    except Exception:
        logger.error("copilot.anomalies_failed")
        return JSONResponse(  # type: ignore[return-value]
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"},
        )


@router.get("/teams", response_model=dict[str, Any])
async def copilot_teams(
    org: str | None = Query(None, description="Filter to a specific org"),
    current_user: AuthenticatedUser = Depends(require_permission("copilot", "view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Team-level Copilot adoption breakdown."""
    try:
        return await copilot_metrics_service.get_copilot_teams(db, org=org)
    except Exception:
        logger.error("copilot.teams_failed")
        return JSONResponse(  # type: ignore[return-value]
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"},
        )


@router.get("/blockers", response_model=dict[str, Any])
async def copilot_blockers(
    org: str | None = Query(None, description="Filter to a specific org"),
    current_user: AuthenticatedUser = Depends(require_permission("copilot", "view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Adoption blockers analysis with recommendations."""
    try:
        return await copilot_metrics_service.get_copilot_blockers(db, org=org)
    except Exception:
        logger.error("copilot.blockers_failed")
        return JSONResponse(  # type: ignore[return-value]
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"},
        )


@router.get("/policy-changes", response_model=dict[str, Any])
async def copilot_policy_changes(
    org: str | None = Query(None, description="Filter to a specific org"),
    current_user: AuthenticatedUser = Depends(require_permission("copilot", "view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Copilot policy change timeline from audit events."""
    try:
        return await copilot_metrics_service.get_copilot_policy_changes(db, org=org)
    except Exception:
        logger.error("copilot.policy_changes_failed")
        return JSONResponse(  # type: ignore[return-value]
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"},
        )


@router.get("/roi", response_model=dict[str, Any])
async def copilot_roi(
    org: str | None = Query(None, description="Filter to a specific org"),
    current_user: AuthenticatedUser = Depends(require_permission("copilot", "view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Copilot ROI and cost optimization report."""
    try:
        return await copilot_metrics_service.get_copilot_roi(db, org=org)
    except Exception:
        logger.error("copilot.roi_failed")
        return JSONResponse(  # type: ignore[return-value]
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"},
        )


@router.get("/adoption-thresholds", response_model=dict[str, Any])
async def copilot_adoption_thresholds(
    current_user: AuthenticatedUser = Depends(require_permission("copilot", "view")),
) -> dict[str, Any]:
    """Return current adoption tier threshold defaults."""
    return {
        "power": 20,
        "regular": 10,
        "minimal": 1,
    }


@router.get("/billing-overview", response_model=dict[str, Any])
async def copilot_billing_overview(
    org: str | None = Query(None, description="Filter to a specific org"),
    current_user: AuthenticatedUser = Depends(require_permission("copilot", "view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Pool info, enterprise budget, spend forecast, pool drawdown."""
    try:
        return await copilot_metrics_service.get_copilot_billing_overview(db, org=org)
    except Exception:
        logger.error("copilot.billing_overview_failed")
        return JSONResponse(  # type: ignore[return-value]
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"},
        )


@router.get("/user-budgets", response_model=dict[str, Any])
async def copilot_user_budgets(
    org: str | None = Query(None, description="Filter to a specific org"),
    current_user: AuthenticatedUser = Depends(require_permission("copilot", "view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Per-user budget list with consumed/budget/status/utilization %."""
    try:
        return await copilot_metrics_service.get_copilot_user_budgets(db, org=org)
    except Exception:
        logger.error("copilot.user_budgets_failed")
        return JSONResponse(  # type: ignore[return-value]
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"},
        )


@router.get("/billing-trends", response_model=dict[str, Any])
async def copilot_billing_trends(
    org: str | None = Query(None, description="Filter to a specific org"),
    current_user: AuthenticatedUser = Depends(require_permission("copilot", "view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Daily credit consumption trends over last 30 days."""
    try:
        return await copilot_metrics_service.get_copilot_billing_trends(db, org=org)
    except Exception:
        logger.error("copilot.billing_trends_failed")
        return JSONResponse(  # type: ignore[return-value]
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"},
        )


@router.get("/activity", response_model=dict[str, Any])
async def copilot_activity(
    org: str | None = Query(None, description="Filter to a specific org"),
    current_user: AuthenticatedUser = Depends(require_permission("copilot", "view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Activity pane: DAU/WAU, completions, acceptance rate, chat per user, requests per mode."""
    try:
        return await copilot_metrics_service.get_copilot_activity(db, org=org)
    except Exception:
        logger.error("copilot.activity_failed")
        return JSONResponse(  # type: ignore[return-value]
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"},
        )


@router.get("/chat-metrics", response_model=dict[str, Any])
async def copilot_chat_metrics(
    org: str | None = Query(None, description="Filter to a specific org"),
    current_user: AuthenticatedUser = Depends(require_permission("copilot", "view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Chat metrics pane: interactions, code actions, active users, action rate."""
    try:
        return await copilot_metrics_service.get_copilot_chat_metrics(db, org=org)
    except Exception:
        logger.error("copilot.chat_metrics_failed")
        return JSONResponse(  # type: ignore[return-value]
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"},
        )


@router.get("/language-breakdown", response_model=dict[str, Any])
async def copilot_language_breakdown(
    org: str | None = Query(None, description="Filter to a specific org"),
    current_user: AuthenticatedUser = Depends(require_permission("copilot", "view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Language breakdown: per-day, distribution, models, editors, top languages."""
    try:
        return await copilot_metrics_service.get_copilot_language_breakdown(db, org=org)
    except Exception:
        logger.error("copilot.language_breakdown_failed")
        return JSONResponse(  # type: ignore[return-value]
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"},
        )


@router.get("/pr-metrics", response_model=dict[str, Any])
async def copilot_pr_metrics(
    org: str | None = Query(None, description="Filter to a specific org"),
    current_user: AuthenticatedUser = Depends(require_permission("copilot", "view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """PR metrics pane: activity, contributions, review suggestions."""
    try:
        return await copilot_metrics_service.get_copilot_pr_metrics(db, org=org)
    except Exception:
        logger.error("copilot.pr_metrics_failed")
        return JSONResponse(  # type: ignore[return-value]
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"},
        )


@router.get("/agent-activity", response_model=dict[str, Any])
async def copilot_agent_activity(
    org: str | None = Query(None, description="Filter to a specific org"),
    current_user: AuthenticatedUser = Depends(require_permission("copilot", "view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Agent activity pane: daily lines, lines by mode/model/language."""
    try:
        return await copilot_metrics_service.get_copilot_agent_activity(db, org=org)
    except Exception:
        logger.error("copilot.agent_activity_failed")
        return JSONResponse(  # type: ignore[return-value]
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"},
        )
