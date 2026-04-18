"""Add Copilot metrics tables and severity column on copilot_policies.

Revision ID: 0037
Revises: 0036
Create Date: 2026-04-18
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers
revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Copilot daily metrics
    op.create_table(
        "copilot_daily_metrics",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("org_slug", sa.Text(), nullable=False),
        sa.Column("metric_type", sa.Text(), nullable=False),
        sa.Column("language", sa.Text(), nullable=True),
        sa.Column("editor", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("active_users", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("engaged_users", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_suggestions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_acceptances", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_lines_suggested", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_lines_accepted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("acceptance_rate", sa.Float(), nullable=True),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "date",
            "org_slug",
            "metric_type",
            "language",
            "editor",
            "model",
            name="uq_copilot_daily_metrics_composite",
        ),
    )
    op.create_index("ix_copilot_daily_metrics_date", "copilot_daily_metrics", ["date"])
    op.create_index("ix_copilot_daily_metrics_org_slug", "copilot_daily_metrics", ["org_slug"])

    # Copilot seat snapshots
    op.create_table(
        "copilot_seat_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("org_slug", sa.Text(), nullable=False),
        sa.Column("github_login", sa.Text(), nullable=False),
        sa.Column("plan_type", sa.Text(), nullable=False, server_default="business"),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_activity_editor", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("pending_cancellation_date", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "snapshot_date",
            "org_slug",
            "github_login",
            name="uq_copilot_seat_snapshots_composite",
        ),
    )
    op.create_index(
        "ix_copilot_seat_snapshots_snapshot_date", "copilot_seat_snapshots", ["snapshot_date"]
    )
    op.create_index("ix_copilot_seat_snapshots_org_slug", "copilot_seat_snapshots", ["org_slug"])
    op.create_index(
        "ix_copilot_seat_snapshots_github_login", "copilot_seat_snapshots", ["github_login"]
    )

    # Fix #5B: Add severity column to copilot_policies
    op.add_column(
        "copilot_policies",
        sa.Column("severity", sa.Text(), nullable=False, server_default="medium"),
    )


def downgrade() -> None:
    op.drop_column("copilot_policies", "severity")
    op.drop_table("copilot_seat_snapshots")
    op.drop_table("copilot_daily_metrics")
