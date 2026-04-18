"""Add partial indexes for lead time query performance.

Revision ID: 0036
Revises: 0035
Create Date: 2026-04-18
"""

from alembic import op

# revision identifiers
revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_events_pr_merged
            ON events (org, repo, created_at DESC)
            WHERE action = 'pull_request.merged';
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_events_deploy_status_sha
            ON events (repo, (data->>'sha'), created_at)
            WHERE action = 'deployment_status.success';
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_events_workflow_success_sha
            ON events (repo, (data->>'head_sha'), created_at)
            WHERE action = 'workflow_run.success';
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_events_issue_opened
            ON events (repo, (data->>'number'), created_at)
            WHERE action = 'issue.opened';
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_events_issue_opened;")
    op.execute("DROP INDEX IF EXISTS idx_events_workflow_success_sha;")
    op.execute("DROP INDEX IF EXISTS idx_events_deploy_status_sha;")
    op.execute("DROP INDEX IF EXISTS idx_events_pr_merged;")
