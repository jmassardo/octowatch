"""Seed project governance detection rules.

Revision ID: 0055
Revises: 0054
Create Date: 2026-05-11 00:00:00.000000+00:00

Seeds the six project-governance detection rules that were added to
rule_library.json in PR #248 but were never inserted into the
rule_definitions table (rules must be seeded via Alembic migration).
"""

import sqlalchemy as sa

from alembic import op

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None

# (name, slug, description, category, severity, confidence, logic_config_json)
_PROJECT_RULES = [
    (
        "Project Visibility Changed to Public",
        "project-visibility-public",
        "Detects when a GitHub Project is changed from private to public visibility, potentially exposing work items, issue titles, and planning data to anyone.",
        "data_exfiltration",
        "critical",
        "high",
        '{"action_filters": ["project.visibility_public"], "field_conditions": [], "time_window_seconds": 0}',
    ),
    (
        "External Collaborator Added to Project",
        "project-collaborator-added-external",
        "Detects when a collaborator is added to a GitHub Project. External collaborators gain visibility into issue titles, status, and planning data across all linked repositories.",
        "privilege_escalation",
        "high",
        "high",
        '{"action_filters": ["project_collaborator.add"], "field_conditions": [], "time_window_seconds": 0}',
    ),
    (
        "Project Collaborator Role Escalated",
        "project-collaborator-role-escalated",
        "Detects when an existing project collaborator's permission level is upgraded (e.g. read to write or admin), granting broader access to project data and settings.",
        "privilege_escalation",
        "medium",
        "high",
        '{"action_filters": ["project_collaborator.update"], "field_conditions": [], "time_window_seconds": 0}',
    ),
    (
        "Project Base Role Elevated",
        "project-base-role-elevated",
        "Detects when the default project access role for all organization members is raised, potentially granting overly permissive access to project data across the org.",
        "privilege_escalation",
        "high",
        "high",
        '{"action_filters": ["project_base_role.update"], "field_conditions": [], "time_window_seconds": 0}',
    ),
    (
        "Project Deleted",
        "project-deleted",
        "Detects when a GitHub Project is deleted. This could indicate evidence destruction, accidental deletion, or an insider removing audit trails of planned work.",
        "defense_evasion",
        "high",
        "high",
        '{"action_filters": ["project.delete"], "field_conditions": [], "time_window_seconds": 0}',
    ),
    (
        "Project Field Deleted",
        "project-field-deleted",
        "Detects when a custom field is removed from a GitHub Project. Deleting tracking fields (e.g. priority, status) can obscure project health data and remove historical context.",
        "defense_evasion",
        "medium",
        "medium",
        '{"action_filters": ["project_field.delete"], "field_conditions": [], "time_window_seconds": 0}',
    ),
]


def upgrade() -> None:
    """Seed project governance detection rules."""
    conn = op.get_bind()
    for name, slug, description, category, severity, confidence, logic_config in _PROJECT_RULES:
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
                "     'pattern', :logic_config ::jsonb,"
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
                "logic_config": logic_config,
            },
        )


def downgrade() -> None:
    """Remove project governance detection rules."""
    slugs = [slug for _, slug, *_ in _PROJECT_RULES]
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM rule_definitions WHERE slug = ANY(:slugs)"),
        {"slugs": slugs},
    )
