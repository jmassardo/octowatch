"""Add rule monitoring mode and dry-run detection flag.

Revision ID: 0050
Revises: 0049
Create Date: 2026-05-18
"""

import sqlalchemy as sa

from alembic import op

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add rule mode and detection dry-run fields."""
    op.add_column(
        "rule_definitions",
        sa.Column("mode", sa.Text(), nullable=False, server_default=sa.text("'active'")),
    )
    op.add_column(
        "detections",
        sa.Column(
            "is_dry_run",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_index("idx_detections_is_dry_run", "detections", ["is_dry_run"])


def downgrade() -> None:
    """Remove rule mode and detection dry-run fields."""
    op.drop_index("idx_detections_is_dry_run", table_name="detections")
    op.drop_column("detections", "is_dry_run")
    op.drop_column("rule_definitions", "mode")
