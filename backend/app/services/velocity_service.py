"""Velocity leadership dashboard service.

Computes DORA metrics, team comparisons, and shipping cadence data
from the ``events`` hypertable.  All queries use the existing audit-event
schema — no new migrations required.

Action patterns used:
- ``workflow_run.*`` / ``workflows.completed_workflow_run`` — deployments
- ``pull_request.*`` — PR activity (merges, reviews)
- ``git.push`` / ``push`` — push events
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


# ── DORA Benchmark Classifications ────────────────────────────────────────────


class DoraTier(Enum):
    """DORA performance tier classification."""

    ELITE = "elite"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


def classify_deploy_frequency(deploys_per_day: float) -> DoraTier:
    """Classify deployment frequency using DORA benchmarks.

    Elite: multiple/day (>1), High: daily-weekly (>=1/7),
    Medium: weekly-monthly (>=1/30), Low: monthly+ (<1/30).
    """
    if deploys_per_day > 1:
        return DoraTier.ELITE
    if deploys_per_day >= 1 / 7:
        return DoraTier.HIGH
    if deploys_per_day >= 1 / 30:
        return DoraTier.MEDIUM
    return DoraTier.LOW


def classify_lead_time(hours: float) -> DoraTier:
    """Classify lead time for changes using DORA benchmarks.

    Elite: <1h, High: <1d (24h), Medium: <1w (168h), Low: >1w.
    """
    if hours < 1:
        return DoraTier.ELITE
    if hours < 24:
        return DoraTier.HIGH
    if hours < 168:
        return DoraTier.MEDIUM
    return DoraTier.LOW


def classify_change_failure_rate(rate_pct: float) -> DoraTier:
    """Classify change failure rate using DORA benchmarks.

    Elite: <5%, High: <10%, Medium: <15%, Low: >15%.
    """
    if rate_pct < 5:
        return DoraTier.ELITE
    if rate_pct < 10:
        return DoraTier.HIGH
    if rate_pct < 15:
        return DoraTier.MEDIUM
    return DoraTier.LOW


def classify_mttr(hours: float) -> DoraTier:
    """Classify mean time to recovery using DORA benchmarks.

    Elite: <1h, High: <1d (24h), Medium: <1w (168h), Low: >1w.
    """
    if hours < 1:
        return DoraTier.ELITE
    if hours < 24:
        return DoraTier.HIGH
    if hours < 168:
        return DoraTier.MEDIUM
    return DoraTier.LOW


# ── Data structures ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class MetricWithTrend:
    """A metric value with trend comparison to previous period."""

    value: float
    previous_value: float
    trend_pct: float
    classification: str


@dataclass(frozen=True)
class LeadershipSummary:
    """Executive summary of DORA + engineering metrics."""

    deployment_frequency: MetricWithTrend
    lead_time: MetricWithTrend
    change_failure_rate: MetricWithTrend
    mttr: MetricWithTrend
    pr_throughput: MetricWithTrend
    active_contributors: MetricWithTrend
    period_days: int


@dataclass(frozen=True)
class TeamMetrics:
    """Per-team breakdown of a velocity metric."""

    team: str
    value: float
    classification: str


@dataclass(frozen=True)
class CadenceDay:
    """Daily activity counts for shipping cadence heatmap."""

    date: str
    deployments: int
    merges: int
    reviews: int


# ── SQL Queries ───────────────────────────────────────────────────────────────

# Deployment counts (workflow successes) per period
_DEPLOY_COUNT_SQL = """
SELECT COUNT(*) AS deploy_count
FROM events
WHERE (
    (action LIKE 'workflow_run.%%' AND data->>'conclusion' = 'success')
    OR action = 'workflows.completed_workflow_run'
)
  AND created_at >= NOW() - MAKE_INTERVAL(days => :period_start)
  AND created_at < NOW() - MAKE_INTERVAL(days => :period_end)
"""

_DEPLOY_COUNT_ORG_SQL = """
SELECT COUNT(*) AS deploy_count
FROM events
WHERE (
    (action LIKE 'workflow_run.%%' AND data->>'conclusion' = 'success')
    OR action = 'workflows.completed_workflow_run'
)
  AND created_at >= NOW() - MAKE_INTERVAL(days => :period_start)
  AND created_at < NOW() - MAKE_INTERVAL(days => :period_end)
  AND org = ANY(:orgs)
