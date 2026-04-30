"""Pydantic schemas for admin authentication settings API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

# ──────── Auth Method ────────


class AuthMethodRead(BaseModel):
    """Read-only representation of an auth method row."""

    id: int
    method_name: str
    display_name: str
    enabled: bool
    config_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AuthMethodUpdate(BaseModel):
    """Partial update payload for toggling / configuring an auth method."""

    enabled: bool | None = None
    config_json: dict[str, Any] | None = None


# ──────── SAML Test ────────


class SAMLTestResult(BaseModel):
    """Result of a SAML connection test."""

    success: bool
    message: str
    details: dict[str, Any] | None = None


# ──────── Session Policy ────────


class SessionPolicyRead(BaseModel):
    """Read-only representation of a session policy row."""

    id: int
    policy_key: str
    policy_value: str
    description: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SessionPolicyUpdate(BaseModel):
    """Partial update payload for a session policy."""

    policy_value: str = Field(..., min_length=1, max_length=256)
    description: str | None = None
