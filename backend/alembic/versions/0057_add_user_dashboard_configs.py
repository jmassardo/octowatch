"""Add user_dashboard_configs table.

Revision ID: 0057
Revises: 0056
Create Date: 2026-06-15 00:00:00.000000+00:00

Stores per-user custom dashboard layouts with persona selection for the
custom dashboard builder feature (issue #252).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_dashboard_configs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
            comment="Unique config identifier",
        ),
        sa.Column(
            "user_id",
            sa.String(255),
            nullable=False,
            comment="GitHub login of the owning user",
        ),
        sa.Column(
            "layout",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
            comment="Widget positions, sizes, and configurations",
        ),
        sa.Column(
            "persona",
            sa.String(50),
            server_default=sa.text("''"),
            nullable=False,
            comment="Selected persona: security-analyst, engineering-manager, platform-engineer, executive",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_user_dashboard_configs_user_id",
        "user_dashboard_configs",
        ["user_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_user_dashboard_configs_user_id",
        table_name="user_dashboard_configs",
    )
    op.drop_table("user_dashboard_configs")
