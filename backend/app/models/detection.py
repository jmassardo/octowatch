"""SQLAlchemy ORM models for detections, rules, suppressions, and baselines."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.models.correlation import ChainMembership, CorrelationChain
    from app.models.integration import Ticket

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Double,
    ForeignKey,
    Index,
    Integer,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.audit_event import Base


class RuleDefinition(Base):
    """Detection rule definition (source of truth; versioned via rule_versions)."""

    __tablename__ = "rule_definitions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    default_severity: Mapped[str] = mapped_column(Text, nullable=False)
    default_confidence: Mapped[str] = mapped_column(Text, nullable=False)
    logic_type: Mapped[str] = mapped_column(Text, nullable=False)
    logic_config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    mode: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    git_commit_sha: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    updated_by: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        onupdate=text("NOW()"),
    )
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'manual'"))
    campaign_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("threat_intel_campaigns.id", ondelete="SET NULL"), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    versions: Mapped[list[RuleVersion]] = relationship(
        "RuleVersion", back_populates="rule", cascade="all, delete-orphan"
    )
    detections: Mapped[list[Detection]] = relationship("Detection", back_populates="rule")

    __table_args__ = (
        Index("idx_rules_enabled", "enabled", "status"),
        Index("idx_rules_category", "category"),
        Index(
            "idx_rules_campaign_enabled",
            "campaign_id",
            "enabled",
            "status",
            postgresql_where=text("campaign_id IS NOT NULL"),
        ),
    )


class RuleVersion(Base):
    """Immutable snapshot of a rule at each version."""

    __tablename__ = "rule_versions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    rule_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("rule_definitions.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    logic_config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    change_summary: Mapped[str | None] = mapped_column(Text)
    changed_by: Mapped[str] = mapped_column(Text, nullable=False)
    git_commit_sha: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    rule: Mapped[RuleDefinition] = relationship("RuleDefinition", back_populates="versions")


class DetectionSuppression(Base):
    """Analyst-authored suppression rules."""

    __tablename__ = "detection_suppressions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    rule_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("rule_definitions.id"), nullable=True
    )
    suppress_actor: Mapped[str | None] = mapped_column(Text)
    suppress_org: Mapped[str | None] = mapped_column(Text)
    suppress_repo: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        onupdate=text("NOW()"),
    )

    __table_args__ = (
        Index(
            "idx_suppressions_active",
            "active",
            "expires_at",
            postgresql_where=Column("active").is_(True),
        ),
    )


class Detection(Base):
    """One row per detected threat finding."""

    __tablename__ = "detections"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    rule_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("rule_definitions.id"), nullable=False
    )
    rule_version: Mapped[int] = mapped_column(Integer, nullable=False)
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[str] = mapped_column(Text, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Double, nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="open")
    is_dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    assigned_to: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str | None] = mapped_column(Text)
    org: Mapped[str | None] = mapped_column(Text)
    repo: Mapped[str | None] = mapped_column(Text)
    source_ip: Mapped[str | None] = mapped_column(INET)
    event_ids: Mapped[list[int]] = mapped_column(ARRAY(BigInteger), nullable=False, default=list)
    context_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[str | None] = mapped_column(Text)
    resolution_note: Mapped[str | None] = mapped_column(Text)
    suppressed_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("detection_suppressions.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        onupdate=text("NOW()"),
    )
    campaign_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("threat_intel_campaigns.id", ondelete="SET NULL"), nullable=True
    )

    rule: Mapped[RuleDefinition] = relationship("RuleDefinition", back_populates="detections")

    @property
    def rule_name(self) -> str | None:
        return self.rule.name if self.rule else None

    @property
    def rule_category(self) -> str | None:
        return self.rule.category if self.rule else None

    @property
    def rule_description(self) -> str | None:
        return self.rule.description if self.rule else None

    chain_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("correlation_chains.id", ondelete="SET NULL"), nullable=True
    )

    tickets: Mapped[list[Ticket]] = relationship(
        "Ticket",
        back_populates="detection",
        lazy="selectin",
    )
    chain: Mapped[CorrelationChain | None] = relationship(
        "CorrelationChain",
        foreign_keys=[chain_id],
        lazy="selectin",
    )
    chain_memberships: Mapped[list[ChainMembership]] = relationship(
        "ChainMembership",
        foreign_keys="ChainMembership.detection_id",
        lazy="selectin",
    )

    __table_args__ = (
        Index("idx_detections_status", "status", "triggered_at"),
        Index("idx_detections_severity", "severity", "status", "triggered_at"),
        Index("idx_detections_rule", "rule_id", "triggered_at"),
        Index("idx_detections_is_dry_run", "is_dry_run"),
        Index("idx_detections_chain_id", "chain_id"),
    )


class SeverityConfig(Base):
    """Per-action-pattern severity overrides configured in admin portal."""

    __tablename__ = "severity_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action_pattern: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    default_severity: Mapped[str] = mapped_column(Text, nullable=False)
    custom_severity: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    updated_by: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        onupdate=text("NOW()"),
    )


class BehavioralBaseline(Base):
    """Rolling statistical baselines for behavioral anomaly detection."""

    __tablename__ = "behavioral_baselines"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    baseline_type: Mapped[str] = mapped_column(Text, nullable=False)
    scope_key: Mapped[str] = mapped_column(Text, nullable=False)
    metric_name: Mapped[str] = mapped_column(Text, nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    mean: Mapped[float] = mapped_column(Double, nullable=False)
    stddev: Mapped[float] = mapped_column(Double, nullable=False, default=0.0)
    p95: Mapped[float] = mapped_column(Double, nullable=False)
    p99: Mapped[float] = mapped_column(Double, nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    push_bypass_hourly_mean: Mapped[float | None] = mapped_column(Double)
    push_bypass_hourly_stddev: Mapped[float | None] = mapped_column(Double)
    alert_dismiss_daily_mean: Mapped[float | None] = mapped_column(Double)
    alert_dismiss_daily_stddev: Mapped[float | None] = mapped_column(Double)
    admin_action_daily_mean: Mapped[float | None] = mapped_column(Double)
    admin_action_daily_stddev: Mapped[float | None] = mapped_column(Double)

    __table_args__ = (
        Index(
            "idx_baselines_lookup",
            "baseline_type",
            "scope_key",
            "metric_name",
            "window_end",
        ),
    )
