"""Standardized error response schemas."""

from __future__ import annotations

from pydantic import BaseModel


class ErrorDetail(BaseModel):
    """Individual validation error detail."""

    field: str
    message: str
    type: str


class ErrorBody(BaseModel):
    """Error response body."""

    code: str
    message: str
    request_id: str | None = None
    details: list[ErrorDetail] | None = None


class ErrorResponse(BaseModel):
    """Top-level error response envelope."""

    error: ErrorBody
