"""SQLAlchemy ORM models for detection-triggered automation."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.audit_event import Base


class AutomationTarget(Base):
    """A configured automation destination (webhook URL or repository_dispatch)."""

    __tablename__ = "automation_targets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # "webhook" or "repository_dispatch"
    target_type: Mapped[str] = mapped_column(Text, nullable=False)

    # Webhook fields
    webhook_url: Mapped[str | None] = mapped_column(Text)
    webhook_secret: Mapped[str | None] = mapped_column(Text)  # encrypted at rest
    webhook_headers: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    # Repository dispatch fields
    dispatch_repo: Mapped[str | None] = mapped_column(Text)  # "owner/repo"
    dispatch_event_type: Mapped[str | None] = mapped_column(Text)  # custom event_type string
    dispatch_token_env_var: Mapped[str | None] = mapped_column(Text)  # env var holding PAT/token

    # Filtering: which detections trigger this target
    rule_ids: Mapped[list[int] | None] = mapped_column(ARRAY(BigInteger), nullable=True)
    rule_categories: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    severity_filter: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    org_filter: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    is_catch_all: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Rate limiting
    rate_limit_per_minute: Mapped[int] = mapped_column(Integer, nullable=False, default=100)

    # Config
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
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

    deliveries: Mapped[list[AutomationDelivery]] = relationship(
        "AutomationDelivery", back_populates="target", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("idx_automation_targets_enabled", "enabled", "target_type"),)


class AutomationDelivery(Base):
    """Tracks each delivery attempt for an automation target."""

    __tablename__ = "automation_deliveries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    target_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("automation_targets.id", ondelete="CASCADE"), nullable=False
    )
    detection_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("detections.id", ondelete="CASCADE"), nullable=False
    )

    # Delivery status
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="pending"
    )  # pending, success, failed, retrying
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Response tracking
    response_code: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[str | None] = mapped_column(Text)  # truncated to 1KB
    error_message: Mapped[str | None] = mapped_column(Text)

    # Payload reference (hash for dedup, not full payload)
    payload_hash: Mapped[str | None] = mapped_column(Text)

    # Dry run flag
    is_dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    target: Mapped[AutomationTarget] = relationship("AutomationTarget", back_populates="deliveries")

    __table_args__ = (
        Index("idx_automation_deliveries_target", "target_id", "created_at"),
        Index("idx_automation_deliveries_detection", "detection_id"),
        Index("idx_automation_deliveries_status", "status", "next_retry_at"),
    )
