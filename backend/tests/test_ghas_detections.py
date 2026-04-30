"""Tests for GHAS disable detection rules (Issue #166).

Verifies that:
- Each GHAS disable action matches its corresponding rule via event_matches_rule()
- Remediation map entries have correct enable-action → dedup-prefix mappings
- The _write_detection_for_event path embeds dedup_key for GHAS rules
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from app.services.detection_service import (
    _REMEDIATION_MAP,
    _repo_short,
    event_matches_rule,
)

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_event(action: str, org: str = "my-org", repo: str = "my-org/my-repo") -> MagicMock:
    """Create a minimal mock AuditEvent for testing."""
    event = MagicMock()
    event.action = action
    event.org = org
    event.repo = repo
    event.actor = "octocat"
    event.source_ip = None
    event.data = {}
    return event


def _make_rule(
    slug: str,
    action_filters: list[str],
    category: str = "security_posture",
    logic_type: str = "pattern",
    default_severity: str = "high",
    default_confidence: str = "high",
) -> MagicMock:
    """Create a minimal mock RuleDefinition."""
    rule = MagicMock()
    rule.slug = slug
    rule.name = slug.replace("-", " ").title()
    rule.category = category
    rule.logic_type = logic_type
    rule.default_severity = default_severity
    rule.default_confidence = default_confidence
    rule.logic_config = {
        "action_filters": action_filters,
        "field_conditions": [],
        "time_window_seconds": 0,
    }
    return rule


# ── GHAS rule definitions ────────────────────────────────────────────────────

GHAS_RULES: list[dict[str, Any]] = [
    {
        "slug": "ghas-code-scanning-disabled",
        "actions": ["code_scanning.disable"],
        "severity": "high",
    },
    {
        "slug": "ghas-dependabot-alerts-disabled",
        "actions": ["dependabot_alerts.disable"],
        "severity": "high",
    },
    {
        "slug": "ghas-dependabot-updates-disabled",
        "actions": ["dependabot_security_updates.disable"],
        "severity": "medium",
    },
    {
        "slug": "ghas-secret-scanning-disabled",
        "actions": [
            "secret_scanning.disable",
            "repository_secret_scanning.disable",
        ],
        "severity": "critical",
    },
    {
        "slug": "ghas-vulnerability-alerts-disabled",
        "actions": ["repository_vulnerability_alerts.disable"],
        "severity": "high",
    },
    {
        "slug": "ghas-advanced-security-disabled",
        "actions": [
            "business.advanced_security_disabled",
            "org.advanced_security_disabled_for_new_repos",
            "repo.advanced_security_disabled",
        ],
        "severity": "critical",
    },
    {
        "slug": "ghas-push-protection-disabled",
        "actions": [
            "secret_scanning_push_protection.disable",
            "repository_secret_scanning_push_protection.disable",
        ],
        "severity": "critical",
    },
]

# Map: enable action → expected dedup_key prefix slug
_GHAS_REMEDIATION_ACTIONS: list[dict[str, Any]] = [
    {
        "enable_actions": ["code_scanning.enable"],
        "slug": "ghas-code-scanning-disabled",
    },
    {
        "enable_actions": ["dependabot_alerts.enable"],
        "slug": "ghas-dependabot-alerts-disabled",
    },
    {
        "enable_actions": ["dependabot_security_updates.enable"],
        "slug": "ghas-dependabot-updates-disabled",
    },
    {
        "enable_actions": [
            "secret_scanning.enable",
            "repository_secret_scanning.enable",
        ],
        "slug": "ghas-secret-scanning-disabled",
    },
    {
        "enable_actions": ["repository_vulnerability_alerts.enable"],
        "slug": "ghas-vulnerability-alerts-disabled",
    },
    {
        "enable_actions": [
            "business.advanced_security_enabled",
            "org.advanced_security_enabled_for_new_repos",
            "repo.advanced_security_enabled",
        ],
        "slug": "ghas-advanced-security-disabled",
    },
    {
        "enable_actions": [
            "secret_scanning_push_protection.enable",
            "repository_secret_scanning_push_protection.enable",
        ],
        "slug": "ghas-push-protection-disabled",
    },
]


# ── Tests: event_matches_rule ────────────────────────────────────────────────


class TestGhasEventMatchesRule:
    """Each GHAS disable action should match its corresponding rule."""

    @pytest.mark.parametrize(
        "rule_def",
        GHAS_RULES,
        ids=[r["slug"] for r in GHAS_RULES],
    )
    def test_disable_action_matches_rule(self, rule_def: dict[str, Any]) -> None:
        """Every listed disable action should match the rule's action filters."""
        rule = _make_rule(
            slug=rule_def["slug"],
            action_filters=rule_def["actions"],
            default_severity=rule_def["severity"],
        )
        for action in rule_def["actions"]:
            event = _make_event(action)
            assert event_matches_rule(event, rule), f"{action} should match rule {rule_def['slug']}"

    @pytest.mark.parametrize(
        "rule_def",
        GHAS_RULES,
        ids=[r["slug"] for r in GHAS_RULES],
    )
    def test_unrelated_action_does_not_match(self, rule_def: dict[str, Any]) -> None:
        """An unrelated action should not match any GHAS rule."""
        rule = _make_rule(
            slug=rule_def["slug"],
            action_filters=rule_def["actions"],
        )
        event = _make_event("repos.create")
        assert not event_matches_rule(event, rule)

    def test_empty_action_filters_matches_everything(self) -> None:
        """A rule with no action_filters should match any event."""
        rule = _make_rule(slug="catch-all", action_filters=[])
        event = _make_event("any.action")
        assert event_matches_rule(event, rule)


