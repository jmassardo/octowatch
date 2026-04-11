"""ORM models for threat intelligence domains, indicators, and feeds."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Double, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.audit_event import Base


class ThreatIntelDomain(Base):
    """Known malicious or suspicious domain for webhook/integration URL matching."""

    __tablename__ = "threat_intel_domains"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    domain: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Double, nullable=False, server_default=text("0.80"))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("TRUE"))
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    added_by: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("idx_threat_intel_active", "active", "domain"),)


class ThreatIntelIndicator(Base):
    """Generic threat intelligence indicator supporting domain, IP, and pattern types."""

    __tablename__ = "threat_intel_indicators"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    indicator_type: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Double, nullable=False, server_default=text("0.80"))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("TRUE"))
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    added_by: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    feed_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    metadata_json: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index("idx_indicators_type_value", "indicator_type", "value"),
        Index(
            "idx_indicators_active",
            "active",
            "indicator_type",
            postgresql_where=text("active = TRUE"),
        ),
    )


class ThreatIntelFeed(Base):
    """Configuration for an external threat intelligence feed."""

    __tablename__ = "threat_intel_feeds"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    feed_type: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'domain'"))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("TRUE"))
    refresh_interval_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1440")
    )
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_fetch_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_indicator_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )
