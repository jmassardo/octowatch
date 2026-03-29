"""Pydantic schemas for organization configuration endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class OrgConfigResponse(BaseModel):
    """Response schema for GET /api/v1/orgs/{org_slug}/config."""

    org_slug: str
    copilot_cost_per_seat: float = Field(
        default=19.0,
        description="Cost per Copilot seat per month. Falls back to 19 when not configured.",
    )

    model_config = {"from_attributes": True}


class OrgConfigUpdate(BaseModel):
    """Request schema for PATCH /api/v1/orgs/{org_slug}/config."""

    copilot_cost_per_seat: float | None = Field(
        default=None,
        ge=0,
        description="Cost per Copilot seat per month. Set to null to reset to default (19).",
    )
