"""Pydantic schemas for setup wizard and admin settings endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SetupLoginRequest(BaseModel):
    """Payload for ``POST /setup/login``."""

    token: str = Field(..., min_length=1)


class GitHubOAuthSetup(BaseModel):
    """Payload for ``POST /setup/github-oauth``."""

    client_id: str = Field(..., min_length=1)
    client_secret: str = Field(..., min_length=1)


class GitHubAppSetup(BaseModel):
    """Payload for ``POST /setup/github-app``."""

    app_id: str = Field(..., min_length=1)
    private_key_pem: str = Field(..., min_length=100)
    enterprise_slug: str = Field(..., min_length=1, pattern=r"^[a-zA-Z0-9-]+$")
    sync_enabled: bool = True
    sync_interval_days: int = Field(default=1, ge=1, le=90)
    sync_orgs: str = ""


class TLSSetup(BaseModel):
    """Payload for ``POST /setup/tls``."""

    cert_pem: str = Field(
        default="",
        description="PEM certificate. If empty, generates self-signed.",
    )
    key_pem: str = Field(default="", description="PEM private key.")
    generate_self_signed: bool = False


class SettingUpdate(BaseModel):
    """Payload for ``PUT /admin/settings/{key}``."""

    value: str = Field(..., min_length=0)
    category: str | None = None
    sensitivity: str | None = None
    description: str | None = None


class SetupStatusResponse(BaseModel):
    """Response for ``GET /setup/status``."""

    setup_required: bool
    setup_hint: str = "Check container logs"


class SettingResponse(BaseModel):
    """Single setting item in API responses (value is masked)."""

    model_config = ConfigDict(from_attributes=True)

    key: str
    value: str
    category: str
    sensitivity: str
    description: str | None = None
    updated_by: str
    updated_at: datetime


class AuditTrailEntry(BaseModel):
    """Single entry in the settings audit trail."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    setting_key: str
    action: str
    changed_by: str
    old_value_masked: str | None = None
    new_value_masked: str | None = None
    created_at: datetime
