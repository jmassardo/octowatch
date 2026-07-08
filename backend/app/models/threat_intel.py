"""ORM models for threat intelligence domains, indicators, feeds, and campaigns."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, Double, ForeignKey, Index, Integer, Text, text
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
    campaign_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("threat_intel_campaigns.id", ondelete="SET NULL"), nullable=True
    )
    metadata_json: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index("idx_indicators_type_value", "indicator_type", "value"),
        Index(
            "idx_indicators_active",
            "active",
            "indicator_type",
            postgresql_where=text("active = TRUE"),
        ),
        Index(
            "idx_indicators_campaign_active",
            "campaign_id",
            "active",
            postgresql_where=text("campaign_id IS NOT NULL"),
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
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("FALSE"))
    parser_type: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'plaintext'")
    )
    parser_config: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    auto_rule_generation: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("TRUE")
    )
    default_campaign_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("threat_intel_campaigns.id", ondelete="SET NULL"), nullable=True
    )


class ThreatIntelCampaign(Base):
    """A named threat campaign grouping related indicators and detections."""

    __tablename__ = "threat_intel_campaigns"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    severity: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'critical'"))
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'active'"))
    source_feed_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("threat_intel_feeds.id", ondelete="SET NULL"), nullable=True
    )
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    indicator_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    __table_args__ = (Index("idx_campaigns_status", "status"),)
