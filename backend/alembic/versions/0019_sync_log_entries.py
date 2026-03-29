"""Add enterprise_sync_log_entries table.

Stores lightweight log entries emitted during enterprise sync runs
so the UI can display real-time sync progress in a log viewer.

Revision ID: 0019
Revises: 0018
"""

from __future__ import annotations

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE enterprise_sync_log_entries (
            id          BIGSERIAL       PRIMARY KEY,
            run_id      UUID            NOT NULL
                            REFERENCES enterprise_sync_runs(id) ON DELETE CASCADE,
            seq         INTEGER         NOT NULL,
            timestamp   TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
            level       VARCHAR(10)     NOT NULL DEFAULT 'info',
            message     TEXT            NOT NULL,
            entity_type VARCHAR(50),
            org         VARCHAR(100),
            details     JSONB
        )
    """)
    op.execute("""
        CREATE INDEX idx_sync_log_entries_run_id_seq
            ON enterprise_sync_log_entries (run_id, seq)
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE IF EXISTS enterprise_sync_log_entries;
    """)
