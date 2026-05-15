"""Pydantic schemas for the custom dashboard configuration endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ─── Widget layout item ──────────────────────────────────────────────────────


class WidgetLayoutItem(BaseModel):
    """A single widget's position and size within the grid."""

    model_config = ConfigDict(from_attributes=True)

    widget_id: str = Field(..., min_length=1, max_length=120, description="Widget identifier")
    x: int = Field(0, ge=0, description="Grid column offset")
    y: int = Field(0, ge=0, description="Grid row offset")
    w: int = Field(4, ge=1, le=12, description="Width in grid columns")
    h: int = Field(3, ge=1, le=12, description="Height in grid rows")


# ─── Dashboard config ────────────────────────────────────────────────────────


class DashboardConfigResponse(BaseModel):
    """Response for GET /dashboard/config."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    layout: list[dict[str, Any]]
    persona: str
    created_at: datetime
    updated_at: datetime


class DashboardConfigUpdate(BaseModel):
    """Request body for PUT /dashboard/config."""

    layout: list[WidgetLayoutItem] = Field(
        default_factory=list,
        max_length=50,
        description="Ordered list of widget positions",
    )
    persona: str = Field(
        "",
        pattern=r"^(security-analyst|engineering-manager|platform-engineer|executive|)$",
        description="Selected persona",
    )


# ─── Widget catalog ──────────────────────────────────────────────────────────


class WidgetInfo(BaseModel):
    """A single available widget in the catalog."""

    id: str
    title: str
    description: str
    category: str
    default_w: int = Field(4, ge=1, le=12)
    default_h: int = Field(3, ge=1, le=12)


class WidgetCatalogResponse(BaseModel):
    """Response for GET /dashboard/widgets."""

    widgets: list[WidgetInfo]


# ─── Persona definitions ─────────────────────────────────────────────────────


class PersonaInfo(BaseModel):
    """A persona with its recommended default layout."""

    id: str
    label: str
    description: str
    default_layout: list[WidgetLayoutItem]


class PersonaListResponse(BaseModel):
    """Response for GET /dashboard/personas."""

    personas: list[PersonaInfo]
