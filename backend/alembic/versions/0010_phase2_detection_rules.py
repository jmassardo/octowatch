"""Seed Phase 2 detection rules — code scanning, webhooks, apps, downloads.

Revision ID: 0010
Revises: 0009
"""

from __future__ import annotations

import json

from sqlalchemy import text

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# Rule definitions
# Each tuple: (name, slug, description, category, default_severity,
#              default_confidence, logic_type, logic_config, enabled)
# ---------------------------------------------------------------------------
_RULES = [
    (
        "Code Scanning Bulk Dismissal",
        "code-scanning-bulk-dismissal",
        "Actor dismissed 5+ code scanning alerts within 2 hours — potential alert suppression",
        "posture_degradation",
        "high",
        "medium",
        "threshold",
        {
            "action_filters": [
                "code_scanning.alert_closed_by_user",
            ],
            "time_window_minutes": 120,
            "threshold": 5,
            "aggregation_key": "actor",
            "field_conditions": [],
            "confidence": 0.75,
        },
        True,
    ),
    (
        "Code Scanning Alert Reappeared",
        "code-scanning-alert-reappeared",
        "Previously dismissed code scanning alert reappeared — underlying vulnerability persists",
        "posture_degradation",
        "medium",
        "medium",
        "pattern",
        {
            "action_filters": [
                "code_scanning.alert_reappeared",
            ],
            "field_conditions": [],
            "confidence": 0.60,
        },
        True,
    ),
    (
        "Webhook to External Domain",
        "webhook-external-domain",
        "Webhook created pointing to an external domain — potential data exfiltration channel",
        "data_exfiltration",
        "high",
        "medium",
        "pattern",
        {
            "action_filters": [
                "hook.create",
            ],
            "field_conditions": [
                {
                    "field": "data.hook_url",
                    "operator": "not_contains",
                    "value": "github.com",
                },
            ],
            "confidence": 0.70,
        },
        True,
    ),
    (
        "Webhook Bulk Creation",
        "webhook-bulk-creation",
        "Actor created 5+ webhooks within one hour — potential exfiltration infrastructure setup",
        "data_exfiltration",
        "high",
        "high",
        "threshold",
        {
            "action_filters": [
                "hook.create",
            ],
            "time_window_minutes": 60,
            "threshold": 5,
            "aggregation_key": "actor",
            "field_conditions": [],
            "confidence": 0.85,
        },
        True,
    ),
    (
        "Webhook Subscribed to All Events",
        "webhook-all-events",
        "Webhook created or modified to subscribe to all events — overly broad data access",
        "data_exfiltration",
        "medium",
        "medium",
        "pattern",
        {
            "action_filters": [
                "hook.create",
                "hook.events_changed",
            ],
            "field_conditions": [
                {
                    "field": "data.events",
                    "operator": "contains",
                    "value": "*",
                },
            ],
            "confidence": 0.65,
        },
        True,
    ),
    (
        "OAuth App Restrictions Disabled",
        "oauth-app-restrictions-disabled",
        "OAuth application restrictions were disabled — third-party apps can access org data freely",
        "access_control",
        "high",
        "high",
        "pattern",
        {
            "action_filters": [
                "org.disable_oauth_app_restrictions",
            ],
            "field_conditions": [],
            "confidence": 0.90,
        },
        True,
    ),
    (
        "GitHub App All Tokens Revoked",
        "github-app-all-tokens-revoked",
        "All tokens for a GitHub App were revoked — potential incident response action",
        "incident_response",
        "high",
        "high",
        "pattern",
        {
            "action_filters": [
                "integration.revoke_all_tokens",
            ],
            "field_conditions": [],
            "confidence": 0.90,
        },
        True,
    ),
    (
        "Org Integration Manager Granted",
        "org-integration-manager-granted",
        "Integration manager role granted — elevated permissions to manage GitHub Apps",
        "privilege_escalation",
        "high",
        "high",
        "pattern",
        {
            "action_filters": [
                "org.integration_manager_added",
            ],
            "field_conditions": [],
            "confidence": 0.85,
        },
        True,
    ),
    (
        "Custom Org Role Created",
        "custom-org-role-created",
        "Custom organization role was created or updated — review permissions granted",
        "privilege_escalation",
        "medium",
        "medium",
        "pattern",
        {
            "action_filters": [
                "organization_role.create",
                "organization_role.update",
            ],
            "field_conditions": [],
            "confidence": 0.65,
        },
        True,
    ),
    (
        "IP Allowlist Bulk Removal",
        "ip-allowlist-bulk-removal",
        "Actor removed 5+ IP allowlist entries within 30 minutes — network controls weakened",
        "access_control",
        "high",
        "medium",
        "threshold",
        {
            "action_filters": [
                "ip_allow_list_entry.destroy",
            ],
            "time_window_minutes": 30,
            "threshold": 5,
            "aggregation_key": "actor",
            "field_conditions": [],
            "confidence": 0.80,
        },
        True,
    ),
    (
        "Bulk Repository Zip Download",
        "bulk-repo-zip-download",
        "Actor downloaded zip archives of 5+ distinct repos within one hour — potential data exfiltration",
        "data_exfiltration",
        "high",
        "high",
        "threshold",
        {
            "action_filters": [
                "repo.download_zip",
            ],
            "time_window_minutes": 60,
            "threshold": 5,
            "aggregation_key": "actor",
            "distinct_count_field": "repo",
            "field_conditions": [],
            "confidence": 0.85,
        },
        True,
    ),
    (
        "Private Repo Fork Then Zip Download",
        "private-repo-fork-then-zip",
        "Actor forked a private or internal repo then downloaded its zip — potential exfiltration sequence",
        "data_exfiltration",
        "high",
        "medium",
        "sequence",
        {
            "action_filters": [
                "repo.fork",
                "repo.download_zip",
            ],
            "sequence_window_minutes": 30,
            "aggregation_key": "actor",
            "field_conditions": [
                {
                    "field": "data.visibility",
                    "operator": "in",
                    "value": ["private", "internal"],
                },
            ],
            "confidence": 0.80,
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
