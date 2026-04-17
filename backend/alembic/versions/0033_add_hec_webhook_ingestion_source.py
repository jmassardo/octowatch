"""Add 'hec' and 'webhook' to events.ingestion_source CHECK constraint.

The HEC (Splunk HTTP Event Collector) receiver writes events with
ingestion_source='hec'.  Add both 'hec' and 'webhook' as allowed
values for future-proofing.

Revision ID: 0033
Revises: 0032
"""

from __future__ import annotations

from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop existing constraint and recreate with additional values.
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
                'github_enterprise_sync', 'github_api_sync',
                'hec', 'webhook'
            ));
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE events DROP CONSTRAINT IF EXISTS chk_events_ingestion_source;
    """)
    op.execute("""
        ALTER TABLE events
            ADD CONSTRAINT chk_events_ingestion_source
            CHECK (ingestion_source IN (
                's3', 'azure_blob', 'minio',
                'github_enterprise_sync', 'github_api_sync'
            ));
    """)
