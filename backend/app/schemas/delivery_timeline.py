"""Pydantic schemas for delivery timeline API responses."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DeliveryTimelineItem(BaseModel):
    """Single delivery timeline record."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    pr_number: int
    repo: str
    org: str
    issue_numbers: list[int]
    backlog_hours: float | None = None
    dev_hours: float | None = None
    review_hours: float | None = None
    deploy_hours: float | None = None
    total_hours: float | None = None
    pr_merged_at: datetime | None = None
    created_at: datetime


class DeliveryTimelineStats(BaseModel):
    """Aggregated delivery timeline statistics."""

    total_prs: int
    avg_backlog_hours: float | None = None
    avg_dev_hours: float | None = None
    avg_review_hours: float | None = None
    avg_deploy_hours: float | None = None
    avg_total_hours: float | None = None
    median_total_hours: float | None = None
    p95_total_hours: float | None = None
    timelines: list[DeliveryTimelineItem]
