"""Seed built-in detection rules.

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

import json

from sqlalchemy import text

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# Rule definitions
# Each tuple: (name, slug, description, category, default_severity,
#              default_confidence, logic_type, logic_config, enabled)
# ---------------------------------------------------------------------------
_RULES = [
    (
        "Bulk Repository Harvesting",
        "bulk-repo-harvesting",
        "Actor cloned more than 15 distinct repositories within a 1-hour window — potential data harvesting",
        "data_exfiltration",
        "high",
        "high",
        "threshold",
        {
            "time_window_minutes": 60,
            "threshold": 15,
            "aggregation_key": "actor",
            "distinct_count_field": "repo",
            "action_filters": ["git.clone"],
            "field_conditions": [],
            "confidence": 0.5,
        },
        True,
    ),
    (
        "Classic PAT with Full Repo Scope",
        "pat-classic-full-repo-scope",
        "Classic personal access token created with full 'repo' scope — overly permissive",
        "access_control",
        "high",
        "high",
        "pattern",
        {
            "action_filters": ["personal_access_token.create"],
            "field_conditions": [
                {"field": "data.scope", "operator": "contains", "value": "repo"},
            ],
            "confidence": 0.5,
        },
        True,
    ),
    (
        "Fine-Grained PAT with All-Repos Write Access",
        "pat-fine-grained-all-repos-write",
        "Fine-grained PAT created with write access to all repositories — overly permissive",
        "access_control",
        "high",
        "high",
        "pattern",
        {
            "action_filters": ["personal_access_token.create"],
            "field_conditions": [
                {"field": "data.token_type", "operator": "eq", "value": "fine-grained"},
                {"field": "data.repository_selection", "operator": "eq", "value": "all"},
            ],
            "confidence": 0.5,
        },
        True,
    ),
    (
        "GitHub App Installed with Org-Wide Access",
        "integration-install-org-level",
        "GitHub App installed with organization-wide access — review permissions granted",
        "access_control",
        "high",
        "high",
        "pattern",
        {
            "action_filters": ["integration_installation.create"],
            "field_conditions": [
                {"field": "data.repository_selection", "operator": "eq", "value": "all"},
            ],
            "confidence": 0.5,
        },
        True,
    ),
    (
        "Push Protection Bypass",
        "push-protection-bypass",
        "Actor bypassed secret push protection — review reason and secret type",
        "policy_violation",
        "medium",
        "high",
        "pattern",
        {
            "action_filters": ["secret_scanning.push_protection.bypass"],
            "field_conditions": [],
            "confidence": 0.5,
        },
        True,
    ),
    (
        "Branch Protection Override",
        "branch-protection-override",
        "Branch protection rule was overridden — potential policy violation",
        "policy_violation",
        "medium",
        "high",
        "pattern",
        {
            "action_filters": [
                "branch_protection_rule.policy_override",
                "protected_branch.update",
            ],
            "field_conditions": [],
            "confidence": 0.5,
        },
        True,
    ),
    (
        "Repeat Bypass Offender",
        "repeat-bypass-offender",
        "Actor bypassed branch or push protection 3 or more times within 7 days",
        "policy_violation",
        "high",
        "high",
        "threshold",
        {
            "time_window_minutes": 10080,
            "threshold": 3,
            "aggregation_key": "actor",
            "action_filters": [
                "secret_scanning.push_protection.bypass",
                "branch_protection_rule.policy_override",
                "protected_branch.update",
            ],
            "field_conditions": [],
            "confidence": 0.5,
        },
        True,
    ),
    (
        "Admin Bypass of Critical Protection",
        "admin-bypass-critical",
        (
            "Actor with org owner or admin role bypassed push or branch protection"
            " — DRAFT: requires IDP role enrichment"
        ),
        "policy_violation",
        "critical",
        "medium",
        "pattern",
        {
            "action_filters": [
                "secret_scanning.push_protection.bypass",
                "branch_protection_rule.policy_override",
            ],
            "field_conditions": [
                {
                    "field": "data.user_role",
                    "operator": "in",
                    "value": ["owner", "admin", "org_owner"],
                },
            ],
            "confidence": 0.5,
        },
        False,
    ),
    (
        "External Collaborator Granted Access",
        "external-collaborator-grant",
        "External (outside) collaborator was granted access to an org or repository",
        "access_control",
        "medium",
        "high",
        "pattern",
        {
            "action_filters": ["org.add_outside_collaborator", "repo.add_member"],
            "field_conditions": [
                {"field": "data.role", "operator": "eq", "value": "outside_collaborator"},
            ],
            "confidence": 0.5,
        },
        True,
    ),
    (
        "External Collaborator Elevated Permissions",
        "external-collaborator-elevated",
        (
            "External collaborator granted write, maintain, or admin permissions"
            " — elevated access review required"
        ),
        "access_control",
        "high",
        "high",
        "pattern",
        {
            "action_filters": [
                "org.add_outside_collaborator",
                "repo.add_member",
                "repo.update_member",
            ],
            "field_conditions": [
                {
                    "field": "data.role",
                    "operator": "in",
                    "value": ["write", "maintain", "admin"],
                },
            ],
            "confidence": 0.5,
        },
        True,
    ),
    (
        "EMU Guest Collaborator Role Granted",
        "emu-guest-role-grant",
        (
            "EMU guest collaborator role granted — review enterprise access scope"
            " (DRAFT: EMU enterprises only)"
        ),
        "access_control",
        "medium",
        "medium",
        "pattern",
        {
            "action_filters": ["enterprise.grant_business_plus_features"],
            "field_conditions": [
                {"field": "data.enterprise_role", "operator": "eq", "value": "guest"},
            ],
            "confidence": 0.5,
        },
        False,
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
