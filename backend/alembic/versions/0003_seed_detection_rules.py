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
            "window_seconds": 3600,
            "threshold": 15,
            "group_by": "actor",
            "distinct_count_field": "repo",
            "conditions": [{"field": "action", "op": "eq", "value": "git.clone"}],
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
            "conditions": [
                {"field": "action", "op": "eq", "value": "personal_access_token.create"},
                {"field": "data.scope", "op": "contains", "value": "repo"},
            ]
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
            "conditions": [
                {"field": "action", "op": "eq", "value": "personal_access_token.create"},
                {"field": "data.token_type", "op": "eq", "value": "fine-grained"},
                {"field": "data.repository_selection", "op": "eq", "value": "all"},
            ]
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
            "conditions": [
                {"field": "action", "op": "eq", "value": "integration_installation.create"},
                {"field": "data.repository_selection", "op": "eq", "value": "all"},
            ]
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
            "conditions": [
                {"field": "action", "op": "eq", "value": "secret_scanning.push_protection.bypass"}
            ]
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
            "conditions": [
                {
                    "field": "action",
                    "op": "in",
                    "value": [
                        "branch_protection_rule.policy_override",
                        "protected_branch.update",
                    ],
                }
            ]
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
            "window_seconds": 604800,
            "threshold": 3,
            "group_by": "actor",
            "actions": [
                "secret_scanning.push_protection.bypass",
                "branch_protection_rule.policy_override",
                "protected_branch.update",
            ],
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
            "conditions": [
                {
                    "field": "action",
                    "op": "in",
                    "value": [
                        "secret_scanning.push_protection.bypass",
                        "branch_protection_rule.policy_override",
                    ],
                },
                {
                    "field": "data.user_role",
                    "op": "in",
                    "value": ["owner", "admin", "org_owner"],
                },
            ]
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
            "conditions": [
                {
                    "field": "action",
                    "op": "in",
                    "value": ["org.add_outside_collaborator", "repo.add_member"],
                },
                {"field": "data.role", "op": "eq", "value": "outside_collaborator"},
            ]
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
            "conditions": [
                {
                    "field": "action",
                    "op": "in",
                    "value": [
                        "org.add_outside_collaborator",
                        "repo.add_member",
                        "repo.update_member",
                    ],
                },
                {
                    "field": "data.role",
                    "op": "in",
                    "value": ["write", "maintain", "admin"],
                },
            ]
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
            "conditions": [
                {
                    "field": "action",
                    "op": "eq",
                    "value": "enterprise.grant_business_plus_features",
                },
                {"field": "data.enterprise_role", "op": "eq", "value": "guest"},
            ]
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
