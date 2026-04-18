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

    Note: TimescaleDB hypertables do not support CREATE INDEX CONCURRENTLY,
    so we use regular CREATE INDEX instead.
    """
    op.execute(
        sa.text("""
        CREATE INDEX IF NOT EXISTS idx_events_workflow_conclusion
            ON events (org, (data->>'conclusion'), created_at DESC)
            WHERE action = 'workflows.completed_workflow_run'
    """)
    )

    op.execute(
        sa.text("""
        CREATE INDEX IF NOT EXISTS idx_events_workflow_run_conclusion
            ON events (org, (data->>'conclusion'), created_at DESC)
            WHERE action LIKE 'workflow_run.%'
    """)
    )

    op.execute(
        sa.text("""
        CREATE INDEX IF NOT EXISTS idx_events_pr_lifecycle
            ON events (org, repo, (data->>'pull_request_id'), created_at)
            WHERE action IN ('pull_request.close', 'pull_request.create')
    """)
    )

    op.execute(
        sa.text("""
        CREATE INDEX IF NOT EXISTS idx_events_push_ref
            ON events (org, repo, (data->>'ref'), created_at)
            WHERE action = 'git.push'
    """)
    )


def downgrade() -> None:
    """Drop workflow metrics and executive metrics indexes."""
    op.execute(sa.text("DROP INDEX IF EXISTS idx_events_workflow_conclusion"))
    op.execute(sa.text("DROP INDEX IF EXISTS idx_events_workflow_run_conclusion"))
    op.execute(sa.text("DROP INDEX IF EXISTS idx_events_pr_lifecycle"))
    op.execute(sa.text("DROP INDEX IF EXISTS idx_events_push_ref"))
