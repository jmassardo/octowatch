"""SQLAlchemy ORM model for per-user Copilot usage reports (UBB billing data)."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.audit_event import Base


class CopilotUsageReport(Base):
    """Per-user daily Copilot usage with AI credit consumption.

    Populated from ``GET /enterprises/{enterprise}/copilot/usage`` or the
    per-org equivalent.  Used for User-Based Billing (UBB) budgeting and
    accurate adoption tier classification.
    """

    __tablename__ = "copilot_usage_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    org_slug: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    github_login: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    total_credits_consumed: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    completions_credits: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    chat_credits: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    pr_credits: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    other_credits: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    budget_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    budget_consumed: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        UniqueConstraint(
            "report_date",
            "org_slug",
            "github_login",
            name="uq_copilot_usage_composite",
        ),
    )
