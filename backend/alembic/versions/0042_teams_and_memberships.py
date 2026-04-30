"""Add teams and team memberships tables.

Revision ID: 0042
Revises: 0041
Create Date: 2025-01-15 00:00:00.000000

"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

# revision identifiers, used by Alembic.
revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create teams, team_memberships, and team_role_assignments tables."""
    op.create_table(
        "teams",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("github_org", sa.Text(), nullable=True),
        sa.Column("github_team_slug", sa.Text(), nullable=True),
        sa.Column(
            "auto_sync",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_teams_slug", "teams", ["slug"])

    op.create_table(
        "team_memberships",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("user_login", sa.Text(), nullable=False),
        sa.Column("added_by", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("team_id", "user_login", name="uq_team_memberships_team_user"),
    )
    op.create_index(
        "ix_team_memberships_user_login",
        "team_memberships",
        ["user_login"],
    )

    op.create_table(
        "team_role_assignments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("org_slug", sa.Text(), nullable=True),
        sa.Column("repo_slugs", JSONB(), nullable=True),
        sa.Column("assigned_by", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["rbac_roles.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("team_id", "role_id", name="uq_team_role_assignments_team_role"),
    )


def downgrade() -> None:
    """Drop teams, team_memberships, and team_role_assignments tables."""
    op.drop_table("team_role_assignments")
    op.drop_table("team_memberships")
    op.drop_index("ix_teams_slug", table_name="teams")
    op.drop_table("teams")
