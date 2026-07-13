"""Add GHAS active committers table.

Revision ID: 0067
Revises: 0066
Create Date: 2026-07-15 00:00:00.000000+00:00

Stores GHAS billing active committer counts per org, populated by the
``ghas_active_committers`` sync entity type.

Resolves: #429
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0067"
down_revision = "0066"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ghas_active_committers",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("org_slug", sa.String(100), nullable=False),
        sa.Column("total_active_committers", sa.Integer, nullable=False, server_default="0"),
        sa.Column("maximum_active_committers", sa.Integer, nullable=False, server_default="0"),
        sa.Column("purchased_committers", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("org_slug", name="uq_ghas_committers_org"),
    )


def downgrade() -> None:
    op.drop_table("ghas_active_committers")
