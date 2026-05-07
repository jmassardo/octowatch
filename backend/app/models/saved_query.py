"""SQLAlchemy ORM model for user-saved queries."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.audit_event import Base


class SavedQuery(Base):
    """A user-saved SQL query with optional sharing and scheduling.

    Supports tagging, sharing with specific users, and lightweight
    cron-based scheduling metadata.
    """

    __tablename__ = "saved_queries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sql_text: Mapped[str] = mapped_column(Text, nullable=False)
    owner_login: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    is_shared: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    shared_with: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    schedule_cron: Mapped[str | None] = mapped_column(Text, nullable=True)
    schedule_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        onupdate=text("NOW()"),
    )
