"""Add query_templates table.

Revision ID: 0024
Revises: 0023
"""

from __future__ import annotations

from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE query_templates (
            id          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            name        TEXT NOT NULL,
            description TEXT,
            sql         TEXT NOT NULL,
            created_by  TEXT,
            org_slug    TEXT,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("CREATE INDEX ix_query_templates_org_slug ON query_templates (org_slug);")
    op.execute("CREATE INDEX ix_query_templates_created_by ON query_templates (created_by);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_query_templates_created_by;")
    op.execute("DROP INDEX IF EXISTS ix_query_templates_org_slug;")
    op.execute("DROP TABLE IF EXISTS query_templates;")
