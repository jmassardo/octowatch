"""Add routing rules and digest mode columns to notification_configs.

Revision ID: 0026
Revises: 0025
"""

from __future__ import annotations

from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Alert routing rules (Issue #38) ──────────────────────────────────
    op.execute("""
        ALTER TABLE notification_configs
            ADD COLUMN IF NOT EXISTS rule_categories TEXT[],
            ADD COLUMN IF NOT EXISTS org_filter TEXT[],
            ADD COLUMN IF NOT EXISTS is_catch_all BOOLEAN NOT NULL DEFAULT false;
    """)

    # ── Digest mode (Issue #54) ──────────────────────────────────────────
    op.execute("""
        ALTER TABLE notification_configs
            ADD COLUMN IF NOT EXISTS digest_enabled BOOLEAN NOT NULL DEFAULT false,
            ADD COLUMN IF NOT EXISTS digest_cron TEXT;
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE notification_configs
            DROP COLUMN IF EXISTS digest_cron,
            DROP COLUMN IF EXISTS digest_enabled,
            DROP COLUMN IF EXISTS is_catch_all,
            DROP COLUMN IF EXISTS org_filter,
            DROP COLUMN IF EXISTS rule_categories;
    """)
