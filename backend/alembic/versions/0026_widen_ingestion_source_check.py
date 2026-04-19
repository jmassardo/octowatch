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
    # TimescaleDB with compression enabled blocks ALTER TABLE … DROP/ADD CONSTRAINT.
    # We must temporarily disable the compression configuration, alter the constraint,
    # then re-enable compression with the original settings.
    op.execute("""
        DO $$
        DECLARE
            cname TEXT;
            has_compression BOOLEAN;
        BEGIN
            -- Check if compression is currently configured on this hypertable
            SELECT EXISTS (
                SELECT 1 FROM timescaledb_information.hypertables
                 WHERE hypertable_name = 'events'
                   AND compression_enabled = true
            ) INTO has_compression;

            IF has_compression THEN
                -- Disable compression to allow DDL changes
                EXECUTE 'ALTER TABLE events SET (timescaledb.compress = false)';
            END IF;

            -- Drop the existing narrow CHECK constraint
            SELECT conname INTO cname
              FROM pg_constraint
             WHERE conrelid = 'events'::regclass
               AND contype = 'c'
               AND pg_get_constraintdef(oid) ILIKE '%ingestion_source%';
            IF cname IS NOT NULL THEN
                EXECUTE format('ALTER TABLE events DROP CONSTRAINT %I', cname);
            END IF;

            -- Add the widened constraint
            ALTER TABLE events
                ADD CONSTRAINT chk_events_ingestion_source
                CHECK (ingestion_source IN (
                    's3', 'azure_blob', 'minio',
                    'github_enterprise_sync', 'github_api_sync',
                    'hec_webhook'
                ));

            IF has_compression THEN
                -- Re-enable compression with original settings
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
                ADD CONSTRAINT events_ingestion_source_check
                CHECK (ingestion_source IN ('s3', 'azure_blob', 'minio'));

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
