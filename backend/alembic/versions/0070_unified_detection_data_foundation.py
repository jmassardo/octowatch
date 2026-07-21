"""add activity_category, utilization_facts, baseline percentiles

Revision ID: 0068
Revises: 0067
Create Date: 2026-07-20 00:00:00.000000+00:00

Adds the unified detection data foundation:
- activity_category column on events for classification
- p25/p75 percentile columns on behavioral_baselines
- utilization_facts table for per-actor feature usage metrics

Resolves: #445
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0070"
down_revision = "0068"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add activity_category to events
    op.add_column("events", sa.Column("activity_category", sa.Text, nullable=True))
    op.create_index(
        "idx_events_activity_category",
        "events",
        ["activity_category", "created_at"],
    )

    # 2. Add p25 and p75 to behavioral_baselines
    op.add_column(
        "behavioral_baselines",
        sa.Column("p25", sa.Double(), nullable=True),
    )
    op.add_column(
        "behavioral_baselines",
        sa.Column("p75", sa.Double(), nullable=True),
    )

    # 3. Create utilization_facts table
    op.create_table(
        "utilization_facts",
        sa.Column(
            "id",
            sa.Uuid,
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("org_slug", sa.Text, nullable=False),
        sa.Column("actor_login", sa.Text, nullable=False),
        sa.Column("feature_area", sa.Text, nullable=False),
        sa.Column("metric_date", sa.Date, nullable=False),
        sa.Column("actions_minutes", sa.Numeric, nullable=True),
        sa.Column("actions_runs", sa.Integer, nullable=True),
        sa.Column("copilot_suggestions", sa.Integer, nullable=True),
        sa.Column("copilot_acceptances", sa.Integer, nullable=True),
        sa.Column("copilot_credits", sa.Numeric, nullable=True),
        sa.Column("ghas_alerts_dismissed", sa.Integer, nullable=True),
        sa.Column("git_clones", sa.Integer, nullable=True),
        sa.Column("git_pushes", sa.Integer, nullable=True),
        sa.Column("packages_published", sa.Integer, nullable=True),
        sa.Column("storage_bytes", sa.BigInteger, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "org_slug",
            "actor_login",
            "feature_area",
            "metric_date",
            name="uq_utilization_facts_org_actor_feature_date",
        ),
    )
    op.create_index(
        "idx_utilization_facts_org_actor",
        "utilization_facts",
        ["org_slug", "actor_login", "metric_date"],
    )
    op.create_index(
        "idx_utilization_facts_feature",
        "utilization_facts",
        ["feature_area", "metric_date"],
    )


def downgrade() -> None:
    op.drop_index("idx_utilization_facts_feature", table_name="utilization_facts")
    op.drop_index("idx_utilization_facts_org_actor", table_name="utilization_facts")
    op.drop_table("utilization_facts")

    op.drop_column("behavioral_baselines", "p75")
    op.drop_column("behavioral_baselines", "p25")

    op.drop_index("idx_events_activity_category", table_name="events")
    op.drop_column("events", "activity_category")
