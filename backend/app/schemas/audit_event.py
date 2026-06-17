"""Pydantic schemas for audit events."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PaginationMeta(BaseModel):
    total: int
    page: int
    page_size: int
    has_next: bool


class EventListParams(BaseModel):
    """Query parameters for GET /events."""

    model_config = ConfigDict(strict=True)

    org: str | None = Field(
        None,
        max_length=255,
        pattern=r"^[a-zA-Z0-9_.-]+$",
    )
    repo: str | None = Field(None, max_length=512)
    actor: str | None = Field(None, max_length=255)
    action: str | None = Field(None, max_length=100, pattern=r"^[\w.*]+$")
    namespace: str | None = Field(None, max_length=100, pattern=r"^[\w]+$")
    source_ip: str | None = Field(None, max_length=50)
    since: datetime | None = None
    until: datetime | None = None
    actor_is_bot: bool | None = None
    geo_country_code: str | None = Field(None, min_length=2, max_length=2, pattern=r"^[A-Z]{2}$")
    sort: str = Field(
        default="created_at_desc",
        pattern=r"^(created_at|action|actor|repo)_(asc|desc)$",
    )
    page: int = Field(default=1, ge=1, le=10_000)
    page_size: int = Field(default=50, ge=1, le=500)
    cursor: str | None = Field(
        None, max_length=100, description="Opaque cursor for keyset pagination"
    )


class EventResponse(BaseModel):
    """Single audit event as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: str
    created_at: datetime
    ingested_at: datetime
    action: str
    namespace: str
    actor: str | None
    actor_id: int | None
    actor_is_bot: bool
    org: str | None
    org_id: int | None
    repo: str | None
    repo_id: int | None
    business: str | None
    source_ip: str | None
    user_agent: str | None
    geo_country_code: str | None
    geo_city: str | None
    geo_is_proxy: bool | None
    data: dict[str, Any]
    ingestion_source: str
    source_file_path: str

    @field_validator("source_ip", mode="before")
    @classmethod
    def _coerce_ip_to_str(cls, v: Any) -> str | None:
        return str(v) if v is not None else None


class EventListResponse(BaseModel):
    items: list[EventResponse]
    total: int
    page: int
    page_size: int
    has_next: bool
    count_is_estimated: bool = False
    next_cursor: str | None = None
