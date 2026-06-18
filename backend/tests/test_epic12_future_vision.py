"""Unit tests for Epic 12: Future Vision & Differentiators.

Covers:
- Plugin system (Issue #39)
- Cross-org correlation (Issue #50)
- Incident response playbooks (Issue #51)
- Natural language query (Issue #62)
- Workflow security scanner (Issue #65)
- Copilot governance policies (Issue #67)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

# ═══════════════════════════════════════════════════════════════════════════════
# Issue #39: Plugin System
# ═══════════════════════════════════════════════════════════════════════════════


class TestEnrichmentPluginBase:
    """Verify the abstract base class contract."""

    def test_cannot_instantiate_abc(self):
        from app.plugins.base import EnrichmentPlugin

        with pytest.raises(TypeError):
            EnrichmentPlugin()  # type: ignore[abstract]

    def test_concrete_subclass_instantiates(self):
        from app.plugins.base import EnrichmentPlugin

        class StubPlugin(EnrichmentPlugin):
            @property
            def name(self) -> str:
                return "stub"

            @property
            def version(self) -> str:
                return "0.0.1"

            async def enrich(self, event: dict[str, Any]) -> dict[str, Any] | None:
                return {"tag": "test"}

        p = StubPlugin()
        assert p.name == "stub"
        assert p.version == "0.0.1"


class TestPluginManager:
    """PluginManager discovery and enrichment orchestration."""

    def test_discover_loads_example_plugin(self):
        from app.plugins.loader import PluginManager

        mgr = PluginManager()
        mgr.discover()
        assert len(mgr.plugins) >= 1
        names = [p.name for p in mgr.plugins]
        assert "ip_reputation" in names

    @pytest.mark.asyncio
    async def test_run_enrichments_returns_merged(self):
        from app.plugins.base import EnrichmentPlugin
        from app.plugins.loader import PluginManager

        class Plugin1(EnrichmentPlugin):
            @property
            def name(self) -> str:
                return "p1"

            @property
            def version(self) -> str:
                return "1.0"

            async def enrich(self, event: dict[str, Any]) -> dict[str, Any] | None:
                return {"score": 10}

        class Plugin2(EnrichmentPlugin):
            @property
            def name(self) -> str:
                return "p2"

            @property
            def version(self) -> str:
                return "1.0"

            async def enrich(self, event: dict[str, Any]) -> dict[str, Any] | None:
                return None  # skip

        mgr = PluginManager()
        mgr.plugins = [Plugin1(), Plugin2()]

        result = await mgr.run_enrichments({"action": "test"})
        assert "p1" in result
        assert result["p1"]["score"] == 10
        assert "p2" not in result

    @pytest.mark.asyncio
    async def test_run_enrichments_isolates_exceptions(self):
        from app.plugins.base import EnrichmentPlugin
        from app.plugins.loader import PluginManager

        class BadPlugin(EnrichmentPlugin):
            @property
            def name(self) -> str:
                return "bad"

            @property
            def version(self) -> str:
                return "0.1"

            async def enrich(self, event: dict[str, Any]) -> dict[str, Any] | None:
                raise RuntimeError("Plugin crash!")

        class GoodPlugin(EnrichmentPlugin):
            @property
            def name(self) -> str:
                return "good"

            @property
            def version(self) -> str:
                return "1.0"

            async def enrich(self, event: dict[str, Any]) -> dict[str, Any] | None:
                return {"ok": True}

        mgr = PluginManager()
        mgr.plugins = [BadPlugin(), GoodPlugin()]

        result = await mgr.run_enrichments({"action": "test"})
        # Bad plugin error is isolated; good plugin still works
        assert "good" in result
        assert result["good"]["ok"] is True
        assert "bad" not in result

    def test_unload_all_clears_plugins(self):
        from app.plugins.loader import PluginManager

        mgr = PluginManager()
        mgr.discover()
        assert len(mgr.plugins) >= 1
        mgr.unload_all()
        assert len(mgr.plugins) == 0

    def test_discover_is_idempotent(self):
        from app.plugins.loader import PluginManager

        mgr = PluginManager()
        mgr.discover()
        count1 = len(mgr.plugins)
        mgr.discover()
        count2 = len(mgr.plugins)
        assert count1 == count2


class TestIPReputationPlugin:
    """Example IP reputation plugin."""

    @pytest.mark.asyncio
    async def test_known_bad_ip(self):
        from app.plugins.example_ip_reputation import IPReputationPlugin

        plugin = IPReputationPlugin()
        plugin.on_load()
        result = await plugin.enrich({"action": "auth.login", "source_ip": "198.51.100.1"})
        assert result is not None
        assert result["reputation"] == "malicious"

    @pytest.mark.asyncio
    async def test_clean_ip_returns_none(self):
        from app.plugins.example_ip_reputation import IPReputationPlugin

        plugin = IPReputationPlugin()
        plugin.on_load()
        result = await plugin.enrich({"action": "auth.login", "source_ip": "10.0.0.1"})
        assert result is None

    @pytest.mark.asyncio
    async def test_no_ip_returns_none(self):
        from app.plugins.example_ip_reputation import IPReputationPlugin

        plugin = IPReputationPlugin()
        plugin.on_load()
        result = await plugin.enrich({"action": "auth.login"})
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# Issue #62: Natural Language Query
# ═══════════════════════════════════════════════════════════════════════════════


class TestNLQueryService:
    """NL-to-SQL translation service."""

    def _svc(self):
        from app.services.nl_query_service import NLQueryService

        return NLQueryService()

    def test_admin_role_changes_last_7_days(self):
        svc = self._svc()
        results = svc.translate("Show me all admin role changes in the last 7 days")
        assert len(results) >= 1
        top = results[0]
        assert "org.update_member" in top.sql or "role" in top.sql.lower()
        assert "7 days" in top.sql or "7" in top.sql
        assert top.confidence >= 0.5

    def test_repo_deletions(self):
        svc = self._svc()
        results = svc.translate("Show repo deletions in the last 30 days")
        assert len(results) >= 1
        assert "repo.destroy" in results[0].sql

    def test_count_query(self):
        svc = self._svc()
        results = svc.translate("How many login failures in the last 24 hours")
        assert len(results) >= 1
        top = results[0]
        assert "COUNT" in top.sql.upper()
        assert "auth.login_failure" in top.sql

    def test_who_query(self):
        svc = self._svc()
        results = svc.translate("Who has been most active in the last 7 days")
        assert len(results) >= 1
        assert "actor" in results[0].sql.lower()

    def test_empty_query_returns_empty(self):
        svc = self._svc()
        results = svc.translate("")
        assert results == []

    def test_ambiguous_query_returns_multiple(self):
        svc = self._svc()
        results = svc.translate("Show all admin role changes in the last 7 days")
        # Should produce both detail and summary interpretations
        assert len(results) >= 2

    def test_branch_protection_query(self):
        svc = self._svc()
        results = svc.translate("List branch protection changes in the past 14 days")
        assert len(results) >= 1
        assert "protected_branch" in results[0].sql

    def test_fallback_for_unknown_query(self):
        svc = self._svc()
        results = svc.translate("xyzzy foobar unrecognized query")
        assert len(results) >= 1
        # Should at least return a fallback
        assert any(r.confidence <= 0.5 for r in results)

    def test_actor_filter(self):
        svc = self._svc()
        results = svc.translate("Show me repo deletions by octocat")
        assert len(results) >= 1
        assert "octocat" in results[0].sql

    def test_severity_filter(self):
        svc = self._svc()
        results = svc.translate("Show critical detections in the last 7 days")
        assert len(results) >= 1
        assert "critical" in results[0].sql

    def test_deduplicates_results(self):
        svc = self._svc()
        results = svc.translate("Show login failures")
        sql_strings = [r.sql for r in results]
        assert len(sql_strings) == len(set(sql_strings))

    def test_max_five_results(self):
        svc = self._svc()
        results = svc.translate("Show me all admin role changes in the last 7 days")
        assert len(results) <= 5


# ═══════════════════════════════════════════════════════════════════════════════
# Issue #65: Workflow Security Scanner
# ═══════════════════════════════════════════════════════════════════════════════


class TestWorkflowScannerService:
    """Workflow YAML security analysis."""

    def _svc(self):
        from app.services.workflow_scanner_service import WorkflowScannerService

        return WorkflowScannerService()

    def test_unpinned_action_detected(self):
        svc = self._svc()
        yaml_content = """
