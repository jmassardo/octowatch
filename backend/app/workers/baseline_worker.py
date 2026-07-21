"""Baseline worker: compute rolling 30-day behavioral baselines per actor/org.

Writes one row per metric into the ``behavioral_baselines`` table, matching
the ``BehavioralBaseline`` ORM model schema exactly.
"""

from __future__ import annotations

import asyncio
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import structlog
from celery import Task

from app.celery_app import celery_app
from app.database import AsyncSessionLocal

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


@celery_app.task(
    name="app.workers.baseline_worker.compute_rolling_baselines",
    bind=True,
    max_retries=2,
)
def compute_rolling_baselines_task(self: Task) -> dict[str, object]:
    """Celery beat task: recompute 30-day behavioral baselines for all active actors."""
    try:
        result = asyncio.run(_compute_baselines())
        return {"status": "ok", "updated": result}
    except Exception as exc:
        logger.error("baseline_worker.task_failed", error=str(exc))
        backoff = min(30 * (2**self.request.retries), 600)
        jitter = secrets.randbelow(max(int(backoff * 0.1), 1))
        raise self.retry(exc=exc, countdown=backoff + jitter) from exc


async def _upsert_baseline(
    session: AsyncSession,
    *,
    baseline_type: str,
    scope_key: str,
    metric_name: str,
    window_start: datetime,
    window_end: datetime,
    mean: float,
    stddev: float,
    p25: float | None = None,
    p75: float | None = None,
    p95: float,
    p99: float,
    sample_count: int,
) -> None:
    """Upsert a single baseline row matching the BehavioralBaseline model."""
    from sqlalchemy import text

    await session.execute(
        text("""
            INSERT INTO behavioral_baselines (
                baseline_type, scope_key, metric_name,
                window_start, window_end,
                mean, stddev, p25, p75, p95, p99,
                sample_count, computed_at
            ) VALUES (
                :baseline_type, :scope_key, :metric_name,
                :window_start, :window_end,
                :mean, :stddev, :p25, :p75, :p95, :p99,
                :sample_count, NOW()
            )
            ON CONFLICT (baseline_type, scope_key, metric_name)
            DO UPDATE SET
                window_start  = EXCLUDED.window_start,
                window_end    = EXCLUDED.window_end,
                mean          = EXCLUDED.mean,
                stddev        = EXCLUDED.stddev,
                p25           = EXCLUDED.p25,
                p75           = EXCLUDED.p75,
                p95           = EXCLUDED.p95,
                p99           = EXCLUDED.p99,
                sample_count  = EXCLUDED.sample_count,
                computed_at   = NOW()
        """),
        {
            "baseline_type": baseline_type,
            "scope_key": scope_key,
            "metric_name": metric_name,
            "window_start": window_start,
            "window_end": window_end,
            "mean": mean,
            "stddev": stddev,
            "p25": p25,
            "p75": p75,
            "p95": p95,
            "p99": p99,
            "sample_count": sample_count,
        },
    )


