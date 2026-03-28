"""Threat intelligence domains lookup table.

Revision ID: 0014
Revises: 0013
"""

from __future__ import annotations

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE threat_intel_domains (
            id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            domain       TEXT NOT NULL UNIQUE,
            source       TEXT NOT NULL,
            confidence   DOUBLE PRECISION NOT NULL DEFAULT 0.80,
            active       BOOLEAN NOT NULL DEFAULT TRUE,
            added_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            added_by     TEXT NOT NULL,
            expires_at   TIMESTAMPTZ,
            notes        TEXT
        );
    """)
    op.execute("CREATE INDEX idx_threat_intel_active ON threat_intel_domains (active, domain);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS threat_intel_domains CASCADE;")
