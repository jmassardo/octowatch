"""Add report_schedules table for scheduled report delivery.

Revision ID: 0027
Revises: 0026
"""

from __future__ import annotations

from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS report_schedules (
            id              SERIAL PRIMARY KEY,
            report_type     VARCHAR(50)  NOT NULL,
            org             TEXT,
            cron_expression VARCHAR(100) NOT NULL,
            export_format   VARCHAR(10)  NOT NULL DEFAULT 'html',
            recipients      TEXT[]       NOT NULL DEFAULT '{}',
            enabled         BOOLEAN      NOT NULL DEFAULT true,
            created_by      TEXT         NOT NULL,
            last_run_at     TIMESTAMPTZ,
            last_status     VARCHAR(20),
            created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        );
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_report_schedules_enabled
            ON report_schedules (enabled)
            WHERE enabled = true;
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS report_schedules;")
