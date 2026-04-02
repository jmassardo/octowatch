"""Add new sync entity tables for outside collaborators, alert summaries, and license consumption.

Adds the following tables:
  - org_outside_collaborators
  - org_secret_scanning_alert_summaries
  - org_dependabot_alert_summaries
  - enterprise_license_consumption

Revision ID: 0022
Revises: 0021
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── org_outside_collaborators ──────────────────────────────────────────
    op.create_table(
        "org_outside_collaborators",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("enterprise_slug", sa.String(100), nullable=False),
        sa.Column("org", sa.String(100), nullable=False),
        sa.Column("login", sa.String(100), nullable=False),
        sa.Column("github_id", sa.BigInteger, nullable=False),
        sa.Column("avatar_url", sa.Text, nullable=True),
        sa.Column("site_admin", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint(
            "enterprise_slug", "org", "login", name="uq_outside_collab_slug_org_login"
        ),
    )
    op.create_index("idx_outside_collab_org", "org_outside_collaborators", ["org"])

    # ── org_secret_scanning_alert_summaries ────────────────────────────────
    op.create_table(
        "org_secret_scanning_alert_summaries",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("enterprise_slug", sa.String(100), nullable=False),
        sa.Column("org", sa.String(100), nullable=False),
        sa.Column("open_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("resolved_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("total_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("enterprise_slug", "org", name="uq_secret_scanning_summary_slug_org"),
    )
    op.create_index(
        "idx_secret_scanning_summary_org",
        "org_secret_scanning_alert_summaries",
        ["org"],
    )

    # ── org_dependabot_alert_summaries ─────────────────────────────────────
    op.create_table(
        "org_dependabot_alert_summaries",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("enterprise_slug", sa.String(100), nullable=False),
        sa.Column("org", sa.String(100), nullable=False),
        sa.Column("open_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("fixed_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("dismissed_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("total_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("critical_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("high_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("medium_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("low_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("enterprise_slug", "org", name="uq_dependabot_summary_slug_org"),
    )
    op.create_index(
        "idx_dependabot_summary_org",
        "org_dependabot_alert_summaries",
        ["org"],
    )

    # ── enterprise_license_consumption ─────────────────────────────────────
    op.create_table(
        "enterprise_license_consumption",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("enterprise_slug", sa.String(100), nullable=False),
        sa.Column("total_seats_purchased", sa.Integer, nullable=False),
        sa.Column("total_seats_consumed", sa.Integer, nullable=False),
        sa.Column("seats", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("enterprise_slug", name="uq_license_consumption_slug"),
    )


def downgrade() -> None:
    op.drop_table("enterprise_license_consumption")
    op.drop_table("org_dependabot_alert_summaries")
    op.drop_table("org_secret_scanning_alert_summaries")
    op.drop_table("org_outside_collaborators")
