"""Add correlation chains and chain memberships tables.

Revision ID: 0051
Revises: 0050
Create Date: 2026-05-25
"""

import sqlalchemy as sa

from alembic import op

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create correlation_chains and chain_memberships tables."""
    op.create_table(
        "correlation_chains",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'open'"),
        ),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assignee", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
    )

    op.create_table(
        "chain_memberships",
        sa.Column(
            "chain_id",
            sa.Text(),
            sa.ForeignKey("correlation_chains.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "detection_id",
            sa.BigInteger(),
            sa.ForeignKey("detections.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("correlation_type", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Double(), nullable=False, server_default=sa.text("0.0")),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    op.add_column(
        "detections",
        sa.Column(
            "chain_id",
            sa.Text(),
            sa.ForeignKey("correlation_chains.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    op.create_index("idx_correlation_chains_status", "correlation_chains", ["status"])
    op.create_index(
        "idx_correlation_chains_severity",
        "correlation_chains",
        ["severity", "status"],
    )
    op.create_index("idx_chain_memberships_detection", "chain_memberships", ["detection_id"])
    op.create_index("idx_detections_chain_id", "detections", ["chain_id"])


def downgrade() -> None:
    """Remove correlation tables and chain_id column."""
    op.drop_index("idx_detections_chain_id", table_name="detections")
    op.drop_index("idx_chain_memberships_detection", table_name="chain_memberships")
    op.drop_index("idx_correlation_chains_severity", table_name="correlation_chains")
    op.drop_index("idx_correlation_chains_status", table_name="correlation_chains")
    op.drop_column("detections", "chain_id")
    op.drop_table("chain_memberships")
    op.drop_table("correlation_chains")
