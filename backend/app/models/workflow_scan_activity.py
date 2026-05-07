"""SQLAlchemy ORM model for workflow scan activity provenance."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, Text, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.models.audit_event import Base


class WorkflowScanActivity(Base):
    """Records provenance for each workflow security scan execution."""

    __tablename__ = "workflow_scan_activities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trigger_event_ids: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), nullable=False, default=list
    )
    org: Mapped[str] = mapped_column(Text, nullable=False)
    repo: Mapped[str] = mapped_column(Text, nullable=False)
    workflow_path: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'pending'"))
    checks_performed: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    findings_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    data_sources: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
