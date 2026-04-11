"""SQLAlchemy ORM model for daily Copilot metrics (TimescaleDB hypertable)."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Integer, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.audit_event import Base


class CopilotDailyMetric(Base):
    """Daily Copilot metric row.

    Each row stores aggregated usage data for a single day, org, metric type,
    language, editor, and model combination.  The ``date`` column is used as
    the TimescaleDB hypertable partition key.
    """

    __tablename__ = "copilot_daily_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    org_slug: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    metric_type: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str | None] = mapped_column(Text, nullable=True)
    editor: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    active_users: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    engaged_users: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_suggestions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_acceptances: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_lines_suggested: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_lines_accepted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    acceptance_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        UniqueConstraint(
            "date",
            "org_slug",
            "metric_type",
            "language",
            "editor",
            "model",
            name="uq_copilot_daily_metrics_composite",
        ),
    )


class CopilotSeatSnapshot(Base):
    """Point-in-time snapshot of a Copilot seat assignment.

    Populated from ``GET /orgs/{org}/copilot/billing/seats``.  Retained for
    historical drilldown and team-level aggregation.
    """

    __tablename__ = "copilot_seat_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    org_slug: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    github_login: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    plan_type: Mapped[str] = mapped_column(Text, nullable=False, default="business")
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_activity_editor: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    pending_cancellation_date: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint(
            "snapshot_date",
            "org_slug",
            "github_login",
            name="uq_copilot_seat_snapshots_composite",
        ),
    )
