"""Pydantic schemas for threat intelligence indicators and feeds."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ─── Indicator schemas ────────────────────────────────────────────────────────


class IndicatorCreate(BaseModel):
    """Request body for creating a threat intel indicator."""

    indicator_type: str = Field(
        ..., pattern=r"^(domain|ip|pattern)$", description="Type: domain, ip, or pattern"
    )
    value: str = Field(..., min_length=1, max_length=500, description="The indicator value")
    source: str = Field(..., min_length=1, max_length=255, description="Intelligence source")
    confidence: float = Field(default=0.80, ge=0.0, le=1.0, description="Confidence score 0-1")
    expires_at: datetime | None = Field(default=None, description="Optional expiry timestamp")
    notes: str | None = Field(default=None, max_length=2000, description="Optional notes")


class IndicatorUpdate(BaseModel):
    """Request body for updating a threat intel indicator."""

    value: str | None = Field(default=None, min_length=1, max_length=500)
    source: str | None = Field(default=None, min_length=1, max_length=255)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    active: bool | None = None
    expires_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=2000)


class IndicatorResponse(BaseModel):
    """Single indicator in API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    indicator_type: str
    value: str
    source: str
    confidence: float
    active: bool
    added_at: datetime
    added_by: str
    expires_at: datetime | None
    notes: str | None
    feed_id: int | None = None
    metadata_json: dict[str, Any] | None = None


class IndicatorListResponse(BaseModel):
    """Paginated list of indicators."""

    items: list[IndicatorResponse]
    total: int
    page: int
    page_size: int


# ─── Feed schemas ─────────────────────────────────────────────────────────────


class FeedCreate(BaseModel):
    """Request body for creating a threat intel feed."""

    name: str = Field(..., min_length=1, max_length=255, description="Feed name")
    url: str = Field(..., min_length=1, max_length=2000, description="Feed URL")
    feed_type: str = Field(
        default="domain", pattern=r"^(domain|ip)$", description="Indicator type for this feed"
    )
    refresh_interval_minutes: int = Field(
        default=1440, ge=15, le=43200, description="Refresh interval in minutes"
    )


class FeedResponse(BaseModel):
    """Single feed in API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    url: str
    feed_type: str
    enabled: bool
    refresh_interval_minutes: int
    last_fetched_at: datetime | None
    last_fetch_status: str | None
    last_indicator_count: int | None
    created_by: str
    created_at: datetime
    updated_at: datetime
    is_default: bool = False


class FeedListResponse(BaseModel):
    """List of feeds."""

    items: list[FeedResponse]


class FeedUpdate(BaseModel):
    """Request body for updating a threat intel feed."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    url: str | None = Field(default=None, min_length=1, max_length=2000)
    feed_type: str | None = Field(default=None, pattern=r"^(domain|ip)$")
    refresh_interval_minutes: int | None = Field(default=None, ge=15, le=43200)
    enabled: bool | None = None


class BulkIndicatorItem(BaseModel):
    """Single indicator in a bulk import request."""

    indicator_type: str = Field(..., pattern=r"^(domain|ip|pattern)$")
    value: str = Field(..., min_length=1, max_length=500)
    source: str = Field(default="manual-bulk", max_length=255)
    confidence: float = Field(default=0.80, ge=0.0, le=1.0)


class BulkIndicatorCreate(BaseModel):
    """Request body for bulk indicator import."""

    indicators: list[BulkIndicatorItem] = Field(..., min_length=1, max_length=5000)


class BulkIndicatorResponse(BaseModel):
    """Response for bulk indicator import."""

    created: int
    duplicates: int
    errors: int


class MatchResponse(BaseModel):
    """A detection that matched a threat intel indicator."""

    model_config = ConfigDict(from_attributes=True)

    detection_id: int
    title: str
    severity: str
    status: str
    actor: str | None
    org: str | None
    repo: str | None
    triggered_at: datetime
    matched_indicator_value: str | None = None
    matched_indicator_type: str | None = None
    matched_feed_name: str | None = None


class MatchListResponse(BaseModel):
    """Paginated list of threat intel matches."""

    items: list[MatchResponse]
    total: int
    page: int
    page_size: int
    total_24h: int = 0
    unique_indicators: int = 0
    top_feed: str | None = None


class AnalyticsResponse(BaseModel):
    """Aggregate analytics for threat intelligence."""

    total_feeds: int
    active_feeds: int
    total_indicators: int
    active_indicators: int
    matches_30d: int
    coverage_score: float
    matches_over_time: list[dict[str, Any]]
    matches_by_feed: list[dict[str, Any]]
    indicator_type_distribution: list[dict[str, Any]]


class FeedRefreshResponse(BaseModel):
    """Response for manual feed refresh."""

    feed_id: int
    status: str
    indicator_count: int | None = None
    message: str
