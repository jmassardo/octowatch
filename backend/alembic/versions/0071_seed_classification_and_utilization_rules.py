"""Seed classification and utilization detection rules.

Revision ID: 0069
Revises: 0068
Create Date: 2026-07-20 10:08:48.076000

"""

from __future__ import annotations

import json

from alembic import op

revision = "0071"
down_revision = "0070"
branch_labels = None
depends_on = None

classification_rules = [
    {
        "name": "Bot Classification",
        "slug": "persona-bot",
        "description": "Classify bot accounts (sender.type=Bot or login matches *[bot])",
        "category": "classification",
        "default_severity": "info",
        "default_confidence": "high",
        "logic_type": "classification",
        "logic_config": {
            "priority": 1,
            "condition": {"field": "actor_is_bot", "op": "eq", "value": True},
            "output_persona": "Bot",
        },
    },
    {
        "name": "Viewer Classification (Zero Activity)",
        "slug": "persona-viewer-zero",
        "description": "Users with no events or only passive activity",
        "category": "classification",
        "default_severity": "info",
        "default_confidence": "high",
        "logic_type": "classification",
        "logic_config": {
            "priority": 2,
            "condition": {"field": "total_events", "op": "eq", "value": 0},
            "output_persona": "Viewer",
        },
    },
    {
        "name": "Developer Classification",
        "slug": "persona-developer",
        "description": "Users with code activity (pushes, PRs)",
        "category": "classification",
        "default_severity": "info",
        "default_confidence": "high",
        "logic_type": "classification",
        "logic_config": {
            "priority": 3,
            "condition": {"field": "code_events", "op": "gte", "value": 1},
            "output_persona": "Developer",
        },
    },
    {
        "name": "Code Reviewer Classification",
        "slug": "persona-code-reviewer",
        "description": "Users with code review activity but no code pushes",
        "category": "classification",
        "default_severity": "info",
        "default_confidence": "medium",
        "logic_type": "classification",
        "logic_config": {
            "priority": 4,
            "conditions": [
                {"field": "code_review_events", "op": "gte", "value": 1},
                {"field": "code_events", "op": "eq", "value": 0},
            ],
            "output_persona": "Code Reviewer",
        },
    },
    {
        "name": "Product Manager Classification",
        "slug": "persona-product-manager",
        "description": "Users focused on issues and project management",
        "category": "classification",
        "default_severity": "info",
        "default_confidence": "medium",
        "logic_type": "classification",
        "logic_config": {
            "priority": 5,
            "conditions": [
                {"field": "issue_mgmt_events", "op": "gte", "value": 1},
                {"field": "code_events", "op": "eq", "value": 0},
                {"field": "code_review_events", "op": "eq", "value": 0},
            ],
            "output_persona": "Product Manager",
        },
    },
    {
        "name": "Admin Classification",
        "slug": "persona-admin",
        "description": "Users whose activity is predominantly administrative",
        "category": "classification",
        "default_severity": "info",
        "default_confidence": "medium",
        "logic_type": "classification",
        "logic_config": {
            "priority": 6,
            "condition": {"field": "admin_pct", "op": "pct_gt", "value": 50},
            "output_persona": "Admin",
        },
    },
    {
        "name": "Collaborator Classification (Fallback)",
        "slug": "persona-collaborator",
        "description": "Users with discussion/documentation/issue activity not matching other personas",
        "category": "classification",
        "default_severity": "info",
        "default_confidence": "low",
        "logic_type": "classification",
        "logic_config": {
            "priority": 7,
            "condition": {"field": "total_events", "op": "gte", "value": 1},
            "output_persona": "Collaborator",
        },
    },
]

