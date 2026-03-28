"""Repository snapshot tables and external_collaborators sync columns.

Creates tables: repositories, repo_branch_protections.
Alters table: external_collaborators (adds data_source, last_synced_at,
sync_run_id columns).

Revision ID: 0007
Revises: 0006
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "repositories",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("org", sa.Text(), nullable=False),
        sa.Column("repo_name", sa.Text(), nullable=False),
        sa.Column("repo_id", sa.BigInteger(), nullable=False),
        sa.Column("visibility", sa.Text(), nullable=False),
        sa.Column("default_branch", sa.Text()),
        sa.Column("archived", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("fork", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("pushed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "synced_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False
        ),
        sa.UniqueConstraint("org", "repo_name", name="uq_repositories_org_name"),
    )
    op.create_index("idx_repositories_org", "repositories", ["org"])
    op.create_index("idx_repositories_repo_id", "repositories", ["repo_id"])
    op.create_index("idx_repositories_visibility", "repositories", ["visibility"])

    op.create_table(
        "repo_branch_protections",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("org", sa.Text(), nullable=False),
        sa.Column("repo_name", sa.Text(), nullable=False),
        sa.Column("branch", sa.Text(), nullable=False),
        sa.Column("required_reviews", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("required_status_checks", postgresql.JSONB()),
        sa.Column("enforce_admins", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "synced_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False
        ),
        sa.UniqueConstraint(
            "org", "repo_name", "branch", name="uq_repo_branch_protections_org_repo_branch"
        ),
    )
    op.create_index(
        "idx_repo_branch_protections_org_repo", "repo_branch_protections", ["org", "repo_name"]
    )

    # Add sync-related columns to external_collaborators
    op.add_column(
        "external_collaborators",
        sa.Column(
            "data_source", sa.Text(), server_default=sa.text("'audit_event'"), nullable=False
        ),
    )
    op.add_column(
        "external_collaborators",
        sa.Column("last_synced_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "external_collaborators",
        sa.Column(
            "sync_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("enterprise_sync_runs.id", ondelete="SET NULL"),
        ),
    )


def downgrade() -> None:
    op.drop_column("external_collaborators", "sync_run_id")
    op.drop_column("external_collaborators", "last_synced_at")
    op.drop_column("external_collaborators", "data_source")
    op.drop_table("repo_branch_protections")
    op.drop_table("repositories")
