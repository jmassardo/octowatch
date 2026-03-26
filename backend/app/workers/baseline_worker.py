"""Baseline worker: compute rolling 30-day behavioral baselines per actor/org."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import structlog
from celery import Task

from app.celery_app import celery_app
from app.database import AsyncSessionLocal

logger = structlog.get_logger(__name__)


@celery_app.task(
    name="workers.compute_rolling_baselines",
    bind=True,
    max_retries=2,
)
def compute_rolling_baselines_task(self: Task) -> dict:
    """Celery beat task: recompute 30-day behavioral baselines for all active actors."""
    try:
        result = asyncio.run(_compute_baselines())
        return {"status": "ok", "updated": result}
    except Exception as exc:
        logger.error("baseline_worker.task_failed", error=str(exc))
        raise self.retry(exc=exc) from exc


async def _compute_baselines() -> int:
    """Query 30-day rolling metrics and upsert into behavioral_baselines table."""
    from sqlalchemy import text

    thirty_days_ago = datetime.now(UTC) - timedelta(days=30)
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

            for row in active_pairs:
                actor = row.actor
                org = row.org

                # Compute per-actor/org metrics over 30-day window
                metrics_result = await session.execute(
                    text("""
                        WITH daily AS (
                            SELECT
                                DATE_TRUNC('day', created_at) AS day,
                                COUNT(*) AS daily_events,
                                COUNT(DISTINCT source_ip) AS daily_ips,
                                COUNT(DISTINCT repo) AS daily_repos
                            FROM events
                            WHERE actor = :actor
                              AND org = :org
                              AND created_at >= :cutoff
                            GROUP BY 1
                        )
                        SELECT
                            AVG(daily_events)  AS avg_daily_events,
                            STDDEV(daily_events) AS stddev_daily_events,
                            AVG(daily_ips) AS avg_daily_ips,
                            AVG(daily_repos) AS avg_daily_repos,
                            COUNT(*) AS active_days
                        FROM daily
                    """),
                    {"actor": actor, "org": org, "cutoff": thirty_days_ago},
                )
                metrics = metrics_result.fetchone()
                if not metrics or metrics.avg_daily_events is None:
                    continue

                # Action distribution
                action_dist_result = await session.execute(
                    text("""
                        SELECT action, COUNT(*) AS cnt
                        FROM events
                        WHERE actor = :actor
                          AND org = :org
                          AND created_at >= :cutoff
                        GROUP BY action
                        ORDER BY cnt DESC
                        LIMIT 20
                    """),
                    {"actor": actor, "org": org, "cutoff": thirty_days_ago},
                )
                action_dist = {r.action: r.cnt for r in action_dist_result.fetchall()}

                # Upsert behavioral_baselines
                await session.execute(
                    text("""
                        INSERT INTO behavioral_baselines (
                            actor, org,
                            avg_daily_events, stddev_daily_events,
                            avg_daily_ips, avg_daily_repos,
                            active_days, action_distribution,
                            window_start, window_end,
                            updated_at
                        ) VALUES (
                            :actor, :org,
                            :avg_daily_events, :stddev_daily_events,
                            :avg_daily_ips, :avg_daily_repos,
                            :active_days, :action_dist::jsonb,
                            :window_start, :window_end,
                            NOW()
                        )
                        ON CONFLICT (actor, org) DO UPDATE SET
                            avg_daily_events     = EXCLUDED.avg_daily_events,
                            stddev_daily_events  = EXCLUDED.stddev_daily_events,
                            avg_daily_ips        = EXCLUDED.avg_daily_ips,
                            avg_daily_repos      = EXCLUDED.avg_daily_repos,
                            active_days          = EXCLUDED.active_days,
                            action_distribution  = EXCLUDED.action_distribution,
                            window_start         = EXCLUDED.window_start,
                            window_end           = EXCLUDED.window_end,
                            updated_at           = NOW()
                    """),
                    {
                        "actor": actor,
                        "org": org,
                        "avg_daily_events": float(metrics.avg_daily_events or 0),
                        "stddev_daily_events": float(metrics.stddev_daily_events or 0),
                        "avg_daily_ips": float(metrics.avg_daily_ips or 0),
                        "avg_daily_repos": float(metrics.avg_daily_repos or 0),
                        "active_days": int(metrics.active_days or 0),
                        "action_dist": __import__("json").dumps(action_dist),
                        "window_start": thirty_days_ago,
                        "window_end": datetime.now(UTC),
                    },
                )
                updated += 1

            await session.commit()
            logger.info("baseline_worker.complete", updated=updated)
        except Exception:
            await session.rollback()
            raise

    return updated
