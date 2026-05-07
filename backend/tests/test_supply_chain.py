"""Tests for the supply chain service and router."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps import get_db, get_valkey
from app.routers import supply_chain as supply_chain_module
from app.services.supply_chain_service import (
    _check_action_ref,
    _compute_score,
    analyze_workflow_file,
)

SECRET = "testsecretkey_for_unit_tests_only_32ch"


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_jwt(sub: str = "testuser", jti: str = "sc-jti") -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": sub,
        "github_id": 12345,
        "jti": jti,
        "exp": now + timedelta(hours=1),
        "iat": now,
    }
    return pyjwt.encode(payload, SECRET, algorithm="HS256")


def _make_session(roles: list[str] | None = None) -> str:
    return json.dumps(
        {
            "github_login": "testuser",
            "github_id": 12345,
            "roles": roles or ["analyst"],
            "scoped_orgs": ["my-org"],
            "scoped_repos": [],
            "scope_type": "scoped",
            "session_expires_at": "2099-01-01T00:00:00+00:00",
        }
    )


def _make_mock_db() -> AsyncMock:
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_result.fetchall.return_value = []
    mock_result.scalar.return_value = 0

    mock_db = AsyncMock()
    mock_db.execute.return_value = mock_result
    return mock_db


def _build_supply_chain_app(
    valkey_session: str | None = None,
) -> tuple[FastAPI, AsyncMock, AsyncMock]:
    """Create a FastAPI app with the supply chain router for testing."""
    app = FastAPI()
    app.include_router(supply_chain_module.router, prefix="/api/v1")

    mock_db = _make_mock_db()
    mock_valkey = AsyncMock()
    mock_valkey.get = AsyncMock(return_value=valkey_session)

    async def override_db():  # type: ignore[return-value]
        yield mock_db

    async def override_valkey():  # type: ignore[return-value]
        yield mock_valkey

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_valkey] = override_valkey

    return app, mock_db, mock_valkey


# ── Fixture loading test ─────────────────────────────────────────────────────


class TestFixtureLoading:
    """Verify the supply chain rules fixture is well-formed."""

    _FIXTURE = (
        Path(__file__).resolve().parent.parent / "app" / "fixtures" / "supply_chain_rules.json"
    )

    def test_fixture_file_exists(self) -> None:
        assert self._FIXTURE.exists(), f"Not found: {self._FIXTURE}"

    def test_fixture_is_valid_json(self) -> None:
        with open(self._FIXTURE) as f:
            data = json.load(f)
        assert isinstance(data, list)
        assert len(data) == 8  # 8 rules defined in requirements

    def test_fixture_rules_have_required_fields(self) -> None:
        with open(self._FIXTURE) as f:
            data = json.load(f)
        required_fields = {
            "name",
            "slug",
            "description",
            "category",
            "default_severity",
            "default_confidence",
            "logic_type",
            "logic_config",
            "created_by",
        }
        for rule in data:
            missing = required_fields - set(rule.keys())
            assert not missing, f"Rule '{rule.get('name', '?')}' missing: {missing}"

    def test_fixture_rules_are_supply_chain_category(self) -> None:
        with open(self._FIXTURE) as f:
            data = json.load(f)
        for rule in data:
            assert rule["category"] == "supply_chain", (
                f"Rule '{rule['name']}' has category '{rule['category']}'"
            )

    def test_fixture_slugs_are_unique(self) -> None:
        with open(self._FIXTURE) as f:
            data = json.load(f)
        slugs = [r["slug"] for r in data]
        assert len(slugs) == len(set(slugs)), "Duplicate slugs"

    def test_fixture_severities_are_valid(self) -> None:
        with open(self._FIXTURE) as f:
            data = json.load(f)
        valid = {"critical", "high", "medium", "low", "info"}
        for rule in data:
            assert rule["default_severity"] in valid, (
                f"Rule '{rule['name']}' bad severity: {rule['default_severity']}"
            )

    def test_fixture_confidences_are_valid(self) -> None:
        with open(self._FIXTURE) as f:
            data = json.load(f)
        valid = {"high", "medium", "low"}
        for rule in data:
            assert rule["default_confidence"] in valid, (
                f"Rule '{rule['name']}' bad confidence: {rule['default_confidence']}"
            )


# ── Workflow analysis tests ──────────────────────────────────────────────────


class TestAnalyzeWorkflowFile:
    """Tests for analyze_workflow_file()."""

    @pytest.mark.asyncio
    async def test_clean_workflow_returns_no_findings(self) -> None:
        content = """
name: CI
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@a5ac7e51b41094c92402da3b24376905380afc29
      - run: echo "hello"
