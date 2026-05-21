"""SQLAlchemy ORM model for delivery timeline enrichment."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.audit_event import Base


class DeliveryTimeline(Base):
    """Enriched delivery timeline linking PRs to issues and CI runs.

    Each row represents a merged pull request with computed phase durations
    from the software delivery lifecycle: backlog → development → review → deploy.
    """

    __tablename__ = "delivery_timelines"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    pr_number: Mapped[int] = mapped_column(Integer, nullable=False)
    repo: Mapped[str] = mapped_column(Text, nullable=False)
    org: Mapped[str] = mapped_column(Text, nullable=False)
    issue_numbers: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), nullable=False, server_default=text("'{}'")
    )
    backlog_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    dev_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    review_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    deploy_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    merge_commit_sha: Mapped[str | None] = mapped_column(Text, nullable=True)
    pr_merged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ci_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        Index("idx_delivery_timelines_org_repo", "org", "repo"),
        Index("idx_delivery_timelines_pr", "org", "repo", "pr_number", unique=True),
        Index("idx_delivery_timelines_created", "created_at"),
    )
