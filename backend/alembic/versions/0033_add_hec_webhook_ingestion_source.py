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
    # Must disable TimescaleDB compression first — ALTER TABLE ADD/DROP CONSTRAINT
    # is blocked when compression is configured on a hypertable.
    op.execute("""
        DO $$
        DECLARE
            cname TEXT;
            has_compression BOOLEAN;
        BEGIN
            SELECT EXISTS (
                SELECT 1 FROM timescaledb_information.hypertables
                 WHERE hypertable_name = 'events'
                   AND compression_enabled = true
            ) INTO has_compression;

            IF has_compression THEN
                EXECUTE 'ALTER TABLE events SET (timescaledb.compress = false)';
            END IF;

            SELECT conname INTO cname
              FROM pg_constraint
             WHERE conrelid = 'events'::regclass
               AND contype = 'c'
               AND pg_get_constraintdef(oid) ILIKE '%ingestion_source%';
            IF cname IS NOT NULL THEN
                EXECUTE format('ALTER TABLE events DROP CONSTRAINT %I', cname);
            END IF;

            ALTER TABLE events
                ADD CONSTRAINT chk_events_ingestion_source
                CHECK (ingestion_source IN (
                    's3', 'azure_blob', 'minio',
                    'github_enterprise_sync', 'github_api_sync',
                    'hec', 'webhook'
                ));

            IF has_compression THEN
                EXECUTE $sql$
                    ALTER TABLE events SET (
                        timescaledb.compress,
                        timescaledb.compress_segmentby = 'org, namespace',
                        timescaledb.compress_orderby   = 'created_at DESC'
                    )
                $sql$;
            END IF;
        END
        $$;
    """)


def downgrade() -> None:
    op.execute("""
        DO $$
        DECLARE
            has_compression BOOLEAN;
        BEGIN
            SELECT EXISTS (
                SELECT 1 FROM timescaledb_information.hypertables
                 WHERE hypertable_name = 'events'
                   AND compression_enabled = true
            ) INTO has_compression;

            IF has_compression THEN
                EXECUTE 'ALTER TABLE events SET (timescaledb.compress = false)';
            END IF;

            ALTER TABLE events DROP CONSTRAINT IF EXISTS chk_events_ingestion_source;

            ALTER TABLE events
                ADD CONSTRAINT chk_events_ingestion_source
                CHECK (ingestion_source IN (
                    's3', 'azure_blob', 'minio',
                    'github_enterprise_sync', 'github_api_sync'
                ));

            IF has_compression THEN
                EXECUTE $sql$
                    ALTER TABLE events SET (
                        timescaledb.compress,
                        timescaledb.compress_segmentby = 'org, namespace',
                        timescaledb.compress_orderby   = 'created_at DESC'
                    )
                $sql$;
            END IF;
        END
        $$;
    """)
