"""Pydantic schemas for actor profiles and activity."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ActorProfile(BaseModel):
    """Public actor profile with computed risk and summary stats."""

    login: str
    avatar_url: str
    display_name: str | None = None
    roles: list[str] = []
    org_memberships: list[str] = []
    detection_count: int = 0
    event_count: int = 0
    risk_score: float = 0.0
    risk_level: str = "low"
    first_seen: datetime | None = None
    last_seen: datetime | None = None


class ActorEventResponse(BaseModel):
    """Lightweight event for the actor activity tab."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    action: str
    namespace: str
    org: str | None = None
    repo: str | None = None
    source_ip: str | None = None
    geo_country_code: str | None = None
    geo_city: str | None = None


class ActorEventListResponse(BaseModel):
    items: list[ActorEventResponse]
    total: int
    page: int
    page_size: int
    has_next: bool


class ActorDetectionResponse(BaseModel):
    """Detection summary for the actor detections tab."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    severity: str
    status: str
    triggered_at: datetime
    rule_name: str | None = None
    org: str | None = None
    repo: str | None = None


class ActorDetectionListResponse(BaseModel):
    items: list[ActorDetectionResponse]
    total: int
    page: int
    page_size: int
    has_next: bool


class ActorLocation(BaseModel):
    """Aggregated location with login frequency."""

    country_code: str | None = None
    city: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    event_count: int = 0
    last_seen: datetime | None = None


class ActorLocationsResponse(BaseModel):
    locations: list[ActorLocation]
    total_events: int = 0


class ExecutiveSummary(BaseModel):
    """Executive dashboard summary data."""

    posture_score: float
    posture_score_previous: float
    score_delta: float
    score_delta_pct: float
    detection_trend: dict[str, int]
    severity_breakdown: dict[str, int]
    compliance_summary: list[ComplianceStatusItem]
    top_risks: list[TopRisk]
    month_over_month: MonthOverMonth


class ComplianceStatusItem(BaseModel):
    framework: str
    controls_assessed: int
    controls_with_evidence: int
    compliance_pct: float


class TopRisk(BaseModel):
    title: str
    severity: str
    category: str
    count: int
    actor: str | None = None


class MonthOverMonth(BaseModel):
    current_detections: int
    previous_detections: int
    current_events: int
    previous_events: int
    detection_change_pct: float
    event_change_pct: float


class TimelineEvent(BaseModel):
    """Single event in the detection investigation timeline."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    action: str
    actor: str | None = None
    org: str | None = None
    repo: str | None = None
    source_ip: str | None = None
    geo_country_code: str | None = None
    geo_city: str | None = None
    geo_latitude: float | None = None
    geo_longitude: float | None = None
    data: dict[str, Any] = {}
    is_sequence_step: bool = False
    sequence_index: int | None = None


class DetectionTimeline(BaseModel):
    """Full timeline for a detection investigation."""

    detection_id: int
    detection_title: str
    detection_severity: str
    detection_category: str | None = None
    events: list[TimelineEvent] = []
    sequence_steps: list[str] = []
    context_data: dict[str, Any] = {}
