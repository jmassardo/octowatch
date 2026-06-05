"""Add copilot_usage_reports table for per-user UBB billing data.

Stores daily per-user AI credit consumption fetched from the GitHub
Copilot usage API.  Used for User-Based Billing budgeting and accurate
adoption tier classification.

Revision ID: 0064
Revises: 0063
"""

import sqlalchemy as sa

from alembic import op

revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "copilot_usage_reports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("org_slug", sa.Text(), nullable=False),
        sa.Column("github_login", sa.Text(), nullable=False),
        sa.Column("total_credits_consumed", sa.Float(), nullable=False, server_default="0"),
        sa.Column("completions_credits", sa.Float(), nullable=False, server_default="0"),
        sa.Column("chat_credits", sa.Float(), nullable=False, server_default="0"),
        sa.Column("pr_credits", sa.Float(), nullable=False, server_default="0"),
        sa.Column("other_credits", sa.Float(), nullable=False, server_default="0"),
        sa.Column("budget_amount", sa.Float(), nullable=True),
        sa.Column("budget_consumed", sa.Float(), nullable=True),
        sa.Column("is_blocked", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "report_date",
            "org_slug",
            "github_login",
            name="uq_copilot_usage_composite",
        ),
    )
    op.create_index(
        "ix_copilot_usage_reports_report_date", "copilot_usage_reports", ["report_date"]
    )
    op.create_index("ix_copilot_usage_reports_org_slug", "copilot_usage_reports", ["org_slug"])
    op.create_index(
        "ix_copilot_usage_reports_github_login", "copilot_usage_reports", ["github_login"]
    )


def downgrade() -> None:
    op.drop_index("ix_copilot_usage_reports_github_login", table_name="copilot_usage_reports")
    op.drop_index("ix_copilot_usage_reports_org_slug", table_name="copilot_usage_reports")
    op.drop_index("ix_copilot_usage_reports_report_date", table_name="copilot_usage_reports")
    op.drop_table("copilot_usage_reports")
