"""Helpers for reading and writing maintenance mode settings."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.settings_service import delete_setting, get_settings_bulk, set_setting

logger = structlog.get_logger(__name__)

DEFAULT_MAINTENANCE_MESSAGE = "OctoWatch is undergoing scheduled maintenance."
MaintenanceSeverity = Literal["info", "warning", "critical"]

_MAINTENANCE_DESCRIPTIONS = {
    "maintenance_mode_enabled": "Whether maintenance mode is currently active.",
    "maintenance_message": "User-facing maintenance banner message.",
    "maintenance_severity": "Maintenance banner severity level.",
    "maintenance_block_writes": "Whether non-admin write requests are blocked during maintenance.",
    "maintenance_started_at": "Timestamp when maintenance mode was enabled.",
    "maintenance_estimated_end": "Estimated end time for the current maintenance window.",
}


@dataclass(slots=True)
class MaintenanceStatus:
    """Internal representation of maintenance mode settings."""

    enabled: bool = False
    message: str = DEFAULT_MAINTENANCE_MESSAGE
    severity: MaintenanceSeverity = "warning"
    block_writes: bool = False
    started_at: datetime | None = None
    estimated_end: datetime | None = None


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        logger.warning("maintenance.invalid_datetime", value=value)
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


async def get_maintenance_status(db: AsyncSession) -> MaintenanceStatus:
    """Read the current maintenance mode settings from the app settings store."""

    values = await get_settings_bulk(
        db,
        [
            "maintenance_mode_enabled",
            "maintenance_message",
            "maintenance_severity",
            "maintenance_block_writes",
            "maintenance_started_at",
            "maintenance_estimated_end",
        ],
    )
    severity = values.get("maintenance_severity", "warning").strip().lower() or "warning"
    if severity not in {"info", "warning", "critical"}:
        logger.warning("maintenance.invalid_severity", severity=severity)
        severity = "warning"
    return MaintenanceStatus(
        enabled=_parse_bool(values.get("maintenance_mode_enabled")),
        message=values.get("maintenance_message") or DEFAULT_MAINTENANCE_MESSAGE,
        severity=severity,
        block_writes=_parse_bool(values.get("maintenance_block_writes")),
        started_at=_parse_datetime(values.get("maintenance_started_at")),
        estimated_end=_parse_datetime(values.get("maintenance_estimated_end")),
    )


async def save_maintenance_status(
    db: AsyncSession,
    status: MaintenanceStatus,
    *,
    changed_by: str = "system",
) -> MaintenanceStatus:
    """Persist the maintenance mode settings to the app settings store."""

    normalized = MaintenanceStatus(
        enabled=status.enabled,
        message=status.message.strip() or DEFAULT_MAINTENANCE_MESSAGE,
        severity=(
            status.severity if status.severity in {"info", "warning", "critical"} else "warning"
        ),
        block_writes=status.block_writes,
        started_at=status.started_at,
        estimated_end=status.estimated_end,
    )

    if normalized.enabled and normalized.started_at is None:
        normalized.started_at = datetime.now(UTC)
    if not normalized.enabled:
        normalized.started_at = None

    await set_setting(
        db,
        "maintenance_mode_enabled",
        str(normalized.enabled).lower(),
        category="System",
        sensitivity="config",
        description=_MAINTENANCE_DESCRIPTIONS["maintenance_mode_enabled"],
        changed_by=changed_by,
    )
    await set_setting(
        db,
        "maintenance_message",
        normalized.message,
        category="System",
        sensitivity="config",
        description=_MAINTENANCE_DESCRIPTIONS["maintenance_message"],
        changed_by=changed_by,
    )
    await set_setting(
        db,
        "maintenance_severity",
        normalized.severity,
        category="System",
        sensitivity="config",
        description=_MAINTENANCE_DESCRIPTIONS["maintenance_severity"],
        changed_by=changed_by,
    )
    await set_setting(
        db,
        "maintenance_block_writes",
        str(normalized.block_writes).lower(),
        category="System",
        sensitivity="config",
        description=_MAINTENANCE_DESCRIPTIONS["maintenance_block_writes"],
        changed_by=changed_by,
    )

    if normalized.started_at is None:
        await delete_setting(db, "maintenance_started_at", changed_by=changed_by)
    else:
        await set_setting(
            db,
            "maintenance_started_at",
            normalized.started_at.astimezone(UTC).isoformat(),
            category="System",
            sensitivity="config",
            description=_MAINTENANCE_DESCRIPTIONS["maintenance_started_at"],
            changed_by=changed_by,
        )

    if normalized.estimated_end is None:
        await delete_setting(db, "maintenance_estimated_end", changed_by=changed_by)
    else:
        await set_setting(
            db,
            "maintenance_estimated_end",
            normalized.estimated_end.astimezone(UTC).isoformat(),
            category="System",
            sensitivity="config",
            description=_MAINTENANCE_DESCRIPTIONS["maintenance_estimated_end"],
            changed_by=changed_by,
        )

    logger.info(
        "maintenance.settings_saved",
        enabled=normalized.enabled,
        severity=normalized.severity,
        block_writes=normalized.block_writes,
        changed_by=changed_by,
    )
    return normalized
