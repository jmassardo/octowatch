"""Retention policy service: manage and enforce data retention across all time-series tables.

Retention settings are stored as app_settings key/value pairs
(e.g. ``retention.events.days`` = ``365``).  The service merges stored
values with built-in defaults and exposes helpers for the admin API and
the Celery worker.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.audit_service import log_action
from app.services.settings_service import get_setting, set_setting

logger = structlog.get_logger(__name__)


# ── Table definitions ────────────────────────────────────────────────────────

RETENTION_TABLES: dict[str, dict[str, Any]] = {
    "events": {"time_col": "created_at", "default_days": 365},
    "audit_trail": {"time_col": "timestamp", "default_days": 365},
    "detections": {"time_col": "triggered_at", "default_days": 365},
    "event_raw_payloads": {"time_col": "ingested_at", "default_days": 90},
    "event_dedup": {"time_col": "created_at", "default_days": 7},
    "enterprise_sync_log_entries": {"time_col": "timestamp", "default_days": 90},
    "behavioral_baselines": {"time_col": "computed_at", "default_days": 180},
    "system_health_events": {"time_col": "occurred_at", "default_days": 90},
}

_SETTINGS_PREFIX = "retention"


def _setting_key(table_name: str) -> str:
    """Return the ``app_settings`` key for a table's retention days."""
    return f"{_SETTINGS_PREFIX}.{table_name}.days"


# ── Read / write policies ────────────────────────────────────────────────────


async def get_all_policies(db: AsyncSession) -> dict[str, dict[str, Any]]:
    """Return retention config for every managed table.

    Each entry contains ``retention_days`` (int) and table metadata.
    """
    policies: dict[str, dict[str, Any]] = {}
    for table_name, meta in RETENTION_TABLES.items():
        stored = await get_setting(db, _setting_key(table_name))
        days = int(stored) if stored is not None else meta["default_days"]
        policies[table_name] = {
            "table_name": table_name,
            "time_column": meta["time_col"],
            "retention_days": days,
            "default_days": meta["default_days"],
        }
    return policies


async def get_policy(db: AsyncSession, table_name: str) -> int:
    """Return the configured retention days for *table_name*."""
    meta = RETENTION_TABLES.get(table_name)
    if meta is None:
        raise ValueError(f"Unknown retention table: {table_name}")
    stored = await get_setting(db, _setting_key(table_name))
    return int(stored) if stored is not None else meta["default_days"]


async def update_policy(
    db: AsyncSession,
    table_name: str,
    retention_days: int,
    *,
    user_login: str,
    ip_address: str | None = None,
) -> None:
    """Persist a new retention value and write an audit-trail entry."""
    if table_name not in RETENTION_TABLES:
        raise ValueError(f"Unknown retention table: {table_name}")
    if retention_days < 1:
        raise ValueError("retention_days must be >= 1")

    old_days = await get_policy(db, table_name)
    await set_setting(
        db,
        _setting_key(table_name),
        str(retention_days),
        category="retention",
        sensitivity="config",
        description=f"Retention period for {table_name}",
        changed_by=user_login,
    )
    await log_action(
        db,
        user_login=user_login,
        ip_address=ip_address,
        action_type="retention_policy_update",
        resource_type="retention_policy",
        resource_id=table_name,
        parameters={"old_days": old_days, "new_days": retention_days},
        outcome="success",
    )
    logger.info(
        "retention.policy_updated",
        table=table_name,
        old_days=old_days,
        new_days=retention_days,
        user=user_login,
    )


# ── Enforcement ──────────────────────────────────────────────────────────────


async def enforce_retention(
    db: AsyncSession,
    table_name: str,
    *,
    archive_callback: Any | None = None,
) -> int:
    """Delete rows older than the retention window for *table_name*.

    If *archive_callback* is provided it is called **before** deletion with
    ``(db, table_name, cutoff_date)`` so that an archival service can export
    the soon-to-be-deleted rows first.

    Returns the number of deleted rows.
    """
    meta = RETENTION_TABLES.get(table_name)
    if meta is None:
        raise ValueError(f"Unknown retention table: {table_name}")

    retention_days = await get_policy(db, table_name)
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    time_col = meta["time_col"]

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
    """Enforce retention on every managed table. Returns ``{table: deleted_count}``."""
    results: dict[str, int] = {}
    for table_name in RETENTION_TABLES:
        try:
            deleted = await enforce_retention(
                db,
                table_name,
                archive_callback=archive_callback,
            )
            results[table_name] = deleted
        except Exception:
            logger.exception("retention.enforce_error", table=table_name)
            results[table_name] = -1
    return results


# ── Storage stats ────────────────────────────────────────────────────────────


async def get_storage_stats(db: AsyncSession) -> dict[str, dict[str, Any]]:
    """Return row counts and approximate sizes for each managed table."""
    stats: dict[str, dict[str, Any]] = {}
    for table_name in RETENTION_TABLES:
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

            stats[table_name] = {
                "row_count": row_count,
                "size_bytes": size_bytes,
            }
        except Exception:
            logger.debug("retention.stats_error", table=table_name)
            stats[table_name] = {"row_count": 0, "size_bytes": 0}
    return stats