def _percentile(values: list[float], pct: float) -> float:
    """Compute the given percentile from a sorted list of values."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = (pct / 100.0) * (len(sorted_vals) - 1)
    lower = int(idx)
    upper = lower + 1
    if upper >= len(sorted_vals):
        return sorted_vals[-1]
    frac = idx - lower
    return sorted_vals[lower] + frac * (sorted_vals[upper] - sorted_vals[lower])


async def _compute_actor_baselines(
    session: AsyncSession,
    actor: str,
    org: str,
    cutoff: datetime,
    window_end: datetime,
) -> int:
    """Compute and upsert baselines for a single actor/org pair. Returns rows written."""
    from sqlalchemy import text as sa_text

    scope_key = f"actor:{actor}:org:{org}"
    written = 0

    # ── daily_events, daily_ips, daily_repos ─────────────────────────────
    daily_result = await session.execute(
        sa_text("""
            WITH daily AS (
                SELECT
                    DATE_TRUNC('day', created_at) AS day,
                    COUNT(*)                       AS daily_events,
                    COUNT(DISTINCT source_ip)       AS daily_ips,
                    COUNT(DISTINCT repo)            AS daily_repos
                FROM events
                WHERE actor = :actor
                  AND org = :org
                  AND created_at >= :cutoff
                GROUP BY 1
            )
            SELECT
                json_agg(json_build_object(
                    'day', day,
                    'daily_events', daily_events,
                    'daily_ips', daily_ips,
                    'daily_repos', daily_repos
                )) AS rows_json,
                COUNT(*) AS sample_count
            FROM daily
        """),
        {"actor": actor, "org": org, "cutoff": cutoff},
    )
    row = daily_result.fetchone()
    if not row or not row.rows_json:
        return 0

    daily_rows = json.loads(row.rows_json) if isinstance(row.rows_json, str) else row.rows_json
    sample_count = int(row.sample_count)

    for metric_col in ("daily_events", "daily_ips", "daily_repos"):
        values = [float(r[metric_col]) for r in daily_rows if r[metric_col] is not None]
        if not values:
            continue
        mean_val = sum(values) / len(values)
        variance = sum((v - mean_val) ** 2 for v in values) / max(len(values) - 1, 1)
        stddev_val = variance**0.5

        await _upsert_baseline(
            session,
            baseline_type="actor",
            scope_key=scope_key,
            metric_name=metric_col,
            window_start=cutoff,
            window_end=window_end,
            mean=mean_val,
            stddev=stddev_val,
            p25=_percentile(values, 25),
            p75=_percentile(values, 75),
            p95=_percentile(values, 95),
            p99=_percentile(values, 99),
            sample_count=sample_count,
        )
        written += 1

    # ── active_hours ─────────────────────────────────────────────────────
    hours_result = await session.execute(
        sa_text("""
            SELECT EXTRACT(HOUR FROM created_at)::int AS hour
            FROM events
            WHERE actor = :actor
              AND org = :org
              AND created_at >= :cutoff
        """),
        {"actor": actor, "org": org, "cutoff": cutoff},
    )
    hour_values = [float(r.hour) for r in hours_result.fetchall()]
    if hour_values:
        mean_hour = sum(hour_values) / len(hour_values)
        variance_hour = sum((h - mean_hour) ** 2 for h in hour_values) / max(
            len(hour_values) - 1, 1
        )
        stddev_hour = variance_hour**0.5

        await _upsert_baseline(
            session,
            baseline_type="actor",
            scope_key=scope_key,
            metric_name="active_hours",
            window_start=cutoff,
            window_end=window_end,
            mean=mean_hour,
            stddev=stddev_hour,
            p25=_percentile(hour_values, 25),
            p75=_percentile(hour_values, 75),
            p95=_percentile(hour_values, 95),
            p99=_percentile(hour_values, 99),
            sample_count=len(hour_values),
        )
        written += 1

    return written


async def _compute_org_baselines(
    session: AsyncSession,
    org: str,
    cutoff: datetime,
    window_end: datetime,
) -> int:
    """Compute and upsert org-level aggregate baselines. Returns rows written."""
    from sqlalchemy import text as sa_text

    scope_key = f"org:{org}"
    written = 0

    daily_result = await session.execute(
        sa_text("""
            WITH daily AS (
                SELECT
                    DATE_TRUNC('day', created_at) AS day,
                    COUNT(*)                       AS daily_events,
                    COUNT(DISTINCT source_ip)       AS daily_ips,
                    COUNT(DISTINCT repo)            AS daily_repos
                FROM events
                WHERE org = :org
                  AND created_at >= :cutoff
                GROUP BY 1
            )
            SELECT
                json_agg(json_build_object(
                    'day', day,
                    'daily_events', daily_events,
                    'daily_ips', daily_ips,
                    'daily_repos', daily_repos
                )) AS rows_json,
                COUNT(*) AS sample_count
            FROM daily
        """),
        {"org": org, "cutoff": cutoff},
    )
    row = daily_result.fetchone()
    if not row or not row.rows_json:
        return 0

    daily_rows = json.loads(row.rows_json) if isinstance(row.rows_json, str) else row.rows_json
    sample_count = int(row.sample_count)

    for metric_col in ("daily_events", "daily_ips", "daily_repos"):
        values = [float(r[metric_col]) for r in daily_rows if r[metric_col] is not None]
        if not values:
            continue
        mean_val = sum(values) / len(values)
        variance = sum((v - mean_val) ** 2 for v in values) / max(len(values) - 1, 1)
        stddev_val = variance**0.5

        await _upsert_baseline(
            session,
            baseline_type="org",
            scope_key=scope_key,
            metric_name=metric_col,
            window_start=cutoff,
            window_end=window_end,
            mean=mean_val,
            stddev=stddev_val,
            p25=_percentile(values, 25),
            p75=_percentile(values, 75),
            p95=_percentile(values, 95),
            p99=_percentile(values, 99),
            sample_count=sample_count,
        )
        written += 1

    # Org-level active_hours
    hours_result = await session.execute(
        sa_text("""
            SELECT EXTRACT(HOUR FROM created_at)::int AS hour
            FROM events
            WHERE org = :org
              AND created_at >= :cutoff
        """),
        {"org": org, "cutoff": cutoff},
    )
    hour_values = [float(r.hour) for r in hours_result.fetchall()]
    if hour_values:
        mean_hour = sum(hour_values) / len(hour_values)
        variance_hour = sum((h - mean_hour) ** 2 for h in hour_values) / max(
            len(hour_values) - 1, 1
        )
        stddev_hour = variance_hour**0.5

        await _upsert_baseline(
            session,
            baseline_type="org",
            scope_key=scope_key,
            metric_name="active_hours",
            window_start=cutoff,
            window_end=window_end,
            mean=mean_hour,
            stddev=stddev_hour,
            p25=_percentile(hour_values, 25),
            p75=_percentile(hour_values, 75),
            p95=_percentile(hour_values, 95),
            p99=_percentile(hour_values, 99),
            sample_count=len(hour_values),
        )
        written += 1

    return written


async def _compute_utilization_baselines(session: AsyncSession) -> int:
    """Compute baselines from utilization_facts for IQR anomaly detection.

    For each (org_slug, actor_login, feature_area) combination with at least
    14 days of data, compute percentile and summary statistics across daily
    metric values and upsert into behavioral_baselines.
    """
    from sqlalchemy import text as sa_text

    metrics = [
        "actions_minutes",
        "actions_runs",
        "copilot_suggestions",
        "copilot_acceptances",
        "copilot_credits",
        "git_clones",
        "git_pushes",
        "packages_published",
        "storage_bytes",
    ]

    now = datetime.now(UTC)
    thirty_days_ago = now - timedelta(days=30)
    written = 0

    # Get distinct actor/org/feature combos with >= 14 days of data
    combos_result = await session.execute(
        sa_text("""
            SELECT org_slug, actor_login, feature_area, COUNT(DISTINCT metric_date) AS day_count
            FROM utilization_facts
            WHERE metric_date >= :cutoff
            GROUP BY org_slug, actor_login, feature_area
            HAVING COUNT(DISTINCT metric_date) >= 14
        """),
        {"cutoff": thirty_days_ago},
    )
    combos = combos_result.fetchall()

    for combo in combos:
        org_slug = combo.org_slug
        actor_login = combo.actor_login
        feature_area = combo.feature_area
        scope_key = f"{org_slug}/{actor_login}"

        for metric in metrics:
            # Query daily values for this metric
            values_result = await session.execute(
                sa_text(f"""
                    SELECT
                        AVG(COALESCE({metric}, 0)) AS mean_val,
                        STDDEV_SAMP(COALESCE({metric}, 0)) AS stddev_val,
                        percentile_cont(0.25) WITHIN GROUP (ORDER BY COALESCE({metric}, 0)) AS p25,
                        percentile_cont(0.75) WITHIN GROUP (ORDER BY COALESCE({metric}, 0)) AS p75,
                        percentile_cont(0.95) WITHIN GROUP (ORDER BY COALESCE({metric}, 0)) AS p95,
                        percentile_cont(0.99) WITHIN GROUP (ORDER BY COALESCE({metric}, 0)) AS p99,
                        COUNT(*) AS sample_count
                    FROM utilization_facts
                    WHERE org_slug = :org_slug
                      AND actor_login = :actor_login
                      AND feature_area = :feature_area
                      AND metric_date >= :cutoff
                      AND {metric} IS NOT NULL
                """),
                {
                    "org_slug": org_slug,
                    "actor_login": actor_login,
                    "feature_area": feature_area,
                    "cutoff": thirty_days_ago,
                },
            )
            row = values_result.fetchone()
            if not row or row.sample_count == 0 or row.mean_val is None:
                continue

            await _upsert_baseline(
                session,
                baseline_type="utilization",
                scope_key=scope_key,
                metric_name=f"{feature_area}.{metric}",
                window_start=thirty_days_ago,
                window_end=now,
                mean=float(row.mean_val),
                stddev=float(row.stddev_val) if row.stddev_val is not None else 0.0,
                p25=float(row.p25) if row.p25 is not None else None,
                p75=float(row.p75) if row.p75 is not None else None,
                p95=float(row.p95) if row.p95 is not None else 0.0,
                p99=float(row.p99) if row.p99 is not None else 0.0,
                sample_count=int(row.sample_count),
            )
            written += 1

    logger.info("baseline_worker.utilization_baselines_complete", written=written)
    return written


async def _compute_baselines() -> int:
    """Query 30-day rolling metrics and upsert into behavioral_baselines table."""
    from sqlalchemy import text

    thirty_days_ago = datetime.now(UTC) - timedelta(days=30)
    now = datetime.now(UTC)
    updated = 0

    async with AsyncSessionLocal() as session:
        try:
            # Get distinct (actor, org) pairs active in last 30 days
            active_pairs_result = await session.execute(
                text("""
                    SELECT DISTINCT actor, org
                    FROM events
                    WHERE created_at >= :cutoff
                      AND actor IS NOT NULL
                      AND org IS NOT NULL
                    LIMIT 5000
                """),
                {"cutoff": thirty_days_ago},
            )
            active_pairs = active_pairs_result.fetchall()

            # Compute per-actor baselines
            for row in active_pairs:
                written = await _compute_actor_baselines(
                    session, row.actor, row.org, thirty_days_ago, now
                )
                updated += written

            # Compute org-level aggregate baselines
            orgs_result = await session.execute(
                text("""
                    SELECT DISTINCT org
                    FROM events
                    WHERE created_at >= :cutoff
                      AND org IS NOT NULL
                    LIMIT 500
                """),
                {"cutoff": thirty_days_ago},
            )
            for org_row in orgs_result.fetchall():
                written = await _compute_org_baselines(session, org_row.org, thirty_days_ago, now)
                updated += written

            # Compute utilization-based baselines for IQR anomaly detection
            utilization_written = await _compute_utilization_baselines(session)
            updated += utilization_written

            await session.commit()
            logger.info("baseline_worker.complete", updated=updated)
        except Exception:
            await session.rollback()
            raise

    return updated
