"""Add SIEM export config table.

Revision ID: 0030
Revises: 0029
Create Date: 2025-01-01 00:00:00.000000+00:00
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

# revision identifiers
revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "siem_export_configs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("export_type", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        # Syslog
        sa.Column("syslog_host", sa.Text(), nullable=True),
        sa.Column("syslog_port", sa.Integer(), nullable=True),
        sa.Column("syslog_protocol", sa.Text(), nullable=True),
        sa.Column("syslog_format", sa.Text(), nullable=True),
        # Splunk HEC
        sa.Column("splunk_hec_url", sa.Text(), nullable=True),
        sa.Column("splunk_hec_token_env_var", sa.Text(), nullable=True),
        sa.Column("splunk_sourcetype", sa.Text(), nullable=True, server_default="octowatch:event"),
        sa.Column("splunk_index", sa.Text(), nullable=True),
        # Webhook
        sa.Column("webhook_url", sa.Text(), nullable=True),
        sa.Column("webhook_secret_env_var", sa.Text(), nullable=True),
        sa.Column("webhook_headers", JSONB(), nullable=True),
        # Common
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("export_events", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column(
            "export_detections", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")
        ),
        sa.Column("created_by", sa.Text(), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("siem_export_configs")
