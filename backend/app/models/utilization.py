"""SQLAlchemy ORM model for utilization facts."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, Index, Integer, Numeric, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.audit_event import Base


class UtilizationFact(Base):
    """Daily pre-aggregated per-user per-feature utilization metrics."""

    __tablename__ = "utilization_facts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    org_slug: Mapped[str] = mapped_column(Text, nullable=False)
    actor_login: Mapped[str] = mapped_column(Text, nullable=False)
    feature_area: Mapped[str] = mapped_column(Text, nullable=False)
    metric_date: Mapped[date] = mapped_column(Date, nullable=False)
    actions_minutes: Mapped[float | None] = mapped_column(Numeric)
    actions_runs: Mapped[int | None] = mapped_column(Integer)
    copilot_suggestions: Mapped[int | None] = mapped_column(Integer)
    copilot_acceptances: Mapped[int | None] = mapped_column(Integer)
    copilot_credits: Mapped[float | None] = mapped_column(Numeric)
    ghas_alerts_dismissed: Mapped[int | None] = mapped_column(Integer)
    git_clones: Mapped[int | None] = mapped_column(Integer)
    git_pushes: Mapped[int | None] = mapped_column(Integer)
    packages_published: Mapped[int | None] = mapped_column(Integer)
    storage_bytes: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        Index("idx_utilization_facts_org_actor", "org_slug", "actor_login", "metric_date"),
        Index("idx_utilization_facts_feature", "feature_area", "metric_date"),
    )