"""
        findings = await analyze_workflow_file(content)
        assert len(findings) == 0

    @pytest.mark.asyncio
    async def test_unpinned_action_detected(self) -> None:
        content = """
name: CI
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
"""
        findings = await analyze_workflow_file(content)
        slug = "action-version-pinning-violation"
        pinning_findings = [f for f in findings if f.rule_slug == slug]
        assert len(pinning_findings) == 1
        assert pinning_findings[0].severity == "medium"
        assert pinning_findings[0].line is not None

    @pytest.mark.asyncio
    async def test_unverified_org_detected(self) -> None:
        content = """
name: CI
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: some-random-org/some-action@v1
"""
        findings = await analyze_workflow_file(content)
        org_findings = [f for f in findings if f.rule_slug == "malicious-github-action"]
        assert len(org_findings) == 1
        assert "some-random-org" in org_findings[0].detail

    @pytest.mark.asyncio
    async def test_pr_target_with_checkout_head(self) -> None:
        content = """
name: PR Review
on: pull_request_target
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@a5ac7e51b41094c92402da3b24376905380afc29
        with:
          ref: ${{ github.event.pull_request.head.sha }}
      - run: npm test
"""
        findings = await analyze_workflow_file(content)
        injection_findings = [f for f in findings if f.rule_slug == "workflow-injection"]
        assert len(injection_findings) >= 1
        critical = [f for f in injection_findings if f.severity == "critical"]
        assert len(critical) == 1

    @pytest.mark.asyncio
    async def test_expression_injection_detected(self) -> None:
        content = """
name: Issue Handler
on: issues
jobs:
  greet:
    runs-on: ubuntu-latest
    steps:
      - run: echo "${{ github.event.issue.title }}"
"""
        findings = await analyze_workflow_file(content)
        injection_findings = [f for f in findings if f.title == "Potential expression injection"]
        assert len(injection_findings) == 1

    @pytest.mark.asyncio
    async def test_local_action_not_flagged(self) -> None:
        content = """
name: CI
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: ./local-action
"""
        findings = await analyze_workflow_file(content)
        assert len(findings) == 0

    @pytest.mark.asyncio
    async def test_docker_action_not_flagged(self) -> None:
        content = """
name: CI
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: docker://alpine:3.18
"""
        findings = await analyze_workflow_file(content)
        assert len(findings) == 0

    @pytest.mark.asyncio
    async def test_multiple_findings_in_single_file(self) -> None:
        content = """
name: CI
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: unknown-org/evil-action@main
      - uses: actions/setup-node@v3
