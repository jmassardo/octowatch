"""Pydantic models for maintenance mode APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

MaintenanceSeverity = Literal["info", "warning", "critical"]


class MaintenanceStatusResponse(BaseModel):
    """Current maintenance mode state exposed to the frontend."""

    enabled: bool
    message: str
    severity: MaintenanceSeverity
    block_writes: bool
    started_at: datetime | None = None
    estimated_end: datetime | None = None


class MaintenanceUpdateRequest(BaseModel):
    """Admin-configurable maintenance mode settings."""

    enabled: bool = False
    message: str = Field(default="OctoWatch is undergoing scheduled maintenance.", min_length=1)
    severity: MaintenanceSeverity = "warning"
    block_writes: bool = False
    estimated_end: datetime | None = None


class MaintenanceToggleRequest(BaseModel):
    """Optional explicit enabled state for quick maintenance toggles."""

    enabled: bool | None = None
