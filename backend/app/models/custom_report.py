"""SQLAlchemy model for user-created custom report definitions."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.audit_event import Base


class CustomReport(Base):
    """Persisted definition of a user-created custom report."""

    __tablename__ = "custom_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="Report display name")
    description: Mapped[str | None] = mapped_column(Text, comment="Optional description")
    owner_login: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="GitHub login of the owner"
    )
    data_sources: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default="{}",
        comment="Data sources: events, detections, posture, copilot, workflows, users",
    )
    columns: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="[]",
        comment="Column definitions: [{field, label, visible}]",
    )
    filters: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="[]",
        comment="Filter definitions: [{field, operator, value}]",
    )
    grouping: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
        comment="Grouping config: {group_by, time_bucket}",
    )
    visualization: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        server_default=text("'table'"),
        comment="Visualization type: table, table_chart, chart",
    )
    is_shared: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    shared_with: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="[]",
        comment="List of GitHub logins this report is shared with",
    )
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="When the report was last executed"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
