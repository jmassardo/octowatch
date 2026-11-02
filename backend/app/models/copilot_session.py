"""SQLAlchemy ORM models for Copilot Chat session analytics (#387, #505).

Schema-only models for Phase 1 of the Copilot sessions design in #387.
Ingestion, API, and frontend wiring are tracked separately in #507, #508,
and #510 and are intentionally not implemented here.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.audit_event import Base


class CopilotSession(Base):
    """One row per Copilot Chat session.

    A TimescaleDB hypertable partitioned on ``created_at`` (weekly chunks).
    TimescaleDB requires unique constraints on a hypertable to include the
    partitioning column, so ``session_id`` uniqueness is enforced via
    ``UNIQUE (session_id, created_at)`` rather than a bare unique constraint
    on ``session_id`` alone. See the 0073 migration docstring for details.
    """

    __tablename__ = "copilot_sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, nullable=False
    )
    session_id: Mapped[str] = mapped_column(Text, nullable=False)
    enterprise: Mapped[str] = mapped_column(Text, nullable=False)
    org: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    actor_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    editor: Mapped[str | None] = mapped_column(Text, nullable=True)
    editor_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    copilot_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str | None] = mapped_column(Text, nullable=True)
    repository: Mapped[str | None] = mapped_column(Text, nullable=True)
    turn_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tool_call_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens_in: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    total_tokens_out: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    ingestion_source: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("session_id", "created_at", name="uq_copilot_sessions_session_id"),
        Index("idx_copilot_sessions_org", "org", "created_at"),
        Index("idx_copilot_sessions_actor", "actor", "created_at"),
    )


class CopilotSessionTurn(Base):
    """One row per prompt/response turn within a Copilot session.

    ``session_id`` references ``CopilotSession.session_id`` by convention,
    not a database-enforced foreign key: TimescaleDB only allows a unique
    constraint on ``copilot_sessions`` that includes ``created_at``, and this
    table does not share that column, so Postgres cannot target it with a
    ``FOREIGN KEY``. See the 0073 migration docstring for details.
    """

    __tablename__ = "copilot_session_turns"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(Text, nullable=False)
    turn_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    prompt_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    finish_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tool_calls: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    references: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    annotations: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    org: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("idx_copilot_session_turns_session_id", "session_id", "turn_index"),
        Index("idx_copilot_session_turns_org", "org", "created_at"),
        Index("idx_copilot_session_turns_created", "created_at"),
    )


class CopilotSessionToolCall(Base):
    """One row per tool invocation within a Copilot session turn.

    ``session_id`` references ``CopilotSession.session_id`` by convention,
    not a database-enforced foreign key, for the same reason documented on
    :class:`CopilotSessionTurn`.
    """

    __tablename__ = "copilot_session_tool_calls"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(Text, nullable=False)
    turn_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tool_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_input: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    tool_output_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    success: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    org: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("idx_copilot_session_tool_calls_session_id", "session_id", "turn_index"),
        Index("idx_copilot_session_tool_calls_org", "org", "created_at"),
        Index("idx_copilot_session_tool_calls_created", "created_at"),
    )
