"""Add missing unique constraint on workflow_findings for upsert support.

workflow_scan_worker.py performs an INSERT ... ON CONFLICT (repo, workflow_path,
rule_id) DO UPDATE, but the 0032 migration that created this table never added
a matching unique constraint/index. Every upsert has been failing since launch
with asyncpg.InvalidColumnReferenceError ("no unique or exclusion constraint
matching the ON CONFLICT specification"), causing scan_workflow_events tasks to
retry forever and permanently stall the baseline queue. Table is empty in all
environments (0 rows), so no deduplication is required before adding the
constraint.

Revision ID: 0072
Revises: 0071
Create Date: 2026-10-29 20:30:00.000000

"""

from __future__ import annotations

from alembic import op

revision = "0072"
down_revision = "0071"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_workflow_findings_repo_workflow_rule",
        "workflow_findings",
        ["repo", "workflow_path", "rule_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_workflow_findings_repo_workflow_rule",
        "workflow_findings",
        type_="unique",
    )
