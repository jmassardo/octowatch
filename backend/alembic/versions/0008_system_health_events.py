"""System health events table for internal OctoWatch monitoring signals.

Revision ID: 0008
Revises: 0007
"""

from __future__ import annotations

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE system_health_events (
            id            BIGINT GENERATED ALWAYS AS IDENTITY,
            occurred_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            org           TEXT,
            signal_type   TEXT NOT NULL,
            severity      TEXT NOT NULL,
            detail        JSONB NOT NULL DEFAULT '{}',
            resolved_at   TIMESTAMPTZ,
            PRIMARY KEY (id, occurred_at)
        );
    """)
    op.execute("SELECT create_hypertable('system_health_events', 'occurred_at');")
    op.execute(
        "CREATE INDEX idx_system_health_org ON system_health_events (org, occurred_at DESC);"
    )
    op.execute("""
        CREATE INDEX idx_system_health_unresolved
            ON system_health_events (signal_type, resolved_at)
        WHERE resolved_at IS NULL;
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS system_health_events CASCADE;")
