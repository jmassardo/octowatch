"""SQLAlchemy ORM models for Copilot governance policies."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.audit_event import Base


class CopilotPolicy(Base):
    """Copilot usage governance policy definition."""

    __tablename__ = "copilot_policies"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    policy_type: Mapped[str] = mapped_column(Text, nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    severity: Mapped[str] = mapped_column(Text, nullable=False, default="medium")
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

    __table_args__ = (Index("idx_copilot_policies_type", "policy_type", "enabled"),)


class CopilotPolicyViolation(Base):
    """Recorded violation of a Copilot governance policy."""

    __tablename__ = "copilot_policy_violations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    policy_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("copilot_policies.id", ondelete="CASCADE"), nullable=False
    )
    actor_login: Mapped[str | None] = mapped_column(Text)
    violation_details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    detection_id: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (Index("idx_copilot_violations_policy", "policy_id", "created_at"),)
