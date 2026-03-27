"""Add external_collaborators table.

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE external_collaborators (
            id              BIGSERIAL PRIMARY KEY,
            org             TEXT NOT NULL,
            repo            TEXT,
            github_login    TEXT NOT NULL,
            github_id       BIGINT,
            role            TEXT NOT NULL
                            CHECK (role IN (
                                'read', 'triage', 'write', 'maintain', 'admin',
                                'outside_collaborator', 'guest_collaborator'
                            )),
            granted_at      TIMESTAMPTZ NOT NULL,
            granted_by      TEXT,
            is_active       BOOLEAN NOT NULL DEFAULT TRUE,
            removed_at      TIMESTAMPTZ,
            removed_by      TEXT,
            last_event_at   TIMESTAMPTZ,
            source_event_id BIGINT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

            -- Requires PostgreSQL 15+.  For PG 14, replace with:
            --   CREATE UNIQUE INDEX uq_ext_collab_org_repo_login
            --       ON external_collaborators (org, COALESCE(repo, ''), github_login);
            UNIQUE NULLS NOT DISTINCT (org, repo, github_login)
        )
    """)

    op.execute("CREATE INDEX idx_ext_collab_org ON external_collaborators (org)")
    op.execute("CREATE INDEX idx_ext_collab_login ON external_collaborators (github_login)")
    op.execute("CREATE INDEX idx_ext_collab_last_event ON external_collaborators (last_event_at)")
    op.execute(
        "CREATE INDEX idx_ext_collab_removed ON external_collaborators (removed_at)"
        " WHERE removed_at IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS external_collaborators CASCADE")
