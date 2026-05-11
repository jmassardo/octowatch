"""Tests for project governance detection rules in the rule library."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_LIBRARY_PATH = Path(__file__).parent.parent / "app" / "fixtures" / "rule_library.json"

_PROJECT_RULES = {
    "project-visibility-public": {
        "category": "data_exfiltration",
        "severity": "critical",
        "logic_type": "pattern",
        "action": "project.visibility_public",
    },
    "project-collaborator-added-external": {
        "category": "privilege_escalation",
        "severity": "high",
        "logic_type": "pattern",
        "action": "project_collaborator.add",
    },
    "project-collaborator-role-escalated": {
        "category": "privilege_escalation",
        "severity": "medium",
        "logic_type": "pattern",
        "action": "project_collaborator.update",
    },
    "project-base-role-elevated": {
        "category": "privilege_escalation",
        "severity": "high",
        "logic_type": "pattern",
        "action": "project_base_role.update",
    },
    "project-deleted": {
        "category": "defense_evasion",
        "severity": "high",
        "logic_type": "pattern",
        "action": "project.delete",
    },
    "project-field-deleted": {
        "category": "defense_evasion",
        "severity": "medium",
        "logic_type": "pattern",
        "action": "project_field.delete",
    },
}


@pytest.fixture()
def library_rules() -> list[dict]:
    with open(_LIBRARY_PATH) as f:
        return json.load(f)


def _get_rule(rules: list[dict], slug: str) -> dict:
    matches = [r for r in rules if r["slug"] == slug]
    assert matches, f"Rule '{slug}' not found in rule_library.json"
    return matches[0]


class TestProjectGovernanceRules:
    """Validate the 6 project governance detection rules."""

    def test_all_project_rules_exist(self, library_rules: list[dict]) -> None:
        slugs = {r["slug"] for r in library_rules}
        for slug in _PROJECT_RULES:
            assert slug in slugs, f"Missing rule: {slug}"

    @pytest.mark.parametrize("slug,expected", list(_PROJECT_RULES.items()))
    def test_rule_category(self, library_rules: list[dict], slug: str, expected: dict) -> None:
        rule = _get_rule(library_rules, slug)
        assert rule["category"] == expected["category"]

    @pytest.mark.parametrize("slug,expected", list(_PROJECT_RULES.items()))
    def test_rule_severity(self, library_rules: list[dict], slug: str, expected: dict) -> None:
        rule = _get_rule(library_rules, slug)
        assert rule["default_severity"] == expected["severity"]

    @pytest.mark.parametrize("slug,expected", list(_PROJECT_RULES.items()))
    def test_rule_logic_type(self, library_rules: list[dict], slug: str, expected: dict) -> None:
        rule = _get_rule(library_rules, slug)
        assert rule["logic_type"] == expected["logic_type"]

    @pytest.mark.parametrize("slug,expected", list(_PROJECT_RULES.items()))
    def test_rule_action_filter(self, library_rules: list[dict], slug: str, expected: dict) -> None:
        rule = _get_rule(library_rules, slug)
        actions = rule["logic_config"]["action_filters"]
        assert expected["action"] in actions

    @pytest.mark.parametrize("slug,expected", list(_PROJECT_RULES.items()))
    def test_rule_has_confidence(
        self, library_rules: list[dict], slug: str, expected: dict
    ) -> None:
        rule = _get_rule(library_rules, slug)
        conf = rule["logic_config"].get("confidence", 0)
        assert 0.5 <= conf <= 1.0, f"Confidence {conf} out of range for {slug}"

    @pytest.mark.parametrize("slug,expected", list(_PROJECT_RULES.items()))
    def test_rule_has_required_fields(
        self, library_rules: list[dict], slug: str, expected: dict
    ) -> None:
        rule = _get_rule(library_rules, slug)
        required = {
            "name",
            "slug",
            "description",
            "category",
            "default_severity",
            "logic_type",
            "logic_config",
        }
        missing = required - rule.keys()
        assert not missing, f"Rule '{slug}' missing fields: {missing}"

    def test_project_rules_use_distinct_actions(self, library_rules: list[dict]) -> None:
        """Each project rule targets a unique audit log action."""
        actions = []
        for slug in _PROJECT_RULES:
            rule = _get_rule(library_rules, slug)
            actions.extend(rule["logic_config"]["action_filters"])
        assert len(actions) == len(set(actions)), f"Duplicate actions: {actions}"
