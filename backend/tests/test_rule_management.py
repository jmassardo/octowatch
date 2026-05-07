from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.schemas.detection import BacktestParams, BulkUpdateRequest, RuleCreate
from tests.test_rules_router import (
    VALID_RULE_PAYLOAD,
    FakeRuleModel,
    _build_rules_app,
    _make_jwt,
    _make_session,
)


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _result_with_mappings_one(row: dict[str, object]) -> MagicMock:
    result = MagicMock()
    result.mappings.return_value.one.return_value = row
    return result


def _result_with_mappings_all(rows: list[dict[str, object]]) -> MagicMock:
    result = MagicMock()
    result.mappings.return_value.all.return_value = rows
    return result


class TestBacktestEndpoint:
    def test_backtest_requires_auth(self) -> None:
        app, _, _ = _build_rules_app(valkey_session=None)
        client = TestClient(app, raise_server_exceptions=False)
        now = datetime.now(UTC)
        resp = client.post(
            "/api/v1/rules/1/backtest",
            json={"start_date": _iso(now - timedelta(days=1)), "end_date": _iso(now)},
            cookies={"csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert resp.status_code == 401

    def test_backtest_validates_time_range(self) -> None:
        token = _make_jwt()
        app, _, _ = _build_rules_app(valkey_session=_make_session(roles=["analyst"]))
        client = TestClient(app, raise_server_exceptions=False)
        now = datetime.now(UTC)
        resp = client.post(
            "/api/v1/rules/1/backtest",
            json={"start_date": _iso(now - timedelta(days=31)), "end_date": _iso(now)},
            cookies={"access_token": token, "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert resp.status_code == 400

    def test_backtest_rule_not_found(self) -> None:
        token = _make_jwt()
        app, _, _ = _build_rules_app(valkey_session=_make_session(roles=["analyst"]))
        now = datetime.now(UTC)
        with patch("app.routers.rules.rule_service.get_rule_by_id", AsyncMock(return_value=None)):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post(
                "/api/v1/rules/999/backtest",
                json={"start_date": _iso(now - timedelta(days=1)), "end_date": _iso(now)},
                cookies={"access_token": token, "csrf_token": "tok"},
                headers={"X-CSRF-Token": "tok"},
            )
        assert resp.status_code == 404

    def test_backtest_returns_results(self) -> None:
        token = _make_jwt()
        app, mock_db, _ = _build_rules_app(valkey_session=_make_session(roles=["analyst"]))
        now = datetime.now(UTC)
        events_result = MagicMock()
        events_result.scalars.return_value.all.return_value = [
            SimpleNamespace(
                id=101,
                created_at=now - timedelta(hours=1),
                action="repo.create",
                actor="alice",
                org="octo",
                repo="widgets",
                source_ip="127.0.0.1",
                data={"key": "value"},
            ),
            SimpleNamespace(
                id=102,
                created_at=now - timedelta(hours=2),
                action="repo.delete",
                actor="bob",
                org="octo",
                repo="gadgets",
                source_ip="127.0.0.2",
                data={},
            ),
        ]
        mock_db.execute.side_effect = [MagicMock(), events_result]

        with (
            patch(
                "app.routers.rules.rule_service.get_rule_by_id",
                AsyncMock(return_value=FakeRuleModel()),
            ),
            patch(
                "app.routers.rules.evaluate_rule_against_event",
                side_effect=[
                    {
                        "matched": True,
                        "reason": "match",
                        "matched_fields": ["action", "actor"],
                    },
                    {"matched": False, "reason": "no match", "matched_fields": []},
                ],
            ),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.post(
                "/api/v1/rules/1/backtest",
                json={
                    "start_date": _iso(now - timedelta(days=1)),
                    "end_date": _iso(now),
                    "max_results": 10,
                },
                cookies={"access_token": token, "csrf_token": "tok"},
                headers={"X-CSRF-Token": "tok"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_matches"] == 1
        assert data["events_scanned"] == 2
        assert data["capped"] is False
        assert data["matches"][0]["event_id"] == 101
        assert data["matches"][0]["matched_conditions"] == ["action", "actor"]


class TestAnalyticsEndpoint:
    def test_analytics_requires_auth(self) -> None:
        app, _, _ = _build_rules_app(valkey_session=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/rules/1/analytics")
        assert resp.status_code == 401

    def test_analytics_rule_not_found(self) -> None:
        token = _make_jwt()
        app, _, _ = _build_rules_app(valkey_session=_make_session(roles=["analyst"]))
        with patch("app.routers.rules.rule_service.get_rule_by_id", AsyncMock(return_value=None)):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/api/v1/rules/999/analytics", cookies={"access_token": token})
        assert resp.status_code == 404

    def test_analytics_returns_data(self) -> None:
        token = _make_jwt()
        app, mock_db, _ = _build_rules_app(valkey_session=_make_session(roles=["analyst"]))
        mock_db.execute.side_effect = [
            _result_with_mappings_one(
                {
                    "total_detections": 6,
                    "false_positives": 2,
                    "mean_time_to_triage_hours": 4.5,
                }
            ),
            _result_with_mappings_all(
                [{"date": "2026-05-01", "count": 4}, {"date": "2026-05-02", "count": 2}]
            ),
            _result_with_mappings_all([{"name": "alice", "count": 3}]),
            _result_with_mappings_all([{"name": "widgets", "count": 2}]),
            _result_with_mappings_all([{"name": "repo.create", "count": 5}]),
        ]

        with patch(
            "app.routers.rules.rule_service.get_rule_by_id",
            AsyncMock(return_value=FakeRuleModel()),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get("/api/v1/rules/1/analytics?days=30", cookies={"access_token": token})

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_detections"] == 6
        assert data["false_positive_rate"] == pytest.approx(2 / 6)
        assert data["mean_time_to_triage_hours"] == 4.5
        assert data["detections_by_day"][0] == {"date": "2026-05-01", "count": 4}
        assert data["top_actors"][0] == {"name": "alice", "count": 3}
        assert data["top_repos"][0] == {"name": "widgets", "count": 2}
        assert data["top_actions"][0] == {"name": "repo.create", "count": 5}


class TestBulkUpdateEndpoint:
    def test_bulk_update_requires_create_permission(self) -> None:
        token = _make_jwt()
        app, _, _ = _build_rules_app(valkey_session=_make_session(roles=["analyst"]))
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/v1/rules/bulk-update",
            json={"rule_ids": [1], "action": "enable"},
            cookies={"access_token": token, "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert resp.status_code == 403

    def test_bulk_update_enable_rules(self) -> None:
        token = _make_jwt()
        app, mock_db, _ = _build_rules_app(valkey_session=_make_session(roles=["rule_author"]))
        rules = [
            FakeRuleModel(id=1, enabled=False, mode="disabled"),
            FakeRuleModel(id=2, enabled=False),
        ]

        with (
            patch(
                "app.routers.rules.rule_service.get_rule_by_id",
                AsyncMock(side_effect=rules),
            ),
            patch("app.routers.rules.invalidate_rule_cache", AsyncMock()),
            patch("app.routers.rules.log_action", AsyncMock()),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.post(
                "/api/v1/rules/bulk-update",
                json={"rule_ids": [1, 2], "action": "enable", "reason": "restore"},
                cookies={"access_token": token, "csrf_token": "tok"},
                headers={"X-CSRF-Token": "tok"},
            )

        assert resp.status_code == 200
        assert resp.json() == {"updated": 2, "failed": []}
        assert all(rule.enabled for rule in rules)
        assert all(rule.mode == "active" for rule in rules)
        assert mock_db.flush.await_count == 2

    def test_bulk_update_disable_rules(self) -> None:
        token = _make_jwt()
        app, _, _ = _build_rules_app(valkey_session=_make_session(roles=["rule_author"]))
        rules = [FakeRuleModel(id=1), FakeRuleModel(id=2)]

        with (
            patch(
                "app.routers.rules.rule_service.get_rule_by_id",
                AsyncMock(side_effect=rules),
            ),
            patch("app.routers.rules.invalidate_rule_cache", AsyncMock()),
            patch("app.routers.rules.log_action", AsyncMock()),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.post(
                "/api/v1/rules/bulk-update",
                json={"rule_ids": [1, 2], "action": "disable"},
                cookies={"access_token": token, "csrf_token": "tok"},
                headers={"X-CSRF-Token": "tok"},
            )

        assert resp.status_code == 200
        assert all(not rule.enabled for rule in rules)
        assert all(rule.mode == "disabled" for rule in rules)

    def test_bulk_update_set_monitoring(self) -> None:
        token = _make_jwt()
        app, _, _ = _build_rules_app(valkey_session=_make_session(roles=["rule_author"]))
        rules = [FakeRuleModel(id=1, enabled=False, mode="disabled"), FakeRuleModel(id=2)]

        with (
            patch(
                "app.routers.rules.rule_service.get_rule_by_id",
                AsyncMock(side_effect=rules),
            ),
            patch("app.routers.rules.invalidate_rule_cache", AsyncMock()),
            patch("app.routers.rules.log_action", AsyncMock()),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.post(
                "/api/v1/rules/bulk-update",
                json={"rule_ids": [1, 2], "action": "set_monitoring"},
                cookies={"access_token": token, "csrf_token": "tok"},
                headers={"X-CSRF-Token": "tok"},
            )

        assert resp.status_code == 200
        assert all(rule.enabled for rule in rules)
        assert all(rule.mode == "monitoring" for rule in rules)


class TestRuleManagementSchemas:
    def test_backtest_params_validation(self) -> None:
        with pytest.raises(ValidationError):
            BacktestParams(
                start_date=datetime.now(UTC),
                end_date=datetime.now(UTC),
                max_results=10001,
            )

    def test_bulk_update_request_validation(self) -> None:
        with pytest.raises(ValidationError):
            BulkUpdateRequest(rule_ids=[], action="archive")

    def test_rule_create_with_mode(self) -> None:
        payload = {**VALID_RULE_PAYLOAD, "mode": "monitoring"}
        rule = RuleCreate(**payload)
        assert rule.mode == "monitoring"
