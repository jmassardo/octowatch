"""SQLAlchemy ORM model for per-organization configuration."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, Numeric, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.audit_event import Base


class OrgConfig(Base):
    """Per-organization configuration overrides.

    Each row stores configuration for a single GitHub organization.
    ``copilot_cost_per_seat`` allows orgs to override the global default
    cost-per-seat ($19) used in Copilot and License Health cost calculations.
    A ``NULL`` value means "use the global default".
    """

    __tablename__ = "org_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    copilot_cost_per_seat: Mapped[float | None] = mapped_column(
        Numeric(precision=10, scale=2), nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()"),
        onupdate=text("NOW()")
    )