"""

# Workflow failure count per period
_FAILURE_COUNT_SQL = """
SELECT COUNT(*) AS fail_count
FROM events
WHERE (
    action LIKE 'workflow_run.%%'
    OR action = 'workflows.completed_workflow_run'
)
  AND (data->>'conclusion' = 'failure' OR data->>'conclusion' = 'timed_out')
  AND created_at >= NOW() - MAKE_INTERVAL(days => :period_start)
  AND created_at < NOW() - MAKE_INTERVAL(days => :period_end)
"""

_FAILURE_COUNT_ORG_SQL = """
SELECT COUNT(*) AS fail_count
FROM events
WHERE (
    action LIKE 'workflow_run.%%'
    OR action = 'workflows.completed_workflow_run'
)
  AND (data->>'conclusion' = 'failure' OR data->>'conclusion' = 'timed_out')
  AND created_at >= NOW() - MAKE_INTERVAL(days => :period_start)
  AND created_at < NOW() - MAKE_INTERVAL(days => :period_end)
  AND org = ANY(:orgs)
"""

# Total workflow runs per period (for CFR denominator)
_TOTAL_RUNS_SQL = """
SELECT COUNT(*) AS total_runs
FROM events
WHERE (
    action LIKE 'workflow_run.%%'
    OR action = 'workflows.completed_workflow_run'
)
  AND data->>'conclusion' NOT IN ('cancelled', 'skipped')
  AND created_at >= NOW() - MAKE_INTERVAL(days => :period_start)
  AND created_at < NOW() - MAKE_INTERVAL(days => :period_end)
"""

_TOTAL_RUNS_ORG_SQL = """
SELECT COUNT(*) AS total_runs
FROM events
WHERE (
    action LIKE 'workflow_run.%%'
    OR action = 'workflows.completed_workflow_run'
)
  AND data->>'conclusion' NOT IN ('cancelled', 'skipped')
  AND created_at >= NOW() - MAKE_INTERVAL(days => :period_start)
  AND created_at < NOW() - MAKE_INTERVAL(days => :period_end)
  AND org = ANY(:orgs)
"""

# PR merged count per period
_PR_MERGED_SQL = """
SELECT COUNT(*) AS pr_merged
FROM events
WHERE action LIKE 'pull_request.%%'
  AND (action LIKE '%%merged%%' OR action LIKE '%%closed%%')
  AND created_at >= NOW() - MAKE_INTERVAL(days => :period_start)
  AND created_at < NOW() - MAKE_INTERVAL(days => :period_end)
"""

_PR_MERGED_ORG_SQL = """
SELECT COUNT(*) AS pr_merged
FROM events
WHERE action LIKE 'pull_request.%%'
  AND (action LIKE '%%merged%%' OR action LIKE '%%closed%%')
  AND created_at >= NOW() - MAKE_INTERVAL(days => :period_start)
  AND created_at < NOW() - MAKE_INTERVAL(days => :period_end)
  AND org = ANY(:orgs)
"""

# Active contributors (unique actors) per period
_CONTRIBUTORS_SQL = """
SELECT COUNT(DISTINCT actor) AS contributors
FROM events
WHERE action NOT IN ('api.request')
  AND actor IS NOT NULL
  AND actor_is_bot = false
  AND created_at >= NOW() - MAKE_INTERVAL(days => :period_start)
  AND created_at < NOW() - MAKE_INTERVAL(days => :period_end)
"""

_CONTRIBUTORS_ORG_SQL = """
SELECT COUNT(DISTINCT actor) AS contributors
FROM events
WHERE action NOT IN ('api.request')
  AND actor IS NOT NULL
  AND actor_is_bot = false
  AND created_at >= NOW() - MAKE_INTERVAL(days => :period_start)
  AND created_at < NOW() - MAKE_INTERVAL(days => :period_end)
  AND org = ANY(:orgs)
"""

# Team comparison: per-org metric aggregates
_TEAM_DEPLOY_FREQ_SQL = """
SELECT org, COUNT(*) AS deploy_count
FROM events
WHERE (
    (action LIKE 'workflow_run.%%' AND data->>'conclusion' = 'success')
    OR action = 'workflows.completed_workflow_run'
)
  AND created_at >= NOW() - MAKE_INTERVAL(days => :period_days)
  AND org IS NOT NULL
