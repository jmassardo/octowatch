"""Add 8 new sync entity tables for expanded GitHub Enterprise sync coverage.

New tables: org_team_repos, repo_collaborators, org_credential_authorizations,
org_webhooks, repo_webhooks, org_actions_permissions, org_self_hosted_runners,
repo_deploy_keys.

Revision ID: 0035
Revises: 0034
Create Date: 2026-04-18
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY

from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Team repos ──────────────────────────────────────────────────────
    op.create_table(
        "org_team_repos",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("org", sa.Text, nullable=False),
        sa.Column("team_slug", sa.Text, nullable=False),
        sa.Column("repo_name", sa.Text, nullable=False),
        sa.Column("repo_id", sa.BigInteger, nullable=False),
        sa.Column("permission", sa.Text, nullable=False),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint(
            "org", "team_slug", "repo_name", name="uq_org_team_repos_org_team_repo"
        ),
    )
    op.create_index("idx_org_team_repos_org_team", "org_team_repos", ["org", "team_slug"])
    op.create_index("idx_org_team_repos_repo", "org_team_repos", ["org", "repo_name"])

    # ── Repo collaborators ──────────────────────────────────────────────
    op.create_table(
        "repo_collaborators",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("org", sa.Text, nullable=False),
        sa.Column("repo_name", sa.Text, nullable=False),
        sa.Column("github_login", sa.Text, nullable=False),
        sa.Column("github_id", sa.BigInteger, nullable=True),
        sa.Column("permission", sa.Text, nullable=False),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint(
            "org", "repo_name", "github_login", name="uq_repo_collaborators_org_repo_login"
        ),
    )
    op.create_index("idx_repo_collaborators_org_repo", "repo_collaborators", ["org", "repo_name"])
    op.create_index("idx_repo_collaborators_login", "repo_collaborators", ["github_login"])

    # ── SAML credential authorizations ──────────────────────────────────
    op.create_table(
        "org_credential_authorizations",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("org", sa.Text, nullable=False),
        sa.Column("github_login", sa.Text, nullable=False),
        sa.Column("credential_id", sa.BigInteger, nullable=False),
        sa.Column("credential_type", sa.Text, nullable=False),
        sa.Column("token_last_eight", sa.String(8), nullable=True),
        sa.Column("credential_authorized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("credential_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scopes", ARRAY(sa.String), nullable=True),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("org", "credential_id", name="uq_org_credential_auth_org_cred"),
    )
    op.create_index("idx_org_credential_auth_org", "org_credential_authorizations", ["org"])
    op.create_index(
        "idx_org_credential_auth_login", "org_credential_authorizations", ["github_login"]
    )

    # ── Org webhooks ────────────────────────────────────────────────────
    op.create_table(
        "org_webhooks",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("org", sa.Text, nullable=False),
        sa.Column("hook_id", sa.BigInteger, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("active", sa.Boolean, nullable=False),
        sa.Column("config_url", sa.Text, nullable=True),
        sa.Column("config_content_type", sa.Text, nullable=True),
        sa.Column("config_insecure_ssl", sa.Text, nullable=True),
        sa.Column("events", ARRAY(sa.String), nullable=True),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("org", "hook_id", name="uq_org_webhooks_org_hook"),
    )
    op.create_index("idx_org_webhooks_org", "org_webhooks", ["org"])

    # ── Repo webhooks ───────────────────────────────────────────────────
    op.create_table(
        "repo_webhooks",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("org", sa.Text, nullable=False),
        sa.Column("repo_name", sa.Text, nullable=False),
        sa.Column("hook_id", sa.BigInteger, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("active", sa.Boolean, nullable=False),
        sa.Column("config_url", sa.Text, nullable=True),
        sa.Column("config_content_type", sa.Text, nullable=True),
        sa.Column("config_insecure_ssl", sa.Text, nullable=True),
        sa.Column("events", ARRAY(sa.String), nullable=True),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("org", "repo_name", "hook_id", name="uq_repo_webhooks_org_repo_hook"),
    )
    op.create_index("idx_repo_webhooks_org_repo", "repo_webhooks", ["org", "repo_name"])

    # ── Actions permissions ─────────────────────────────────────────────
    op.create_table(
        "org_actions_permissions",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("org", sa.Text, nullable=False),
        sa.Column("enabled_repositories", sa.Text, nullable=False),
        sa.Column("allowed_actions", sa.Text, nullable=True),
        sa.Column(
            "github_owned_allowed",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "verified_allowed",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("patterns_allowed", ARRAY(sa.String), nullable=True),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("org", name="uq_org_actions_permissions_org"),
    )
    op.create_index("idx_org_actions_permissions_org", "org_actions_permissions", ["org"])

    # ── Self-hosted runners ─────────────────────────────────────────────
    op.create_table(
        "org_self_hosted_runners",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("org", sa.Text, nullable=False),
        sa.Column("runner_id", sa.BigInteger, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("os", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("busy", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("labels", ARRAY(sa.String), nullable=True),
        sa.Column("runner_group_id", sa.BigInteger, nullable=True),
        sa.Column("runner_group_name", sa.Text, nullable=True),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("org", "runner_id", name="uq_org_self_hosted_runners_org_runner"),
    )
    op.create_index("idx_org_self_hosted_runners_org", "org_self_hosted_runners", ["org"])

    # ── Deploy keys ─────────────────────────────────────────────────────
    op.create_table(
        "repo_deploy_keys",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("org", sa.Text, nullable=False),
        sa.Column("repo_name", sa.Text, nullable=False),
        sa.Column("key_id", sa.BigInteger, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("read_only", sa.Boolean, nullable=False),
        sa.Column("key_added_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("org", "repo_name", "key_id", name="uq_repo_deploy_keys_org_repo_key"),
    )
    op.create_index("idx_repo_deploy_keys_org_repo", "repo_deploy_keys", ["org", "repo_name"])


def downgrade() -> None:
    op.drop_table("repo_deploy_keys")
    op.drop_table("org_self_hosted_runners")
    op.drop_table("org_actions_permissions")
    op.drop_table("repo_webhooks")
    op.drop_table("org_webhooks")
    op.drop_table("org_credential_authorizations")
    op.drop_table("repo_collaborators")
    op.drop_table("org_team_repos")
