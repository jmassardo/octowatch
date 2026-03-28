"""ORM model for system health events."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.audit_event import Base


class SystemHealthEvent(Base):
    """Internal OctoWatch monitoring signal stored in a TimescaleDB hypertable."""

    __tablename__ = "system_health_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, server_default=text("NOW()")
    )
    org: Mapped[str | None] = mapped_column(Text, nullable=True)
    signal_type: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_system_health_org", "org", occurred_at.desc()),
        Index(
            "idx_system_health_unresolved",
            "signal_type",
            "resolved_at",
            postgresql_where=text("resolved_at IS NULL"),
        ),
    )
