"""Integration tests for the rules router.

Tests cover:
- GET /rules → 200 (requires any authenticated role)
- POST /rules → 201 for rule_author
- POST /rules → 403 for analyst (insufficient permissions)
- GET /rules/:id → 200 / 404
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps import get_db, get_valkey
from app.routers import rules as rules_router_module

SECRET = "testsecretkey_for_unit_tests_only_32ch"


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_jwt(sub: str = "testuser", jti: str = "rules-jti") -> str:
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
    mock_result.scalar_one_or_none.return_value = None
    db = AsyncMock()
    db.execute = AsyncMock(return_value=mock_result)
    # session.add() is synchronous in SQLAlchemy — use MagicMock to avoid
    # the "coroutine was never awaited" RuntimeWarning from AsyncMock.
    db.add = MagicMock()
    return db


@dataclass
class FakeRuleModel:
    """Fake rule model object compatible with RuleResponse.model_validate(from_attributes=True)."""

    id: int = 1
    name: str = "Test Rule"
    slug: str = "test-rule"
    description: str | None = None
    category: str = "other"
    default_severity: str = "medium"
    default_confidence: str = "medium"
    logic_type: str = "threshold"
    logic_config: dict[str, Any] = field(
        default_factory=lambda: {"action_filters": ["repos.create"], "threshold": 5}
    )
    enabled: bool = True
    status: str = "draft"
    version: int = 1
    git_commit_sha: str | None = None
    created_by: str = "testuser"
    updated_by: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


VALID_RULE_PAYLOAD: dict[str, Any] = {
    "name": "Test Detection Rule",
    "slug": "test-detection-rule",
    "description": "A test detection rule",
    "category": "other",
    "default_severity": "medium",
    "default_confidence": "medium",
    "logic_type": "threshold",
    "logic_config": {
        "action_filters": ["repos.create"],
        "threshold": 5,
        "time_window_minutes": 60,
        "aggregation_key": "actor",
    },
    "enabled": True,
    "status": "draft",
}


def _build_rules_app(valkey_session: str | None = None) -> tuple[FastAPI, AsyncMock, AsyncMock]:
    app = FastAPI()
    app.include_router(rules_router_module.router, prefix="/api/v1")

    mock_db = _make_mock_db()
    mock_valkey = AsyncMock()
    mock_valkey.get = AsyncMock(return_value=valkey_session)

    async def override_db():
        yield mock_db

    async def override_valkey():
        yield mock_valkey

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_valkey] = override_valkey

    return app, mock_db, mock_valkey


# ─── Unauthenticated ──────────────────────────────────────────────────────────


class TestRulesUnauthenticated:
    def test_list_rules_without_auth_returns_401(self):
        app, _, _ = _build_rules_app(valkey_session=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/rules")
        assert resp.status_code == 401

    def test_create_rule_without_auth_returns_401(self):
        app, _, _ = _build_rules_app(valkey_session=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/v1/rules",
            json=VALID_RULE_PAYLOAD,
            cookies={"csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert resp.status_code == 401


# ─── List rules ───────────────────────────────────────────────────────────────


class TestListRules:
    def test_analyst_can_list_rules(self):
        token = _make_jwt()
        app, _, _ = _build_rules_app(valkey_session=_make_session(roles=["analyst"]))
        with patch(
            "app.routers.rules.rule_service.list_rules",
            AsyncMock(return_value=([], 0)),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get("/api/v1/rules", cookies={"access_token": token})
        assert resp.status_code == 200

    def test_list_rules_returns_paginated_response(self):
        token = _make_jwt()
        app, _, _ = _build_rules_app(valkey_session=_make_session(roles=["analyst"]))
        fake_rule = FakeRuleModel()
        with patch(
            "app.routers.rules.rule_service.list_rules",
            AsyncMock(return_value=([fake_rule], 1)),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get("/api/v1/rules", cookies={"access_token": token})
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["name"] == "Test Rule"

    def test_list_rules_returns_correct_schema_keys(self):
        token = _make_jwt()
        app, _, _ = _build_rules_app(valkey_session=_make_session(roles=["analyst"]))
        with patch(
            "app.routers.rules.rule_service.list_rules",
            AsyncMock(return_value=([], 0)),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get("/api/v1/rules", cookies={"access_token": token})
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data

    def test_list_rules_respects_limit_param(self):
        token = _make_jwt()
        app, _, _ = _build_rules_app(valkey_session=_make_session(roles=["analyst"]))
        with patch(
            "app.routers.rules.rule_service.list_rules",
            AsyncMock(return_value=([], 0)),
        ) as mock_list:
            client = TestClient(app, raise_server_exceptions=True)
            client.get("/api/v1/rules?limit=10", cookies={"access_token": token})
        # Verify limit was passed to the service
        call_kwargs = mock_list.call_args.kwargs
        assert call_kwargs.get("limit") == 10


# ─── Create rule ──────────────────────────────────────────────────────────────


class TestCreateRule:
    def test_rule_author_can_create_rule(self):
        token = _make_jwt()
        app, _, _ = _build_rules_app(valkey_session=_make_session(roles=["rule_author"]))
        fake_rule = FakeRuleModel()
        with patch(
            "app.routers.rules.rule_service.get_rule_by_slug",
            AsyncMock(return_value=None),
        ):
            with patch(
                "app.routers.rules.rule_service.create_rule",
                AsyncMock(return_value=fake_rule),
            ):
                client = TestClient(app, raise_server_exceptions=True)
                resp = client.post(
                    "/api/v1/rules",
                    json=VALID_RULE_PAYLOAD,
                    cookies={"access_token": token, "csrf_token": "tok"},
                    headers={"X-CSRF-Token": "tok"},
                )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Test Rule"
        assert data["slug"] == "test-rule"

    def test_analyst_cannot_create_rule_gets_403(self):
        """analyst role is not in (rule_author, sys_admin) → 403."""
        token = _make_jwt()
        app, _, _ = _build_rules_app(valkey_session=_make_session(roles=["analyst"]))
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/v1/rules",
            json=VALID_RULE_PAYLOAD,
            cookies={"access_token": token, "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert resp.status_code == 403

    def test_report_admin_cannot_create_rule_gets_403(self):
        token = _make_jwt()
        app, _, _ = _build_rules_app(valkey_session=_make_session(roles=["report_admin"]))
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/v1/rules",
            json=VALID_RULE_PAYLOAD,
            cookies={"access_token": token, "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert resp.status_code == 403

    def test_sys_admin_can_create_rule(self):
        token = _make_jwt()
        app, _, _ = _build_rules_app(valkey_session=_make_session(roles=["sys_admin"]))
        fake_rule = FakeRuleModel()
        with patch(
            "app.routers.rules.rule_service.get_rule_by_slug",
            AsyncMock(return_value=None),
        ):
            with patch(
                "app.routers.rules.rule_service.create_rule",
                AsyncMock(return_value=fake_rule),
            ):
                client = TestClient(app, raise_server_exceptions=True)
                resp = client.post(
                    "/api/v1/rules",
                    json=VALID_RULE_PAYLOAD,
                    cookies={"access_token": token, "csrf_token": "tok"},
                    headers={"X-CSRF-Token": "tok"},
                )
        assert resp.status_code == 201

    def test_duplicate_slug_returns_409(self):
        token = _make_jwt()
        app, _, _ = _build_rules_app(valkey_session=_make_session(roles=["rule_author"]))
        # Slug already exists → should return 409
        with patch(
            "app.routers.rules.rule_service.get_rule_by_slug",
            AsyncMock(return_value=FakeRuleModel()),  # Returns existing rule
        ):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post(
                "/api/v1/rules",
                json=VALID_RULE_PAYLOAD,
                cookies={"access_token": token, "csrf_token": "tok"},
                headers={"X-CSRF-Token": "tok"},
            )
        assert resp.status_code == 409

    def test_invalid_rule_payload_returns_422(self):
        token = _make_jwt()
        app, _, _ = _build_rules_app(valkey_session=_make_session(roles=["rule_author"]))
        client = TestClient(app, raise_server_exceptions=False)
        bad_payload = {
            "name": "Bad Rule",
            "slug": "INVALID SLUG WITH SPACES",  # violates ^[a-z0-9-]+$
            "category": "other",
            "default_severity": "medium",
            "default_confidence": "medium",
            "logic_type": "threshold",
            "logic_config": {},
        }
        resp = client.post(
            "/api/v1/rules",
            json=bad_payload,
            cookies={"access_token": token, "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert resp.status_code == 422

    def test_invalid_distinct_count_field_returns_422(self):
        """§1.7: Creating a rule with invalid distinct_count_field → 422."""
        token = _make_jwt()
        app, _, _ = _build_rules_app(valkey_session=_make_session(roles=["rule_author"]))
        client = TestClient(app, raise_server_exceptions=False)
        payload = {
            **VALID_RULE_PAYLOAD,
            "slug": "test-distinct-bad",
            "logic_config": {
                **VALID_RULE_PAYLOAD["logic_config"],
                "distinct_count_field": "password_hash",
            },
        }
        resp = client.post(
            "/api/v1/rules",
            json=payload,
            cookies={"access_token": token, "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert resp.status_code == 422
        assert "distinct_count_field" in resp.json()["detail"]
        assert "password_hash" in resp.json()["detail"]

    def test_valid_distinct_count_field_accepted(self):
        """§1.7: Creating a rule with valid distinct_count_field → proceeds normally."""
        token = _make_jwt()
        app, _, _ = _build_rules_app(valkey_session=_make_session(roles=["rule_author"]))
        fake_rule = FakeRuleModel()
        payload = {
            **VALID_RULE_PAYLOAD,
            "slug": "test-distinct-good",
            "logic_config": {
                **VALID_RULE_PAYLOAD["logic_config"],
                "distinct_count_field": "repo",
            },
        }
        with patch(
            "app.routers.rules.rule_service.get_rule_by_slug",
            AsyncMock(return_value=None),
        ):
            with patch(
                "app.routers.rules.rule_service.create_rule",
                AsyncMock(return_value=fake_rule),
            ):
                client = TestClient(app, raise_server_exceptions=True)
                resp = client.post(
                    "/api/v1/rules",
                    json=payload,
                    cookies={"access_token": token, "csrf_token": "tok"},
                    headers={"X-CSRF-Token": "tok"},
                )
        assert resp.status_code == 201


# ─── Update rule validation ──────────────────────────────────────────────────


class TestUpdateRuleValidation:
    """Tests for distinct_count_field validation on PUT /rules/{id} (§1.7)."""

    def test_update_invalid_distinct_count_field_returns_422(self):
        token = _make_jwt()
        app, _, _ = _build_rules_app(valkey_session=_make_session(roles=["rule_author"]))
        client = TestClient(app, raise_server_exceptions=False)
        payload = {
            **VALID_RULE_PAYLOAD,
            "logic_config": {
                **VALID_RULE_PAYLOAD["logic_config"],
                "distinct_count_field": "secret_key",
            },
        }
        resp = client.put(
            "/api/v1/rules/1",
            json=payload,
            cookies={"access_token": token, "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert resp.status_code == 422
        assert "distinct_count_field" in resp.json()["detail"]

    def test_update_valid_distinct_count_field_proceeds(self):
        token = _make_jwt()
        app, _, _ = _build_rules_app(valkey_session=_make_session(roles=["rule_author"]))
        fake_rule = FakeRuleModel()
        payload = {
            **VALID_RULE_PAYLOAD,
            "logic_config": {
                **VALID_RULE_PAYLOAD["logic_config"],
                "distinct_count_field": "action",
            },
        }
        with patch(
            "app.routers.rules.rule_service.get_rule_by_id",
            AsyncMock(return_value=fake_rule),
        ):
            with patch(
                "app.routers.rules.rule_service.update_rule",
                AsyncMock(return_value=fake_rule),
            ):
                with patch(
                    "app.routers.rules.invalidate_rule_cache",
                    AsyncMock(),
                ):
                    client = TestClient(app, raise_server_exceptions=True)
                    resp = client.put(
                        "/api/v1/rules/1",
                        json=payload,
                        cookies={"access_token": token, "csrf_token": "tok"},
                        headers={"X-CSRF-Token": "tok"},
                    )
        assert resp.status_code == 200


# ─── Get single rule ─────────────────────────────────────────────────────────


class TestGetRule:
    def test_get_rule_by_id_returns_200(self):
        token = _make_jwt()
        app, _, _ = _build_rules_app(valkey_session=_make_session(roles=["analyst"]))
        fake_rule = FakeRuleModel()
        with patch(
            "app.routers.rules.rule_service.get_rule_by_id",
            AsyncMock(return_value=fake_rule),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get("/api/v1/rules/1", cookies={"access_token": token})
        assert resp.status_code == 200
        assert resp.json()["id"] == 1

    def test_get_nonexistent_rule_returns_404(self):
        token = _make_jwt()
        app, _, _ = _build_rules_app(valkey_session=_make_session(roles=["analyst"]))
        with patch(
            "app.routers.rules.rule_service.get_rule_by_id",
            AsyncMock(return_value=None),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/api/v1/rules/9999", cookies={"access_token": token})
        assert resp.status_code == 404
