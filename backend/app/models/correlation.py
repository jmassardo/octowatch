"""SQLAlchemy ORM models for correlation chains and chain memberships."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Double, ForeignKey, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.audit_event import Base


class CorrelationChain(Base):
    """Investigation chain grouping related detections."""

    __tablename__ = "correlation_chains"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="open")
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        onupdate=text("NOW()"),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    assignee: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)

    memberships: Mapped[list[ChainMembership]] = relationship(
        "ChainMembership",
        back_populates="chain",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index("idx_correlation_chains_status", "status"),
        Index("idx_correlation_chains_severity", "severity", "status"),
    )


class ChainMembership(Base):
    """Association between a correlation chain and a detection."""

    __tablename__ = "chain_memberships"

    chain_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("correlation_chains.id", ondelete="CASCADE"),
        primary_key=True,
    )
    detection_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("detections.id", ondelete="CASCADE"),
        primary_key=True,
    )
    correlation_type: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Double, nullable=False, default=0.0)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    chain: Mapped[CorrelationChain] = relationship("CorrelationChain", back_populates="memberships")

    __table_args__ = (Index("idx_chain_memberships_detection", "detection_id"),)
