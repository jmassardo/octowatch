"""add delivery_timelines table

Revision ID: 0061
Revises: 0060
Create Date: 2026-07-01 00:00:00.000000+00:00

Adds the delivery_timelines table for enriched PR delivery metrics,
linking pull requests to issues and CI runs with computed phase durations.
Implements #320.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, UUID

from alembic import op

# revision identifiers, used by Alembic.
revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "delivery_timelines",
        sa.Column(
            "id",
            UUID(as_uuid=False),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("pr_number", sa.Integer(), nullable=False),
        sa.Column("repo", sa.Text(), nullable=False),
        sa.Column("org", sa.Text(), nullable=False),
        sa.Column(
            "issue_numbers",
            ARRAY(sa.Integer()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("backlog_hours", sa.Float(), nullable=True),
        sa.Column("dev_hours", sa.Float(), nullable=True),
        sa.Column("review_hours", sa.Float(), nullable=True),
        sa.Column("deploy_hours", sa.Float(), nullable=True),
        sa.Column("total_hours", sa.Float(), nullable=True),
        sa.Column("merge_commit_sha", sa.Text(), nullable=True),
        sa.Column("pr_merged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ci_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_delivery_timelines_org_repo",
        "delivery_timelines",
        ["org", "repo"],
    )
    op.create_index(
        "idx_delivery_timelines_pr",
        "delivery_timelines",
        ["org", "repo", "pr_number"],
        unique=True,
    )
    op.create_index(
        "idx_delivery_timelines_created",
        "delivery_timelines",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_delivery_timelines_created", table_name="delivery_timelines")
    op.drop_index("idx_delivery_timelines_pr", table_name="delivery_timelines")
    op.drop_index("idx_delivery_timelines_org_repo", table_name="delivery_timelines")
    op.drop_table("delivery_timelines")
