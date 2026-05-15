"""Add packages and package_alerts tables for GitHub Packages monitoring.

Revision ID: 0058
Revises: 0057
Create Date: 2026-06-15
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create packages and package_alerts tables."""
    op.create_table(
        "packages",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("org", sa.Text(), nullable=False),
        sa.Column("repo", sa.Text(), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("package_type", sa.Text(), nullable=False),
        sa.Column(
            "visibility",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'private'"),
        ),
        sa.Column("owner", sa.Text(), nullable=True),
        sa.Column(
            "versions_count",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("latest_version", sa.Text(), nullable=True),
        sa.Column("last_published_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.Column(
            "is_stale",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "published_outside_actions",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "published_by_external",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_index("idx_packages_org", "packages", ["org"])
    op.create_index("idx_packages_visibility", "packages", ["visibility"])
    op.create_index("idx_packages_type", "packages", ["package_type"])
    op.create_index("idx_packages_org_name", "packages", ["org", "name"], unique=True)

    op.create_table(
        "package_alerts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column(
            "package_id",
            sa.BigInteger(),
            sa.ForeignKey("packages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("alert_type", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "detected_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'open'"),
        ),
    )
    op.create_index("idx_package_alerts_package_id", "package_alerts", ["package_id"])
    op.create_index("idx_package_alerts_status", "package_alerts", ["status"])
    op.create_index("idx_package_alerts_severity", "package_alerts", ["severity"])
    op.create_index("idx_package_alerts_type", "package_alerts", ["alert_type"])


def downgrade() -> None:
    """Drop package_alerts and packages tables."""
    op.drop_index("idx_package_alerts_type", table_name="package_alerts")
    op.drop_index("idx_package_alerts_severity", table_name="package_alerts")
    op.drop_index("idx_package_alerts_status", table_name="package_alerts")
    op.drop_index("idx_package_alerts_package_id", table_name="package_alerts")
    op.drop_table("package_alerts")

    op.drop_index("idx_packages_org_name", table_name="packages")
    op.drop_index("idx_packages_type", table_name="packages")
    op.drop_index("idx_packages_visibility", table_name="packages")
    op.drop_index("idx_packages_org", table_name="packages")
    op.drop_table("packages")
