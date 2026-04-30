"""Auth method configs and session policy settings.

Revision ID: 0040
Revises: 0039
Create Date: 2024-01-21 00:00:00.000000+00:00

This migration:
1. Creates auth_method_configs table (github_oauth, saml_sso, local_password)
2. Creates session_policy_settings table (max_session_duration, idle_timeout)
3. Seeds default rows for both tables
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── auth_method_configs ──
    op.create_table(
        "auth_method_configs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("method_name", sa.String(64), unique=True, nullable=False, index=True),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("config_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # ── session_policy_settings ──
    op.create_table(
        "session_policy_settings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("policy_key", sa.String(64), unique=True, nullable=False, index=True),
        sa.Column("policy_value", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # ── Seed default auth methods ──
    auth_methods = sa.table(
        "auth_method_configs",
        sa.column("method_name", sa.String),
        sa.column("display_name", sa.String),
        sa.column("enabled", sa.Boolean),
        sa.column("config_json", sa.JSON),
    )
    op.bulk_insert(
        auth_methods,
        [
            {
                "method_name": "github_oauth",
                "display_name": "GitHub OAuth",
                "enabled": True,
                "config_json": {},
            },
            {
                "method_name": "saml_sso",
                "display_name": "SAML SSO",
                "enabled": False,
                "config_json": {},
            },
            {
                "method_name": "local_password",
                "display_name": "Local Password",
                "enabled": False,
                "config_json": {},
            },
        ],
    )

    # ── Seed default session policies ──
    session_policies = sa.table(
        "session_policy_settings",
        sa.column("policy_key", sa.String),
        sa.column("policy_value", sa.String),
        sa.column("description", sa.Text),
    )
    op.bulk_insert(
        session_policies,
        [
            {
                "policy_key": "max_session_duration",
                "policy_value": "86400",
                "description": "Maximum session lifetime in seconds (default 24h)",
            },
            {
                "policy_key": "idle_timeout",
                "policy_value": "3600",
                "description": "Session idle timeout in seconds (default 1h)",
            },
        ],
    )


def downgrade() -> None:
    op.drop_table("session_policy_settings")
    op.drop_table("auth_method_configs")