"""
        findings = await analyze_workflow_file(content)
        assert len(findings) >= 3  # pinning + unverified org + more pinning


# ── _check_action_ref unit tests ─────────────────────────────────────────────


class TestCheckActionRef:
    """Unit tests for the _check_action_ref helper."""

    def test_sha_pinned_verified_org(self) -> None:
        findings = _check_action_ref("actions/checkout@a5ac7e51b41094c92402da3b24376905380afc29", 1)
        assert len(findings) == 0

    def test_tag_ref_verified_org(self) -> None:
        findings = _check_action_ref("actions/checkout@v4", 5)
        assert len(findings) == 1
        assert findings[0].rule_slug == "action-version-pinning-violation"

    def test_unverified_org_sha_pinned(self) -> None:
        findings = _check_action_ref(
            "random-org/action@a5ac7e51b41094c92402da3b24376905380afc29", 1
        )
        assert len(findings) == 1
        assert findings[0].rule_slug == "malicious-github-action"
        assert findings[0].severity == "medium"  # lower severity since SHA-pinned

    def test_unverified_org_tag_ref(self) -> None:
        findings = _check_action_ref("random-org/action@v1", 1)
        assert len(findings) == 2  # both pinning and unverified org

    def test_local_action_skipped(self) -> None:
        findings = _check_action_ref("./local-action", 1)
        assert len(findings) == 0

    def test_docker_action_skipped(self) -> None:
        findings = _check_action_ref("docker://alpine:3.18", 1)
        assert len(findings) == 0


# ── Score computation tests ──────────────────────────────────────────────────


class TestComputeScore:
    """Unit tests for the _compute_score helper."""

    def test_perfect_score(self) -> None:
        score = _compute_score(
            total_detections=0,
            critical=0,
            unpinned=0,
            risky_workflows=0,
        )
        assert score == 100

    def test_critical_deductions(self) -> None:
        score = _compute_score(
            total_detections=3,
            critical=3,
            unpinned=0,
            risky_workflows=0,
        )
        assert score == 70  # -30 for critical

    def test_critical_cap_at_40(self) -> None:
        score = _compute_score(
            total_detections=10,
            critical=10,
            unpinned=0,
            risky_workflows=0,
        )
        assert score == 60  # -40 cap for critical

    def test_unpinned_deductions(self) -> None:
        score = _compute_score(
            total_detections=0,
            critical=0,
            unpinned=5,
            risky_workflows=0,
        )
        assert score == 90  # -10 for unpinned

    def test_risky_workflow_deductions(self) -> None:
        score = _compute_score(
            total_detections=0,
            critical=0,
            unpinned=0,
            risky_workflows=2,
        )
        assert score == 90  # -10 for risky

    def test_minimum_score_is_zero(self) -> None:
        score = _compute_score(
            total_detections=100,
            critical=50,
            unpinned=100,
            risky_workflows=50,
        )
        assert score == 0

    def test_combined_deductions(self) -> None:
        score = _compute_score(
            total_detections=5,
            critical=2,
            unpinned=3,
            risky_workflows=1,
        )
        # -20 critical, -6 unpinned, -5 risky, -3 non-critical = 66
        assert score == 66


# ── Router tests ─────────────────────────────────────────────────────────────


class TestSupplyChainRouter:
    """Integration tests for the supply-chain router endpoints."""

    @patch("app.services.rbac_service.get_scoped_orgs", new_callable=AsyncMock)
    @patch("app.services.supply_chain_service.get_supply_chain_posture", new_callable=AsyncMock)
    def test_get_posture(
        self,
        mock_posture: AsyncMock,
        mock_orgs: AsyncMock,
    ) -> None:
        from app.services.supply_chain_service import SupplyChainPosture

        mock_orgs.return_value = ["my-org"]
        mock_posture.return_value = SupplyChainPosture(
            score=85,
            unpinned_actions=3,
            dependency_alerts=5,
            risky_workflows=1,
            rules_active=8,
            total_detections=10,
            critical_detections=2,
            recent_risks=[],
        )

        token = _make_jwt()
        app, _, _ = _build_supply_chain_app(valkey_session=_make_session(roles=["analyst"]))
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get(
            "/api/v1/supply-chain/posture",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["score"] == 85
        assert data["rules_active"] == 8

    @patch("app.services.rbac_service.get_scoped_orgs", new_callable=AsyncMock)
    @patch("app.services.supply_chain_service.get_dependency_risk_summary", new_callable=AsyncMock)
    def test_get_risks(
        self,
        mock_risks: AsyncMock,
        mock_orgs: AsyncMock,
    ) -> None:
        from app.services.supply_chain_service import DependencyRiskSummary

        mock_orgs.return_value = ["my-org"]
        mock_risks.return_value = DependencyRiskSummary(
            total_risks=15,
            by_severity={"critical": 3, "high": 5, "medium": 7},
            by_type={"action-version-pinning-violation": 10, "workflow-injection": 5},
            top_repos=[{"repo": "my-org/repo1", "count": 8}],
        )

        token = _make_jwt()
        app, _, _ = _build_supply_chain_app(valkey_session=_make_session(roles=["analyst"]))
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get(
            "/api/v1/supply-chain/risks",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_risks"] == 15

    def test_analyze_workflow_endpoint(self) -> None:
        workflow_content = """
name: CI
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: unknown/action@main
"""
        token = _make_jwt()
        app, _, _ = _build_supply_chain_app(valkey_session=_make_session(roles=["analyst"]))
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.post(
            "/api/v1/supply-chain/analyze-workflow",
            json={"content": workflow_content},
            cookies={"access_token": token, "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_findings"] >= 2
        assert data["risk_level"] in {"critical", "high", "medium", "low", "none"}
        assert isinstance(data["findings"], list)

    def test_analyze_workflow_empty_content_rejected(self) -> None:
        token = _make_jwt()
        app, _, _ = _build_supply_chain_app(valkey_session=_make_session(roles=["analyst"]))
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/v1/supply-chain/analyze-workflow",
            json={"content": ""},
            cookies={"access_token": token, "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert resp.status_code == 422

    def test_analyze_clean_workflow(self) -> None:
        workflow_content = """
name: CI
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@a5ac7e51b41094c92402da3b24376905380afc29
      - run: echo "hello"
"""
        token = _make_jwt()
        app, _, _ = _build_supply_chain_app(valkey_session=_make_session(roles=["analyst"]))
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.post(
            "/api/v1/supply-chain/analyze-workflow",
            json={"content": workflow_content},
            cookies={"access_token": token, "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_findings"] == 0
        assert data["risk_level"] == "none"

    def test_unauthenticated_returns_401(self) -> None:
        app, _, _ = _build_supply_chain_app(valkey_session=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/supply-chain/posture")
        assert resp.status_code == 401
