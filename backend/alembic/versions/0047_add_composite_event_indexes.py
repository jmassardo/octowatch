"""Add composite indexes for common Events Explorer query patterns.

Revision ID: 0047
Revises: 0046
Create Date: 2025-07-14

These indexes optimize the most common filter combinations used in the
Events Explorer: org+action, org+actor, and org+namespace, each sorted
by created_at DESC for efficient keyset and offset pagination.

NOTE: CONCURRENTLY is NOT used because TimescaleDB hypertables do not
support concurrent index creation.
"""

from alembic import op

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create composite indexes for common Events Explorer filter patterns."""
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_events_org_action ON events (org, action, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_events_org_actor ON events (org, actor, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_events_org_namespace "
        "ON events (org, namespace, created_at DESC)"
    )


def downgrade() -> None:
    """Drop composite indexes."""
    op.execute("DROP INDEX IF EXISTS idx_events_org_namespace")
    op.execute("DROP INDEX IF EXISTS idx_events_org_actor")
    op.execute("DROP INDEX IF EXISTS idx_events_org_action")
