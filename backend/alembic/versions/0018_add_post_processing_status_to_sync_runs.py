"""Add post_processing_status column to enterprise_sync_runs.

Tracks the state of detection + baseline computation that runs
automatically after a sync completes.

Revision ID: 0018
Revises: 0017
"""

from __future__ import annotations

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE enterprise_sync_runs
        ADD COLUMN post_processing_status TEXT;
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE enterprise_sync_runs
        DROP COLUMN IF EXISTS post_processing_status;
    """)