name: CI
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
"""
        result = svc.scan_workflow(yaml_content, ".github/workflows/ci.yml")
        rule_ids = [f.rule_id for f in result.findings]
        assert "unpinned-action" in rule_ids

    def test_pinned_action_passes(self):
        svc = self._svc()
        yaml_content = """
name: CI
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@a5ac7e51b41094c92402da3b24376905380afc29
"""
        result = svc.scan_workflow(yaml_content, ".github/workflows/ci.yml")
        rule_ids = [f.rule_id for f in result.findings]
        assert "unpinned-action" not in rule_ids

    def test_pr_target_checkout_detected(self):
        svc = self._svc()
        yaml_content = """
name: Label
on: pull_request_target
jobs:
  label:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
"""
        result = svc.scan_workflow(yaml_content, ".github/workflows/label.yml")
        rule_ids = [f.rule_id for f in result.findings]
        assert "pull-request-target-checkout" in rule_ids

    def test_pr_target_without_checkout_is_fine(self):
        svc = self._svc()
        yaml_content = """
name: Label
on: pull_request_target
jobs:
  label:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/labeler@v4
"""
        result = svc.scan_workflow(yaml_content, ".github/workflows/label.yml")
        rule_ids = [f.rule_id for f in result.findings]
        assert "pull-request-target-checkout" not in rule_ids

    def test_write_all_permissions_detected(self):
        svc = self._svc()
        yaml_content = """
