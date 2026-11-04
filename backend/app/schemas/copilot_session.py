"""Pydantic schemas for Copilot session API responses (#387, #508).

Covers only the overview and detail endpoints in scope for #508. The
remaining Copilot session endpoints from #387 are intentionally not
implemented here.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class CopilotSessionModelCount(BaseModel):
    """Session count for a single Copilot model."""

    model: str
    count: int


class CopilotSessionEditorCount(BaseModel):
    """Session count for a single editor."""

    editor: str
    count: int


class CopilotSessionOverview(BaseModel):
    """Aggregated Copilot session overview statistics."""

    total_sessions: int
    avg_duration_seconds: float | None = None
    top_models: list[CopilotSessionModelCount]
    top_editors: list[CopilotSessionEditorCount]
    lookback_days: int


class CopilotSessionTurnItem(BaseModel):
    """Single prompt/response turn within a Copilot session."""

    model_config = ConfigDict(from_attributes=True)

    turn_index: int | None = None
    created_at: datetime | None = None
    prompt_text: str | None = None
    prompt_tokens: int | None = None
    response_text: str | None = None
    response_tokens: int | None = None
    model: str | None = None
    finish_reason: str | None = None
    latency_ms: int | None = None
    tool_calls: Any | None = None
    references: Any | None = None
    annotations: Any | None = None


class CopilotSessionDetail(BaseModel):
    """Full Copilot session detail, including all turns."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: str
    created_at: datetime
    enterprise: str
    org: str | None = None
    actor: str
    actor_id: int | None = None
    editor: str | None = None
    editor_version: str | None = None
    copilot_version: str | None = None
    model: str | None = None
    language: str | None = None
    repository: str | None = None
    turn_count: int | None = None
    tool_call_count: int | None = None
    total_tokens_in: int | None = None
    total_tokens_out: int | None = None
    duration_seconds: int | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    turns: list[CopilotSessionTurnItem]
