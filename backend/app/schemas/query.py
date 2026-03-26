"""Pydantic schemas for self-service query endpoint."""

from __future__ import annotations

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
    description: str | None
    sql: str
    created_by: str
    created_at: str


class QueryTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=1000)
    sql: str = Field(..., min_length=10, max_length=50_000)
