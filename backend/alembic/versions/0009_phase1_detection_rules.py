"""Seed Phase 1 detection rules — audit stream, security features, visibility, access.

Revision ID: 0009
Revises: 0008
"""

from __future__ import annotations

import json

from sqlalchemy import text

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# Rule definitions
# Each tuple: (name, slug, description, category, default_severity,
#              default_confidence, logic_type, logic_config, enabled)
# ---------------------------------------------------------------------------
_RULES = [
    (
        "Audit Stream Destination Changed",
        "audit-stream-destination-changed",
        "Audit log streaming destination was changed or created — potential evidence tampering",
        "defense_evasion",
        "critical",
        "high",
        "pattern",
        {
            "action_filters": [
                "audit_log_streaming.update",
                "audit_log_streaming.create",
            ],
            "field_conditions": [],
            "confidence": 0.90,
        },
        True,
    ),
    (
        "Audit Stream Disabled",
        "audit-stream-disabled",
        "Audit log streaming was disabled or destroyed — loss of security visibility",
        "defense_evasion",
        "critical",
        "high",
        "pattern",
        {
            "action_filters": [
                "audit_log_streaming.disabled",
                "audit_log_streaming.destroy",
            ],
            "field_conditions": [],
            "confidence": 0.95,
        },
        True,
    ),
    (
        "Bulk Security Feature Disable",
        "bulk-security-feature-disable",
        "Multiple security features disabled within one hour by same actor — coordinated defense evasion",
        "defense_evasion",
        "critical",
        "high",
        "threshold",
        {
            "action_filters": [
                "secret_scanning.disable",
                "secret_scanning_new_repos.disable",
                "repository_secret_scanning.disable",
                "repo.codeql_disabled",
                "org.codeql_disabled",
                "repo.advanced_security_disabled",
                "org.advanced_security_disabled_on_all_repos",
                "dependabot_alerts.disable_for_new_repos",
                "dependency_graph.disable",
            ],
            "time_window_minutes": 60,
            "threshold": 3,
            "aggregation_key": "actor",
            "field_conditions": [],
            "confidence": 0.85,
        },
        True,
    ),
    (
        "Secret Scanning Disabled",
        "secret-scanning-disable",
        "Secret scanning was disabled on a repository — secrets may go undetected",
        "defense_evasion",
        "high",
        "high",
        "pattern",
        {
            "action_filters": [
                "secret_scanning.disable",
                "repository_secret_scanning.disable",
            ],
            "field_conditions": [],
            "confidence": 0.85,
        },
        True,
    ),
    (
        "Push Protection Disabled",
        "push-protection-disable",
        "Secret scanning push protection was disabled — secrets can be pushed without blocking",
        "defense_evasion",
        "high",
        "high",
        "pattern",
        {
            "action_filters": [
                "repository_secret_scanning_push_protection.disable",
            ],
            "field_conditions": [],
            "confidence": 0.85,
        },
        True,
    ),
    (
        "CodeQL Disabled",
        "codeql-disable",
        "CodeQL code scanning was disabled — code vulnerabilities may go undetected",
        "defense_evasion",
        "high",
        "high",
        "pattern",
        {
            "action_filters": [
                "repo.codeql_disabled",
                "org.codeql_disabled",
            ],
            "field_conditions": [],
            "confidence": 0.85,
        },
        True,
    ),
    (
        "GHAS Disabled",
        "ghas-disable",
        "GitHub Advanced Security was disabled — all GHAS features become unavailable",
        "defense_evasion",
        "critical",
        "high",
        "pattern",
        {
            "action_filters": [
                "repo.advanced_security_disabled",
                "org.advanced_security_disabled_on_all_repos",
            ],
            "field_conditions": [],
            "confidence": 0.90,
        },
        True,
    ),
    (
        "Secret Scanning Public Leak",
        "secret-scanning-public-leak",
        "Secret scanning detected a publicly leaked secret — immediate rotation required",
        "data_exfiltration",
        "critical",
        "high",
        "pattern",
        {
            "action_filters": [
                "secret_scanning_alert.public_leak",
                "secret_scanning_alert.create",
            ],
            "field_conditions": [
                {
                    "field": "data.publicly_leaked",
                    "operator": "eq",
                    "value": True,
                },
            ],
            "confidence": 0.95,
        },
        True,
    ),
    (
        "Secret Scanning Dismissal Spike",
        "secret-scanning-dismissal-spike",
        "Actor dismissed 10+ secret scanning alerts within 8 hours — potential alert fatigue or suppression",
        "posture_degradation",
        "high",
        "medium",
        "threshold",
        {
            "action_filters": [
                "secret_scanning_alert.resolve",
            ],
            "time_window_minutes": 480,
            "threshold": 10,
            "aggregation_key": "actor",
            "field_conditions": [],
            "confidence": 0.70,
        },
        True,
    ),
    (
        "Repository Private to Public",
        "repo-private-to-public",
        "Repository visibility changed from private to public — potential data exposure",
        "data_exfiltration",
        "critical",
        "high",
        "pattern",
        {
            "action_filters": [
                "repo.access",
            ],
            "field_conditions": [
                {
                    "field": "data.visibility",
                    "operator": "eq",
                    "value": "public",
                },
                {
                    "field": "data.previous_visibility",
                    "operator": "eq",
                    "value": "private",
                },
            ],
            "confidence": 0.95,
        },
        True,
    ),
    (
        "Repository Internal to Public",
        "repo-internal-to-public",
        "Repository visibility changed from internal to public — potential data exposure",
        "data_exfiltration",
        "high",
        "high",
        "pattern",
        {
            "action_filters": [
                "repo.access",
            ],
            "field_conditions": [
                {
                    "field": "data.visibility",
                    "operator": "eq",
                    "value": "public",
                },
                {
                    "field": "data.previous_visibility",
                    "operator": "eq",
                    "value": "internal",
                },
            ],
            "confidence": 0.90,
        },
        True,
    ),
    (
        "Org Member Elevated to Admin",
        "org-member-to-admin",
        "Organization member was elevated to admin role — review privilege escalation",
        "privilege_escalation",
        "high",
        "high",
        "pattern",
        {
            "action_filters": [
                "org.member_to_admin",
            ],
            "field_conditions": [],
            "confidence": 0.90,
        },
        True,
    ),
    (
        "IP Allowlist Disabled",
        "ip-allowlist-disabled",
        "IP allowlist was disabled — network access controls removed",
        "access_control",
        "high",
        "high",
        "pattern",
        {
            "action_filters": [
                "ip_allow_list.disable",
                "ip_allow_list.disable_for_installed_apps",
            ],
            "field_conditions": [],
            "confidence": 0.90,
        },
        True,
    ),
    (
        "SAML SSO Disabled",
        "saml-sso-disabled",
        "SAML single sign-on was disabled — identity controls removed from organization",
        "access_control",
        "critical",
        "high",
        "pattern",
        {
            "action_filters": [
                "org.disable_saml",
            ],
            "field_conditions": [],
            "confidence": 0.95,
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
