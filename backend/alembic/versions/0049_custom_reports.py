"""Add custom_reports table.

Revision ID: 0049
Revises: 0048
Create Date: 2026-05-15

User-created custom report definitions with configurable data sources,
columns, filters, grouping, visualization, and sharing.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from alembic import op

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create custom_reports table."""
    op.create_table(
        "custom_reports",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("owner_login", sa.String(255), nullable=False),
        sa.Column(
            "data_sources",
            ARRAY(sa.Text),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("columns", JSONB, nullable=False, server_default="[]"),
        sa.Column("filters", JSONB, nullable=False, server_default="[]"),
        sa.Column("grouping", JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "visualization",
            sa.String(50),
            nullable=False,
            server_default=sa.text("'table'"),
        ),
        sa.Column(
            "is_shared",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("shared_with", JSONB, nullable=False, server_default="[]"),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
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
    )
    op.create_index(
        "ix_custom_reports_owner_login",
        "custom_reports",
        ["owner_login"],
    )
    op.create_index(
        "ix_custom_reports_is_shared",
        "custom_reports",
        ["is_shared"],
    )


def downgrade() -> None:
    """Drop custom_reports table."""
    op.drop_index("ix_custom_reports_is_shared", table_name="custom_reports")
    op.drop_index("ix_custom_reports_owner_login", table_name="custom_reports")
    op.drop_table("custom_reports")
