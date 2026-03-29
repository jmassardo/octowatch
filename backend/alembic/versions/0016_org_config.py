"""Add org_config table for per-org configuration overrides.

Revision ID: 0016
Revises: 0015
"""

from __future__ import annotations

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE org_config (
            id                    INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            org_slug              TEXT NOT NULL UNIQUE,
            copilot_cost_per_seat DOUBLE PRECISION,
            created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("CREATE UNIQUE INDEX idx_org_config_slug ON org_config (org_slug);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS org_config CASCADE;")
