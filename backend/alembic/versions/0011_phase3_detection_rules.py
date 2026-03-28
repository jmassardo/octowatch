"""Seed Phase 3 detection rules — workflows, branch protection, Copilot, Codespaces.

Revision ID: 0011
Revises: 0010
"""

from __future__ import annotations

import json

from sqlalchemy import text

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# Rule definitions
# Each tuple: (name, slug, description, category, default_severity,
#              default_confidence, logic_type, logic_config, enabled)
# ---------------------------------------------------------------------------
_RULES = [
    (
        "Workflow Excessive Secrets",
        "workflow-excessive-secrets",
        "Workflow job was prepared with 10+ secrets — review for overly permissive secret access",
        "data_exfiltration",
        "high",
        "medium",
        "pattern",
        {
            "action_filters": [
                "workflows.prepared_workflow_job",
            ],
            "field_conditions": [
                {
                    "field": "data.secrets_passed_count",
                    "operator": "gte",
                    "value": 10,
                },
            ],
            "confidence": 0.65,
        },
        True,
    ),
    (
        "Branch Protection Weakened",
        "branch-protection-weakened",
        "Branch protection rules were weakened — reduced enforcement on protected branches",
        "posture_degradation",
        "high",
        "medium",
        "pattern",
        {
            "action_filters": [
                "protected_branch.update_admin_enforced",
                "protected_branch.update_pull_request_reviews_enforcement_level",
                "protected_branch.policy_override",
            ],
            "field_conditions": [],
            "confidence": 0.75,
        },
        True,
    ),
    (
        "Required Status Check Removed",
        "required-status-check-removed",
        "Required status check was removed from branch protection — CI gate weakened",
        "posture_degradation",
        "medium",
        "high",
        "pattern",
        {
            "action_filters": [
                "required_status_check.destroy",
            ],
            "field_conditions": [],
            "confidence": 0.80,
        },
        True,
    ),
    (
        "Environment Self-Review Enabled",
        "environment-self-review-enabled",
        "Environment protection changed to allow self-review — deployment approval bypass risk",
        "posture_degradation",
        "high",
        "medium",
        "pattern",
        {
            "action_filters": [
                "environment.update_protection_rule",
            ],
            "field_conditions": [
                {
                    "field": "data.prevent_self_review",
                    "operator": "eq",
                    "value": False,
                },
            ],
            "confidence": 0.70,
        },
        True,
    ),
    (
        "Environment Approvers Removed",
        "environment-approvers-removed",
        "All required reviewers removed from environment protection — unattended deployments possible",
        "posture_degradation",
        "high",
        "high",
        "pattern",
        {
            "action_filters": [
                "environment.update_protection_rule",
            ],
            "field_conditions": [
                {
                    "field": "data.approvers",
                    "operator": "eq",
                    "value": [],
                },
            ],
            "confidence": 0.85,
        },
        True,
    ),
    (
        "Copilot Seats Opened to All Members",
        "copilot-seats-opened-to-all",
        "Copilot seat management changed to all members — review AI code assistant access scope",
        "posture_change",
        "medium",
        "high",
        "pattern",
        {
            "action_filters": [
                "copilot.cfb_seat_management_changed",
            ],
            "field_conditions": [
                {
                    "field": "data.new_value",
                    "operator": "eq",
                    "value": "all_members",
                },
            ],
            "confidence": 0.80,
        },
        True,
    ),
    (
        "Copilot SWE Agent Repo Enabled",
        "copilot-swe-agent-repo-enabled",
        "Copilot SWE agent was enabled on a repository — autonomous code generation activated",
        "posture_change",
        "medium",
        "high",
        "pattern",
        {
            "action_filters": [
                "copilot.swe_agent_repo_enabled",
            ],
            "field_conditions": [],
            "confidence": 0.75,
        },
        True,
    ),
    (
        "Copilot Custom Instructions Changed",
        "copilot-custom-instructions-changed",
        "Copilot custom instructions were created or updated — review AI behavior modifications",
        "posture_change",
        "low",
        "high",
        "pattern",
        {
            "action_filters": [
                "copilot.custom_instructions_created",
                "copilot.custom_instructions_updated",
            ],
            "field_conditions": [],
            "confidence": 0.70,
        },
        True,
    ),
    (
        "Codespace Export from Repository",
        "codespace-export-from-repo",
        "Codespace environment was exported — review for sensitive data exfiltration",
        "data_exfiltration",
        "medium",
        "medium",
        "pattern",
        {
            "action_filters": [
                "codespaces.export_environment",
            ],
            "field_conditions": [],
            "confidence": 0.60,
        },
        True,
    ),
    (
        "Dependabot Alerts Disabled",
        "dependabot-alerts-disabled",
        "Dependabot alerts were disabled — dependency vulnerabilities may go undetected",
        "defense_evasion",
        "high",
        "high",
        "pattern",
        {
            "action_filters": [
                "dependabot_alerts.disable_for_new_repos",
                "dependabot_alerts.disable",
            ],
            "field_conditions": [],
            "confidence": 0.85,
        },
        True,
    ),
]

_INSERT_SQL = text("""
    INSERT INTO rule_definitions (
        name, slug, description, category,
        default_severity, default_confidence,
        logic_type, logic_config,
        enabled, status, version, created_by
    ) VALUES (
        :name, :slug, :description, :category,
        :default_severity, :default_confidence,
        :logic_type, CAST(:logic_config AS JSONB),
        :enabled, 'active', 1, 'seed'
    )
    ON CONFLICT (slug) DO NOTHING
""")


def upgrade() -> None:
    bind = op.get_bind()
    for (
        name,
        slug,
        description,
        category,
        default_severity,
        default_confidence,
        logic_type,
        logic_config,
        enabled,
    ) in _RULES:
        bind.execute(
            _INSERT_SQL,
            {
                "name": name,
                "slug": slug,
                "description": description,
                "category": category,
                "default_severity": default_severity,
                "default_confidence": default_confidence,
                "logic_type": logic_type,
                "logic_config": json.dumps(logic_config),
                "enabled": enabled,
            },
        )


def downgrade() -> None:
    slugs = [r[1] for r in _RULES]
    op.get_bind().execute(
        text("DELETE FROM rule_definitions WHERE slug = ANY(:slugs)"),
        {"slugs": slugs},
    )
