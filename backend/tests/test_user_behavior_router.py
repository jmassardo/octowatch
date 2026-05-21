"""Tests for the user_behavior router.

Tests cover:
- Unauthenticated requests → 401
- Authenticated requests return 200 with correct schema
- RBAC scope enforcement (403 when no orgs)
- Risk summary endpoint
- Risky users endpoint with filtering
- Anomalies endpoint
- Permission drift endpoint
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps import get_db, get_valkey
from app.routers import user_behavior as ub_module

SECRET = "testsecretkey_for_unit_tests_only_32ch"


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_jwt(sub: str = "testuser", jti: str = "ub-jti") -> str:
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
    scope_type: str = "scoped",
) -> str:
    return json.dumps(
        {
            "github_login": "testuser",
            "github_id": 12345,
            "roles": roles or ["analyst"],
            "scoped_orgs": orgs or ["my-org"],
            "scoped_repos": [],
            "scope_type": scope_type,
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
    app.include_router(ub_module.router, prefix="/api/v1")

    mock_db = _make_mock_db()
    mock_valkey = AsyncMock()
    mock_valkey.get = AsyncMock(return_value=valkey_session)
    mock_valkey.exists = AsyncMock(return_value=1 if valkey_session else 0)

    async def override_db():
        yield mock_db

    async def override_valkey():
        return mock_valkey

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_valkey] = override_valkey

    return app, mock_db, mock_valkey


# ─── Tests ────────────────────────────────────────────────────────────────────


class TestRiskSummaryEndpoint:
    """Tests for GET /user-behavior/risk-summary."""

    def test_unauthenticated_returns_401(self) -> None:
        app, _, _ = _build_app()
        client = TestClient(app)
        resp = client.get("/api/v1/user-behavior/risk-summary")
        assert resp.status_code == 401

    @patch("app.services.rbac_service.get_scoped_orgs", new_callable=AsyncMock)
    @patch(
        "app.services.user_behavior_service.get_risk_summary",
        new_callable=AsyncMock,
    )
    def test_authenticated_returns_200(
        self,
        mock_get_summary: AsyncMock,
        mock_scoped_orgs: AsyncMock,
    ) -> None:
        session_data = _make_session()
        app, _, _ = _build_app(valkey_session=session_data)
        client = TestClient(app)

        mock_scoped_orgs.return_value = ["my-org"]
        mock_get_summary.return_value = {
            "total_users_with_signals": 5,
            "high_risk_count": 1,
            "medium_risk_count": 2,
            "low_risk_count": 2,
            "anomaly_count": 1,
            "top_categories": [],
            "lookback_days": 30,
        }

        token = _make_jwt()
        resp = client.get(
            "/api/v1/user-behavior/risk-summary",
            cookies={"access_token": token},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_users_with_signals"] == 5
        assert data["high_risk_count"] == 1
        assert "top_categories" in data

    @patch("app.services.rbac_service.get_scoped_orgs", new_callable=AsyncMock)
    def test_no_orgs_scoped_user_returns_403(
        self,
        mock_scoped_orgs: AsyncMock,
    ) -> None:
        session_data = _make_session(orgs=[], scope_type="scoped")
        app, _, _ = _build_app(valkey_session=session_data)
        client = TestClient(app)

        mock_scoped_orgs.return_value = []

        token = _make_jwt()
        resp = client.get(
            "/api/v1/user-behavior/risk-summary",
            cookies={"access_token": token},
        )
        assert resp.status_code == 403

    @patch("app.services.rbac_service.get_scoped_orgs", new_callable=AsyncMock)
    @patch(
        "app.services.user_behavior_service.get_risk_summary",
        new_callable=AsyncMock,
    )
    def test_lookback_days_parameter(
        self,
        mock_get_summary: AsyncMock,
        mock_scoped_orgs: AsyncMock,
    ) -> None:
        session_data = _make_session()
        app, _, _ = _build_app(valkey_session=session_data)
        client = TestClient(app)

        mock_scoped_orgs.return_value = ["my-org"]
        mock_get_summary.return_value = {
            "total_users_with_signals": 0,
            "high_risk_count": 0,
            "medium_risk_count": 0,
            "low_risk_count": 0,
            "anomaly_count": 0,
            "top_categories": [],
            "lookback_days": 7,
        }

        token = _make_jwt()
        resp = client.get(
            "/api/v1/user-behavior/risk-summary?lookback_days=7",
            cookies={"access_token": token},
        )

        assert resp.status_code == 200
        assert resp.json()["lookback_days"] == 7


class TestRiskyUsersEndpoint:
    """Tests for GET /user-behavior/risky-users."""

    def test_unauthenticated_returns_401(self) -> None:
        app, _, _ = _build_app()
        client = TestClient(app)
        resp = client.get("/api/v1/user-behavior/risky-users")
        assert resp.status_code == 401

    @patch("app.services.rbac_service.get_scoped_orgs", new_callable=AsyncMock)
    @patch(
        "app.services.user_behavior_service.get_risky_users",
        new_callable=AsyncMock,
    )
    def test_authenticated_returns_paginated_users(
        self,
        mock_get_users: AsyncMock,
        mock_scoped_orgs: AsyncMock,
    ) -> None:
        session_data = _make_session()
        app, _, _ = _build_app(valkey_session=session_data)
        client = TestClient(app)

        mock_scoped_orgs.return_value = ["my-org"]
        mock_get_users.return_value = {
            "users": [
                {
                    "user_login": "risky-admin",
                    "risk_score": 22,
                    "risk_level": "high",
                    "signals": [],
                    "category_breakdown": [],
                    "orgs": ["my-org"],
                    "last_risky_action_at": None,
                }
            ],
            "total": 1,
            "page": 1,
            "page_size": 50,
        }

        token = _make_jwt()
        resp = client.get(
            "/api/v1/user-behavior/risky-users",
            cookies={"access_token": token},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["users"][0]["user_login"] == "risky-admin"
        assert data["users"][0]["risk_level"] == "high"

    @patch("app.services.rbac_service.get_scoped_orgs", new_callable=AsyncMock)
    @patch(
        "app.services.user_behavior_service.get_risky_users",
        new_callable=AsyncMock,
    )
    def test_risk_level_filter(
        self,
        mock_get_users: AsyncMock,
        mock_scoped_orgs: AsyncMock,
    ) -> None:
        session_data = _make_session()
        app, _, _ = _build_app(valkey_session=session_data)
        client = TestClient(app)

        mock_scoped_orgs.return_value = ["my-org"]
        mock_get_users.return_value = {
            "users": [],
            "total": 0,
            "page": 1,
            "page_size": 50,
        }

        token = _make_jwt()
        resp = client.get(
            "/api/v1/user-behavior/risky-users?risk_level=high",
            cookies={"access_token": token},
        )

        assert resp.status_code == 200


class TestAnomaliesEndpoint:
    """Tests for GET /user-behavior/anomalies."""

    def test_unauthenticated_returns_401(self) -> None:
        app, _, _ = _build_app()
        client = TestClient(app)
        resp = client.get("/api/v1/user-behavior/anomalies")
        assert resp.status_code == 401

    @patch("app.services.rbac_service.get_scoped_orgs", new_callable=AsyncMock)
    @patch(
        "app.services.user_behavior_service.get_anomalous_users",
        new_callable=AsyncMock,
    )
    def test_authenticated_returns_anomalies(
        self,
        mock_get_anomalies: AsyncMock,
        mock_scoped_orgs: AsyncMock,
    ) -> None:
        session_data = _make_session()
        app, _, _ = _build_app(valkey_session=session_data)
        client = TestClient(app)

        mock_scoped_orgs.return_value = ["my-org"]
        mock_get_anomalies.return_value = {
            "anomalies": [
                {
                    "user_login": "spike-user",
                    "recent_event_count": 500,
                    "baseline_daily_avg": 10,
                    "activity_ratio": 3.5,
                    "recent_action_types": 20,
                    "baseline_action_types": 8,
                    "recent_ips": 5,
                    "baseline_ips": 2,
                    "deviation_reasons": ["Activity volume 3.5x above baseline"],
                }
            ],
            "lookback_days": 30,
        }

        token = _make_jwt()
        resp = client.get(
            "/api/v1/user-behavior/anomalies",
            cookies={"access_token": token},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["anomalies"]) == 1
        assert data["anomalies"][0]["user_login"] == "spike-user"
        assert data["anomalies"][0]["activity_ratio"] == 3.5

    @patch("app.services.rbac_service.get_scoped_orgs", new_callable=AsyncMock)
    @patch(
        "app.services.user_behavior_service.get_anomalous_users",
        new_callable=AsyncMock,
    )
    def test_threshold_parameter(
        self,
        mock_get_anomalies: AsyncMock,
        mock_scoped_orgs: AsyncMock,
    ) -> None:
        session_data = _make_session()
        app, _, _ = _build_app(valkey_session=session_data)
        client = TestClient(app)

        mock_scoped_orgs.return_value = ["my-org"]
        mock_get_anomalies.return_value = {"anomalies": [], "lookback_days": 30}

        token = _make_jwt()
        resp = client.get(
            "/api/v1/user-behavior/anomalies?threshold=3.0",
            cookies={"access_token": token},
        )

        assert resp.status_code == 200


class TestPermissionDriftEndpoint:
    """Tests for GET /user-behavior/permission-drift."""

    def test_unauthenticated_returns_401(self) -> None:
        app, _, _ = _build_app()
        client = TestClient(app)
        resp = client.get("/api/v1/user-behavior/permission-drift")
        assert resp.status_code == 401

    @patch("app.services.rbac_service.get_scoped_orgs", new_callable=AsyncMock)
    @patch(
        "app.services.user_behavior_service.get_permission_drift",
        new_callable=AsyncMock,
    )
    def test_authenticated_returns_permission_drift(
        self,
        mock_get_drift: AsyncMock,
        mock_scoped_orgs: AsyncMock,
    ) -> None:
        session_data = _make_session()
        app, _, _ = _build_app(valkey_session=session_data)
        client = TestClient(app)

        mock_scoped_orgs.return_value = ["my-org"]
        mock_get_drift.return_value = {
            "users": [
                {
                    "user_login": "over-privileged",
                    "total_events": 15,
                    "admin_events": 12,
                    "dev_events": 2,
                    "admin_pct": 80.0,
                    "last_active": "2025-01-10T09:00:00+00:00",
                    "status": "review_recommended",
                    "reason": "High admin activity with minimal development",
                }
            ],
            "lookback_days": 90,
        }

        token = _make_jwt()
        resp = client.get(
            "/api/v1/user-behavior/permission-drift",
            cookies={"access_token": token},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["users"]) == 1
        assert data["users"][0]["status"] == "review_recommended"
        assert data["users"][0]["admin_pct"] == 80.0
