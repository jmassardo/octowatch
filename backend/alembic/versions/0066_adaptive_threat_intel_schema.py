"""Adaptive threat intel schema: campaigns, expanded indicators, feed parsers.

Revision ID: 0066
Revises: 0065
Create Date: 2026-07-08 00:00:00.000000+00:00

Adds the data model foundations for campaign-attributed threat intel and
structured feed parsing:

- New ``threat_intel_campaigns`` table for named campaigns
- ``threat_intel_indicators.campaign_id`` FK for attribution
- ``rule_definitions.source``, ``campaign_id``, ``expires_at`` columns
- ``detections.campaign_id`` FK for detection attribution
- ``threat_intel_feeds`` parser columns for structured format support

Resolves: #334
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0066"
down_revision = "0065"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── New table: threat_intel_campaigns ─────────────────────────────────
    op.create_table(
        "threat_intel_campaigns",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("name", sa.Text, nullable=False, unique=True),
        sa.Column("slug", sa.Text, nullable=False, unique=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "last_updated",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("severity", sa.Text, nullable=False, server_default=sa.text("'critical'")),
        sa.Column("status", sa.Text, nullable=False, server_default=sa.text("'active'")),
        sa.Column("source_feed_id", sa.BigInteger, nullable=True),
        sa.Column("metadata_json", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column("indicator_count", sa.Integer, nullable=False, server_default=sa.text("0")),
    )
    # Add FK to feeds after both tables exist (avoids ordering issue)
    op.create_foreign_key(
        "fk_campaigns_source_feed",
        "threat_intel_campaigns",
        "threat_intel_feeds",
        ["source_feed_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "idx_campaigns_status",
        "threat_intel_campaigns",
        ["status"],
    )

    # ── Alter threat_intel_indicators ─────────────────────────────────────
    op.add_column(
        "threat_intel_indicators",
        sa.Column("campaign_id", sa.BigInteger, nullable=True),
    )
    op.create_foreign_key(
        "fk_indicators_campaign",
        "threat_intel_indicators",
        "threat_intel_campaigns",
        ["campaign_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "idx_indicators_campaign_active",
        "threat_intel_indicators",
        ["campaign_id", "active"],
        postgresql_where=sa.text("campaign_id IS NOT NULL"),
    )

    # ── Alter rule_definitions ────────────────────────────────────────────
    op.add_column(
        "rule_definitions",
        sa.Column("source", sa.Text, nullable=False, server_default=sa.text("'manual'")),
    )
    op.add_column(
        "rule_definitions",
        sa.Column("campaign_id", sa.BigInteger, nullable=True),
    )
    op.add_column(
        "rule_definitions",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_rules_campaign",
        "rule_definitions",
        "threat_intel_campaigns",
        ["campaign_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "idx_rules_campaign_enabled",
        "rule_definitions",
        ["campaign_id", "enabled", "status"],
        postgresql_where=sa.text("campaign_id IS NOT NULL"),
    )

    # ── Alter detections ──────────────────────────────────────────────────
    op.add_column(
        "detections",
        sa.Column("campaign_id", sa.BigInteger, nullable=True),
    )
    op.create_foreign_key(
        "fk_detections_campaign",
        "detections",
        "threat_intel_campaigns",
        ["campaign_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "idx_detections_campaign_triggered",
        "detections",
        ["campaign_id", "triggered_at"],
        postgresql_where=sa.text("campaign_id IS NOT NULL"),
    )

    # ── Alter threat_intel_feeds ──────────────────────────────────────────
    op.add_column(
        "threat_intel_feeds",
        sa.Column("parser_type", sa.Text, nullable=False, server_default=sa.text("'plaintext'")),
    )
    op.add_column(
        "threat_intel_feeds",
        sa.Column("parser_config", sa.dialects.postgresql.JSONB, nullable=True),
    )
    op.add_column(
        "threat_intel_feeds",
        sa.Column(
            "auto_rule_generation",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("TRUE"),
        ),
    )
    op.add_column(
        "threat_intel_feeds",
        sa.Column("default_campaign_id", sa.BigInteger, nullable=True),
    )
    op.create_foreign_key(
        "fk_feeds_default_campaign",
        "threat_intel_feeds",
        "threat_intel_campaigns",
        ["default_campaign_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # ── Reverse threat_intel_feeds ────────────────────────────────────────
    op.drop_constraint("fk_feeds_default_campaign", "threat_intel_feeds", type_="foreignkey")
    op.drop_column("threat_intel_feeds", "default_campaign_id")
    op.drop_column("threat_intel_feeds", "auto_rule_generation")
    op.drop_column("threat_intel_feeds", "parser_config")
    op.drop_column("threat_intel_feeds", "parser_type")

    # ── Reverse detections ────────────────────────────────────────────────
    op.drop_index("idx_detections_campaign_triggered", "detections")
    op.drop_constraint("fk_detections_campaign", "detections", type_="foreignkey")
    op.drop_column("detections", "campaign_id")

    # ── Reverse rule_definitions ──────────────────────────────────────────
    op.drop_index("idx_rules_campaign_enabled", "rule_definitions")
    op.drop_constraint("fk_rules_campaign", "rule_definitions", type_="foreignkey")
    op.drop_column("rule_definitions", "expires_at")
    op.drop_column("rule_definitions", "campaign_id")
    op.drop_column("rule_definitions", "source")

    # ── Reverse threat_intel_indicators ───────────────────────────────────
    op.drop_index("idx_indicators_campaign_active", "threat_intel_indicators")
    op.drop_constraint("fk_indicators_campaign", "threat_intel_indicators", type_="foreignkey")
    op.drop_column("threat_intel_indicators", "campaign_id")

    # ── Drop campaigns table ─────────────────────────────────────────────
    op.drop_index("idx_campaigns_status", "threat_intel_campaigns")
    op.drop_constraint("fk_campaigns_source_feed", "threat_intel_campaigns", type_="foreignkey")
    op.drop_table("threat_intel_campaigns")
