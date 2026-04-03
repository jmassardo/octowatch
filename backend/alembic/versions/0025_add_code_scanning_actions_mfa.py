"""Add code scanning alert summaries, actions workflow summaries, and MFA status.

Revision ID: 0025
Revises: 0024
"""

from __future__ import annotations

from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Code scanning alert summaries ─────────────────────────────────────
    op.execute("""
        CREATE TABLE org_code_scanning_alert_summaries (
            id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            enterprise_slug VARCHAR(100) NOT NULL,
            org             VARCHAR(100) NOT NULL,
            open_count      INTEGER NOT NULL DEFAULT 0,
            fixed_count     INTEGER NOT NULL DEFAULT 0,
            dismissed_count INTEGER NOT NULL DEFAULT 0,
            total_count     INTEGER NOT NULL DEFAULT 0,
            error_count     INTEGER NOT NULL DEFAULT 0,
            warning_count   INTEGER NOT NULL DEFAULT 0,
            note_count      INTEGER NOT NULL DEFAULT 0,
            synced_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_code_scanning_summary_slug_org
                UNIQUE (enterprise_slug, org)
        );
    """)
    op.execute("""
        CREATE INDEX idx_code_scanning_summary_org
            ON org_code_scanning_alert_summaries (org);
    """)

    # ── Actions workflow summaries ────────────────────────────────────────
    op.execute("""
        CREATE TABLE org_actions_workflow_summaries (
            id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            enterprise_slug   VARCHAR(100) NOT NULL,
            org               VARCHAR(100) NOT NULL,
            total_workflows   INTEGER NOT NULL DEFAULT 0,
            active_workflows  INTEGER NOT NULL DEFAULT 0,
            total_runs        INTEGER NOT NULL DEFAULT 0,
            successful_runs   INTEGER NOT NULL DEFAULT 0,
            failed_runs       INTEGER NOT NULL DEFAULT 0,
            cancelled_runs    INTEGER NOT NULL DEFAULT 0,
            synced_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_actions_workflow_summary_slug_org
                UNIQUE (enterprise_slug, org)
        );
    """)
    op.execute("""
        CREATE INDEX idx_actions_workflow_summary_org
            ON org_actions_workflow_summaries (org);
    """)

    # ── MFA status column on org_members ──────────────────────────────────
    op.execute("""
        ALTER TABLE org_members
            ADD COLUMN IF NOT EXISTS mfa_enabled BOOLEAN;
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE org_members DROP COLUMN IF EXISTS mfa_enabled;")
    op.execute("DROP TABLE IF EXISTS org_actions_workflow_summaries;")
    op.execute("DROP TABLE IF EXISTS org_code_scanning_alert_summaries;")
