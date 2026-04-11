"""SQLAlchemy model for scheduled report delivery."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.models.audit_event import Base


class ReportSchedule(Base):
    """Persisted schedule for automated report generation and delivery."""

    __tablename__ = "report_schedules"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    report_type: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="soc2, iso27001, nist-csf, or metric report type"
    )
    org: Mapped[str | None] = mapped_column(Text)
    cron_expression: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="Cron expression, e.g. '0 8 1 * *'"
    )
    export_format: Mapped[str] = mapped_column(
        String(10), nullable=False, default="html", comment="pdf, html, xlsx, csv"
    )
    recipients: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, comment="Email addresses"
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[str | None] = mapped_column(String(20), comment="success or failed")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
