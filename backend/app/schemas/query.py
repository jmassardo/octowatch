"""Pydantic schemas for self-service query endpoint."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class QueryRunRequest(BaseModel):
    """Request body for POST /query/run."""

    sql: str = Field(
        ...,
        min_length=10,
        max_length=50_000,
        description="SELECT-only SQL query to execute against the event store.",
    )
    org: str | None = Field(
        None,
        max_length=255,
        pattern=r"^[a-zA-Z0-9_.-]+$",
        description="Optional org to narrow query scope.",
    )
    format: str = Field(
        default="json",
        pattern=r"^(json|csv)$",
    )


class QueryRunResponse(BaseModel):
    """Response for POST /query/run."""

    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    execution_ms: int
    query_id: str


class QueryTemplate(BaseModel):
    """Saved query template."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    sql: str
    created_by: str | None = None
    org_slug: str | None = None
    created_at: datetime
    updated_at: datetime | None = None


class QueryTemplateCreate(BaseModel):
    """Request body for creating a query template."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=1000)
    sql: str = Field(..., min_length=10, max_length=50_000)
    org_slug: str | None = Field(None, max_length=255)


# ── Saved Queries ─────────────────────────────────────────────────────────────


class SavedQueryCreate(BaseModel):
    """Request body for saving a query."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=2000)
    sql_text: str = Field(..., min_length=10, max_length=50_000)
    tags: list[str] | None = Field(None, max_length=20)


class SavedQueryUpdate(BaseModel):
    """Request body for updating a saved query."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=2000)
    sql_text: str | None = Field(None, min_length=10, max_length=50_000)
    tags: list[str] | None = None


class SavedQueryResponse(BaseModel):
    """Response schema for a saved query."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    sql_text: str
    owner_login: str
    is_shared: bool = False
    shared_with: list[str] | None = None
    tags: list[str] | None = None
    schedule_cron: str | None = None
    schedule_enabled: bool = False
    last_run_at: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None


class ShareQueryRequest(BaseModel):
    """Request body for sharing a query with other users."""

    logins: list[str] = Field(..., min_length=1, max_length=50)


class ScheduleQueryRequest(BaseModel):
    """Request body for scheduling a saved query."""

    cron: str = Field(..., min_length=5, max_length=100)
    enabled: bool = True


class SchemaColumn(BaseModel):
    """A column in a database table schema."""

    name: str
    type: str


class SchemaTable(BaseModel):
    """A table in the database schema with its columns."""

    table: str
    columns: list[SchemaColumn]