GROUP BY org
ORDER BY deploy_count DESC
"""

_TEAM_DEPLOY_FREQ_ORG_SQL = """
SELECT org, COUNT(*) AS deploy_count
FROM events
WHERE (
    (action LIKE 'workflow_run.%%' AND data->>'conclusion' = 'success')
    OR action = 'workflows.completed_workflow_run'
)
  AND created_at >= NOW() - MAKE_INTERVAL(days => :period_days)
  AND org = ANY(:orgs)
  AND org IS NOT NULL
GROUP BY org
ORDER BY deploy_count DESC
"""

_TEAM_CFR_SQL = """
SELECT
    org,
    COUNT(*) FILTER (
        WHERE data->>'conclusion' IN ('failure', 'timed_out')
    ) * 100.0 / NULLIF(COUNT(*), 0) AS cfr
FROM events
WHERE (
    action LIKE 'workflow_run.%%'
    OR action = 'workflows.completed_workflow_run'
)
  AND data->>'conclusion' NOT IN ('cancelled', 'skipped')
  AND created_at >= NOW() - MAKE_INTERVAL(days => :period_days)
  AND org IS NOT NULL
GROUP BY org
ORDER BY cfr DESC
"""

_TEAM_CFR_ORG_SQL = """
SELECT
    org,
    COUNT(*) FILTER (
        WHERE data->>'conclusion' IN ('failure', 'timed_out')
    ) * 100.0 / NULLIF(COUNT(*), 0) AS cfr
FROM events
WHERE (
    action LIKE 'workflow_run.%%'
    OR action = 'workflows.completed_workflow_run'
)
  AND data->>'conclusion' NOT IN ('cancelled', 'skipped')
  AND created_at >= NOW() - MAKE_INTERVAL(days => :period_days)
  AND org = ANY(:orgs)
  AND org IS NOT NULL
GROUP BY org
ORDER BY cfr DESC
"""

_TEAM_LEAD_TIME_SQL = """
SELECT org, COUNT(*) AS deploy_count
FROM events
WHERE (
    (action LIKE 'workflow_run.%%' AND data->>'conclusion' = 'success')
    OR action = 'workflows.completed_workflow_run'
)
  AND created_at >= NOW() - MAKE_INTERVAL(days => :period_days)
  AND org IS NOT NULL
GROUP BY org
ORDER BY deploy_count DESC
"""

_TEAM_LEAD_TIME_ORG_SQL = """
SELECT org, COUNT(*) AS deploy_count
FROM events
WHERE (
    (action LIKE 'workflow_run.%%' AND data->>'conclusion' = 'success')
    OR action = 'workflows.completed_workflow_run'
)
  AND created_at >= NOW() - MAKE_INTERVAL(days => :period_days)
  AND org = ANY(:orgs)
  AND org IS NOT NULL
GROUP BY org
ORDER BY deploy_count DESC
"""

_TEAM_MTTR_SQL = """
SELECT
    org,
    COUNT(*) FILTER (
        WHERE data->>'conclusion' IN ('failure', 'timed_out')
    ) AS fail_count,
    COUNT(*) AS total_count
FROM events
WHERE (
    action LIKE 'workflow_run.%%'
    OR action = 'workflows.completed_workflow_run'
)
  AND data->>'conclusion' NOT IN ('cancelled', 'skipped')
  AND created_at >= NOW() - MAKE_INTERVAL(days => :period_days)
  AND org IS NOT NULL
GROUP BY org
ORDER BY fail_count DESC
"""

_TEAM_MTTR_ORG_SQL = """
SELECT
    org,
    COUNT(*) FILTER (
        WHERE data->>'conclusion' IN ('failure', 'timed_out')
    ) AS fail_count,
    COUNT(*) AS total_count
FROM events
WHERE (
    action LIKE 'workflow_run.%%'
    OR action = 'workflows.completed_workflow_run'
)
  AND data->>'conclusion' NOT IN ('cancelled', 'skipped')
  AND created_at >= NOW() - MAKE_INTERVAL(days => :period_days)
  AND org = ANY(:orgs)
  AND org IS NOT NULL
