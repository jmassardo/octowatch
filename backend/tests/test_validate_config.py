"""Tests for the validate_logic_config helper and POST /rules/validate-config endpoint.

Covers:
- validate_logic_config() unit tests for all logic types
- Common validation (action_filters, field_conditions, confidence)
- Threshold-specific validation
- Sequence-specific validation
- Statistical-specific validation
- Pattern-type (no extra required fields)
- POST /rules/validate-config endpoint (auth, valid/invalid payloads)
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock

import jwt as pyjwt
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps import get_db, get_valkey
from app.routers import rules as rules_router_module
from app.routers.rules import validate_logic_config

SECRET = "testsecretkey_for_unit_tests_only_32ch"


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_jwt(sub: str = "testuser", jti: str = "validate-jti") -> str:
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


def _build_app(valkey_session: str | None = None) -> FastAPI:
    app = FastAPI()
    app.include_router(rules_router_module.router, prefix="/api/v1")

    mock_db = AsyncMock()
    mock_valkey = AsyncMock()
    mock_valkey.get = AsyncMock(return_value=valkey_session)

    async def override_db():
        yield mock_db

    async def override_valkey():
        yield mock_valkey

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_valkey] = override_valkey
    return app


# ═════════════════════════════════════════════════════════════════════════════
# Unit tests for validate_logic_config()
# ═════════════════════════════════════════════════════════════════════════════


class TestValidateLogicConfigCommon:
    """Tests for common validation rules (all logic types)."""

    def test_action_filters_not_a_list_returns_error(self):
        errors, _ = validate_logic_config("pattern", {"action_filters": "not-a-list"})
        assert any("action_filters must be a list" in e for e in errors)

    def test_action_filters_with_non_string_elements_returns_error(self):
        errors, _ = validate_logic_config("pattern", {"action_filters": [1, 2]})
        assert any("must be a string" in e for e in errors)

    def test_action_filters_valid_list_passes(self):
        errors, _ = validate_logic_config("pattern", {"action_filters": ["a.b", "c.d"]})
        assert not any("action_filters" in e for e in errors)

    def test_field_conditions_not_a_list_returns_error(self):
        errors, _ = validate_logic_config("pattern", {"field_conditions": "bad"})
        assert any("field_conditions must be a list" in e for e in errors)

    def test_field_conditions_element_not_a_dict_returns_error(self):
        errors, _ = validate_logic_config("pattern", {"field_conditions": ["bad"]})
        assert any("field_conditions[0] must be an object" in e for e in errors)

    def test_field_conditions_missing_required_keys_returns_errors(self):
        errors, _ = validate_logic_config(
            "pattern",
            {"field_conditions": [{"field": "x"}]},
        )
        assert any("missing required key 'operator'" in e for e in errors)
        assert any("missing required key 'value'" in e for e in errors)

    def test_field_conditions_invalid_operator_returns_error(self):
        errors, _ = validate_logic_config(
            "pattern",
            {"field_conditions": [{"field": "x", "operator": "invalid_op", "value": "y"}]},
        )
        assert any("not a valid operator" in e for e in errors)

    def test_field_conditions_valid_scope_contains_operator_passes(self):
        errors, _ = validate_logic_config(
            "pattern",
            {
                "field_conditions": [
                    {"field": "data.scope", "operator": "scope_contains", "value": "repo"}
                ]
            },
        )
        assert not any("operator" in e for e in errors)

    def test_field_conditions_valid_passes(self):
        errors, _ = validate_logic_config(
            "pattern",
            {"field_conditions": [{"field": "data.role", "operator": "eq", "value": "admin"}]},
        )
        assert not any("field_conditions" in e for e in errors)

    def test_confidence_out_of_range_returns_error(self):
        errors, _ = validate_logic_config("pattern", {"confidence": 1.5})
        assert any("confidence must be a float between 0 and 1" in e for e in errors)

    def test_confidence_negative_returns_error(self):
        errors, _ = validate_logic_config("pattern", {"confidence": -0.1})
        assert any("confidence must be a float between 0 and 1" in e for e in errors)

    def test_confidence_not_a_number_returns_error(self):
        errors, _ = validate_logic_config("pattern", {"confidence": "high"})
        assert any("confidence must be a float between 0 and 1" in e for e in errors)

    def test_confidence_valid_passes(self):
        errors, _ = validate_logic_config("pattern", {"confidence": 0.5})
        assert not any("confidence" in e for e in errors)

    def test_confidence_zero_passes(self):
        errors, _ = validate_logic_config("pattern", {"confidence": 0.0})
        assert not any("confidence" in e for e in errors)

    def test_confidence_one_passes(self):
        errors, _ = validate_logic_config("pattern", {"confidence": 1.0})
        assert not any("confidence" in e for e in errors)


class TestValidateLogicConfigThreshold:
    """Tests for threshold-specific validation."""

    def _valid_threshold_config(self) -> dict[str, Any]:
        return {
            "threshold": 5,
            "time_window_minutes": 60,
            "aggregation_key": "actor",
            "action_filters": ["git.clone"],
            "field_conditions": [],
            "confidence": 0.5,
        }

    def test_valid_threshold_config_passes(self):
        errors, _ = validate_logic_config("threshold", self._valid_threshold_config())
        assert errors == []

    def test_threshold_missing_threshold_returns_error(self):
        cfg = self._valid_threshold_config()
        del cfg["threshold"]
        errors, _ = validate_logic_config("threshold", cfg)
        assert any("threshold is required" in e for e in errors)

    def test_threshold_zero_returns_error(self):
        cfg = self._valid_threshold_config()
        cfg["threshold"] = 0
        errors, _ = validate_logic_config("threshold", cfg)
        assert any("threshold must be an integer greater than 0" in e for e in errors)

    def test_threshold_negative_returns_error(self):
        cfg = self._valid_threshold_config()
        cfg["threshold"] = -1
        errors, _ = validate_logic_config("threshold", cfg)
        assert any("threshold must be an integer greater than 0" in e for e in errors)

    def test_threshold_missing_time_window_minutes_returns_error(self):
        cfg = self._valid_threshold_config()
        del cfg["time_window_minutes"]
        errors, _ = validate_logic_config("threshold", cfg)
        assert any("time_window_minutes is required" in e for e in errors)

    def test_threshold_time_window_zero_returns_error(self):
        cfg = self._valid_threshold_config()
        cfg["time_window_minutes"] = 0
        errors, _ = validate_logic_config("threshold", cfg)
        assert any("time_window_minutes must be an integer greater than 0" in e for e in errors)

    def test_threshold_missing_aggregation_key_returns_error(self):
        cfg = self._valid_threshold_config()
        del cfg["aggregation_key"]
        errors, _ = validate_logic_config("threshold", cfg)
        assert any("aggregation_key is required" in e for e in errors)

    def test_threshold_invalid_aggregation_key_returns_error(self):
        cfg = self._valid_threshold_config()
        cfg["aggregation_key"] = "invalid_key"
        errors, _ = validate_logic_config("threshold", cfg)
        assert any("aggregation_key must be one of" in e for e in errors)

    def test_threshold_valid_aggregation_keys(self):
        for key in ("actor", "repo", "org"):
            cfg = self._valid_threshold_config()
            cfg["aggregation_key"] = key
            errors, _ = validate_logic_config("threshold", cfg)
            assert errors == [], f"aggregation_key '{key}' should be valid"

    def test_threshold_invalid_distinct_count_field_returns_error(self):
        cfg = self._valid_threshold_config()
        cfg["distinct_count_field"] = "password_hash"
        errors, _ = validate_logic_config("threshold", cfg)
        assert any("distinct_count_field must be one of" in e for e in errors)

    def test_threshold_valid_distinct_count_field_passes(self):
        cfg = self._valid_threshold_config()
        cfg["distinct_count_field"] = "repo"
        errors, _ = validate_logic_config("threshold", cfg)
        assert errors == []

    def test_threshold_with_distinct_count_field_all_valid_values(self):
        valid_fields = {
            "actor",
            "org",
            "repo",
            "source_ip",
            "user_agent",
            "geo_country_code",
            "action",
        }
        for field in valid_fields:
            cfg = self._valid_threshold_config()
            cfg["distinct_count_field"] = field
            errors, _ = validate_logic_config("threshold", cfg)
            assert errors == [], f"distinct_count_field '{field}' should be valid"


class TestValidateLogicConfigSequence:
    """Tests for sequence-specific validation."""

    def _valid_sequence_config(self) -> dict[str, Any]:
        return {
            "sequence_steps": [
                {"action": "a.b", "min_count": 1},
                {"action": "c.d", "min_count": 2},
            ],
            "aggregation_key": "actor",
            "time_window_minutes": 120,
            "action_filters": ["a.b", "c.d"],
            "field_conditions": [],
            "confidence": 0.65,
        }

    def test_valid_sequence_config_passes(self):
        errors, _ = validate_logic_config("sequence", self._valid_sequence_config())
        assert errors == []

    def test_sequence_missing_steps_returns_error(self):
        cfg = self._valid_sequence_config()
        del cfg["sequence_steps"]
        errors, _ = validate_logic_config("sequence", cfg)
        assert any("sequence_steps is required" in e for e in errors)

    def test_sequence_steps_not_a_list_returns_error(self):
        cfg = self._valid_sequence_config()
        cfg["sequence_steps"] = "not-a-list"
        errors, _ = validate_logic_config("sequence", cfg)
        assert any("sequence_steps must be a list" in e for e in errors)

    def test_sequence_steps_less_than_2_returns_error(self):
        cfg = self._valid_sequence_config()
        cfg["sequence_steps"] = [{"action": "a.b", "min_count": 1}]
        errors, _ = validate_logic_config("sequence", cfg)
        assert any("at least 2 steps" in e for e in errors)

    def test_sequence_step_missing_action_returns_error(self):
        cfg = self._valid_sequence_config()
        cfg["sequence_steps"] = [
            {"min_count": 1},
            {"action": "c.d", "min_count": 2},
        ]
        errors, _ = validate_logic_config("sequence", cfg)
        assert any("missing required key 'action'" in e for e in errors)

    def test_sequence_step_missing_min_count_returns_error(self):
        cfg = self._valid_sequence_config()
        cfg["sequence_steps"] = [
            {"action": "a.b", "min_count": 1},
            {"action": "c.d"},
        ]
        errors, _ = validate_logic_config("sequence", cfg)
        assert any("missing required key 'min_count'" in e for e in errors)

    def test_sequence_step_min_count_zero_returns_error(self):
        cfg = self._valid_sequence_config()
        cfg["sequence_steps"] = [
            {"action": "a.b", "min_count": 0},
            {"action": "c.d", "min_count": 2},
        ]
        errors, _ = validate_logic_config("sequence", cfg)
        assert any("min_count must be an integer >= 1" in e for e in errors)

    def test_sequence_step_not_a_dict_returns_error(self):
        cfg = self._valid_sequence_config()
        cfg["sequence_steps"] = ["not_a_dict", {"action": "c.d", "min_count": 2}]
        errors, _ = validate_logic_config("sequence", cfg)
        assert any("sequence_steps[0] must be an object" in e for e in errors)

    def test_sequence_missing_aggregation_key_returns_error(self):
        cfg = self._valid_sequence_config()
        del cfg["aggregation_key"]
        errors, _ = validate_logic_config("sequence", cfg)
        assert any("aggregation_key is required" in e for e in errors)

    def test_sequence_invalid_aggregation_key_returns_error(self):
        cfg = self._valid_sequence_config()
        cfg["aggregation_key"] = "bad_key"
        errors, _ = validate_logic_config("sequence", cfg)
        assert any("aggregation_key must be one of" in e for e in errors)

    def test_sequence_missing_time_window_minutes_returns_error(self):
        cfg = self._valid_sequence_config()
        del cfg["time_window_minutes"]
        errors, _ = validate_logic_config("sequence", cfg)
        assert any("time_window_minutes is required" in e for e in errors)

    def test_sequence_time_window_zero_returns_error(self):
        cfg = self._valid_sequence_config()
        cfg["time_window_minutes"] = 0
        errors, _ = validate_logic_config("sequence", cfg)
        assert any("time_window_minutes must be an integer greater than 0" in e for e in errors)


class TestValidateLogicConfigStatistical:
    """Tests for statistical-specific validation."""

    def test_valid_statistical_config_passes(self):
        cfg: dict[str, Any] = {
            "x_config": {"engine": "zscore"},
            "action_filters": [],
            "field_conditions": [],
            "confidence": 0.5,
        }
        errors, _ = validate_logic_config("statistical", cfg)
        assert errors == []

    def test_statistical_missing_x_config_returns_error(self):
        errors, _ = validate_logic_config("statistical", {})
        assert any("x_config is required" in e for e in errors)

    def test_statistical_x_config_not_a_dict_returns_error(self):
        errors, _ = validate_logic_config("statistical", {"x_config": "bad"})
        assert any("x_config must be an object" in e for e in errors)

    def test_statistical_x_config_missing_engine_returns_error(self):
        errors, _ = validate_logic_config("statistical", {"x_config": {"other": "value"}})
        assert any("x_config.engine is required" in e for e in errors)


class TestValidateLogicConfigPattern:
    """Tests for pattern-type: no extra required fields beyond common."""

    def test_pattern_with_empty_config_no_type_specific_errors(self):
        errors, _ = validate_logic_config("pattern", {})
        # Should have no errors since pattern has no extra required fields
        assert errors == []

    def test_pattern_with_full_config_passes(self):
        cfg: dict[str, Any] = {
            "action_filters": ["some.action"],
            "field_conditions": [{"field": "data.scope", "operator": "contains", "value": "repo"}],
            "confidence": 0.5,
        }
        errors, _ = validate_logic_config("pattern", cfg)
        assert errors == []


class TestValidateLogicConfigReturnType:
    """Tests that the function returns the correct tuple shape."""

    def test_returns_tuple_of_two_lists(self):
        result = validate_logic_config("pattern", {})
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], list)
        assert isinstance(result[1], list)

    def test_multiple_errors_accumulated(self):
        cfg: dict[str, Any] = {
            "action_filters": 123,
            "field_conditions": "bad",
            "confidence": "invalid",
        }
        errors, _ = validate_logic_config("threshold", cfg)
        # Should have common errors + threshold-specific errors
        # (action_filters + field_conditions + confidence + threshold fields)
        assert len(errors) >= 5


# ═════════════════════════════════════════════════════════════════════════════
# Integration tests for POST /rules/validate-config endpoint
# ═════════════════════════════════════════════════════════════════════════════


class TestValidateConfigEndpoint:
    """Integration tests for POST /api/v1/rules/validate-config."""

    def test_unauthenticated_returns_401(self):
        app = _build_app(valkey_session=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/v1/rules/validate-config",
            json={"logic_type": "pattern", "logic_config": {}},
        )
        assert resp.status_code == 401

    def test_analyst_can_validate_config(self):
        token = _make_jwt()
        app = _build_app(valkey_session=_make_session(roles=["analyst"]))
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.post(
            "/api/v1/rules/validate-config",
            json={"logic_type": "pattern", "logic_config": {}},
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True

    def test_rule_author_can_validate_config(self):
        token = _make_jwt()
        app = _build_app(valkey_session=_make_session(roles=["rule_author"]))
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.post(
            "/api/v1/rules/validate-config",
            json={"logic_type": "pattern", "logic_config": {}},
            cookies={"access_token": token},
        )
        assert resp.status_code == 200

    def test_valid_threshold_config_returns_valid_true(self):
        token = _make_jwt()
        app = _build_app(valkey_session=_make_session(roles=["analyst"]))
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.post(
            "/api/v1/rules/validate-config",
            json={
                "logic_type": "threshold",
                "logic_config": {
                    "threshold": 5,
                    "time_window_minutes": 60,
                    "aggregation_key": "actor",
                    "action_filters": ["git.clone"],
                    "field_conditions": [],
                    "confidence": 0.5,
                },
            },
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["errors"] == []

    def test_invalid_threshold_config_returns_valid_false_with_errors(self):
        token = _make_jwt()
        app = _build_app(valkey_session=_make_session(roles=["analyst"]))
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.post(
            "/api/v1/rules/validate-config",
            json={
                "logic_type": "threshold",
                "logic_config": {},
            },
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert len(data["errors"]) >= 3  # threshold, time_window_minutes, aggregation_key

    def test_invalid_logic_type_returns_422(self):
        token = _make_jwt()
        app = _build_app(valkey_session=_make_session(roles=["analyst"]))
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/v1/rules/validate-config",
            json={
                "logic_type": "invalid_type",
                "logic_config": {},
            },
            cookies={"access_token": token},
        )
        assert resp.status_code == 422

    def test_missing_logic_type_returns_422(self):
        token = _make_jwt()
        app = _build_app(valkey_session=_make_session(roles=["analyst"]))
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/v1/rules/validate-config",
            json={"logic_config": {}},
            cookies={"access_token": token},
        )
        assert resp.status_code == 422

    def test_missing_logic_config_returns_422(self):
        token = _make_jwt()
        app = _build_app(valkey_session=_make_session(roles=["analyst"]))
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/v1/rules/validate-config",
            json={"logic_type": "pattern"},
            cookies={"access_token": token},
        )
        assert resp.status_code == 422

    def test_valid_sequence_config_returns_valid_true(self):
        token = _make_jwt()
        app = _build_app(valkey_session=_make_session(roles=["analyst"]))
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.post(
            "/api/v1/rules/validate-config",
            json={
                "logic_type": "sequence",
                "logic_config": {
                    "sequence_steps": [
                        {"action": "a.b", "min_count": 1},
                        {"action": "c.d", "min_count": 2},
                    ],
                    "aggregation_key": "actor",
                    "time_window_minutes": 120,
                },
            },
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True

    def test_valid_statistical_config_returns_valid_true(self):
        token = _make_jwt()
        app = _build_app(valkey_session=_make_session(roles=["analyst"]))
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.post(
            "/api/v1/rules/validate-config",
            json={
                "logic_type": "statistical",
                "logic_config": {
                    "x_config": {"engine": "zscore"},
                },
            },
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True

    def test_response_includes_warnings_field(self):
        token = _make_jwt()
        app = _build_app(valkey_session=_make_session(roles=["analyst"]))
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.post(
            "/api/v1/rules/validate-config",
            json={"logic_type": "pattern", "logic_config": {}},
            cookies={"access_token": token},
        )
        data = resp.json()
        assert "warnings" in data
        assert isinstance(data["warnings"], list)
