"""Retention policy service: manage and enforce data retention across all time-series tables.

Retention policies are stored in the ``retention_policies`` table.  This
service reads them (with a short TTL cache to avoid DB hits on every
cleanup cycle), validates updates against enforced minimums, and provides
helpers for the admin API and the Celery worker.

Legacy ``app_settings`` overrides are still honoured for backwards
compatibility but the ``retention_policies`` table is the source of truth.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.retention_policy import RetentionPolicy
from app.services.audit_service import log_action

logger = structlog.get_logger(__name__)


# ── In-memory cache (5 minute TTL) ──────────────────────────────────────────

_CACHE_TTL_SECONDS = 300
_policy_cache: dict[str, dict[str, Any]] | None = None
_policy_cache_ts: float = 0.0


# Mapping from data_type → (actual table name, time column).
# The retention_policies table stores logical data_type keys; this mapping
# translates them to the physical SQL table name used for DELETE statements.
_TABLE_MAP: dict[str, dict[str, str]] = {
    "events": {"table": "events", "time_col": "created_at"},
    "raw_payloads": {"table": "event_raw_payloads", "time_col": "ingested_at"},
    "detections": {"table": "detections", "time_col": "triggered_at"},
    "event_dedup": {"table": "event_dedup", "time_col": "created_at"},
    "audit_trail": {"table": "audit_trail", "time_col": "timestamp"},
    "enterprise_sync_log": {"table": "enterprise_sync_log_entries", "time_col": "timestamp"},
    "system_health_events": {"table": "system_health_events", "time_col": "occurred_at"},
    "behavioral_baselines": {"table": "behavioral_baselines", "time_col": "computed_at"},
    "copilot_metrics": {"table": "copilot_daily_metrics", "time_col": "metric_date"},
    "report_history": {"table": "report_schedules", "time_col": "updated_at"},
    "notification_history": {"table": "notification_configs", "time_col": "updated_at"},
}

# Hardcoded fallback defaults — used only when the DB table doesn't exist yet
# or a data_type is missing from the DB.
_FALLBACK_DEFAULTS: dict[str, dict[str, Any]] = {
    "events": {"retention_days": 365, "minimum_days": 90, "time_col": "created_at"},
    "raw_payloads": {"retention_days": 90, "minimum_days": 7, "time_col": "ingested_at"},
    "detections": {"retention_days": 365, "minimum_days": 30, "time_col": "triggered_at"},
    "event_dedup": {"retention_days": 7, "minimum_days": 1, "time_col": "created_at"},
    "audit_trail": {"retention_days": 730, "minimum_days": 365, "time_col": "timestamp"},
    "enterprise_sync_log": {"retention_days": 90, "minimum_days": 7, "time_col": "timestamp"},
    "system_health_events": {"retention_days": 90, "minimum_days": 7, "time_col": "occurred_at"},
    "behavioral_baselines": {"retention_days": 180, "minimum_days": 30, "time_col": "computed_at"},
}


def invalidate_cache() -> None:
    """Force the next read to reload policies from the database."""
    global _policy_cache, _policy_cache_ts  # noqa: PLW0603
    _policy_cache = None
    _policy_cache_ts = 0.0


async def get_retention_policies(db: AsyncSession) -> dict[str, dict[str, Any]]:
    """Return all retention policies, keyed by ``data_type``.

    Results are cached in memory for up to ``_CACHE_TTL_SECONDS``.
    """
    global _policy_cache, _policy_cache_ts  # noqa: PLW0603

    now = time.monotonic()
    if _policy_cache is not None and (now - _policy_cache_ts) < _CACHE_TTL_SECONDS:
        return _policy_cache

    try:
        result = await db.execute(select(RetentionPolicy).order_by(RetentionPolicy.data_type))
        rows = list(result.scalars().all())
    except Exception:
        # Table may not exist yet (pre-migration) — fall back gracefully
        logger.debug("retention.db_read_fallback", reason="retention_policies table not available")
        return _build_fallback_policies()

    if not rows:
        return _build_fallback_policies()

    policies: dict[str, dict[str, Any]] = {}
    for row in rows:
        table_meta = _TABLE_MAP.get(row.data_type, {})
        policies[row.data_type] = {
            "data_type": row.data_type,
            "category": row.category,
            "display_name": row.display_name,
            "description": row.description,
            "retention_days": row.retention_days,
            "minimum_days": row.minimum_days,
            "is_system": row.is_system,
            "updated_by": row.updated_by,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "table_name": table_meta.get("table", row.data_type),
            "time_column": table_meta.get("time_col", "created_at"),
        }

    _policy_cache = policies
    _policy_cache_ts = now
    return policies


def _build_fallback_policies() -> dict[str, dict[str, Any]]:
    """Build policies from hardcoded fallback defaults."""
    policies: dict[str, dict[str, Any]] = {}
    for data_type, meta in _FALLBACK_DEFAULTS.items():
        table_meta = _TABLE_MAP.get(data_type, {})
        policies[data_type] = {
            "data_type": data_type,
            "category": "core_data",
            "display_name": data_type.replace("_", " ").title(),
            "description": f"Retention policy for {data_type}",
            "retention_days": meta["retention_days"],
            "minimum_days": meta["minimum_days"],
            "is_system": True,
            "updated_by": None,
            "updated_at": None,
            "table_name": table_meta.get("table", data_type),
            "time_column": table_meta.get("time_col", meta.get("time_col", "created_at")),
        }
    return policies


# ── Read / write policies ────────────────────────────────────────────────────


async def get_all_policies(db: AsyncSession) -> dict[str, dict[str, Any]]:
    """Return retention config for every managed data type.

    Each entry contains ``retention_days`` (int) and table metadata.
    """
    return await get_retention_policies(db)


async def get_policy(db: AsyncSession, data_type: str) -> int:
    """Return the configured retention days for *data_type*."""
    policies = await get_retention_policies(db)
    policy = policies.get(data_type)
    if policy is None:
        raise ValueError(f"Unknown retention data type: {data_type}")
    return int(policy["retention_days"])


async def update_retention_policy(
    db: AsyncSession,
    data_type: str,
    retention_days: int,
    *,
    user_login: str,
    ip_address: str | None = None,
) -> dict[str, Any]:
    """Update the retention period for *data_type*.

    Validates against the enforced ``minimum_days`` and records an audit
    trail entry.  Returns the updated policy dict.
    """
    result = await db.execute(select(RetentionPolicy).where(RetentionPolicy.data_type == data_type))
    policy = result.scalar_one_or_none()
    if policy is None:
        raise ValueError(f"Unknown retention data type: {data_type}")

    if retention_days < policy.minimum_days:
        raise ValueError(
            f"retention_days ({retention_days}) must be >= minimum_days ({policy.minimum_days})"
        )

    old_days = policy.retention_days
    now = datetime.now(UTC)
    await db.execute(
        update(RetentionPolicy)
        .where(RetentionPolicy.data_type == data_type)
        .values(
            retention_days=retention_days,
            updated_by=user_login,
            updated_at=now,
        )
    )

    await log_action(
        db,
        user_login=user_login,
        ip_address=ip_address,
        action_type="retention_policy_update",
        resource_type="retention_policy",
        resource_id=data_type,
        parameters={"old_days": old_days, "new_days": retention_days},
        outcome="success",
    )
    logger.info(
        "retention.policy_updated",
        data_type=data_type,
        old_days=old_days,
        new_days=retention_days,
        user=user_login,
    )

    # Invalidate cache so next read picks up changes
    invalidate_cache()

    return {
        "data_type": data_type,
        "retention_days": retention_days,
        "minimum_days": policy.minimum_days,
        "old_days": old_days,
        "updated_by": user_login,
    }


# Legacy compatibility alias
async def update_policy(
    db: AsyncSession,
    table_name: str,
    retention_days: int,
    *,
    user_login: str,
    ip_address: str | None = None,
) -> None:
    """Legacy alias for ``update_retention_policy``.

    Maps the old ``table_name`` parameter to ``data_type`` and delegates.
    """
    await update_retention_policy(
        db,
        table_name,
        retention_days,
        user_login=user_login,
        ip_address=ip_address,
    )


# ── Enforcement ──────────────────────────────────────────────────────────────


async def enforce_retention(
    db: AsyncSession,
    data_type: str,
    *,
    archive_callback: Any | None = None,
) -> int:
    """Delete rows older than the retention window for *data_type*.

    If *archive_callback* is provided it is called **before** deletion with
    ``(db, table_name, cutoff_date)`` so that an archival service can export
    the soon-to-be-deleted rows first.

    Returns the number of deleted rows.
    """
    policies = await get_retention_policies(db)
    policy = policies.get(data_type)
    if policy is None:
        raise ValueError(f"Unknown retention data type: {data_type}")

    retention_days = policy["retention_days"]
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    table_name = policy["table_name"]
    time_col = policy["time_column"]

    # Optional archival step
    if archive_callback is not None:
        await archive_callback(db, table_name, cutoff)

    result = await db.execute(
        text(f"DELETE FROM {table_name} WHERE {time_col} < :cutoff"),  # noqa: S608
        {"cutoff": cutoff},
    )
    deleted = int(getattr(result, "rowcount", 0) or 0)
    if deleted:
        logger.info(
            "retention.enforced",
            table=table_name,
            data_type=data_type,
            deleted=deleted,
            cutoff=cutoff.isoformat(),
            retention_days=retention_days,
        )
    return deleted


async def enforce_all(
    db: AsyncSession,
    *,
    archive_callback: Any | None = None,
) -> dict[str, int]:
    """Enforce retention on every managed data type. Returns ``{data_type: deleted_count}``."""
    policies = await get_retention_policies(db)
    results: dict[str, int] = {}
    for data_type in policies:
        try:
            deleted = await enforce_retention(
                db,
                data_type,
                archive_callback=archive_callback,
            )
            results[data_type] = deleted
        except Exception:
            logger.exception("retention.enforce_error", data_type=data_type)
            results[data_type] = -1
    return results


# ── Storage stats ────────────────────────────────────────────────────────────


async def get_storage_stats(db: AsyncSession) -> dict[str, dict[str, Any]]:
    """Return row counts and approximate sizes for each managed table."""
    policies = await get_retention_policies(db)
    stats: dict[str, dict[str, Any]] = {}
    for data_type, policy in policies.items():
        table_name = policy["table_name"]
        try:
            row_result = await db.execute(
                text(f"SELECT COUNT(*) FROM {table_name}")  # noqa: S608
            )
            row_count = row_result.scalar() or 0

            # pg_total_relation_size gives bytes including indexes + toast
            size_result = await db.execute(
                text("SELECT pg_total_relation_size(:tbl) AS size_bytes"),
                {"tbl": table_name},
            )
            size_row = size_result.fetchone()
            size_bytes = size_row[0] if size_row else 0

            stats[data_type] = {
                "row_count": row_count,
                "size_bytes": size_bytes,
            }
        except Exception:
            logger.debug("retention.stats_error", data_type=data_type)
            stats[data_type] = {"row_count": 0, "size_bytes": 0}
    return stats
