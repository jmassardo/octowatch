"""Enterprise-level snapshot tables.

Creates tables: enterprise_orgs, enterprise_members,
github_app_installations.

Revision ID: 0005
Revises: 0004
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "enterprise_orgs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("enterprise_slug", sa.Text(), nullable=False),
        sa.Column("org_login", sa.Text(), nullable=False),
        sa.Column("org_id", sa.BigInteger(), nullable=False),
        sa.Column("visibility", sa.Text()),
        sa.Column("plan", sa.Text()),
        sa.Column("member_count", sa.Integer()),
        sa.Column(
            "synced_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False
        ),
        sa.UniqueConstraint("enterprise_slug", "org_login", name="uq_enterprise_orgs_slug_login"),
    )
    op.create_index("idx_enterprise_orgs_slug", "enterprise_orgs", ["enterprise_slug"])
    op.create_index("idx_enterprise_orgs_org_id", "enterprise_orgs", ["org_id"])

    op.create_table(
        "enterprise_members",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("enterprise_slug", sa.Text(), nullable=False),
        sa.Column("github_login", sa.Text(), nullable=False),
        sa.Column("github_id", sa.BigInteger(), nullable=False),
        sa.Column("role", sa.Text()),
        sa.Column(
            "synced_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False
        ),
        sa.UniqueConstraint(
            "enterprise_slug", "github_login", name="uq_enterprise_members_slug_login"
        ),
    )
    op.create_index("idx_enterprise_members_slug", "enterprise_members", ["enterprise_slug"])
    op.create_index("idx_enterprise_members_github_id", "enterprise_members", ["github_id"])

    op.create_table(
        "github_app_installations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("app_id", sa.Integer(), nullable=False),
        sa.Column("installation_id", sa.BigInteger(), nullable=False),
        sa.Column("target_type", sa.Text(), nullable=False),
        sa.Column("target_login", sa.Text(), nullable=False),
        sa.Column("permissions", postgresql.JSONB()),
        sa.Column(
            "synced_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False
        ),
        sa.UniqueConstraint(
            "app_id", "installation_id", name="uq_github_app_installations_app_install"
        ),
    )
    op.create_index("idx_github_app_installations_app_id", "github_app_installations", ["app_id"])
    op.create_index(
        "idx_github_app_installations_target",
        "github_app_installations",
        ["target_type", "target_login"],
    )


def downgrade() -> None:
    op.drop_table("github_app_installations")
    op.drop_table("enterprise_members")
    op.drop_table("enterprise_orgs")