name: Deploy
on: push
permissions: write-all
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - run: echo deploy
"""
        result = svc.scan_workflow(yaml_content, ".github/workflows/deploy.yml")
        rule_ids = [f.rule_id for f in result.findings]
        assert "excessive-permissions" in rule_ids

    def test_self_hosted_runner_flagged(self):
        svc = self._svc()
        yaml_content = """
name: Build
on: push
jobs:
  build:
    runs-on: self-hosted
    steps:
      - run: echo build
"""
        result = svc.scan_workflow(yaml_content, ".github/workflows/build.yml")
        rule_ids = [f.rule_id for f in result.findings]
        assert "self-hosted-runner" in rule_ids

    def test_script_injection_detected(self):
        svc = self._svc()
        yaml_content = """
name: Greet
on: issues
jobs:
  greet:
    runs-on: ubuntu-latest
    steps:
      - run: echo "${{ github.event.issue.title }}"
"""
        result = svc.scan_workflow(yaml_content, ".github/workflows/greet.yml")
        rule_ids = [f.rule_id for f in result.findings]
        assert "script-injection" in rule_ids

    def test_secret_in_pr_target_detected(self):
        import yaml

        from app.services.workflow_scanner_service import WorkflowScannerService

        # Construct the workflow dict directly to avoid YAML parsing issues
        # with ${{ }} template syntax
        workflow = {
            "name": "PR Build",
            "on": "pull_request_target",
            "jobs": {
                "build": {
                    "runs-on": "ubuntu-latest",
                    "env": {"TOKEN": "secrets.DEPLOY_TOKEN"},
                    "steps": [{"run": "curl -H 'Authorization: $TOKEN' https://api.example.com"}],
                }
            },
        }
        yaml_str = yaml.dump(workflow, default_flow_style=False)
        svc = WorkflowScannerService()
        result = svc.scan_workflow(yaml_str, ".github/workflows/pr-build.yml")
        rule_ids = [f.rule_id for f in result.findings]
        assert "secret-in-pr" in rule_ids

    def test_malformed_yaml_handled_gracefully(self):
        svc = self._svc()
        result = svc.scan_workflow("{{{{not yaml}}}", ".github/workflows/bad.yml")
        rule_ids = [f.rule_id for f in result.findings]
        assert "malformed-yaml" in rule_ids
        assert result.score == 50

    def test_score_calculation(self):
        svc = self._svc()
        # Clean workflow should score 100
        yaml_content = """
name: CI
on: push
permissions:
  contents: read
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo clean
"""
        result = svc.scan_workflow(yaml_content, ".github/workflows/ci.yml")
        assert result.score == 100

    def test_suggest_fix_returns_string(self):
        svc = self._svc()
        yaml_content = """
name: CI
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
"""
        result = svc.scan_workflow(yaml_content, ".github/workflows/ci.yml")
        assert len(result.findings) >= 1
        fix = svc.suggest_fix(result.findings[0])
        assert isinstance(fix, str)
        assert len(fix) > 0

    def test_local_action_not_flagged(self):
        svc = self._svc()
        yaml_content = """
