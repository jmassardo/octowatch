"""Add Epic 12 tables: playbooks, Copilot policies, workflow findings.

Revision ID: 0031
Revises: 0030
Create Date: 2025-07-24 00:00:00.000000+00:00
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from alembic import op

# revision identifiers
revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Issue #39 – plugin enrichment data on events
    op.add_column("events", sa.Column("custom_enrichments", JSONB(), nullable=True))

    # Playbook templates
    op.create_table(
        "playbook_templates",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "detection_categories",
            ARRAY(sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("steps", JSONB(), nullable=False, server_default="[]"),
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
    op.create_index("ix_playbook_templates_slug", "playbook_templates", ["slug"])

    # Playbook executions
    op.create_table(
        "playbook_executions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("template_id", sa.BigInteger(), nullable=False),
        sa.Column("detection_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("step_results", JSONB(), nullable=False, server_default="[]"),
        sa.Column("started_by", sa.Text(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["playbook_templates.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["detection_id"],
            ["detections.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_playbook_executions_detection_id", "playbook_executions", ["detection_id"])
    op.create_index("ix_playbook_executions_status", "playbook_executions", ["status"])

    # Copilot policies
    op.create_table(
        "copilot_policies",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("policy_type", sa.Text(), nullable=False),
        sa.Column("config", JSONB(), nullable=False, server_default="{}"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
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
    op.create_index(
        "ix_copilot_policies_type_enabled",
        "copilot_policies",
        ["policy_type", "enabled"],
    )

    # Copilot policy violations
    op.create_table(
        "copilot_policy_violations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("policy_id", sa.BigInteger(), nullable=False),
        sa.Column("actor_login", sa.Text(), nullable=True),
        sa.Column("violation_details", JSONB(), nullable=False, server_default="{}"),
        sa.Column("detection_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["policy_id"],
            ["copilot_policies.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_copilot_policy_violations_policy_created",
        "copilot_policy_violations",
        ["policy_id", "created_at"],
    )

    # Workflow findings
    op.create_table(
        "workflow_findings",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("repo", sa.Text(), nullable=False),
        sa.Column("org", sa.Text(), nullable=False),
        sa.Column("workflow_path", sa.Text(), nullable=False),
        sa.Column("rule_id", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("details", JSONB(), nullable=False, server_default="{}"),
        sa.Column("suggested_fix", sa.Text(), nullable=True),
        sa.Column(
            "scanned_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_workflow_findings_repo_scanned", "workflow_findings", ["repo", "scanned_at"]
    )
    op.create_index("ix_workflow_findings_org", "workflow_findings", ["org"])
    op.create_index("ix_workflow_findings_severity", "workflow_findings", ["severity"])


def downgrade() -> None:
    op.drop_table("workflow_findings")
    op.drop_table("copilot_policy_violations")
    op.drop_table("copilot_policies")
    op.drop_table("playbook_executions")
    op.drop_table("playbook_templates")
    op.drop_column("events", "custom_enrichments")
