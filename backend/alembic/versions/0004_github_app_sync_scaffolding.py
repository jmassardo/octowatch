"""GitHub App config and sync run scaffolding.

Creates tables: github_app_configs, enterprise_sync_runs,
enterprise_sync_entity_cursors.

Revision ID: 0004
Revises: 0003
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "github_app_configs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
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
        sa.Column("app_id", sa.Integer(), nullable=False),
        sa.Column("installation_id", sa.BigInteger(), nullable=False),
        sa.Column("enterprise_slug", sa.Text()),
        sa.Column("org_login", sa.Text()),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.UniqueConstraint("app_id", "installation_id", name="uq_github_app_configs_app_install"),
    )
    op.create_index("idx_github_app_configs_enterprise", "github_app_configs", ["enterprise_slug"])
    op.create_index("idx_github_app_configs_org", "github_app_configs", ["org_login"])

    op.create_table(
        "enterprise_sync_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("trigger_type", sa.Text(), nullable=False),
        sa.Column("triggered_by", sa.Text()),
        sa.Column("scope", sa.Text(), server_default=sa.text("'full'"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("error_message", sa.Text()),
        sa.Column("entity_counts", postgresql.JSONB()),
    )
    op.create_index("idx_enterprise_sync_runs_status", "enterprise_sync_runs", ["status"])
    op.create_index("idx_enterprise_sync_runs_created_at", "enterprise_sync_runs", ["created_at"])

    op.create_table(
        "enterprise_sync_entity_cursors",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("enterprise_sync_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("org", sa.Text()),
        sa.Column("last_cursor", sa.Text()),
        sa.Column("items_synced", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'in_progress'"), nullable=False),
        sa.UniqueConstraint("run_id", "entity_type", "org", name="uq_sync_cursors_run_entity_org"),
    )
    op.create_index("idx_sync_cursors_run_id", "enterprise_sync_entity_cursors", ["run_id"])


def downgrade() -> None:
    op.drop_table("enterprise_sync_entity_cursors")
    op.drop_table("enterprise_sync_runs")
    op.drop_table("github_app_configs")