name: CI
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: ./local-action
"""
        result = svc.scan_workflow(yaml_content, ".github/workflows/ci.yml")
        rule_ids = [f.rule_id for f in result.findings]
        assert "unpinned-action" not in rule_ids


# ═══════════════════════════════════════════════════════════════════════════════
# Issue #67: Copilot Governance
# ═══════════════════════════════════════════════════════════════════════════════


class TestCopilotGovernanceService:
    """Copilot governance policy evaluation."""

    def test_acceptance_threshold_violation(self):
        from app.services.copilot_governance_service import _evaluate_acceptance_threshold

        config = {"min_acceptance_rate": 15.0}
        metrics = {
            "seats": [
                {"login": "alice", "acceptance_rate": 5.0},
                {"login": "bob", "acceptance_rate": 20.0},
            ]
        }
        violations = _evaluate_acceptance_threshold(config, metrics)
        assert len(violations) == 1
        assert violations[0]["actor_login"] == "alice"
        assert violations[0]["type"] == "low_acceptance_rate"

    def test_acceptance_threshold_no_violations(self):
        from app.services.copilot_governance_service import _evaluate_acceptance_threshold

        config = {"min_acceptance_rate": 5.0}
        metrics = {
            "seats": [
                {"login": "alice", "acceptance_rate": 10.0},
            ]
        }
        violations = _evaluate_acceptance_threshold(config, metrics)
        assert len(violations) == 0

    def test_seat_classification_violation(self):
        from app.services.copilot_governance_service import _evaluate_seat_classification

        config = {"allowed_classifications": ["internal", "public"]}
        metrics = {
            "seats": [
                {"login": "alice", "repo_classification": "confidential"},
                {"login": "bob", "repo_classification": "internal"},
            ]
        }
        violations = _evaluate_seat_classification(config, metrics)
        assert len(violations) == 1
        assert violations[0]["actor_login"] == "alice"

    def test_usage_frequency_violation(self):
        from app.services.copilot_governance_service import _evaluate_usage_frequency

        config = {"min_suggestions_per_day": 2}
        metrics = {
            "seats": [
                {"login": "alice", "daily_suggestions": 0.5},
                {"login": "bob", "daily_suggestions": 10.0},
            ]
        }
        violations = _evaluate_usage_frequency(config, metrics)
        assert len(violations) == 1
        assert violations[0]["actor_login"] == "alice"

    def test_empty_seats_no_violations(self):
        from app.services.copilot_governance_service import _evaluate_acceptance_threshold

        config = {"min_acceptance_rate": 10.0}
        violations = _evaluate_acceptance_threshold(config, {"seats": []})
        assert len(violations) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Issue #51: Playbooks — fixture validation
# ═══════════════════════════════════════════════════════════════════════════════


class TestPlaybookFixtures:
    """Validate built-in playbook templates."""

    def test_playbooks_json_loads(self):
        fixture_path = Path(__file__).parent.parent / "app" / "fixtures" / "playbooks.json"
        data = json.loads(fixture_path.read_text())
        assert isinstance(data, list)
        assert len(data) >= 4

    def test_each_playbook_has_required_fields(self):
        fixture_path = Path(__file__).parent.parent / "app" / "fixtures" / "playbooks.json"
        playbooks = json.loads(fixture_path.read_text())
        for pb in playbooks:
            assert "name" in pb
            assert "slug" in pb
            assert "description" in pb
            assert "detection_categories" in pb
            assert "steps" in pb
            assert isinstance(pb["steps"], list)
            assert len(pb["steps"]) >= 1

    def test_each_step_has_required_fields(self):
        fixture_path = Path(__file__).parent.parent / "app" / "fixtures" / "playbooks.json"
        playbooks = json.loads(fixture_path.read_text())
        for pb in playbooks:
            for step in pb["steps"]:
                assert "title" in step
                assert "description" in step
                assert "action_type" in step
                assert step["action_type"] in ("manual", "link", "api")
                assert "required" in step

    def test_playbook_slugs_unique(self):
        fixture_path = Path(__file__).parent.parent / "app" / "fixtures" / "playbooks.json"
        playbooks = json.loads(fixture_path.read_text())
        slugs = [pb["slug"] for pb in playbooks]
        assert len(slugs) == len(set(slugs))


# ═══════════════════════════════════════════════════════════════════════════════
# Issue #50: Cross-Org Rules — fixture validation
# ═══════════════════════════════════════════════════════════════════════════════


class TestCrossOrgRules:
    """Validate cross-org detection rules in rule_library.json."""

    def test_cross_org_rules_exist(self):
        fixture_path = Path(__file__).parent.parent / "app" / "fixtures" / "rule_library.json"
        rules = json.loads(fixture_path.read_text())
        cross_org_rules = [r for r in rules if r.get("logic_type") == "cross_namespace_sequence"]
        assert len(cross_org_rules) >= 3

    def test_cross_org_rules_have_steps(self):
        fixture_path = Path(__file__).parent.parent / "app" / "fixtures" / "rule_library.json"
        rules = json.loads(fixture_path.read_text())
        for rule in rules:
            if rule.get("logic_type") == "cross_namespace_sequence":
                config = rule["logic_config"]
                assert "steps" in config
                assert len(config["steps"]) >= 2
                assert "aggregation_key" in config
                assert "time_window_minutes" in config

    def test_cross_org_rule_slugs(self):
        fixture_path = Path(__file__).parent.parent / "app" / "fixtures" / "rule_library.json"
        rules = json.loads(fixture_path.read_text())
        cross_org_slugs = [
            r["slug"] for r in rules if r.get("logic_type") == "cross_namespace_sequence"
        ]
        assert "cross-org-admin-escalation" in cross_org_slugs
        assert "cross-org-secret-alert-trigger" in cross_org_slugs
        assert "cross-org-rapid-repo-access" in cross_org_slugs


# ═══════════════════════════════════════════════════════════════════════════════
# Model import verification
# ═══════════════════════════════════════════════════════════════════════════════


class TestModelImports:
    """Verify all new models are importable via the models package."""

    def test_playbook_models_importable(self):
        from app.models import PlaybookExecution, PlaybookTemplate

        assert PlaybookTemplate.__tablename__ == "playbook_templates"
        assert PlaybookExecution.__tablename__ == "playbook_executions"

    def test_copilot_policy_models_importable(self):
        from app.models import CopilotPolicy, CopilotPolicyViolation

        assert CopilotPolicy.__tablename__ == "copilot_policies"
        assert CopilotPolicyViolation.__tablename__ == "copilot_policy_violations"

    def test_workflow_finding_model_importable(self):
        from app.models import WorkflowFinding

        assert WorkflowFinding.__tablename__ == "workflow_findings"

    def test_audit_event_has_custom_enrichments(self):
        from app.models import AuditEvent

        assert hasattr(AuditEvent, "custom_enrichments")


# ═══════════════════════════════════════════════════════════════════════════════
# Router registration verification
# ═══════════════════════════════════════════════════════════════════════════════


class TestRouterRegistration:
    """Verify new routers are registered in the FastAPI app."""

    def test_app_has_cross_org_routes(self):
        from app.main import app

        paths = [r.path for r in app.routes if hasattr(r, "path")]
        assert any("/cross-org" in p for p in paths)

    def test_app_has_playbook_routes(self):
        from app.main import app

        paths = [r.path for r in app.routes if hasattr(r, "path")]
        assert any("/playbooks" in p for p in paths)

    def test_app_has_workflow_routes(self):
        from app.main import app

        paths = [r.path for r in app.routes if hasattr(r, "path")]
        assert any("/workflows" in p for p in paths)

    def test_app_has_copilot_governance_routes(self):
        from app.main import app

        paths = [r.path for r in app.routes if hasattr(r, "path")]
        assert any("/copilot/governance" in p for p in paths)

    def test_app_has_nl_query_endpoint(self):
        from app.main import app

        paths = [r.path for r in app.routes if hasattr(r, "path")]
        assert any("/query/nl" in p for p in paths)


# ═══════════════════════════════════════════════════════════════════════════════
# Migration file exists
# ═══════════════════════════════════════════════════════════════════════════════


class TestMigration:
    """Verify the migration file is present and well-formed."""

    def test_migration_file_exists(self):
        migration = (
            Path(__file__).parent.parent / "alembic" / "versions" / "0032_add_epic12_tables.py"
        )
        assert migration.exists()

    def test_migration_has_revision_chain(self):
        migration = (
            Path(__file__).parent.parent / "alembic" / "versions" / "0032_add_epic12_tables.py"
        )
        content = migration.read_text()
        assert 'revision = "0032"' in content
        assert 'down_revision = "0031"' in content


# ═══════════════════════════════════════════════════════════════════════════════
# Plugin development documentation
# ═══════════════════════════════════════════════════════════════════════════════


class TestPluginDocs:
    """Verify plugin development documentation exists."""

    def test_plugin_guide_exists(self):
        doc = Path(__file__).parent.parent.parent / "docs" / "plugin-development.md"
        assert doc.exists()

    def test_plugin_guide_has_content(self):
        doc = Path(__file__).parent.parent.parent / "docs" / "plugin-development.md"
        content = doc.read_text()
        assert "EnrichmentPlugin" in content
        assert "enrich" in content
        assert "on_load" in content
