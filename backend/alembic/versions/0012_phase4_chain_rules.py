"""Seed Phase 4 cross-namespace sequence rules — disabled until engine support deployed.

Revision ID: 0012
Revises: 0011
"""

from __future__ import annotations

import json

from sqlalchemy import text

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# Rule definitions
# Each tuple: (name, slug, description, category, default_severity,
#              default_confidence, logic_type, logic_config, enabled)
#
# NOTE: All Phase 4 rules are seeded with enabled=False because the
# cross_namespace_sequence engine enhancement is not yet deployed.
# ---------------------------------------------------------------------------
_RULES = [
    (
        "Supply Chain Staging Sequence",
        "supply-chain-staging-sequence",
        "Actor created a repo, added secrets, and triggered a workflow run within 30 minutes — potential supply chain attack staging",
        "supply_chain",
        "critical",
        "medium",
        "cross_namespace_sequence",
        {
            "aggregation_key": "actor",
            "time_window_minutes": 30,
            "require_distinct_steps": True,
            "steps": [
                {"step": 1, "action_filters": ["repo.create"]},
                {
                    "step": 2,
                    "action_filters": [
                        "repo.create_actions_secret",
                        "org.create_actions_secret",
                    ],
                },
                {"step": 3, "action_filters": ["workflows.created_workflow_run"]},
            ],
            "field_conditions": [],
            "confidence": 0.75,
        },
        False,
    ),
    (
        "Security Control Erasure",
        "security-control-erasure",
        "Actor disabled security scanning and then identity controls within 24 hours — coordinated defense evasion",
        "defense_evasion",
        "critical",
        "high",
        "cross_namespace_sequence",
        {
            "aggregation_key": "actor",
            "time_window_minutes": 1440,
            "steps": [
                {
                    "step": 1,
                    "action_filters": [
                        "secret_scanning.disable",
                        "repo.codeql_disabled",
                        "org.advanced_security_disabled_on_all_repos",
                    ],
                },
                {
                    "step": 2,
                    "action_filters": [
                        "org.disable_saml",
                        "ip_allow_list.disable",
                        "org.disable_oauth_app_restrictions",
                    ],
                },
            ],
            "field_conditions": [],
            "confidence": 0.90,
        },
        False,
    ),
    (
        "Privilege Pivot to OAuth Approval",
        "privilege-pivot-oauth-approval",
        "Actor escalated privileges then approved an OAuth app or installed a GitHub App within one hour",
        "privilege_escalation",
        "critical",
        "high",
        "cross_namespace_sequence",
        {
            "aggregation_key": "actor",
            "time_window_minutes": 60,
            "steps": [
                {
                    "step": 1,
                    "action_filters": [
                        "org.member_to_admin",
                        "org.integration_manager_added",
                    ],
                },
                {
                    "step": 2,
                    "action_filters": [
                        "org.oauth_app_access_approved",
                        "integration_installation.create",
                    ],
                },
            ],
            "field_conditions": [],
            "confidence": 0.85,
        },
        False,
    ),
    (
        "Insider Bulk Exfiltration",
        "insider-bulk-exfil",
        "Actor cloned 3+ repos and fetched 5+ repos within 2 hours — potential insider data theft",
        "data_exfiltration",
        "critical",
        "high",
        "cross_namespace_sequence",
        {
            "aggregation_key": "actor",
            "time_window_minutes": 120,
            "require_distinct_steps": False,
            "steps": [
                {
                    "step": 1,
                    "action_filters": ["repo.download_zip", "git.clone"],
                    "min_count": 3,
                },
                {
                    "step": 2,
                    "action_filters": ["git.fetch"],
                    "min_count": 5,
                },
            ],
            "field_conditions": [],
            "confidence": 0.80,
        },
        False,
    ),
    (
        "Defense Evasion Then Exfiltration",
        "defense-evasion-then-exfil",
        "Actor disabled audit streaming then downloaded or cloned repos within 4 hours — evasion followed by exfiltration",
        "data_exfiltration",
        "critical",
        "high",
        "cross_namespace_sequence",
        {
            "aggregation_key": "actor",
            "time_window_minutes": 240,
            "steps": [
                {
                    "step": 1,
                    "action_filters": [
                        "audit_log_streaming.disabled",
                        "audit_log_streaming.destroy",
                    ],
                },
                {
                    "step": 2,
                    "action_filters": [
                        "repo.download_zip",
                        "git.clone",
                    ],
                },
            ],
            "field_conditions": [],
            "confidence": 0.85,
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
    # Extend logic_type CHECK constraint to include 'cross_namespace_sequence'
    op.execute("""
        ALTER TABLE rule_definitions
            DROP CONSTRAINT IF EXISTS rule_definitions_logic_type_check;
    """)
    op.execute("""
        ALTER TABLE rule_definitions
            ADD CONSTRAINT rule_definitions_logic_type_check
            CHECK (logic_type IN (
                'threshold', 'pattern', 'sequence', 'statistical',
                'cross_namespace_sequence'
            ));
    """)

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
