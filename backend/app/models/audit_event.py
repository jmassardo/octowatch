"""SQLAlchemy ORM models for audit events and deduplication tables."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Index,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class AuditEvent(Base):
    """Normalized audit event (TimescaleDB hypertable, weekly chunks)."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, primary_key=True
    )
    document_id: Mapped[str] = mapped_column(Text, nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    # namespace is a generated column (split_part(action, '.', 1)) — read-only in ORM
    namespace: Mapped[str] = mapped_column(Text, nullable=False)

    # Actor
    actor: Mapped[str | None] = mapped_column(Text)
    actor_id: Mapped[int | None] = mapped_column(BigInteger)
    actor_is_bot: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Org/repo scope
    org: Mapped[str | None] = mapped_column(Text)
    org_id: Mapped[int | None] = mapped_column(BigInteger)
    repo: Mapped[str | None] = mapped_column(Text)
    repo_id: Mapped[int | None] = mapped_column(BigInteger)
    business: Mapped[str | None] = mapped_column(Text)
    business_id: Mapped[int | None] = mapped_column(BigInteger)

    # Network
    source_ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)

    # GeoIP
    geo_country_code: Mapped[str | None] = mapped_column(Text)
    geo_city: Mapped[str | None] = mapped_column(Text)
    geo_latitude: Mapped[float | None] = mapped_column()
    geo_longitude: Mapped[float | None] = mapped_column()
    geo_is_proxy: Mapped[bool | None] = mapped_column(Boolean)

    # Payload
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    # Ingestion metadata
    ingestion_source: Mapped[str] = mapped_column(Text, nullable=False)
    source_file_path: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        Index("idx_events_actor", "actor", "created_at"),
        Index("idx_events_org", "org", "created_at"),
        Index("idx_events_namespace", "namespace", "created_at"),
        Index("idx_events_action", "action", "created_at"),
    )


class EventDedup(Base):
    """Global deduplication lookup table for TimescaleDB cross-chunk dedup."""

    __tablename__ = "event_dedup"

    document_id: Mapped[str] = mapped_column(Text, primary_key=True)
    event_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )


class EventRawPayload(Base):
    """Stores the complete unmodified JSON for each event."""

    __tablename__ = "event_raw_payloads"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    source_file: Mapped[str] = mapped_column(Text, nullable=False)
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    event_id: Mapped[int | None] = mapped_column(BigInteger)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        Index(
            "idx_raw_payloads_event_id",
            "event_id",
            postgresql_where=Column("event_id").isnot(None),
        ),
    )
