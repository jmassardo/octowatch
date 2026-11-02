"""Add Copilot session tables (schema + ORM models only, #505).

Adds three new tables for Copilot Chat session analytics, as designed in
#387 (Phase 1 — schema only, no ingestion/API/frontend work):

- ``copilot_sessions``: one row per Copilot session, a TimescaleDB hypertable
  partitioned on ``created_at`` with weekly chunks (mirrors the ``events``
  table pattern in 0001_initial_schema.py).
- ``copilot_session_turns``: one row per prompt/response turn in a session.
- ``copilot_session_tool_calls``: one row per tool invocation within a turn.

Note on ``session_id`` uniqueness: TimescaleDB requires that any unique
constraint (including the primary key) on a hypertable include the
partitioning column. Since ``copilot_sessions`` is partitioned on
``created_at``, the "session_id NOT NULL UNIQUE" requirement from #387 is
implemented as ``UNIQUE (session_id, created_at)`` rather than a bare unique
constraint on ``session_id`` alone (verified against timescaledb:2.25.1-pg16:
a plain ``UNIQUE (session_id)`` is rejected with "cannot create a unique
index without the column \"created_at\" (used in partitioning)"). As a
consequence, ``copilot_session_turns.session_id`` and
``copilot_session_tool_calls.session_id`` are plain indexed TEXT columns
referencing ``copilot_sessions.session_id`` by convention rather than a
database-enforced ``FOREIGN KEY``, since Postgres foreign keys must target an
exact column-for-column unique constraint on the parent and the two child
tables do not share ``copilot_sessions.created_at``. Referential integrity
for this relationship is maintained at the application layer, consistent
with how other hypertables in this schema (e.g. ``events``) are not
FK-referenced by child tables.

Revision ID: 0073
Revises: 0072
Create Date: 2026-11-02 00:00:00.000000+00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "0073"
down_revision = "0072"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ─── copilot_sessions (TimescaleDB hypertable) ─────────────────────────
    op.execute("""
        CREATE TABLE copilot_sessions (
            id                BIGINT GENERATED ALWAYS AS IDENTITY,
            created_at        TIMESTAMPTZ NOT NULL,
            session_id        TEXT        NOT NULL,
            enterprise        TEXT        NOT NULL,
            org               TEXT,
            actor             TEXT        NOT NULL,
            actor_id          BIGINT,
            editor            TEXT,
            editor_version    TEXT,
            copilot_version   TEXT,
            model             TEXT,
            language          TEXT,
            repository        TEXT,
            turn_count        INTEGER,
            tool_call_count   INTEGER,
            total_tokens_in   BIGINT,
            total_tokens_out  BIGINT,
            duration_seconds  INTEGER,
            started_at        TIMESTAMPTZ,
            ended_at          TIMESTAMPTZ,
            ingested_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            data              JSONB,
            ingestion_source  TEXT,
            PRIMARY KEY (id, created_at)
        )
    """)

    op.execute("""
        SELECT create_hypertable(
            'copilot_sessions',
            'created_at',
            chunk_time_interval => INTERVAL '1 week',
            if_not_exists => TRUE
        )
    """)

    # Partition-inclusive unique constraint; see module docstring.
    op.execute("""
        ALTER TABLE copilot_sessions
            ADD CONSTRAINT uq_copilot_sessions_session_id UNIQUE (session_id, created_at)
    """)

    op.execute("CREATE INDEX idx_copilot_sessions_org ON copilot_sessions (org, created_at DESC)")
    op.execute(
        "CREATE INDEX idx_copilot_sessions_actor ON copilot_sessions (actor, created_at DESC)"
    )

    # ─── copilot_session_turns ──────────────────────────────────────────────
    op.create_table(
        "copilot_session_turns",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("turn_index", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("prompt_text", sa.Text(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("response_text", sa.Text(), nullable=True),
        sa.Column("response_tokens", sa.Integer(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("finish_reason", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("tool_calls", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("references", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("annotations", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("org", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_copilot_session_turns_session_id",
        "copilot_session_turns",
        ["session_id", "turn_index"],
    )
    op.create_index(
        "idx_copilot_session_turns_org",
        "copilot_session_turns",
        ["org", "created_at"],
    )
    op.create_index(
        "idx_copilot_session_turns_created",
        "copilot_session_turns",
        ["created_at"],
    )

    # ─── copilot_session_tool_calls ─────────────────────────────────────────
    op.create_table(
        "copilot_session_tool_calls",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("turn_index", sa.Integer(), nullable=True),
        sa.Column("tool_name", sa.Text(), nullable=True),
        sa.Column("tool_input", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("tool_output_summary", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("org", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_copilot_session_tool_calls_session_id",
        "copilot_session_tool_calls",
        ["session_id", "turn_index"],
    )
    op.create_index(
        "idx_copilot_session_tool_calls_org",
        "copilot_session_tool_calls",
        ["org", "created_at"],
    )
    op.create_index(
        "idx_copilot_session_tool_calls_created",
        "copilot_session_tool_calls",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_copilot_session_tool_calls_created", table_name="copilot_session_tool_calls")
    op.drop_index("idx_copilot_session_tool_calls_org", table_name="copilot_session_tool_calls")
    op.drop_index(
        "idx_copilot_session_tool_calls_session_id", table_name="copilot_session_tool_calls"
    )
    op.drop_table("copilot_session_tool_calls")

    op.drop_index("idx_copilot_session_turns_created", table_name="copilot_session_turns")
    op.drop_index("idx_copilot_session_turns_org", table_name="copilot_session_turns")
    op.drop_index("idx_copilot_session_turns_session_id", table_name="copilot_session_turns")
    op.drop_table("copilot_session_turns")

    op.execute("DROP TABLE IF EXISTS copilot_sessions CASCADE")
