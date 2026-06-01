"""Seed runaway workflow queue detection rules.

Revision ID: 0060
Revises: 0059
Create Date: 2026-06-15 00:00:00.000000+00:00

Seeds two detection rules for alerting on runaway GitHub Actions workflow
queues before the enterprise 50,000 pending run limit is hit:

1. Statistical anomaly rule (3σ above 7-day rolling baseline)
2. Per-actor threshold rule (>500 runs from single actor in 1 hour)

Resolves: #303
"""

import sqlalchemy as sa

from alembic import op

revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None

_WORKFLOW_QUEUE_RULES = [
    (
        "Runaway Workflow Queue \u2014 Anomaly",
        "runaway-workflow-queue-anomaly",
        (
            "Detects when hourly workflows.created_workflow_run event volume "
            "exceeds 3 standard deviations above the rolling 7-day baseline, "
            "indicating a potential runaway automation that could exhaust the "
            "enterprise 50,000 pending workflow run queue limit."
        ),
        "supply_chain",
        "high",
        "high",
        "statistical",
        (
            '{"action_filters": ["workflows.created_workflow_run"], '
            '"x_config": {"engine": "volume_anomaly", "z_multiplier": 3.0, '
            '"baseline_days": 7, "aggregation_interval_minutes": 60}, '
            '"time_window_minutes": 60, "confidence": 0.75}'
        ),
    ),
    (
        "Runaway Workflow Queue \u2014 Actor Spike",
        "runaway-workflow-queue-actor-spike",
        (
            "Detects when a single actor or GitHub App triggers more than "
            "500 workflow runs within one hour, indicating a misconfigured "
            "automation or infinite loop that could exhaust the enterprise "
            "50,000 pending workflow run queue limit."
        ),
        "supply_chain",
        "high",
        "high",
        "threshold",
        (
            '{"action_filters": ["workflows.created_workflow_run"], '
            '"aggregation_key": "actor", "threshold": 500, '
            '"time_window_minutes": 60, "field_conditions": [], '
            '"confidence": 0.8}'
        ),
    ),
]


def upgrade() -> None:
    """Seed runaway workflow queue detection rules."""
    conn = op.get_bind()
    for (
        name,
        slug,
        description,
        category,
        severity,
        confidence,
        logic_type,
        logic_config,
    ) in _WORKFLOW_QUEUE_RULES:
        conn.execute(
            sa.text(
                "INSERT INTO rule_definitions"
                "    (name, slug, description, category,"
                "     default_severity, default_confidence,"
                "     logic_type, logic_config,"
                "     enabled, status, version, created_by)"
                " VALUES"
                "    (:name, :slug, :description, :category,"
                "     :severity, :confidence,"
                "     :logic_type, :logic_config ::jsonb,"
                "     true, 'active', 1, 'system')"
                " ON CONFLICT (slug) DO UPDATE SET"
                "    name = EXCLUDED.name,"
                "    description = EXCLUDED.description,"
                "    category = EXCLUDED.category,"
                "    default_severity = EXCLUDED.default_severity,"
                "    default_confidence = EXCLUDED.default_confidence,"
                "    logic_type = EXCLUDED.logic_type,"
                "    logic_config = EXCLUDED.logic_config,"
                "    enabled = true,"
                "    status = 'active',"
                "    updated_at = NOW()"
            ),
            {
                "name": name,
                "slug": slug,
                "description": description,
                "category": category,
                "severity": severity,
                "confidence": confidence,
                "logic_type": logic_type,
                "logic_config": logic_config,
            },
        )


def downgrade() -> None:
    """Remove runaway workflow queue detection rules."""
    slugs = [slug for _, slug, *_ in _WORKFLOW_QUEUE_RULES]
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM rule_definitions WHERE slug = ANY(:slugs)"),
        {"slugs": slugs},
    )
