"""Velocity leadership dashboard router.

Provides endpoints for the executive leadership view of engineering
velocity metrics, including DORA metrics, team comparisons, and
shipping cadence data.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Literal

import redis.asyncio as aioredis
import structlog
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_db, get_valkey, require_permission
from app.services.velocity_service import (
    get_leadership_summary,
    get_shipping_cadence,
    get_team_comparison,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/velocity", tags=["velocity"])

_CACHE_TTL = 300  # 5 minutes


# ── Pydantic models ───────────────────────────────────────────────────────────


class MetricWithTrendResponse(BaseModel):
    """A metric value with trend comparison to previous period."""

    value: float
    previous_value: float
    trend_pct: float
    classification: str


class LeadershipSummaryResponse(BaseModel):
    """Executive summary of DORA + engineering metrics."""

    deployment_frequency: MetricWithTrendResponse
    lead_time: MetricWithTrendResponse
    change_failure_rate: MetricWithTrendResponse
    mttr: MetricWithTrendResponse
    pr_throughput: MetricWithTrendResponse
    active_contributors: MetricWithTrendResponse
    period_days: int
    cached_at: datetime | None = None


class TeamMetricsResponse(BaseModel):
    """Per-team breakdown of a velocity metric."""

    team: str
    value: float
    classification: str


class TeamComparisonResponse(BaseModel):
    """Response for team comparison endpoint."""

    items: list[TeamMetricsResponse]
    metric: str
    period_days: int
    cached_at: datetime | None = None


class CadenceDayResponse(BaseModel):
    """Daily activity counts for shipping cadence heatmap."""

    date: str
    deployments: int
    merges: int
    reviews: int


class ShippingCadenceResponse(BaseModel):
    """Response for shipping cadence endpoint."""

    items: list[CadenceDayResponse]
    period_days: int
    cached_at: datetime | None = None


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/leadership-summary", response_model=LeadershipSummaryResponse)
async def leadership_summary(
    period: int = Query(default=30, ge=7, le=180),
    current_user: AuthenticatedUser = Depends(require_permission("velocity", "view")),
    db: AsyncSession = Depends(get_db),
    valkey: aioredis.Redis = Depends(get_valkey),
) -> LeadershipSummaryResponse:
    """Return DORA metrics + trends for executive leadership view.

    Computes deployment frequency, lead time, change failure rate, MTTR,
    PR throughput, and active contributors with trend comparison to the
    previous equivalent period.
    """
    scoped_orgs = current_user.scoped_orgs or []
    org_key = ",".join(sorted(scoped_orgs)) if scoped_orgs else "all"
    cache_key = f"vel:v1:leadership:{org_key}:{period}"

    cached_raw = await valkey.get(cache_key)
    if cached_raw:
        try:
            data = json.loads(cached_raw)
            return LeadershipSummaryResponse.model_validate(data)
        except Exception:
            logger.warning("velocity.cache_parse_error", key=cache_key)

    summary = await get_leadership_summary(
        db,
        scoped_orgs=scoped_orgs if scoped_orgs else None,
        period=period,
    )

    response = LeadershipSummaryResponse(
        deployment_frequency=MetricWithTrendResponse(
            value=summary.deployment_frequency.value,
            previous_value=summary.deployment_frequency.previous_value,
            trend_pct=summary.deployment_frequency.trend_pct,
            classification=summary.deployment_frequency.classification,
        ),
        lead_time=MetricWithTrendResponse(
            value=summary.lead_time.value,
            previous_value=summary.lead_time.previous_value,
            trend_pct=summary.lead_time.trend_pct,
            classification=summary.lead_time.classification,
        ),
        change_failure_rate=MetricWithTrendResponse(
            value=summary.change_failure_rate.value,
            previous_value=summary.change_failure_rate.previous_value,
            trend_pct=summary.change_failure_rate.trend_pct,
            classification=summary.change_failure_rate.classification,
        ),
        mttr=MetricWithTrendResponse(
            value=summary.mttr.value,
            previous_value=summary.mttr.previous_value,
            trend_pct=summary.mttr.trend_pct,
            classification=summary.mttr.classification,
        ),
        pr_throughput=MetricWithTrendResponse(
            value=summary.pr_throughput.value,
            previous_value=summary.pr_throughput.previous_value,
            trend_pct=summary.pr_throughput.trend_pct,
            classification=summary.pr_throughput.classification,
        ),
        active_contributors=MetricWithTrendResponse(
            value=summary.active_contributors.value,
            previous_value=summary.active_contributors.previous_value,
            trend_pct=summary.active_contributors.trend_pct,
            classification=summary.active_contributors.classification,
        ),
        period_days=summary.period_days,
        cached_at=datetime.now(UTC),
    )

    try:
        await valkey.setex(
            cache_key,
            _CACHE_TTL,
            json.dumps(response.model_dump(mode="json")),
        )
    except Exception:
        logger.warning("velocity.cache_write_error", key=cache_key)

    return response


@router.get("/team-comparison", response_model=TeamComparisonResponse)
async def team_comparison(
    period: int = Query(default=30, ge=7, le=180),
    metric: Literal["deploy_freq", "lead_time", "cfr", "mttr"] = Query(default="deploy_freq"),
    current_user: AuthenticatedUser = Depends(require_permission("velocity", "view")),
    db: AsyncSession = Depends(get_db),
    valkey: aioredis.Redis = Depends(get_valkey),
) -> TeamComparisonResponse:
    """Return per-team/org breakdown of a velocity metric.

    Compares teams/organizations on deployment frequency, lead time,
    change failure rate, or mean time to recovery.
    """
    scoped_orgs = current_user.scoped_orgs or []
    org_key = ",".join(sorted(scoped_orgs)) if scoped_orgs else "all"
    cache_key = f"vel:v1:teams:{org_key}:{period}:{metric}"

    cached_raw = await valkey.get(cache_key)
    if cached_raw:
        try:
            data = json.loads(cached_raw)
            return TeamComparisonResponse.model_validate(data)
        except Exception:
            logger.warning("velocity.cache_parse_error", key=cache_key)

    teams = await get_team_comparison(
        db,
        scoped_orgs=scoped_orgs if scoped_orgs else None,
        period=period,
        metric=metric,
    )

    response = TeamComparisonResponse(
        items=[
            TeamMetricsResponse(
                team=t.team,
                value=t.value,
                classification=t.classification,
            )
            for t in teams
        ],
        metric=metric,
        period_days=period,
        cached_at=datetime.now(UTC),
    )

    try:
        await valkey.setex(
            cache_key,
            _CACHE_TTL,
            json.dumps(response.model_dump(mode="json")),
        )
    except Exception:
        logger.warning("velocity.cache_write_error", key=cache_key)

    return response


@router.get("/shipping-cadence", response_model=ShippingCadenceResponse)
async def shipping_cadence(
    period: int = Query(default=90, ge=7, le=365),
    current_user: AuthenticatedUser = Depends(require_permission("velocity", "view")),
    db: AsyncSession = Depends(get_db),
    valkey: aioredis.Redis = Depends(get_valkey),
) -> ShippingCadenceResponse:
    """Return daily activity counts for shipping cadence heatmap.

    Returns deployment, merge, and review counts for each day in the
    selected period, formatted for a calendar heatmap visualization.
    """
    scoped_orgs = current_user.scoped_orgs or []
    org_key = ",".join(sorted(scoped_orgs)) if scoped_orgs else "all"
    cache_key = f"vel:v1:cadence:{org_key}:{period}"

    cached_raw = await valkey.get(cache_key)
    if cached_raw:
        try:
            data = json.loads(cached_raw)
            return ShippingCadenceResponse.model_validate(data)
        except Exception:
            logger.warning("velocity.cache_parse_error", key=cache_key)

    cadence = await get_shipping_cadence(
        db,
        scoped_orgs=scoped_orgs if scoped_orgs else None,
        period=period,
    )

    response = ShippingCadenceResponse(
        items=[
            CadenceDayResponse(
                date=c.date,
                deployments=c.deployments,
                merges=c.merges,
                reviews=c.reviews,
            )
            for c in cadence
        ],
        period_days=period,
        cached_at=datetime.now(UTC),
    )

    try:
        await valkey.setex(
            cache_key,
            _CACHE_TTL,
            json.dumps(response.model_dump(mode="json")),
        )
    except Exception:
        logger.warning("velocity.cache_write_error", key=cache_key)

    return response
