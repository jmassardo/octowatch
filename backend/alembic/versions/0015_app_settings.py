"""Add app_settings, app_settings_audit, and setup_state tables.

Revision ID: 0015
Revises: 0014
"""

from __future__ import annotations

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE app_settings (
            id           INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            key          TEXT NOT NULL UNIQUE,
            encrypted_value TEXT NOT NULL,
            category     TEXT NOT NULL DEFAULT 'config',
            sensitivity  TEXT NOT NULL DEFAULT 'config',
            description  TEXT,
            updated_by   TEXT NOT NULL DEFAULT 'system',
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("CREATE INDEX idx_app_settings_key ON app_settings (key);")

    op.execute("""
        CREATE TABLE app_settings_audit (
            id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            setting_key      TEXT NOT NULL,
            action           TEXT NOT NULL,
            changed_by       TEXT NOT NULL,
            old_value_masked TEXT,
            new_value_masked TEXT,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("CREATE INDEX idx_app_settings_audit_key ON app_settings_audit (setting_key);")

    op.execute("""
        CREATE TABLE setup_state (
            id               INTEGER PRIMARY KEY DEFAULT 1,
            is_complete      BOOLEAN NOT NULL DEFAULT FALSE,
            completed_by     TEXT,
            completed_at     TIMESTAMPTZ,
            setup_token_hash TEXT,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS setup_state CASCADE;")
    op.execute("DROP TABLE IF EXISTS app_settings_audit CASCADE;")
    op.execute("DROP TABLE IF EXISTS app_settings CASCADE;")
