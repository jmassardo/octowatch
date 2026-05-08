"""Add notifications and notification_preferences tables.

Revision ID: 0054
Revises: 0053
Create Date: 2026-07-01
"""

import sqlalchemy as sa

from alembic import op

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Text, nullable=False, index=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("severity", sa.Text, nullable=False, server_default="info"),
        sa.Column("read", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("source", sa.Text, nullable=False, server_default="system"),
        sa.Column("link", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index("ix_notifications_user_read", "notifications", ["user_id", "read"])

    op.create_table(
        "notification_preferences",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Text, nullable=False, unique=True, index=True),
        sa.Column("in_app_enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("email_enabled", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("slack_enabled", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("severity_filter", sa.Text, nullable=False, server_default="info"),
        sa.Column("detection_alerts", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("sync_alerts", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("system_alerts", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_user_read", table_name="notifications")
    op.drop_table("notification_preferences")
    op.drop_table("notifications")
