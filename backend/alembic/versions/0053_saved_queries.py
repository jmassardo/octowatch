"""Add saved_queries table for user-saved queries with sharing and scheduling.

Revision ID: 0051
Revises: 0050
Create Date: 2026-06-15
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from alembic import op

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create saved_queries table."""
    op.create_table(
        "saved_queries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sql_text", sa.Text(), nullable=False),
        sa.Column("owner_login", sa.Text(), nullable=False),
        sa.Column(
            "is_shared",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("shared_with", JSONB(), nullable=True),
        sa.Column("tags", ARRAY(sa.Text()), nullable=True),
        sa.Column("schedule_cron", sa.Text(), nullable=True),
        sa.Column(
            "schedule_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_saved_queries_owner_login",
        "saved_queries",
        ["owner_login"],
    )
    # GIN index on shared_with JSONB for fast lookup of shared queries
    op.execute("CREATE INDEX ix_saved_queries_shared_with ON saved_queries USING GIN (shared_with)")
    # Grant readonly access for the query explorer role
    op.execute("GRANT SELECT ON saved_queries TO readonly_query_user")


def downgrade() -> None:
    """Drop saved_queries table."""
    op.execute("REVOKE SELECT ON saved_queries FROM readonly_query_user")
    op.drop_index("ix_saved_queries_shared_with", table_name="saved_queries")
    op.drop_index("ix_saved_queries_owner_login", table_name="saved_queries")
    op.drop_table("saved_queries")
