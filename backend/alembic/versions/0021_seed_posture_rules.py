"""Seed posture-assessment detection rules.

These rules evaluate the *current state* of synced metadata (org settings,
branch protections, repositories) rather than audit log events.

Revision ID: 0021
Revises: 0020
"""

from __future__ import annotations

import json

from sqlalchemy import text

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# Rule definitions
# Each tuple: (name, slug, description, category, default_severity,
#              default_confidence, logic_type, logic_config, enabled)
# ---------------------------------------------------------------------------
_RULES = [
    (
        "IP Allow List Disabled",
        "posture-ip-allowlist-disabled",
        "Organisation does not have IP allow list enabled",
        "access_control",
        "high",
        "high",
        "posture",
        {
            "entity_type": "org",
            "check_type": "field_value",
            "field": "ip_allow_list_enabled",
            "operator": "eq",
            "value": False,
            "confidence": 0.95,
        },
        True,
    ),
    (
        "2FA Not Required",
        "posture-2fa-not-required",
        "Organisation does not require two-factor authentication",
        "access_control",
        "high",
        "high",
        "posture",
        {
            "entity_type": "org",
            "check_type": "field_value",
            "field": "two_factor_required",
            "operator": "eq",
            "value": False,
            "confidence": 0.95,
        },
        True,
    ),
    (
        "Default Repo Permission Write or Admin",
        "posture-default-repo-permission-write",
        "Organisation grants write or admin permission by default",
        "access_control",
        "medium",
        "medium",
        "posture",
        {
            "entity_type": "org",
            "check_type": "field_value",
            "field": "default_repo_permission",
            "operator": "in",
            "value": ["write", "admin"],
            "confidence": 0.85,
        },
        True,
    ),
    (
        "Private Fork Allowed",
        "posture-private-fork-allowed",
        "Organisation allows forking private repositories",
        "data_exfiltration",
        "medium",
        "medium",
        "posture",
        {
            "entity_type": "org",
            "check_type": "field_value",
            "field": "members_can_fork_private_repos",
            "operator": "eq",
            "value": True,
            "confidence": 0.80,
        },
        True,
    ),
    (
        "Public Repo Creation Allowed",
        "posture-public-repo-creation-allowed",
        "Organisation allows creating public repositories",
        "data_exfiltration",
        "low",
        "low",
        "posture",
        {
            "entity_type": "org",
            "check_type": "field_value",
            "field": "members_can_create_public_repos",
            "operator": "eq",
            "value": True,
            "confidence": 0.75,
        },
        True,
    ),
    (
        "No Branch Protection on Default Branch",
        "posture-no-branch-protection",
        "Non-archived repo default branch has no branch protection",
        "posture_degradation",
        "high",
        "high",
        "posture",
        {
            "entity_type": "branch_protection",
            "check_type": "missing_protection",
            "confidence": 0.90,
        },
        True,
    ),
    (
        "Branch Protection No Review Required",
        "posture-branch-no-review-required",
        "Branch protection requires zero approving reviews",
        "posture_degradation",
        "medium",
        "medium",
        "posture",
        {
            "entity_type": "branch_protection",
            "check_type": "field_value",
            "field": "required_reviews",
            "operator": "lt",
            "value": 1,
            "confidence": 0.85,
        },
        True,
    ),
    (
        "Branch Protection Admins Not Enforced",
        "posture-branch-admins-not-enforced",
        "Branch protection does not enforce rules on admins",
        "posture_degradation",
        "low",
        "low",
        "posture",
        {
            "entity_type": "branch_protection",
            "check_type": "field_value",
            "field": "enforce_admins",
            "operator": "eq",
            "value": False,
            "confidence": 0.75,
        },
        True,
    ),
    (
        "Public Repository in Enterprise",
        "posture-public-repo-in-enterprise",
        "Enterprise organisation contains a public repository",
        "data_exfiltration",
        "info",
        "low",
        "posture",
        {
            "entity_type": "repo",
            "check_type": "field_value",
            "field": "visibility",
            "operator": "eq",
            "value": "public",
            "confidence": 0.70,
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