utilization_rules = [
    {
        "name": "Actions Minutes Anomaly",
        "slug": "actions-minutes-anomaly",
        "description": "Anomalous Actions minutes consumption detected via IQR",
        "category": "utilization",
        "default_severity": "medium",
        "default_confidence": "medium",
        "logic_type": "statistical",
        "logic_config": {
            "x_config": {"engine": "iqr_anomaly"},
            "metric_field": "actions_minutes",
            "source": "utilization_facts",
            "multiplier": 3.0,
            "min_baseline_days": 14,
        },
    },
    {
        "name": "Runner Registration Spike",
        "slug": "runner-registration-spike",
        "description": "Unusual number of self-hosted runners registered in short window",
        "category": "utilization",
        "default_severity": "high",
        "default_confidence": "high",
        "logic_type": "threshold",
        "logic_config": {
            "action_filters": [
                "org.register_self_hosted_runner",
                "org.add_self_hosted_runner",
            ],
            "threshold": 5,
            "window_minutes": 60,
            "aggregation_key": "org",
        },
    },
    {
        "name": "Actions Cache Abuse",
        "slug": "actions-cache-abuse",
        "description": "Excessive Actions cache writes suggesting abuse or misconfiguration",
        "category": "utilization",
        "default_severity": "medium",
        "default_confidence": "medium",
        "logic_type": "threshold",
        "logic_config": {
            "action_filters": ["workflows.cache_write"],
            "threshold": 50,
            "window_minutes": 60,
            "aggregation_key": "actor",
        },
    },
    {
        "name": "Workflow Concurrency Flood",
        "slug": "workflow-concurrency-flood",
        "description": "Excessive concurrent workflow runs from a single actor",
        "category": "utilization",
        "default_severity": "medium",
        "default_confidence": "high",
        "logic_type": "threshold",
        "logic_config": {
            "action_filters": ["workflows.created_workflow_run"],
            "threshold": 20,
            "window_minutes": 15,
            "aggregation_key": "actor",
        },
    },
    {
        "name": "GHAS Mass Alert Dismiss",
        "slug": "ghas-mass-alert-dismiss",
        "description": "Mass dismissal of security alerts",
        "category": "utilization",
        "default_severity": "high",
        "default_confidence": "high",
        "logic_type": "threshold",
        "logic_config": {
            "action_filters": [
                "secret_scanning.dismiss_alert",
                "code_scanning.dismiss_alert",
                "dependabot.dismiss_alert",
            ],
            "threshold": 10,
            "window_minutes": 30,
            "aggregation_key": "actor",
        },
    },
    {
        "name": "GHAS Mass Disable",
        "slug": "ghas-mass-disable",
        "description": "Advanced Security disabled on multiple repos rapidly",
        "category": "utilization",
        "default_severity": "critical",
        "default_confidence": "high",
        "logic_type": "threshold",
        "logic_config": {
            "action_filters": ["repo.advanced_security_disabled"],
            "threshold": 3,
            "window_minutes": 60,
            "aggregation_key": "actor",
        },
    },
    {
        "name": "Push Protection Bypass Frequency",
        "slug": "push-protection-bypass-freq",
        "description": "Frequent push protection bypasses from same actor",
        "category": "utilization",
        "default_severity": "high",
        "default_confidence": "high",
        "logic_type": "threshold",
        "logic_config": {
            "action_filters": ["secret_scanning.push_protection_bypass"],
            "threshold": 3,
            "window_minutes": 1440,
            "aggregation_key": "actor",
        },
    },
    {
        "name": "GHAS Committer Spike",
        "slug": "ghas-committer-spike",
        "description": "Anomalous increase in active GHAS committers (cost signal)",
        "category": "utilization",
        "default_severity": "medium",
        "default_confidence": "medium",
        "logic_type": "statistical",
        "logic_config": {
            "x_config": {"engine": "iqr_anomaly"},
            "metric_field": "ghas_committers",
            "source": "utilization_facts",
            "multiplier": 2.5,
            "min_baseline_days": 14,
        },
    },
    {
        "name": "Copilot Credit Anomaly",
        "slug": "copilot-credit-anomaly",
        "description": "Anomalous Copilot premium request credit consumption",
        "category": "utilization",
        "default_severity": "medium",
        "default_confidence": "medium",
        "logic_type": "statistical",
        "logic_config": {
            "x_config": {"engine": "iqr_anomaly"},
            "metric_field": "copilot_credits",
            "source": "utilization_facts",
            "multiplier": 3.0,
            "min_baseline_days": 7,
        },
    },
    {
        "name": "Copilot Premium Budget Burn",
        "slug": "copilot-premium-budget-burn",
        "description": "Copilot premium credits exceeding daily budget threshold",
        "category": "utilization",
        "default_severity": "medium",
        "default_confidence": "high",
        "logic_type": "threshold",
        "logic_config": {
            "action_filters": ["copilot.premium_request"],
            "threshold": 100,
            "window_minutes": 1440,
            "aggregation_key": "actor",
        },
    },
    {
        "name": "Copilot Mass Seat Change",
        "slug": "copilot-mass-seat-change",
        "description": "Bulk Copilot seat assignment or removal",
        "category": "utilization",
        "default_severity": "medium",
        "default_confidence": "high",
        "logic_type": "threshold",
        "logic_config": {
            "action_filters": [
                "copilot.seat_assignment_created",
                "copilot.seat_cancelled_by_organisation",
            ],
            "threshold": 10,
            "window_minutes": 30,
            "aggregation_key": "org",
        },
    },
    {
        "name": "Copilot Inactive Seats",
        "slug": "copilot-inactive-seats",
        "description": "High proportion of Copilot seats with no recent activity",
        "category": "utilization",
        "default_severity": "low",
        "default_confidence": "medium",
        "logic_type": "statistical",
        "logic_config": {
            "x_config": {"engine": "iqr_anomaly"},
            "metric_field": "copilot_inactive_pct",
            "source": "utilization_facts",
            "multiplier": 2.0,
            "min_baseline_days": 30,
        },
    },
    {
        "name": "Git Clone Anomaly",
        "slug": "git-clone-anomaly",
        "description": "Anomalous number of repository clones by single actor",
        "category": "utilization",
        "default_severity": "medium",
        "default_confidence": "medium",
        "logic_type": "statistical",
        "logic_config": {
            "x_config": {"engine": "iqr_anomaly"},
            "metric_field": "git_clones",
            "source": "utilization_facts",
            "multiplier": 3.0,
            "min_baseline_days": 14,
        },
    },
    {
        "name": "Mass Repo Access",
        "slug": "mass-repo-access",
        "description": "Single actor accessing an unusually high number of repos",
        "category": "utilization",
        "default_severity": "high",
        "default_confidence": "medium",
        "logic_type": "threshold",
        "logic_config": {
            "action_filters": ["git.clone", "repo.access"],
            "threshold": 30,
            "window_minutes": 60,
            "aggregation_key": "actor",
            "distinct_field": "repo",
        },
    },
    {
        "name": "Rate Limit Exhaustion",
        "slug": "rate-limit-exhaustion",
        "description": "Actor repeatedly hitting API rate limits",
        "category": "utilization",
        "default_severity": "medium",
        "default_confidence": "high",
        "logic_type": "threshold",
        "logic_config": {
            "action_filters": ["api.rate_limit_exceeded"],
            "threshold": 5,
            "window_minutes": 60,
            "aggregation_key": "actor",
        },
    },
    {
        "name": "Package Publish Flood",
        "slug": "package-publish-flood",
        "description": "Excessive package versions published in short window",
        "category": "utilization",
        "default_severity": "medium",
        "default_confidence": "high",
        "logic_type": "threshold",
        "logic_config": {
            "action_filters": ["packages.package_version_published"],
            "threshold": 20,
            "window_minutes": 60,
            "aggregation_key": "actor",
        },
    },
    {
        "name": "Storage Growth Anomaly",
        "slug": "storage-growth-anomaly",
        "description": "Anomalous storage consumption growth",
        "category": "utilization",
        "default_severity": "low",
        "default_confidence": "medium",
        "logic_type": "statistical",
        "logic_config": {
            "x_config": {"engine": "iqr_anomaly"},
            "metric_field": "storage_bytes",
            "source": "utilization_facts",
            "multiplier": 3.0,
            "min_baseline_days": 14,
        },
    },
    {
        "name": "Package Mass Delete",
        "slug": "package-mass-delete",
        "description": "Mass deletion of package versions (supply chain risk)",
        "category": "utilization",
        "default_severity": "high",
        "default_confidence": "high",
        "logic_type": "threshold",
        "logic_config": {
            "action_filters": [
                "packages.package_version_deleted",
                "packages.package_deleted",
            ],
            "threshold": 5,
            "window_minutes": 30,
            "aggregation_key": "actor",
        },
    },
    {
        "name": "Cross-Feature Risk Escalation",
        "slug": "cross-feature-risk-escalation",
        "description": "Composite risk score from multiple triggered utilization rules",
        "category": "utilization",
        "default_severity": "high",
        "default_confidence": "medium",
        "logic_type": "utilization_composite",
        "logic_config": {
            "feature_area": "multi",
            "contributing_rules": [
                "actions-minutes-anomaly",
                "workflow-concurrency-flood",
                "runner-registration-spike",
                "ghas-mass-alert-dismiss",
                "copilot-credit-anomaly",
                "git-clone-anomaly",
                "mass-repo-access",
            ],
            "score_formula": "weighted_sum",
            "weights": {"statistical": 0.4, "threshold": 0.6},
            "recency_decay_days": 7,
            "risk_threshold": 0.7,
        },
    },
    {
        "name": "API Scraping Pattern",
        "slug": "api-scraping-pattern",
        "description": "Sequential API access pattern suggesting automated scraping",
        "category": "utilization",
        "default_severity": "medium",
        "default_confidence": "medium",
        "logic_type": "sequence",
        "logic_config": {
            "steps": [
                {"action_filter": "api.rate_limit_exceeded"},
                {"action_filter": "git.clone", "max_gap_minutes": 5},
                {"action_filter": "git.clone", "max_gap_minutes": 5},
            ],
            "window_minutes": 30,
            "scope": "actor",
        },
    },
]


def upgrade() -> None:
    """Seed classification and utilization detection rules."""
    for rule in classification_rules + utilization_rules:
        name = str(rule["name"]).replace("'", "''")
        slug = rule["slug"]
        description = str(rule["description"]).replace("'", "''")
        category = rule["category"]
        severity = rule["default_severity"]
        confidence = rule["default_confidence"]
        logic_type = rule["logic_type"]
        logic_config = json.dumps(rule["logic_config"])
        op.execute(
            f"""
            INSERT INTO rule_definitions (name, slug, description, category, default_severity,
                default_confidence, logic_type, logic_config, enabled, status, mode, version,
                source, created_by)
            VALUES (
                '{name}',
                '{slug}',
                '{description}',
                '{category}',
                '{severity}',
                '{confidence}',
                '{logic_type}',
                '{logic_config}'::jsonb,
                TRUE, 'active', 'active', 1, 'system', 'system'
            )
            ON CONFLICT (slug) DO NOTHING;
            """
        )


def downgrade() -> None:
    """Remove seeded classification and utilization detection rules."""
    op.execute(
        "DELETE FROM rule_definitions "
        "WHERE source = 'system' AND category IN ('classification', 'utilization')"
    )
