"""SQLAlchemy model for user dashboard configuration."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.audit_event import Base


class UserDashboardConfig(Base):
    """Persisted per-user custom dashboard layout and persona selection."""

    __tablename__ = "user_dashboard_configs"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        comment="Unique config identifier",
    )
    user_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
        comment="GitHub login of the owning user",
    )
    layout: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="[]",
        comment="Widget positions, sizes, and configurations",
    )
    persona: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        server_default=text("''"),
        comment="Selected persona",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )
