"""Allow 'copilot_session_api' as an ingestion_cursors.source_type.

The #507 Copilot session ingestion worker (poll_copilot_sessions, registered
on a 15-minute Celery beat schedule) persists its polling progress via the
existing ingestion_cursors table, using source_type="copilot_session_api".
However, the 0001 migration's inline CHECK constraint only allows
('s3', 'azure_blob', 'minio'), so every cursor upsert from the new worker
would fail with a CheckViolationError as soon as it runs, causing the task to
error out on every 15-minute tick. This was flagged as an out-of-allowlist
finding by the #507 lane and is fixed here as a standalone, additive
migration before that worker ships.

Revision ID: 0074
Revises: 0073
Create Date: 2026-11-04 17:05:00.000000

"""

from __future__ import annotations

from alembic import op

revision = "0074"
down_revision = "0073"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "ingestion_cursors_source_type_check",
        "ingestion_cursors",
        type_="check",
    )
    op.create_check_constraint(
        "ingestion_cursors_source_type_check",
        "ingestion_cursors",
        "source_type IN ('s3', 'azure_blob', 'minio', 'copilot_session_api')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ingestion_cursors_source_type_check",
        "ingestion_cursors",
        type_="check",
    )
    op.create_check_constraint(
        "ingestion_cursors_source_type_check",
        "ingestion_cursors",
        "source_type IN ('s3', 'azure_blob', 'minio')",
    )