GROUP BY org
ORDER BY fail_count DESC
"""

# Shipping cadence: daily counts
_CADENCE_SQL = """
SELECT
    date_trunc('day', created_at)::date AS day,
    COUNT(*) FILTER (
        WHERE (action LIKE 'workflow_run.%%' AND data->>'conclusion' = 'success')
              OR action = 'workflows.completed_workflow_run'
    ) AS deployments,
    COUNT(*) FILTER (
        WHERE action LIKE 'pull_request.%%'
              AND (action LIKE '%%merged%%' OR action LIKE '%%closed%%')
    ) AS merges,
    COUNT(*) FILTER (
        WHERE action LIKE 'pull_request_review.%%'
              OR action = 'pull_request.reviewed'
    ) AS reviews
FROM events
WHERE created_at >= NOW() - MAKE_INTERVAL(days => :period_days)
  AND (
    action LIKE 'workflow_run.%%'
    OR action = 'workflows.completed_workflow_run'
    OR action LIKE 'pull_request.%%'
    OR action LIKE 'pull_request_review.%%'
  )
GROUP BY day
ORDER BY day
"""

_CADENCE_ORG_SQL = """
SELECT
    date_trunc('day', created_at)::date AS day,
    COUNT(*) FILTER (
        WHERE (action LIKE 'workflow_run.%%' AND data->>'conclusion' = 'success')
              OR action = 'workflows.completed_workflow_run'
    ) AS deployments,
    COUNT(*) FILTER (
        WHERE action LIKE 'pull_request.%%'
              AND (action LIKE '%%merged%%' OR action LIKE '%%closed%%')
    ) AS merges,
    COUNT(*) FILTER (
        WHERE action LIKE 'pull_request_review.%%'
              OR action = 'pull_request.reviewed'
    ) AS reviews
FROM events
WHERE created_at >= NOW() - MAKE_INTERVAL(days => :period_days)
  AND org = ANY(:orgs)
  AND (
    action LIKE 'workflow_run.%%'
    OR action = 'workflows.completed_workflow_run'
    OR action LIKE 'pull_request.%%'
    OR action LIKE 'pull_request_review.%%'
  )
