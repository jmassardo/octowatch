"""Add validity, locations_count, resolved_by, updated_at to secret_scanning_alerts.

Revision ID: 0052
Revises: 0051
Create Date: 2026-06-01
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add extra columns required for enhanced secret scanning ingestion."""
    op.add_column(
        "secret_scanning_alerts",
        sa.Column("validity", sa.String(50), nullable=True),
    )
    op.add_column(
        "secret_scanning_alerts",
        sa.Column(
            "locations_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "secret_scanning_alerts",
        sa.Column("resolved_by", sa.String(255), nullable=True),
    )
    op.add_column(
        "secret_scanning_alerts",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_secret_scanning_alert_validity",
        "secret_scanning_alerts",
        ["validity"],
    )


def downgrade() -> None:
    """Remove extra secret scanning columns."""
    op.drop_index("idx_secret_scanning_alert_validity", table_name="secret_scanning_alerts")
    op.drop_column("secret_scanning_alerts", "updated_at")
    op.drop_column("secret_scanning_alerts", "resolved_by")
    op.drop_column("secret_scanning_alerts", "locations_count")
    op.drop_column("secret_scanning_alerts", "validity")
