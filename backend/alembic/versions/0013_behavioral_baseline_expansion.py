"""Expand behavioral baselines with push-bypass, alert-dismiss, admin-action metrics.

Revision ID: 0013
Revises: 0012
"""

from __future__ import annotations

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE behavioral_baselines
            ADD COLUMN IF NOT EXISTS push_bypass_hourly_mean    DOUBLE PRECISION,
            ADD COLUMN IF NOT EXISTS push_bypass_hourly_stddev  DOUBLE PRECISION,
            ADD COLUMN IF NOT EXISTS alert_dismiss_daily_mean   DOUBLE PRECISION,
            ADD COLUMN IF NOT EXISTS alert_dismiss_daily_stddev DOUBLE PRECISION,
            ADD COLUMN IF NOT EXISTS admin_action_daily_mean    DOUBLE PRECISION,
            ADD COLUMN IF NOT EXISTS admin_action_daily_stddev  DOUBLE PRECISION;
    """)


def downgrade() -> None:
    for col in [
        "push_bypass_hourly_mean",
        "push_bypass_hourly_stddev",
        "alert_dismiss_daily_mean",
        "alert_dismiss_daily_stddev",
        "admin_action_daily_mean",
        "admin_action_daily_stddev",
    ]:
        op.execute(f"ALTER TABLE behavioral_baselines DROP COLUMN IF EXISTS {col};")
