"""Pydantic schemas for correlation chains and chain memberships."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ChainMemberResponse(BaseModel):
    """A detection's membership in a chain."""

    model_config = ConfigDict(from_attributes=True)

    detection_id: int
    correlation_type: str
    confidence: float
    added_at: datetime
    detection_title: str
    detection_severity: str
    detection_status: str
    detection_actor: str | None
    detection_triggered_at: datetime


class CorrelationChainResponse(BaseModel):
    """Full correlation chain with members."""

    model_config = ConfigDict(from_attributes=True)

    chain_id: str
    title: str
    status: str
    severity: str
    assignee: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
    members: list[ChainMemberResponse] = []
    detection_count: int = 0


class CorrelationChainSummary(BaseModel):
    """Lightweight chain for list views."""

    model_config = ConfigDict(from_attributes=True)

    chain_id: str
    title: str
    status: str
    severity: str
    assignee: str | None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
    detection_count: int = 0


class CorrelationChainListResponse(BaseModel):
    """Paginated list of chains."""

    items: list[CorrelationChainSummary]
    total: int
    page: int
    page_size: int
    has_next: bool


class CorrelationChainListParams(BaseModel):
    """Query parameters for GET /correlations/chains."""

    status: str | None = Field(None, max_length=50)
    severity: str | None = Field(None, max_length=50)
    assignee: str | None = Field(None, max_length=255)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=500)


class UpdateChainRequest(BaseModel):
    """Request body for PUT /correlations/chains/{id}."""

    status: str | None = Field(None, pattern=r"^(open|investigating|resolved)$")
    assignee: str | None = Field(None, max_length=255)
    title: str | None = Field(None, min_length=1, max_length=500)
    notes: str | None = Field(None, max_length=5000)


class MergeChainRequest(BaseModel):
    """Request body for POST /correlations/chains/{id}/merge."""

    source_chain_id: str = Field(..., min_length=1, max_length=255)


class CorrelationRunResponse(BaseModel):
    """Result of running correlation for a single detection."""

    detection_id: int
    chain_id: str | None
    match_count: int
    created_new_chain: bool


class ChainMetrics(BaseModel):
    """Summary metrics for the chains dashboard."""

    active_chains: int
    avg_chain_size: float
    chains_resolved_today: int
    total_chains: int
