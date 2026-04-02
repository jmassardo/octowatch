"""Add TimescaleDB retention policies for hypertables.

Revision ID: 0023
Revises: 0022
"""

from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Retain events for 2 years (730 days)
    op.execute("""
        SELECT add_retention_policy('events', INTERVAL '730 days', if_not_exists => true);
    """)
    # Retain audit trail for 3 years (1095 days)
    op.execute("""
        SELECT add_retention_policy('audit_trail', INTERVAL '1095 days', if_not_exists => true);
    """)
    # Retain system health events for 180 days
    op.execute("""
        SELECT add_retention_policy('system_health_events', INTERVAL '180 days', if_not_exists => true);
    """)


def downgrade() -> None:
    op.execute("SELECT remove_retention_policy('events', if_exists => true);")
    op.execute("SELECT remove_retention_policy('audit_trail', if_exists => true);")
    op.execute("SELECT remove_retention_policy('system_health_events', if_exists => true);")