# ── Tests: remediation map entries ───────────────────────────────────────────


class TestGhasRemediationMap:
    """Each GHAS enable action should resolve the corresponding disable detection."""

    @pytest.mark.parametrize(
        "remap",
        _GHAS_REMEDIATION_ACTIONS,
        ids=[r["slug"] for r in _GHAS_REMEDIATION_ACTIONS],
    )
    def test_enable_action_in_remediation_map(self, remap: dict[str, Any]) -> None:
        """Every GHAS enable action should appear in _REMEDIATION_MAP."""
        for enable_action in remap["enable_actions"]:
            found = False
            for mapping in _REMEDIATION_MAP:
                if enable_action in mapping["actions"]:
                    found = True
                    break
            assert found, f"Enable action {enable_action} not found in _REMEDIATION_MAP"

    @pytest.mark.parametrize(
        "remap",
        _GHAS_REMEDIATION_ACTIONS,
        ids=[r["slug"] for r in _GHAS_REMEDIATION_ACTIONS],
    )
    def test_dedup_prefix_contains_slug(self, remap: dict[str, Any]) -> None:
        """The dedup_prefix_fn should produce a key containing the rule slug."""
        for enable_action in remap["enable_actions"]:
            # Find a mapping that matches both the action AND produces the GHAS slug
            found = False
            for mapping in _REMEDIATION_MAP:
                if enable_action in mapping["actions"]:
                    event = _make_event(enable_action)
                    prefix = mapping["dedup_prefix_fn"](event)
                    if remap["slug"] in prefix:
                        found = True
                        break
            assert found, f"No remediation mapping for {enable_action} with slug {remap['slug']}"

    @pytest.mark.parametrize(
        "remap",
        _GHAS_REMEDIATION_ACTIONS,
        ids=[r["slug"] for r in _GHAS_REMEDIATION_ACTIONS],
    )
    def test_dedup_prefix_format(self, remap: dict[str, Any]) -> None:
        """The prefix should follow posture:<slug>:<org>:<repo_short> format."""
        enable_action = remap["enable_actions"][0]
        event = _make_event(enable_action, org="acme", repo="acme/web-app")
        expected = f"posture:{remap['slug']}:acme:web-app"

        found = False
        for mapping in _REMEDIATION_MAP:
            if enable_action in mapping["actions"]:
                prefix = mapping["dedup_prefix_fn"](event)
                if prefix == expected:
                    found = True
                    break
        assert found, f"Expected prefix {expected!r} not found for action {enable_action}"

    def test_all_seven_ghas_rules_have_remediation_entries(self) -> None:
        """All 7 GHAS rules should have corresponding remediation map entries."""
        ghas_slugs = {r["slug"] for r in GHAS_RULES}
        mapped_slugs: set[str] = set()

        for mapping in _REMEDIATION_MAP:
            event = _make_event(mapping["actions"][0])
            prefix = mapping["dedup_prefix_fn"](event)
            # Extract slug from posture:<slug>:<rest>
            parts = prefix.split(":")
            if len(parts) >= 2 and parts[0] == "posture":
                slug = parts[1]
                if slug in ghas_slugs:
                    mapped_slugs.add(slug)

        assert ghas_slugs == mapped_slugs, (
            f"Missing remediation entries for: {ghas_slugs - mapped_slugs}"
        )


# ── Tests: dedup key generation for GHAS detections ─────────────────────────


class TestGhasDetectionDedupKey:
    """Verify that pattern detections for GHAS rules include a dedup_key."""

    def test_ghas_rule_generates_dedup_key(self) -> None:
        """A GHAS pattern rule should include dedup_key in context_data."""
        rule_slug = "ghas-code-scanning-disabled"
        event_org = "acme"
        event_repo = "acme/web-app"

        repo_short = _repo_short(event_repo)
        expected_key = f"posture:{rule_slug}:{event_org}:{repo_short}"
        assert expected_key == "posture:ghas-code-scanning-disabled:acme:web-app"

    def test_repo_short_extracts_name(self) -> None:
        """_repo_short should extract repo name from org/repo format."""
        assert _repo_short("acme/web-app") == "web-app"
        assert _repo_short("web-app") == "web-app"
        assert _repo_short(None) == ""
        assert _repo_short("") == ""

    @pytest.mark.parametrize(
        "rule_def",
        GHAS_RULES,
        ids=[r["slug"] for r in GHAS_RULES],
    )
    def test_dedup_key_matches_remediation_prefix(self, rule_def: dict[str, Any]) -> None:
        """The dedup_key from a GHAS detection should be matchable by its
        corresponding remediation entry."""
        slug = rule_def["slug"]
        org = "test-org"
        repo = "test-org/test-repo"
        repo_short = _repo_short(repo)

        # Build the dedup_key as _write_detection_for_event would
        detection_dedup_key = f"posture:{slug}:{org}:{repo_short}"

        # Find the corresponding remediation entry and check prefix match
        remap = next(
            (r for r in _GHAS_REMEDIATION_ACTIONS if r["slug"] == slug),
            None,
        )
        assert remap is not None, f"No remediation mapping for {slug}"

        enable_action = remap["enable_actions"][0]
        event = _make_event(enable_action, org=org, repo=repo)

        found = False
        for mapping in _REMEDIATION_MAP:
            if enable_action in mapping["actions"]:
                prefix = mapping["dedup_prefix_fn"](event)
                if detection_dedup_key.startswith(prefix):
                    found = True
                    break
        assert found, (
            f"Detection dedup_key {detection_dedup_key!r} "
            f"not matched by any remediation prefix for {enable_action}"
        )
