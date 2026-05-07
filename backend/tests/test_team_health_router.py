"""Tests for the team_health router and service layer.

Tests cover:
- Unauthenticated requests → 401
- Authenticated requests return 200 with correct schema
- RBAC scope enforcement (403 when no orgs)
- All five endpoints: bus-factor, engagement, policy-violations,
  knowledge-concentration, summary
- Service-level unit tests for computation logic
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps import get_db, get_valkey
from app.routers import team_health as team_health_module

SECRET = "testsecretkey_for_unit_tests_only_32ch"

_RBAC_PATCH = "app.routers.team_health.rbac_service.get_scoped_orgs"


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_jwt(sub: str = "testuser", jti: str = "th-jti") -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": sub,
        "github_id": 12345,
        "jti": jti,
        "exp": now + timedelta(hours=1),
        "iat": now,
    }
    return pyjwt.encode(payload, SECRET, algorithm="HS256")


def _make_session(
    orgs: list[str] | None = None,
    roles: list[str] | None = None,
) -> str:
    return json.dumps(
        {
            "github_login": "testuser",
            "github_id": 12345,
            "roles": roles or ["analyst"],
            "scoped_orgs": orgs or ["my-org"],
            "scoped_repos": [],
            "scope_type": "scoped",
            "session_expires_at": "2099-01-01T00:00:00+00:00",
        }
    )


def _make_mock_db() -> AsyncMock:
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_result.fetchall.return_value = []
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalar.return_value = 0
    db = AsyncMock()
    db.execute = AsyncMock(return_value=mock_result)
    return db


def _build_app(
    valkey_session: str | None = None,
) -> tuple[FastAPI, AsyncMock, AsyncMock]:
    app = FastAPI()
    app.include_router(team_health_module.router, prefix="/api/v1")

    mock_db = _make_mock_db()
    mock_valkey = AsyncMock()
    mock_valkey.get = AsyncMock(return_value=valkey_session)

    async def override_db() -> AsyncGenerator[AsyncMock, None]:
        yield mock_db

    async def override_valkey() -> AsyncGenerator[AsyncMock, None]:
        yield mock_valkey

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_valkey] = override_valkey

    return app, mock_db, mock_valkey


# ─── Unauthenticated requests ─────────────────────────────────────────────────


class TestUnauthenticated:
    """All endpoints should return 401 when no auth cookie is present."""

    def test_bus_factor_without_auth_returns_401(self) -> None:
        app, _, _ = _build_app(valkey_session=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/team-health/bus-factor")
        assert resp.status_code == 401

    def test_engagement_without_auth_returns_401(self) -> None:
        app, _, _ = _build_app(valkey_session=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/team-health/engagement")
        assert resp.status_code == 401

    def test_policy_violations_without_auth_returns_401(self) -> None:
        app, _, _ = _build_app(valkey_session=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/team-health/policy-violations")
        assert resp.status_code == 401

    def test_knowledge_concentration_without_auth_returns_401(self) -> None:
        app, _, _ = _build_app(valkey_session=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/team-health/knowledge-concentration")
        assert resp.status_code == 401

    def test_summary_without_auth_returns_401(self) -> None:
        app, _, _ = _build_app(valkey_session=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/team-health/summary")
        assert resp.status_code == 401


# ─── RBAC enforcement ─────────────────────────────────────────────────────────


class TestRbacEnforcement:
    """403 when user has no org access."""

    def test_bus_factor_returns_403_when_no_orgs(self) -> None:
        token = _make_jwt(jti="noorgs-bf")
        session = _make_session(orgs=["my-org"])
        app, _, _ = _build_app(valkey_session=session)

        with patch(_RBAC_PATCH, AsyncMock(return_value=[])):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get(
                "/api/v1/team-health/bus-factor",
                cookies={"access_token": token},
            )
        assert resp.status_code == 403

    def test_summary_returns_403_when_no_orgs(self) -> None:
        token = _make_jwt(jti="noorgs-sum")
        session = _make_session(orgs=["my-org"])
        app, _, _ = _build_app(valkey_session=session)

        with patch(_RBAC_PATCH, AsyncMock(return_value=[])):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get(
                "/api/v1/team-health/summary",
                cookies={"access_token": token},
            )
        assert resp.status_code == 403


# ─── Authenticated requests ───────────────────────────────────────────────────


class TestBusFactor:
    """Test the bus-factor endpoint with mocked DB."""

    def test_bus_factor_returns_200_with_empty_data(self) -> None:
        session = _make_session()
        app, _, _ = _build_app(valkey_session=session)
        token = _make_jwt()

        with patch(_RBAC_PATCH, AsyncMock(return_value=["my-org"])):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get(
                "/api/v1/team-health/bus-factor",
                cookies={"access_token": token},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert "repos" in body
        assert "lookback_days" in body
        assert isinstance(body["repos"], list)

    def test_bus_factor_accepts_lookback_days_param(self) -> None:
        session = _make_session()
        app, _, _ = _build_app(valkey_session=session)
        token = _make_jwt()

        with patch(_RBAC_PATCH, AsyncMock(return_value=["my-org"])):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get(
                "/api/v1/team-health/bus-factor?lookback_days=30",
                cookies={"access_token": token},
            )
        assert resp.status_code == 200
        assert resp.json()["lookback_days"] == 30


class TestEngagement:
    """Test the engagement endpoint."""

    def test_engagement_returns_200_with_structure(self) -> None:
        session = _make_session()
        app, _, _ = _build_app(valkey_session=session)
        token = _make_jwt()

        with patch(_RBAC_PATCH, AsyncMock(return_value=["my-org"])):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get(
                "/api/v1/team-health/engagement",
                cookies={"access_token": token},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert "tiers" in body
        assert "counts" in body
        assert "total_developers" in body
        assert "active_pct" in body
        assert "trend" in body
        assert "lookback_days" in body
        # All tier keys present
        for tier in ("active", "regular", "occasional", "dormant"):
            assert tier in body["tiers"]
            assert tier in body["counts"]


class TestPolicyViolations:
    """Test the policy-violations endpoint."""

    def test_policy_violations_returns_200(self) -> None:
        session = _make_session()
        app, _, _ = _build_app(valkey_session=session)
        token = _make_jwt()

        with patch(_RBAC_PATCH, AsyncMock(return_value=["my-org"])):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get(
                "/api/v1/team-health/policy-violations",
                cookies={"access_token": token},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert "violations" in body
        assert "current_count" in body
        assert "previous_count" in body
        assert "trend_direction" in body
        assert "lookback_days" in body


class TestKnowledgeConcentration:
    """Test the knowledge-concentration endpoint."""

    def test_knowledge_concentration_returns_200(self) -> None:
        session = _make_session()
        app, _, _ = _build_app(valkey_session=session)
        token = _make_jwt()

        with patch(_RBAC_PATCH, AsyncMock(return_value=["my-org"])):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get(
                "/api/v1/team-health/knowledge-concentration",
                cookies={"access_token": token},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert "risks" in body
        assert "lookback_days" in body
        assert isinstance(body["risks"], list)


class TestSummary:
    """Test the summary endpoint."""

    def test_summary_returns_200_with_all_fields(self) -> None:
        session = _make_session()
        app, _, _ = _build_app(valkey_session=session)
        token = _make_jwt()

        with patch(_RBAC_PATCH, AsyncMock(return_value=["my-org"])):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get(
                "/api/v1/team-health/summary",
                cookies={"access_token": token},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert "bus_factor_score" in body
        assert "active_contributors_pct" in body
        assert "total_developers" in body
        assert "dormant_developers" in body
        assert "policy_violations_count" in body
        assert "policy_violations_trend" in body
        assert "knowledge_concentration_risk" in body
        assert "engagement_counts" in body


# ─── Service-level unit tests ─────────────────────────────────────────────────


class TestServiceBusFactorComputation:
    """Test bus factor computation logic with mocked query results."""

    def test_bus_factor_with_single_contributor_is_critical(self) -> None:
        """A repo with only 1 contributor should have bus_factor=1 (critical)."""
        session = _make_session()
        app, mock_db, _ = _build_app(valkey_session=session)

        # Simulate a repo with 1 contributor at 100%
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            ("my-org/repo-a", 1, ["alice"], [100.0]),
        ]
        mock_db.execute = AsyncMock(return_value=mock_result)

        token = _make_jwt()
        with patch(_RBAC_PATCH, AsyncMock(return_value=["my-org"])):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get(
                "/api/v1/team-health/bus-factor",
                cookies={"access_token": token},
            )
        assert resp.status_code == 200
        repos = resp.json()["repos"]
        assert len(repos) == 1
        assert repos[0]["bus_factor"] == 1
        assert repos[0]["risk_level"] == "critical"
        assert repos[0]["top_contributors"][0]["login"] == "alice"

    def test_bus_factor_with_many_contributors_is_low_risk(self) -> None:
        """A repo with 4+ significant contributors should be low risk."""
        session = _make_session()
        app, mock_db, _ = _build_app(valkey_session=session)

        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            (
                "my-org/repo-b",
                4,
                ["alice", "bob", "carol", "dave"],
                [30.0, 28.0, 22.0, 20.0],
            ),
        ]
        mock_db.execute = AsyncMock(return_value=mock_result)

        token = _make_jwt()
        with patch(_RBAC_PATCH, AsyncMock(return_value=["my-org"])):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get(
                "/api/v1/team-health/bus-factor",
                cookies={"access_token": token},
            )
        assert resp.status_code == 200
        repos = resp.json()["repos"]
        assert len(repos) == 1
        assert repos[0]["bus_factor"] == 4
        assert repos[0]["risk_level"] == "low"


class TestServicePolicyViolationsFiltering:
    """Test that git.push events are only flagged when force=true."""

    def test_non_force_push_is_not_a_violation(self) -> None:
        session = _make_session()
        app, mock_db, _ = _build_app(valkey_session=session)

        now = datetime.now(UTC)
        # First call: violations query; second call: previous count
        violation_result = MagicMock()
        violation_result.fetchall.return_value = [
            ("git.push", "alice", "my-org/repo-a", "my-org", now, {"force": False}),
        ]
        prev_result = MagicMock()
        prev_result.scalar.return_value = 0

        mock_db.execute = AsyncMock(side_effect=[violation_result, prev_result])

        token = _make_jwt()
        with patch(_RBAC_PATCH, AsyncMock(return_value=["my-org"])):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get(
                "/api/v1/team-health/policy-violations",
                cookies={"access_token": token},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["current_count"] == 0
        assert len(body["violations"]) == 0

    def test_force_push_is_a_violation(self) -> None:
        session = _make_session()
        app, mock_db, _ = _build_app(valkey_session=session)

        now = datetime.now(UTC)
        violation_result = MagicMock()
        violation_result.fetchall.return_value = [
            ("git.push", "alice", "my-org/repo-a", "my-org", now, {"force": True}),
        ]
        prev_result = MagicMock()
        prev_result.scalar.return_value = 1

        mock_db.execute = AsyncMock(side_effect=[violation_result, prev_result])

        token = _make_jwt()
        with patch(_RBAC_PATCH, AsyncMock(return_value=["my-org"])):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get(
                "/api/v1/team-health/policy-violations",
                cookies={"access_token": token},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["current_count"] == 1
        assert body["violations"][0]["type"] == "force_push_default_branch"
        assert body["violations"][0]["severity"] == "high"


class TestServiceEngagementTiers:
    """Test engagement tier classification."""

    def test_engagement_tiers_classification(self) -> None:
        session = _make_session()
        app, mock_db, _ = _build_app(valkey_session=session)

        now = datetime.now(UTC)
        # First call: engagement query; second call: trend query
        engagement_result = MagicMock()
        engagement_result.fetchall.return_value = [
            ("alice", now - timedelta(days=2), 15),  # Active
            ("bob", now - timedelta(days=10), 8),  # Regular
            ("carol", now - timedelta(days=20), 3),  # Occasional
            ("dave", now - timedelta(days=45), 1),  # Dormant
        ]
        trend_result = MagicMock()
        trend_result.fetchall.return_value = []

        mock_db.execute = AsyncMock(side_effect=[engagement_result, trend_result])

        token = _make_jwt()
        with patch(_RBAC_PATCH, AsyncMock(return_value=["my-org"])):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get(
                "/api/v1/team-health/engagement",
                cookies={"access_token": token},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["counts"]["active"] == 1
        assert body["counts"]["regular"] == 1
        assert body["counts"]["occasional"] == 1
        assert body["counts"]["dormant"] == 1
        assert body["total_developers"] == 4
        assert body["active_pct"] == 25.0


class TestServiceKnowledgeConcentration:
    """Test knowledge concentration risk detection."""

    def test_high_concentration_detected(self) -> None:
        session = _make_session()
        app, mock_db, _ = _build_app(valkey_session=session)

        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            ("my-org/critical-repo", "alice", 85.0, 100),
        ]
        mock_db.execute = AsyncMock(return_value=mock_result)

        token = _make_jwt()
        with patch(_RBAC_PATCH, AsyncMock(return_value=["my-org"])):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get(
                "/api/v1/team-health/knowledge-concentration",
                cookies={"access_token": token},
            )
        assert resp.status_code == 200
        risks = resp.json()["risks"]
        assert len(risks) == 1
        assert risks[0]["risk_level"] == "high"
        assert risks[0]["top_actor"] == "alice"
        assert risks[0]["concentration_pct"] == 85.0
        assert "recommendation" in risks[0]
