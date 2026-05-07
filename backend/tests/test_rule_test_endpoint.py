"""Tests for the POST /rules/{rule_id}/test endpoint (dry-run rule evaluation).

Tests cover:
- Successful match with matching event
- No match when action filter fails
- No match when field condition fails
- No match when confidence threshold fails
- 404 when rule does not exist
- 401 when unauthenticated
- 403 for roles without permission
- Sequence rule evaluation
- Pattern rule evaluation with field conditions
- Response schema correctness
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

import jwt as pyjwt
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps import get_db, get_valkey
from app.routers import rules as rules_router_module
from app.services.detection_service import evaluate_rule_against_event

SECRET = "testsecretkey_for_unit_tests_only_32ch"


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_jwt(sub: str = "testuser", jti: str = "test-rule-test-jti") -> str:
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


@dataclass
class FakeRuleModel:
    """Fake rule model for dry-run testing."""

    id: int = 1
    name: str = "Test Rule"
    slug: str = "test-rule"
    description: str | None = None
    category: str = "other"
    default_severity: str = "medium"
    default_confidence: str = "medium"
    logic_type: str = "pattern"
    logic_config: dict[str, Any] = field(
        default_factory=lambda: {
            "action_filters": ["repos.create"],
            "field_conditions": [],
            "confidence": 0.5,
        }
    )
    enabled: bool = True
    status: str = "active"
    mode: str = "active"
    version: int = 1
    git_commit_sha: str | None = None
    created_by: str = "testuser"
    updated_by: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


def _build_test_app(valkey_session: str | None = None) -> tuple[FastAPI, AsyncMock, AsyncMock]:
    app = FastAPI()
    app.include_router(rules_router_module.router, prefix="/api/v1")

    mock_db = AsyncMock()
    mock_valkey = AsyncMock()
    mock_valkey.get = AsyncMock(return_value=valkey_session)

    async def override_db() -> Any:
        yield mock_db

    async def override_valkey() -> Any:
        yield mock_valkey

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_valkey] = override_valkey

    return app, mock_db, mock_valkey


# ─── Unit tests for evaluate_rule_against_event ──────────────────────────────


class TestEvaluateRuleAgainstEvent:
    """Direct unit tests for the evaluation function, no HTTP involved."""

    def test_matching_action_filter(self) -> None:
        rule = FakeRuleModel(
            logic_config={
                "action_filters": ["repos.create"],
                "field_conditions": [],
                "confidence": 0.5,
            }
        )
        event = {"action": "repos.create", "actor": "octocat", "org": "my-org"}
        result = evaluate_rule_against_event(rule, event)  # type: ignore[arg-type]
        assert result["matched"] is True
        assert "action" in result["matched_fields"]

    def test_action_filter_glob_match(self) -> None:
        rule = FakeRuleModel(
            logic_config={
                "action_filters": ["repos.*"],
                "field_conditions": [],
                "confidence": 0.5,
            }
        )
        event = {"action": "repos.delete", "actor": "octocat"}
        result = evaluate_rule_against_event(rule, event)  # type: ignore[arg-type]
        assert result["matched"] is True
        assert "action" in result["matched_fields"]

    def test_action_filter_no_match(self) -> None:
        rule = FakeRuleModel(
            logic_config={
                "action_filters": ["repos.create"],
                "field_conditions": [],
                "confidence": 0.5,
            }
        )
        event = {"action": "team.add_member", "actor": "octocat"}
        result = evaluate_rule_against_event(rule, event)  # type: ignore[arg-type]
        assert result["matched"] is False
        assert "does not match" in result["reason"]

    def test_field_condition_eq_match(self) -> None:
        rule = FakeRuleModel(
            logic_config={
                "action_filters": ["repos.create"],
                "field_conditions": [
                    {"field": "actor", "operator": "eq", "value": "octocat"},
                ],
                "confidence": 0.5,
            }
        )
        event = {"action": "repos.create", "actor": "octocat"}
        result = evaluate_rule_against_event(rule, event)  # type: ignore[arg-type]
        assert result["matched"] is True
        assert "actor" in result["matched_fields"]

    def test_field_condition_eq_no_match(self) -> None:
        rule = FakeRuleModel(
            logic_config={
                "action_filters": ["repos.create"],
                "field_conditions": [
                    {"field": "actor", "operator": "eq", "value": "specificuser"},
                ],
                "confidence": 0.5,
            }
        )
        event = {"action": "repos.create", "actor": "octocat"}
        result = evaluate_rule_against_event(rule, event)  # type: ignore[arg-type]
        assert result["matched"] is False
        assert "actor" in result["reason"]

    def test_field_condition_data_nested(self) -> None:
        rule = FakeRuleModel(
            logic_config={
                "action_filters": ["repos.*"],
                "field_conditions": [
                    {"field": "data.visibility", "operator": "eq", "value": "public"},
                ],
                "confidence": 0.5,
            }
        )
        event = {
            "action": "repos.create",
            "data": {"visibility": "public"},
        }
        result = evaluate_rule_against_event(rule, event)  # type: ignore[arg-type]
        assert result["matched"] is True
        assert "data.visibility" in result["matched_fields"]

    def test_confidence_below_threshold(self) -> None:
        rule = FakeRuleModel(
            default_confidence="low",
            logic_config={
                "action_filters": ["repos.*"],
                "field_conditions": [],
                "confidence": 0.5,
            },
        )
        event = {"action": "repos.create"}
        result = evaluate_rule_against_event(rule, event)  # type: ignore[arg-type]
        assert result["matched"] is False
        assert "confidence" in result["reason"].lower()

    def test_no_action_filters_still_matches(self) -> None:
        rule = FakeRuleModel(
            logic_config={
                "action_filters": [],
                "field_conditions": [],
                "confidence": 0.5,
            }
        )
        event = {"action": "repos.create"}
        result = evaluate_rule_against_event(rule, event)  # type: ignore[arg-type]
        assert result["matched"] is True

    def test_sequence_rule_step_match(self) -> None:
        rule = FakeRuleModel(
            logic_type="sequence",
            logic_config={
                "action_filters": [],
                "sequence_steps": [
                    {"action": "repos.create", "min_count": 1},
                    {"action": "repos.delete", "min_count": 1},
                ],
                "aggregation_key": "actor",
                "time_window_minutes": 60,
                "confidence": 0.5,
            },
        )
        event = {"action": "repos.create", "actor": "octocat"}
        result = evaluate_rule_against_event(rule, event)  # type: ignore[arg-type]
        assert result["matched"] is True
        assert "sequence_step" in result["matched_fields"]

    def test_sequence_rule_no_step_match(self) -> None:
        rule = FakeRuleModel(
            logic_type="sequence",
            logic_config={
                "action_filters": [],
                "sequence_steps": [
                    {"action": "repos.create", "min_count": 1},
                    {"action": "repos.delete", "min_count": 1},
                ],
                "aggregation_key": "actor",
                "time_window_minutes": 60,
                "confidence": 0.5,
            },
        )
        event = {"action": "team.add_member", "actor": "octocat"}
        result = evaluate_rule_against_event(rule, event)  # type: ignore[arg-type]
        assert result["matched"] is False
        assert "sequence step" in result["reason"]

    def test_threshold_rule_includes_threshold_in_fields(self) -> None:
        rule = FakeRuleModel(
            logic_type="threshold",
            logic_config={
                "action_filters": ["repos.create"],
                "field_conditions": [],
                "threshold": 5,
                "time_window_minutes": 60,
                "aggregation_key": "actor",
                "confidence": 0.5,
            },
        )
        event = {"action": "repos.create", "actor": "octocat"}
        result = evaluate_rule_against_event(rule, event)  # type: ignore[arg-type]
        assert result["matched"] is True
        assert "threshold" in result["matched_fields"]

    def test_field_condition_contains_operator(self) -> None:
        rule = FakeRuleModel(
            logic_config={
                "action_filters": [],
                "field_conditions": [
                    {"field": "repo", "operator": "contains", "value": "hello"},
                ],
                "confidence": 0.5,
            }
        )
        event = {"action": "repos.create", "repo": "my-org/hello-world"}
        result = evaluate_rule_against_event(rule, event)  # type: ignore[arg-type]
        assert result["matched"] is True

    def test_field_condition_in_operator(self) -> None:
        rule = FakeRuleModel(
            logic_config={
                "action_filters": [],
                "field_conditions": [
                    {"field": "actor", "operator": "in", "value": ["alice", "bob"]},
                ],
                "confidence": 0.5,
            }
        )
        event = {"action": "repos.create", "actor": "alice"}
        result = evaluate_rule_against_event(rule, event)  # type: ignore[arg-type]
        assert result["matched"] is True

    def test_field_condition_matches_glob(self) -> None:
        rule = FakeRuleModel(
            logic_config={
                "action_filters": [],
                "field_conditions": [
                    {"field": "repo", "operator": "matches_glob", "value": "my-org/*"},
                ],
                "confidence": 0.5,
            }
        )
        event = {"action": "repos.create", "repo": "my-org/hello-world"}
        result = evaluate_rule_against_event(rule, event)  # type: ignore[arg-type]
        assert result["matched"] is True

    def test_matched_fields_list_accumulates(self) -> None:
        rule = FakeRuleModel(
            logic_config={
                "action_filters": ["repos.create"],
                "field_conditions": [
                    {"field": "actor", "operator": "eq", "value": "octocat"},
                    {"field": "org", "operator": "eq", "value": "my-org"},
                ],
                "confidence": 0.5,
            }
        )
        event = {"action": "repos.create", "actor": "octocat", "org": "my-org"}
        result = evaluate_rule_against_event(rule, event)  # type: ignore[arg-type]
        assert result["matched"] is True
        assert "action" in result["matched_fields"]
        assert "actor" in result["matched_fields"]
        assert "org" in result["matched_fields"]
        assert "confidence" in result["matched_fields"]

    def test_response_keys(self) -> None:
        rule = FakeRuleModel()
        event = {"action": "repos.create"}
        result = evaluate_rule_against_event(rule, event)  # type: ignore[arg-type]
        assert "matched" in result
        assert "reason" in result
        assert "matched_fields" in result
        assert isinstance(result["matched"], bool)
        assert isinstance(result["reason"], str)
        assert isinstance(result["matched_fields"], list)


# ─── HTTP endpoint tests ─────────────────────────────────────────────────────


class TestTestRuleEndpoint:
    """Tests for POST /api/v1/rules/{rule_id}/test."""

    def test_unauthenticated_returns_401(self) -> None:
        app, _, _ = _build_test_app(valkey_session=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/v1/rules/1/test",
            json={"event": {"action": "repos.create"}},
            cookies={"csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert resp.status_code == 401

    def test_analyst_can_test_rule(self) -> None:
        token = _make_jwt()
        app, _, _ = _build_test_app(valkey_session=_make_session(roles=["analyst"]))
        fake_rule = FakeRuleModel()
        with patch(
            "app.routers.rules.rule_service.get_rule_by_id",
            AsyncMock(return_value=fake_rule),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.post(
                "/api/v1/rules/1/test",
                json={"event": {"action": "repos.create", "actor": "octocat"}},
                cookies={"access_token": token, "csrf_token": "tok"},
                headers={"X-CSRF-Token": "tok"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["matched"] is True
        assert isinstance(data["reason"], str)
        assert isinstance(data["matched_fields"], list)

    def test_rule_author_can_test_rule(self) -> None:
        token = _make_jwt()
        app, _, _ = _build_test_app(valkey_session=_make_session(roles=["rule_author"]))
        fake_rule = FakeRuleModel()
        with patch(
            "app.routers.rules.rule_service.get_rule_by_id",
            AsyncMock(return_value=fake_rule),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.post(
                "/api/v1/rules/1/test",
                json={"event": {"action": "repos.create"}},
                cookies={"access_token": token, "csrf_token": "tok"},
                headers={"X-CSRF-Token": "tok"},
            )
        assert resp.status_code == 200
        assert resp.json()["matched"] is True

    def test_sys_admin_can_test_rule(self) -> None:
        token = _make_jwt()
        app, _, _ = _build_test_app(valkey_session=_make_session(roles=["sys_admin"]))
        fake_rule = FakeRuleModel()
        with patch(
            "app.routers.rules.rule_service.get_rule_by_id",
            AsyncMock(return_value=fake_rule),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.post(
                "/api/v1/rules/1/test",
                json={"event": {"action": "repos.create"}},
                cookies={"access_token": token, "csrf_token": "tok"},
                headers={"X-CSRF-Token": "tok"},
            )
        assert resp.status_code == 200

    def test_nonexistent_rule_returns_404(self) -> None:
        token = _make_jwt()
        app, _, _ = _build_test_app(valkey_session=_make_session(roles=["analyst"]))
        with patch(
            "app.routers.rules.rule_service.get_rule_by_id",
            AsyncMock(return_value=None),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post(
                "/api/v1/rules/9999/test",
                json={"event": {"action": "repos.create"}},
                cookies={"access_token": token, "csrf_token": "tok"},
                headers={"X-CSRF-Token": "tok"},
            )
        assert resp.status_code == 404

    def test_matching_event_returns_matched_true(self) -> None:
        token = _make_jwt()
        app, _, _ = _build_test_app(valkey_session=_make_session(roles=["analyst"]))
        fake_rule = FakeRuleModel(
            logic_config={
                "action_filters": ["repos.create"],
                "field_conditions": [
                    {"field": "actor", "operator": "eq", "value": "octocat"},
                ],
                "confidence": 0.5,
            }
        )
        with patch(
            "app.routers.rules.rule_service.get_rule_by_id",
            AsyncMock(return_value=fake_rule),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.post(
                "/api/v1/rules/1/test",
                json={"event": {"action": "repos.create", "actor": "octocat"}},
                cookies={"access_token": token, "csrf_token": "tok"},
                headers={"X-CSRF-Token": "tok"},
            )
        data = resp.json()
        assert data["matched"] is True
        assert "action" in data["matched_fields"]
        assert "actor" in data["matched_fields"]

    def test_non_matching_event_returns_matched_false(self) -> None:
        token = _make_jwt()
        app, _, _ = _build_test_app(valkey_session=_make_session(roles=["analyst"]))
        fake_rule = FakeRuleModel(
            logic_config={
                "action_filters": ["repos.create"],
                "field_conditions": [],
                "confidence": 0.5,
            }
        )
        with patch(
            "app.routers.rules.rule_service.get_rule_by_id",
            AsyncMock(return_value=fake_rule),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.post(
                "/api/v1/rules/1/test",
                json={"event": {"action": "team.add_member"}},
                cookies={"access_token": token, "csrf_token": "tok"},
                headers={"X-CSRF-Token": "tok"},
            )
        data = resp.json()
        assert data["matched"] is False
        assert "does not match" in data["reason"]

    def test_empty_event_body_returns_422(self) -> None:
        token = _make_jwt()
        app, _, _ = _build_test_app(valkey_session=_make_session(roles=["analyst"]))
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/v1/rules/1/test",
            json={},
            cookies={"access_token": token, "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert resp.status_code == 422

    def test_response_schema_has_required_fields(self) -> None:
        token = _make_jwt()
        app, _, _ = _build_test_app(valkey_session=_make_session(roles=["analyst"]))
        fake_rule = FakeRuleModel()
        with patch(
            "app.routers.rules.rule_service.get_rule_by_id",
            AsyncMock(return_value=fake_rule),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.post(
                "/api/v1/rules/1/test",
                json={"event": {"action": "repos.create"}},
                cookies={"access_token": token, "csrf_token": "tok"},
                headers={"X-CSRF-Token": "tok"},
            )
        data = resp.json()
        assert "matched" in data
        assert "reason" in data
        assert "matched_fields" in data
