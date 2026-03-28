"""Org-level snapshot tables.

Creates tables: org_members, org_teams, org_team_members.

Revision ID: 0006
Revises: 0005
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "org_members",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("org", sa.Text(), nullable=False),
        sa.Column("github_login", sa.Text(), nullable=False),
        sa.Column("github_id", sa.BigInteger(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column(
            "synced_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False
        ),
        sa.UniqueConstraint("org", "github_login", name="uq_org_members_org_login"),
    )
    op.create_index("idx_org_members_org", "org_members", ["org"])
    op.create_index("idx_org_members_github_id", "org_members", ["github_id"])

    op.create_table(
        "org_teams",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("org", sa.Text(), nullable=False),
        sa.Column("team_slug", sa.Text(), nullable=False),
        sa.Column("team_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("privacy", sa.Text()),
        sa.Column("parent_team_slug", sa.Text()),
        sa.Column(
            "synced_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False
        ),
        sa.UniqueConstraint("org", "team_slug", name="uq_org_teams_org_slug"),
    )
    op.create_index("idx_org_teams_org", "org_teams", ["org"])
    op.create_index("idx_org_teams_team_id", "org_teams", ["team_id"])

    op.create_table(
        "org_team_members",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("org", sa.Text(), nullable=False),
        sa.Column("team_slug", sa.Text(), nullable=False),
        sa.Column("github_login", sa.Text(), nullable=False),
        sa.Column("github_id", sa.BigInteger()),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column(
            "synced_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False
        ),
        sa.UniqueConstraint(
            "org", "team_slug", "github_login", name="uq_org_team_members_org_team_login"
        ),
    )
    op.create_index("idx_org_team_members_org_team", "org_team_members", ["org", "team_slug"])
    op.create_index("idx_org_team_members_login", "org_team_members", ["github_login"])


def downgrade() -> None:
    op.drop_table("org_team_members")
    op.drop_table("org_teams")
    op.drop_table("org_members")
