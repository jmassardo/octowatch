"""Seed playbook templates for all built-in detection rules.

Revision ID: 0060
Revises: 0059
Create Date: 2026-06-01 00:00:00.000000+00:00

Seeds playbook templates from the playbooks.json fixture so that every
built-in detection rule category has an associated response playbook with
step-by-step investigation and remediation guidance.  Closes #301.
"""

from __future__ import annotations

import json
from pathlib import Path

import sqlalchemy as sa

from alembic import op

revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None

_FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent.parent / "app" / "fixtures" / "playbooks.json"
)

_INSERT_SQL = sa.text(
    "INSERT INTO playbook_templates"
    "    (name, slug, description, detection_categories, steps, created_by)"
    " VALUES"
    "    (:name, :slug, :description, :detection_categories,"
    "     :steps ::jsonb, 'system')"
    " ON CONFLICT (slug) DO UPDATE SET"
    "    name = EXCLUDED.name,"
    "    description = EXCLUDED.description,"
    "    detection_categories = EXCLUDED.detection_categories,"
    "    steps = EXCLUDED.steps,"
    "    updated_at = NOW()"
)


def upgrade() -> None:
    """Seed playbook templates from fixtures/playbooks.json."""
    conn = op.get_bind()
    playbooks = json.loads(_FIXTURE_PATH.read_text())

    for pb in playbooks:
        conn.execute(
            _INSERT_SQL,
            {
                "name": pb["name"],
                "slug": pb["slug"],
                "description": pb["description"],
                "detection_categories": pb["detection_categories"],
                "steps": json.dumps(pb["steps"]),
            },
        )


def downgrade() -> None:
    """Remove seeded playbook templates."""
    conn = op.get_bind()
    playbooks = json.loads(_FIXTURE_PATH.read_text())
    slugs = [pb["slug"] for pb in playbooks]
    conn.execute(
        sa.text("DELETE FROM playbook_templates WHERE slug = ANY(:slugs)"),
        {"slugs": slugs},
    )
