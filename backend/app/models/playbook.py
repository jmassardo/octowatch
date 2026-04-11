"""SQLAlchemy ORM models for incident response playbooks."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.audit_event import Base


class PlaybookTemplate(Base):
    """Reusable incident response playbook template."""

    __tablename__ = "playbook_templates"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    detection_categories: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list
    )
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        onupdate=text("NOW()"),
    )

    executions: Mapped[list[PlaybookExecution]] = relationship(
        "PlaybookExecution", back_populates="template", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("idx_playbook_templates_slug", "slug"),)


class PlaybookExecution(Base):
    """Tracks execution of a playbook against a specific detection."""

    __tablename__ = "playbook_executions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    template_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("playbook_templates.id", ondelete="CASCADE"), nullable=False
    )
    detection_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("detections.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    step_results: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    started_by: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    template: Mapped[PlaybookTemplate] = relationship(
        "PlaybookTemplate", back_populates="executions"
    )

    __table_args__ = (
        Index("idx_playbook_executions_detection", "detection_id"),
        Index("idx_playbook_executions_status", "status"),
    )
