"""Reconcile TimescaleDB retention policies with centralized retention_policies table.

Revision ID: 0046
Revises: 0045
Create Date: 2026-05-06

The old migration 0023 created TimescaleDB retention policies with values
(events=730d, audit_trail=1095d, health=180d) that conflict with the
centralized retention_policies table (migration 0041). This migration
updates the TimescaleDB policies to match the source of truth.
"""

from alembic import op

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Update TimescaleDB retention policies to match retention_policies table.

    Uses the centralized table as source of truth for all retention values.
    Safe to run whether or not TimescaleDB is installed — errors are silently ignored.
    """
    # Remove old hardcoded TimescaleDB policies and re-create from source of truth.
    # If TimescaleDB is not installed, these are no-ops.
    op.execute("""
        DO $$
        BEGIN
            -- Only proceed if TimescaleDB is installed
            IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
                -- Remove old hardcoded policies
                PERFORM remove_retention_policy('events', if_exists => true);
                PERFORM remove_retention_policy('audit_trail', if_exists => true);
                PERFORM remove_retention_policy('system_health_events', if_exists => true);

                -- Re-create from retention_policies table values
                PERFORM add_retention_policy(
                    'events',
                    (SELECT (retention_days || ' days')::INTERVAL FROM retention_policies WHERE data_type = 'events'),
                    if_not_exists => true
                );
                PERFORM add_retention_policy(
                    'audit_trail',
                    (SELECT (retention_days || ' days')::INTERVAL FROM retention_policies WHERE data_type = 'audit_trail'),
                    if_not_exists => true
                );
                PERFORM add_retention_policy(
                    'system_health_events',
                    (SELECT (retention_days || ' days')::INTERVAL FROM retention_policies WHERE data_type = 'system_health_events'),
                    if_not_exists => true
                );
            END IF;
        END $$;
    """)


def downgrade() -> None:
    """Revert to original hardcoded TimescaleDB retention policies."""
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
                PERFORM remove_retention_policy('events', if_exists => true);
                PERFORM remove_retention_policy('audit_trail', if_exists => true);
                PERFORM remove_retention_policy('system_health_events', if_exists => true);

                PERFORM add_retention_policy('events', INTERVAL '730 days', if_not_exists => true);
                PERFORM add_retention_policy('audit_trail', INTERVAL '1095 days', if_not_exists => true);
                PERFORM add_retention_policy('system_health_events', INTERVAL '180 days', if_not_exists => true);
            END IF;
        END $$;
    """)
