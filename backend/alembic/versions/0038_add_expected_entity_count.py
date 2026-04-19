"""Add expected_entity_count to enterprise_sync_runs.

Revision ID: 0038
Revises: 0037
Create Date: 2026-05-01

Adds a nullable integer column that records how many (entity_type, org) tasks
the orchestrator dispatched for a given sync run.  _maybe_finalize_run uses
this value to avoid prematurely marking a run completed when fast-finishing
tasks call it before slower tasks have created their cursor rows.
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers
revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "enterprise_sync_runs",
        sa.Column("expected_entity_count", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("enterprise_sync_runs", "expected_entity_count")
