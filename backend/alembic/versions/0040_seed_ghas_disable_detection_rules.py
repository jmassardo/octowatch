"""Seed GHAS disable detection rules.

Revision ID: 0040
Revises: 0039
Create Date: 2024-01-21 00:00:00.000000+00:00

Adds built-in detection rules for GitHub Advanced Security (GHAS) feature
disable events.  When someone disables code scanning, Dependabot, secret
scanning, vulnerability alerts, advanced security, or push protection, the
detection pipeline will now create a detection.
"""

import sqlalchemy as sa

from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None

# Each tuple: (name, slug, description, category, severity, confidence, logic_config_json)
_GHAS_RULES = [
    (
        "GHAS Code Scanning Disabled",
        "ghas-code-scanning-disabled",
        "Code scanning was disabled on a repository",
        "security_posture",
        "high",
        "high",
        '{"action_filters": ["code_scanning.disable"], "field_conditions": [], "time_window_seconds": 0}',
    ),
    (
        "GHAS Dependabot Alerts Disabled",
        "ghas-dependabot-alerts-disabled",
        "Dependabot alerts were disabled",
        "security_posture",
        "high",
        "high",
        '{"action_filters": ["dependabot_alerts.disable"], "field_conditions": [], "time_window_seconds": 0}',
    ),
    (
        "GHAS Dependabot Security Updates Disabled",
        "ghas-dependabot-updates-disabled",
        "Dependabot security updates were disabled",
        "security_posture",
        "medium",
        "high",
        '{"action_filters": ["dependabot_security_updates.disable"], "field_conditions": [], "time_window_seconds": 0}',
    ),
    (
        "GHAS Secret Scanning Disabled",
        "ghas-secret-scanning-disabled",
        "Secret scanning was disabled",
        "security_posture",
        "critical",
        "high",
        '{"action_filters": ["secret_scanning.disable", "repository_secret_scanning.disable"], "field_conditions": [], "time_window_seconds": 0}',
    ),
    (
        "GHAS Vulnerability Alerts Disabled",
        "ghas-vulnerability-alerts-disabled",
        "Vulnerability alerts were disabled on a repository",
        "security_posture",
        "high",
        "high",
        '{"action_filters": ["repository_vulnerability_alerts.disable"], "field_conditions": [], "time_window_seconds": 0}',
    ),
    (
        "GHAS Advanced Security Disabled",
        "ghas-advanced-security-disabled",
        "GitHub Advanced Security was disabled",
        "security_posture",
        "critical",
        "high",
        '{"action_filters": ["business.advanced_security_disabled", "org.advanced_security_disabled_for_new_repos", "repo.advanced_security_disabled"], "field_conditions": [], "time_window_seconds": 0}',
    ),
    (
        "GHAS Push Protection Disabled",
        "ghas-push-protection-disabled",
        "Secret scanning push protection was disabled",
        "security_posture",
        "critical",
        "high",
        '{"action_filters": ["secret_scanning_push_protection.disable", "repository_secret_scanning_push_protection.disable"], "field_conditions": [], "time_window_seconds": 0}',
    ),
]


def upgrade() -> None:
    """Seed GHAS disable detection rules."""
    conn = op.get_bind()
    for name, slug, description, category, severity, confidence, logic_config in _GHAS_RULES:
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
    """Remove GHAS disable detection rules."""
    slugs = [slug for _, slug, *_ in _GHAS_RULES]
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM rule_definitions WHERE slug = ANY(:slugs)"),
        {"slugs": slugs},
    )