GROUP BY day
ORDER BY day
"""


# ── Helpers ───────────────────────────────────────────────────────────────────


def _compute_trend(current: float, previous: float) -> float:
    """Compute trend percentage between two values.

    Returns 0.0 when previous is zero (avoids division by zero).
    """
    if previous == 0:
        return 0.0
    return round(((current - previous) / previous) * 100, 1)


async def _scalar(
    db: AsyncSession,
    sql: str,
    params: dict[str, Any],
) -> int:
    """Execute a scalar COUNT query and return the integer result."""
    result = await db.execute(text(sql), params)
    row = result.fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def _select_sql(
    base_sql: str,
    org_sql: str,
    scoped_orgs: list[str] | None,
) -> tuple[str, bool]:
    """Choose between the all-orgs and org-scoped SQL variant."""
    if scoped_orgs:
        return org_sql, True
    return base_sql, False


def _params_for_period(
    period_start: int,
    period_end: int,
    scoped_orgs: list[str] | None,
    use_org: bool,
) -> dict[str, Any]:
    """Build query parameters for a period-based query."""
    params: dict[str, Any] = {
        "period_start": period_start,
        "period_end": period_end,
    }
    if use_org and scoped_orgs:
        params["orgs"] = scoped_orgs
    return params


# ── Service Functions ─────────────────────────────────────────────────────────


async def get_leadership_summary(
    db: AsyncSession,
    scoped_orgs: list[str] | None,
    period: int = 30,
) -> LeadershipSummary:
    """Compute DORA metrics + trends for executive leadership view.

    Queries the events table for the current period (0..period days ago)
    and the previous period (period..2*period days ago) to calculate
    trend percentages.
    """
    # Current period: [now - period, now]
    # Previous period: [now - 2*period, now - period]
    current_start = period
    current_end = 0
    prev_start = period * 2
    prev_end = period

    # ── Deployment frequency ──────────────────────────────────────────────
    deploy_sql, use_org = _select_sql(_DEPLOY_COUNT_SQL, _DEPLOY_COUNT_ORG_SQL, scoped_orgs)
    curr_deploys = await _scalar(
        db,
        deploy_sql,
        _params_for_period(current_start, current_end, scoped_orgs, use_org),
    )
    prev_deploys = await _scalar(
        db,
        deploy_sql,
        _params_for_period(prev_start, prev_end, scoped_orgs, use_org),
    )
    deploy_freq = round(curr_deploys / max(period, 1), 2)
    prev_deploy_freq = round(prev_deploys / max(period, 1), 2)

    # ── Total workflow runs (for CFR) ─────────────────────────────────────
    total_sql, use_org = _select_sql(_TOTAL_RUNS_SQL, _TOTAL_RUNS_ORG_SQL, scoped_orgs)
    curr_total = await _scalar(
        db,
        total_sql,
        _params_for_period(current_start, current_end, scoped_orgs, use_org),
    )
    prev_total = await _scalar(
        db,
        total_sql,
        _params_for_period(prev_start, prev_end, scoped_orgs, use_org),
    )

    # ── Failure count (for CFR and MTTR) ──────────────────────────────────
    fail_sql, use_org = _select_sql(_FAILURE_COUNT_SQL, _FAILURE_COUNT_ORG_SQL, scoped_orgs)
    curr_failures = await _scalar(
        db,
        fail_sql,
        _params_for_period(current_start, current_end, scoped_orgs, use_org),
    )
    prev_failures = await _scalar(
        db,
        fail_sql,
        _params_for_period(prev_start, prev_end, scoped_orgs, use_org),
    )

    # ── Lead time proxy ───────────────────────────────────────────────────
    # Estimated as 24h / deploys_per_day (more frequent = shorter lead time)
    lead_time_hours = round(24.0 / max(deploy_freq, 0.01), 1)
    prev_lead_time = round(24.0 / max(prev_deploy_freq, 0.01), 1)

    # ── Change failure rate ───────────────────────────────────────────────
    cfr = round((curr_failures / max(curr_total, 1)) * 100, 1)
    prev_cfr = round((prev_failures / max(prev_total, 1)) * 100, 1)

    # ── MTTR proxy ────────────────────────────────────────────────────────
    # Estimated from failure rate × 24h window
    mttr_hours = round((curr_failures / max(curr_total, 1)) * 24, 1)
    prev_mttr = round((prev_failures / max(prev_total, 1)) * 24, 1)

    # ── PR throughput ─────────────────────────────────────────────────────
    pr_sql, use_org = _select_sql(_PR_MERGED_SQL, _PR_MERGED_ORG_SQL, scoped_orgs)
    curr_prs = await _scalar(
        db,
        pr_sql,
        _params_for_period(current_start, current_end, scoped_orgs, use_org),
    )
    prev_prs = await _scalar(
        db,
        pr_sql,
        _params_for_period(prev_start, prev_end, scoped_orgs, use_org),
    )
    # Convert to per-week
    pr_per_week = round(curr_prs / max(period / 7, 1), 1)
    prev_pr_per_week = round(prev_prs / max(period / 7, 1), 1)

    # ── Active contributors ───────────────────────────────────────────────
    contrib_sql, use_org = _select_sql(_CONTRIBUTORS_SQL, _CONTRIBUTORS_ORG_SQL, scoped_orgs)
    curr_contribs = await _scalar(
        db,
        contrib_sql,
        _params_for_period(current_start, current_end, scoped_orgs, use_org),
    )
    prev_contribs = await _scalar(
        db,
        contrib_sql,
        _params_for_period(prev_start, prev_end, scoped_orgs, use_org),
    )
    # Convert to per-week
    contrib_per_week = round(curr_contribs / max(period / 7, 1), 1)
    prev_contrib_per_week = round(prev_contribs / max(period / 7, 1), 1)

    return LeadershipSummary(
        deployment_frequency=MetricWithTrend(
            value=deploy_freq,
            previous_value=prev_deploy_freq,
            trend_pct=_compute_trend(deploy_freq, prev_deploy_freq),
            classification=classify_deploy_frequency(deploy_freq).value,
        ),
        lead_time=MetricWithTrend(
            value=lead_time_hours,
            previous_value=prev_lead_time,
            trend_pct=_compute_trend(lead_time_hours, prev_lead_time),
            classification=classify_lead_time(lead_time_hours).value,
        ),
        change_failure_rate=MetricWithTrend(
            value=cfr,
            previous_value=prev_cfr,
            trend_pct=_compute_trend(cfr, prev_cfr),
            classification=classify_change_failure_rate(cfr).value,
        ),
        mttr=MetricWithTrend(
            value=mttr_hours,
            previous_value=prev_mttr,
            trend_pct=_compute_trend(mttr_hours, prev_mttr),
            classification=classify_mttr(mttr_hours).value,
        ),
        pr_throughput=MetricWithTrend(
            value=pr_per_week,
            previous_value=prev_pr_per_week,
            trend_pct=_compute_trend(pr_per_week, prev_pr_per_week),
            classification="n/a",
        ),
        active_contributors=MetricWithTrend(
            value=contrib_per_week,
            previous_value=prev_contrib_per_week,
            trend_pct=_compute_trend(contrib_per_week, prev_contrib_per_week),
            classification="n/a",
        ),
        period_days=period,
    )


async def get_team_comparison(
    db: AsyncSession,
    scoped_orgs: list[str] | None,
    period: int = 30,
    metric: str = "deploy_freq",
) -> list[TeamMetrics]:
    """Compute per-org/team breakdown of a velocity metric.

    Supported metrics: deploy_freq, lead_time, cfr, mttr.
    """
    params: dict[str, Any] = {"period_days": period}
    if scoped_orgs:
        params["orgs"] = scoped_orgs

    if metric == "deploy_freq":
        sql = _TEAM_DEPLOY_FREQ_ORG_SQL if scoped_orgs else _TEAM_DEPLOY_FREQ_SQL
        result = await db.execute(text(sql), params)
        rows = result.fetchall()
        return [
            TeamMetrics(
                team=str(row[0]),
                value=round(int(row[1]) / max(period, 1), 2),
                classification=classify_deploy_frequency(int(row[1]) / max(period, 1)).value,
            )
            for row in rows
        ]

    if metric == "cfr":
        sql = _TEAM_CFR_ORG_SQL if scoped_orgs else _TEAM_CFR_SQL
        result = await db.execute(text(sql), params)
        rows = result.fetchall()
        return [
            TeamMetrics(
                team=str(row[0]),
                value=round(float(row[1]) if row[1] is not None else 0, 1),
                classification=classify_change_failure_rate(
                    float(row[1]) if row[1] is not None else 0
                ).value,
            )
            for row in rows
        ]

    if metric == "lead_time":
        sql = _TEAM_LEAD_TIME_ORG_SQL if scoped_orgs else _TEAM_LEAD_TIME_SQL
        result = await db.execute(text(sql), params)
        rows = result.fetchall()
        return [
            TeamMetrics(
                team=str(row[0]),
                value=round(24.0 / max(int(row[1]) / max(period, 1), 0.01), 1),
                classification=classify_lead_time(
                    24.0 / max(int(row[1]) / max(period, 1), 0.01)
                ).value,
            )
            for row in rows
        ]

    if metric == "mttr":
        sql = _TEAM_MTTR_ORG_SQL if scoped_orgs else _TEAM_MTTR_SQL
        result = await db.execute(text(sql), params)
        rows = result.fetchall()
        return [
            TeamMetrics(
                team=str(row[0]),
                value=round(
                    (int(row[1]) / max(int(row[2]), 1)) * 24,
                    1,
                ),
                classification=classify_mttr((int(row[1]) / max(int(row[2]), 1)) * 24).value,
            )
            for row in rows
        ]

    logger.warning("velocity.unknown_metric", metric=metric)
    return []


async def get_shipping_cadence(
    db: AsyncSession,
    scoped_orgs: list[str] | None,
    period: int = 90,
) -> list[CadenceDay]:
    """Compute daily activity counts for shipping cadence heatmap."""
    params: dict[str, Any] = {"period_days": period}
    if scoped_orgs:
        sql = _CADENCE_ORG_SQL
        params["orgs"] = scoped_orgs
    else:
        sql = _CADENCE_SQL

    result = await db.execute(text(sql), params)
    rows = result.fetchall()

    # Build a map of existing data
    data_map: dict[str, CadenceDay] = {}
    for row in rows:
        day_str = str(row[0])
        data_map[day_str] = CadenceDay(
            date=day_str,
            deployments=int(row[1]),
            merges=int(row[2]),
            reviews=int(row[3]),
        )

    # Fill in missing days with zeros
    now = datetime.now(UTC)
    all_days: list[CadenceDay] = []
    for i in range(period - 1, -1, -1):
        from datetime import timedelta

        d = now - timedelta(days=i)
        day_str = d.strftime("%Y-%m-%d")
        if day_str in data_map:
            all_days.append(data_map[day_str])
        else:
            all_days.append(CadenceDay(date=day_str, deployments=0, merges=0, reviews=0))

    return all_days
