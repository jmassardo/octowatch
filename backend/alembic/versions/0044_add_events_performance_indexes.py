"""Add performance indexes for events queries.

Revision ID: 0044
Revises: 0043
Create Date: 2026-05-06 00:00:00.000000+00:00

Adds indexes to speed up the Events Explorer page:
- Composite index on (org, created_at DESC) for the main listing query
- Partial indexes on org+actor, org+action, org+repo, org+namespace for
  the suggestion/typeahead DISTINCT queries
"""

from alembic import op

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Main events listing: WHERE org = ANY(...) ORDER BY created_at DESC
    op.execute(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_events_org_created_at"
        " ON events (org, created_at DESC)"
    )
    # Suggestions: SELECT DISTINCT action WHERE org = ANY(...)
    op.execute(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_events_org_action ON events (org, action)"
    )
    # Suggestions: SELECT DISTINCT actor WHERE org = ANY(...) AND actor IS NOT NULL
    op.execute(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_events_org_actor"
        " ON events (org, actor) WHERE actor IS NOT NULL AND actor != ''"
    )
    # Suggestions: SELECT DISTINCT repo WHERE org = ANY(...) AND repo IS NOT NULL
    op.execute(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_events_org_repo"
        " ON events (org, repo) WHERE repo IS NOT NULL AND repo != ''"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_events_org_repo")
    op.execute("DROP INDEX IF EXISTS ix_events_org_actor")
    op.execute("DROP INDEX IF EXISTS ix_events_org_action")
    op.execute("DROP INDEX IF EXISTS ix_events_org_created_at")
