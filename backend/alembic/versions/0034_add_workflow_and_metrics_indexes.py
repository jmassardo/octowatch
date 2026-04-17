"""Add partial expression indexes for workflow metrics and executive metrics.

Revision ID: 0034
Revises: 0033
Create Date: 2025-01-01
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create partial expression indexes for workflow metrics queries.

    Uses AUTOCOMMIT because CREATE INDEX CONCURRENTLY cannot run inside a
    transaction block.
    """
    connection = op.get_bind()
    connection.execution_options(isolation_level="AUTOCOMMIT")

    connection.execute(
        sa.text("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_events_workflow_conclusion
            ON events (org, (data->>'conclusion'), created_at DESC)
            WHERE action = 'workflows.completed_workflow_run'
    """)
    )

    connection.execute(
        sa.text("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_events_workflow_run_conclusion
            ON events (org, (data->>'conclusion'), created_at DESC)
            WHERE action LIKE 'workflow_run.%'
    """)
    )

    connection.execute(
        sa.text("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_events_pr_lifecycle
            ON events (org, repo, (data->>'pull_request_id'), created_at)
            WHERE action IN ('pull_request.close', 'pull_request.create')
    """)
    )

    connection.execute(
        sa.text("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_events_push_ref
            ON events (org, repo, (data->>'ref'), created_at)
            WHERE action = 'git.push'
    """)
    )


def downgrade() -> None:
    """Drop workflow metrics and executive metrics indexes."""
    connection = op.get_bind()
    connection.execution_options(isolation_level="AUTOCOMMIT")

    connection.execute(sa.text("DROP INDEX CONCURRENTLY IF EXISTS idx_events_workflow_conclusion"))
    connection.execute(
        sa.text("DROP INDEX CONCURRENTLY IF EXISTS idx_events_workflow_run_conclusion")
    )
    connection.execute(sa.text("DROP INDEX CONCURRENTLY IF EXISTS idx_events_pr_lifecycle"))
    connection.execute(sa.text("DROP INDEX CONCURRENTLY IF EXISTS idx_events_push_ref"))
