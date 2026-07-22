"""Add automation_targets and automation_deliveries.

Revision ID: 0068
Revises: 0067
Create Date: 2026-07-22 00:00:00.000000+00:00

Adds tables for detection-triggered automation: configurable webhook and
repository_dispatch targets with delivery tracking and retry support.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0068"
down_revision = "0067"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "automation_targets",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("target_type", sa.Text(), nullable=False),
        # Webhook fields
        sa.Column("webhook_url", sa.Text(), nullable=True),
        sa.Column("webhook_secret", sa.Text(), nullable=True),
        sa.Column("webhook_headers", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        # Repository dispatch fields
        sa.Column("dispatch_repo", sa.Text(), nullable=True),
        sa.Column("dispatch_event_type", sa.Text(), nullable=True),
        sa.Column("dispatch_token_env_var", sa.Text(), nullable=True),
        # Filtering
        sa.Column("rule_ids", postgresql.ARRAY(sa.BigInteger()), nullable=True),
        sa.Column("rule_categories", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("severity_filter", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("org_filter", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("is_catch_all", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        # Rate limiting
        sa.Column(
            "rate_limit_per_minute", sa.Integer(), nullable=False, server_default=sa.text("100")
        ),
        # Config
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default=sa.text("3")),
        sa.Column("created_by", sa.Text(), nullable=False),
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
        "idx_automation_targets_enabled",
        "automation_targets",
        ["enabled", "target_type"],
    )

    op.create_table(
        "automation_deliveries",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("target_id", sa.BigInteger(), nullable=False),
        sa.Column("detection_id", sa.BigInteger(), nullable=False),
        # Delivery status
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        # Response tracking
        sa.Column("response_code", sa.Integer(), nullable=True),
        sa.Column("response_body", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        # Payload reference
        sa.Column("payload_hash", sa.Text(), nullable=True),
        # Dry run
        sa.Column("is_dry_run", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["target_id"], ["automation_targets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["detection_id"], ["detections.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "idx_automation_deliveries_target",
        "automation_deliveries",
        ["target_id", "created_at"],
    )
    op.create_index(
        "idx_automation_deliveries_detection",
        "automation_deliveries",
        ["detection_id"],
    )
    op.create_index(
        "idx_automation_deliveries_status",
        "automation_deliveries",
        ["status", "next_retry_at"],
    )


def downgrade() -> None:
    op.drop_table("automation_deliveries")
    op.drop_table("automation_targets")
