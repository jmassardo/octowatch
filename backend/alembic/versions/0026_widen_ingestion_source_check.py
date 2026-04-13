"""Widen events.ingestion_source CHECK to allow github_enterprise_sync and github_api_sync.

The original CHECK constraint on events.ingestion_source only permits
's3', 'azure_blob', and 'minio'.  The GitHub Enterprise sync worker
writes 'github_enterprise_sync' and the new REST-API activity sync
writes 'github_api_sync'.  Both values must be allowed.

Revision ID: 0026
Revises: 0025
"""

from __future__ import annotations

from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the existing narrow CHECK constraint and recreate with additional values.
    # TimescaleDB hypertables do not support ALTER TABLE … DROP CONSTRAINT by name
    # on the parent table, so we target the constraint name from pg_constraint.
    op.execute("""
        DO $$
        DECLARE
            cname TEXT;
        BEGIN
            SELECT conname INTO cname
              FROM pg_constraint
             WHERE conrelid = 'events'::regclass
               AND contype = 'c'
               AND pg_get_constraintdef(oid) ILIKE '%ingestion_source%';
            IF cname IS NOT NULL THEN
                EXECUTE format('ALTER TABLE events DROP CONSTRAINT %I', cname);
            END IF;
        END
        $$;
    """)
    op.execute("""
        ALTER TABLE events
            ADD CONSTRAINT chk_events_ingestion_source
            CHECK (ingestion_source IN (
                's3', 'azure_blob', 'minio',
                'github_enterprise_sync', 'github_api_sync'
            ));
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE events DROP CONSTRAINT IF EXISTS chk_events_ingestion_source;
    """)
    op.execute("""
        ALTER TABLE events
            ADD CONSTRAINT events_ingestion_source_check
            CHECK (ingestion_source IN ('s3', 'azure_blob', 'minio'));
    """)
