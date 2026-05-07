"""Add workflow_scan_activities table.

Revision ID: 0048
Revises: 0046
Create Date: 2026-05-10

Records provenance for each workflow security scan execution, tracking
which events triggered the scan, what checks were performed, and results.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY

from alembic import op

revision = "0048"
down_revision = "0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create workflow_scan_activities table."""
    op.create_table(
        "workflow_scan_activities",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("trigger_event_ids", ARRAY(sa.Integer), nullable=False, server_default="{}"),
        sa.Column("org", sa.Text, nullable=False),
        sa.Column("repo", sa.Text, nullable=False),
        sa.Column("workflow_path", sa.Text, nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Text, nullable=False, server_default=sa.text("'pending'")),
        sa.Column("checks_performed", ARRAY(sa.Text), nullable=False, server_default="{}"),
        sa.Column("findings_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("data_sources", ARRAY(sa.Text), nullable=False, server_default="{}"),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
    )
    op.create_index(
        "ix_wf_scan_activity_org_repo",
        "workflow_scan_activities",
        ["org", "repo"],
    )
    op.create_index(
        "ix_wf_scan_activity_started_at",
        "workflow_scan_activities",
        ["started_at"],
    )
    op.create_index(
        "ix_wf_scan_activity_status",
        "workflow_scan_activities",
        ["status"],
    )


def downgrade() -> None:
    """Drop workflow_scan_activities table."""
    op.drop_index("ix_wf_scan_activity_status", table_name="workflow_scan_activities")
    op.drop_index("ix_wf_scan_activity_started_at", table_name="workflow_scan_activities")
    op.drop_index("ix_wf_scan_activity_org_repo", table_name="workflow_scan_activities")
    op.drop_table("workflow_scan_activities")
