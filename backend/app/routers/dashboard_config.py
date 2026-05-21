"""Custom dashboard configuration router.

Endpoints for managing per-user dashboard layouts with persona-based
onboarding and a browsable widget catalog.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_current_user, get_db, verify_csrf
from app.models.dashboard_config import UserDashboardConfig
from app.schemas.dashboard_config import (
    DashboardConfigResponse,
    DashboardConfigUpdate,
    PersonaInfo,
    PersonaListResponse,
    WidgetCatalogResponse,
    WidgetInfo,
    WidgetLayoutItem,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# ─── Widget catalog (static) ─────────────────────────────────────────────────

WIDGET_CATALOG: list[WidgetInfo] = [
    WidgetInfo(
        id="unified-security",
        title="Unified Security",
        description="Cross-signal security posture with alert trends and severity breakdowns.",
        category="security",
        default_w=12,
        default_h=4,
    ),
    WidgetInfo(
        id="security-overview",
        title="Security Overview",
        description="Active detections by severity with direct drill-down into threats.",
        category="security",
        default_w=6,
        default_h=3,
    ),
    WidgetInfo(
        id="detection-summary",
        title="Detection Summary",
        description="Recent detection counts with severity emphasis for fast triage.",
        category="security",
        default_w=6,
        default_h=3,
    ),
    WidgetInfo(
        id="alert-trends",
        title="Alert Trends",
        description="Security alert volume over time grouped by severity.",
        category="security",
        default_w=6,
        default_h=3,
    ),
    WidgetInfo(
        id="mttr-chart",
        title="MTTR Chart",
        description="Mean time to resolve security detections by severity band.",
        category="security",
        default_w=6,
        default_h=3,
    ),
    WidgetInfo(
        id="posture-score",
        title="Posture Score",
        description="Overall security posture score across monitored organizations.",
        category="security",
        default_w=4,
        default_h=3,
    ),
    WidgetInfo(
        id="compliance-status",
        title="Compliance Status",
        description="Compliance framework adherence summary with pass/fail breakdown.",
        category="security",
        default_w=4,
        default_h=3,
    ),
    WidgetInfo(
        id="sync-health",
        title="Sync Health",
        description="Current sync status, monitoring coverage, and next scheduled refresh.",
        category="operations",
        default_w=4,
        default_h=3,
    ),
    WidgetInfo(
        id="ingestion-status",
        title="Ingestion Status",
        description=(
            "Real-time ingestion pipeline health: events/sec, last event time, and worker status."
        ),
        category="operations",
        default_w=4,
        default_h=3,
    ),
    WidgetInfo(
        id="workflow-health",
        title="Workflow Health",
        description="GitHub Actions workflow success rates and health indicators.",
        category="operations",
        default_w=6,
        default_h=3,
    ),
    WidgetInfo(
        id="failure-rates",
        title="Failure Rates",
        description="CI/CD pipeline failure rates by repository and workflow.",
        category="operations",
        default_w=6,
        default_h=3,
    ),
    WidgetInfo(
        id="event-volume",
        title="Event Volume",
        description="24-hour event activity trend to spot ingestion shifts or spikes.",
        category="activity",
        default_w=6,
        default_h=3,
    ),
    WidgetInfo(
        id="top-actors",
        title="Top Actors",
        description="Most active humans in recent audit events for investigation context.",
        category="activity",
        default_w=4,
        default_h=3,
    ),
    WidgetInfo(
        id="recent-events",
        title="Recent Events",
        description="Stream of the latest audit events with action type and actor details.",
        category="activity",
        default_w=12,
        default_h=4,
    ),
    WidgetInfo(
        id="velocity-metrics",
        title="Velocity Metrics",
        description="Development velocity tracking including PR throughput and cycle time.",
        category="activity",
        default_w=6,
        default_h=3,
    ),
    WidgetInfo(
        id="team-health",
        title="Team Health",
        description="Aggregated team health indicators across repositories and workflows.",
        category="activity",
        default_w=6,
        default_h=3,
    ),
    WidgetInfo(
        id="copilot-usage",
        title="Copilot Usage",
        description="Adoption snapshot showing overall usage and power-user concentration.",
        category="copilot",
        default_w=4,
        default_h=3,
    ),
]

WIDGET_CATALOG_BY_ID = {w.id: w for w in WIDGET_CATALOG}


# ─── Persona definitions ─────────────────────────────────────────────────────


def _layout_from_ids(widget_ids: list[str]) -> list[WidgetLayoutItem]:
    """Build a grid layout from a list of widget IDs using their default sizes."""
    items: list[WidgetLayoutItem] = []
    x, y = 0, 0
    for wid in widget_ids:
        widget = WIDGET_CATALOG_BY_ID.get(wid)
        if not widget:
            continue
        w = widget.default_w
        h = widget.default_h
        if x + w > 12:
            x = 0
            y += h
        items.append(WidgetLayoutItem(widget_id=wid, x=x, y=y, w=w, h=h))
        x += w
        if x >= 12:
            x = 0
            y += h
    return items


PERSONAS: list[PersonaInfo] = [
    PersonaInfo(
        id="security-analyst",
        label="Security Analyst",
        description="Focus on threat detection, alert triage, and security posture.",
        default_layout=_layout_from_ids(
            [
                "unified-security",
                "detection-summary",
                "alert-trends",
                "mttr-chart",
                "security-overview",
                "posture-score",
                "top-actors",
                "recent-events",
            ]
        ),
    ),
    PersonaInfo(
        id="engineering-manager",
        label="Engineering Manager",
        description="Track team velocity, development health, and Copilot adoption.",
        default_layout=_layout_from_ids(
            [
                "velocity-metrics",
                "team-health",
                "copilot-usage",
                "event-volume",
                "workflow-health",
                "failure-rates",
            ]
        ),
    ),
    PersonaInfo(
        id="platform-engineer",
        label="Platform Engineer",
        description="Monitor workflows, sync health, and operational reliability.",
        default_layout=_layout_from_ids(
            [
                "sync-health",
                "ingestion-status",
                "workflow-health",
                "failure-rates",
                "event-volume",
                "top-actors",
                "copilot-usage",
                "recent-events",
            ]
        ),
    ),
    PersonaInfo(
        id="executive",
        label="Executive",
        description="High-level security posture, compliance status, and key metrics.",
        default_layout=_layout_from_ids(
            [
                "posture-score",
                "compliance-status",
                "unified-security",
                "velocity-metrics",
                "copilot-usage",
                "team-health",
            ]
        ),
    ),
]

PERSONAS_BY_ID = {p.id: p for p in PERSONAS}


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/config", response_model=DashboardConfigResponse)
async def get_dashboard_config(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DashboardConfigResponse:
    """Return the current user's saved dashboard configuration.

    If no config exists yet, a default config is created using the
    security-analyst persona layout so the dashboard is never empty.
    """
    stmt = select(UserDashboardConfig).where(
        UserDashboardConfig.user_id == current_user.github_login,
    )
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()

    if config is None:
        default_persona = PERSONAS_BY_ID["security-analyst"]
        now = datetime.now(UTC)
        config = UserDashboardConfig(
            user_id=current_user.github_login,
            layout=[item.model_dump() for item in default_persona.default_layout],
            persona="security-analyst",
            created_at=now,
            updated_at=now,
        )
        db.add(config)
        await db.flush()
        logger.info(
            "dashboard_config.created_default",
            user=current_user.github_login,
        )

    return DashboardConfigResponse(
        id=str(config.id),
        user_id=config.user_id,
        layout=config.layout,
        persona=config.persona,
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


@router.put(
    "/config",
    response_model=DashboardConfigResponse,
    dependencies=[Depends(verify_csrf)],
)
async def update_dashboard_config(
    body: DashboardConfigUpdate,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DashboardConfigResponse:
    """Save or update the current user's dashboard layout and persona."""
    stmt = select(UserDashboardConfig).where(
        UserDashboardConfig.user_id == current_user.github_login,
    )
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()

    serialized_layout: list[dict[str, Any]] = [item.model_dump() for item in body.layout]
    now = datetime.now(UTC)

    if config is None:
        config = UserDashboardConfig(
            user_id=current_user.github_login,
            layout=serialized_layout,
            persona=body.persona,
            created_at=now,
            updated_at=now,
        )
        db.add(config)
    else:
        config.layout = serialized_layout
        config.persona = body.persona
        config.updated_at = now

    await db.flush()

    logger.info(
        "dashboard_config.updated",
        user=current_user.github_login,
        widget_count=len(body.layout),
        persona=body.persona,
    )

    return DashboardConfigResponse(
        id=str(config.id),
        user_id=config.user_id,
        layout=config.layout,
        persona=config.persona,
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


@router.get("/widgets", response_model=WidgetCatalogResponse)
async def list_widgets(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> WidgetCatalogResponse:
    """Return the full widget catalog available for dashboard configuration."""
    return WidgetCatalogResponse(widgets=WIDGET_CATALOG)


@router.get("/personas", response_model=PersonaListResponse)
async def list_personas(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> PersonaListResponse:
    """Return available personas with their recommended default layouts."""
    return PersonaListResponse(personas=PERSONAS)
