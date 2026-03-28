"""ORM model for threat intelligence domains."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Double, Index, Text, text
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
