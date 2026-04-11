"""Prometheus application metrics for OctoWatch.

Defines custom metrics that are collected alongside the auto-instrumented HTTP
request metrics provided by ``prometheus-fastapi-instrumentator``.

Usage in worker code::

    from app.services.metrics_service import DETECTION_PIPELINE_DURATION
    with DETECTION_PIPELINE_DURATION.time():
        run_pipeline(...)

The ``collect_infrastructure_metrics`` helper is designed to be called from a
Celery Beat task so that gauge values (queue depths, DB pool stats, cache hit
rates) stay fresh between Prometheus scrapes.
"""

from __future__ import annotations

from typing import cast

import redis as sync_redis
import structlog
from prometheus_client import Counter, Gauge, Histogram, Info

from app.config import settings

# ── Application info ────────────────────────────────────────────────────────
APP_INFO: Info = Info("octowatch", "OctoWatch application metadata")

# ── Detection pipeline ──────────────────────────────────────────────────────
DETECTION_PIPELINE_DURATION: Histogram = Histogram(
    "octowatch_detection_pipeline_duration_seconds",
    "Time spent executing the detection pipeline for an event batch",
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)

DETECTION_COUNT: Counter = Counter(
    "octowatch_detections_total",
    "Total detections created",
    ["severity"],
)

# ── Ingestion ───────────────────────────────────────────────────────────────
INGESTION_EVENTS_TOTAL: Counter = Counter(
    "octowatch_ingestion_events_total",
    "Total audit-log events ingested",
    ["source"],
)

INGESTION_THROUGHPUT: Gauge = Gauge(
    "octowatch_ingestion_events_per_second",
    "Current ingestion throughput (events/sec), updated by the collection task",
)

# ── Celery queue depths ────────────────────────────────────────────────────
CELERY_QUEUE_DEPTH: Gauge = Gauge(
    "octowatch_celery_queue_depth",
    "Number of pending messages in a Celery queue",
    ["queue"],
)

# ── Database connection pool ────────────────────────────────────────────────
DB_CONNECTIONS_ACTIVE: Gauge = Gauge(
    "octowatch_db_connections_active",
    "Number of active connections in the SQLAlchemy async pool",
)

# ── Cache ───────────────────────────────────────────────────────────────────
CACHE_HIT_RATE: Gauge = Gauge(
    "octowatch_cache_hit_rate",
    "Valkey cache hit rate (0.0–1.0), computed from INFO stats",
)


def set_app_info(version: str, environment: str) -> None:
    """Record static application metadata as a Prometheus Info metric."""
    APP_INFO.info({"version": version, "environment": environment})


async def collect_infrastructure_metrics() -> dict[str, object]:
    """Collect point-in-time gauge values for queues, DB pool, and cache.

    Designed to be called periodically (e.g. every 15 s from Celery Beat).
    Returns a summary dict suitable for structured logging.
    """
    summary: dict[str, object] = {}

    # ── Celery queue depths via Valkey LLEN ──────────────────────────────────
    queues = ("ingestion", "detection", "baseline", "notification", "github_sync")
    try:
        r = sync_redis.Redis.from_url(settings.VALKEY_URL, decode_responses=True)
        for q in queues:
            depth = cast(int, r.llen(q))
            CELERY_QUEUE_DEPTH.labels(queue=q).set(depth)
            summary[f"queue_{q}"] = depth
        r.close()
    except Exception:
        # Best-effort metric collection — Valkey may not be reachable
        structlog.get_logger(__name__).debug("metrics.queue_depth_collection_failed")

    # ── DB connection pool stats ─────────────────────────────────────────────
    try:
        from app import database as _db_mod

        pool = _db_mod.engine.pool
        checked_out = int(getattr(pool, "checkedout", lambda: 0)())
        DB_CONNECTIONS_ACTIVE.set(checked_out)
        summary["db_connections_active"] = checked_out
    except Exception:
        structlog.get_logger(__name__).debug("metrics.db_pool_stats_failed")

    # ── Valkey cache hit rate ────────────────────────────────────────────────
    try:
        r = sync_redis.Redis.from_url(settings.VALKEY_URL, decode_responses=True)
        info = cast(dict[str, object], r.info("stats"))
        hits = int(str(info.get("keyspace_hits", 0)))
        misses = int(str(info.get("keyspace_misses", 0)))
        total = hits + misses
        rate = hits / total if total > 0 else 0.0
        CACHE_HIT_RATE.set(rate)
        summary["cache_hit_rate"] = round(rate, 4)
        r.close()
    except Exception:
        structlog.get_logger(__name__).debug("metrics.cache_hit_rate_failed")

    return summary
