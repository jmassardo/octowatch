"""Tests for the audit trail service and audit logging in routers.

Tests cover:
- audit_service.log_action: creates entries and flushes
- deps.get_request_meta: IP/UA extraction
- Router audit logging integration: rules, admin, admin_settings,
  detections, sync
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps import get_db, get_request_meta, get_valkey
from app.models.audit_trail import AuditTrail
from app.services.audit_service import log_action

SECRET = "testsecretkey_for_unit_tests_only_32ch"


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_jwt(sub: str = "testuser", jti: str = "audit-jti") -> str:
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
    """Create a mock async DB session with sync-compatible add()."""
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


def _make_mock_request(
    forwarded_for: str | None = None,
    user_agent: str = "TestAgent/1.0",
    client_host: str = "127.0.0.1",
) -> MagicMock:
    """Create a mock FastAPI Request with headers and client info."""
    request = MagicMock()
    headers: dict[str, str] = {"user-agent": user_agent}
    if forwarded_for is not None:
        headers["x-forwarded-for"] = forwarded_for
    request.headers = headers
    request.client = MagicMock()
    request.client.host = client_host
    return request


# ─── log_action unit tests ───────────────────────────────────────────────────


class TestLogAction:
    @pytest.mark.asyncio
    async def test_creates_audit_entry_and_flushes(self) -> None:
        """log_action should call db.add with an AuditTrail and then flush."""
        db = _make_mock_db()
        entry = await log_action(
            db,
            user_login="octocat",
            action_type="rule.create",
            resource_type="rule",
            resource_id="42",
        )
        assert isinstance(entry, AuditTrail)
        assert entry.user_login == "octocat"
        assert entry.action_type == "rule.create"
        assert entry.resource_type == "rule"
        assert entry.resource_id == "42"
        assert entry.outcome == "success"
        db.add.assert_called_once_with(entry)
        db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_passes_all_fields(self) -> None:
        """All optional fields should be stored in the AuditTrail object."""
        db = _make_mock_db()
        params = {"key": "value"}
        entry = await log_action(
            db,
            user_login="testuser",
            user_github_id=999,
            ip_address="10.0.0.1",
            user_agent="Mozilla/5.0",
            action_type="setting.update",
            resource_type="setting",
            resource_id="my_key",
            parameters=params,
            outcome="success",
            error_detail=None,
        )
        assert entry.user_github_id == 999
        assert entry.ip_address == "10.0.0.1"
        assert entry.user_agent == "Mozilla/5.0"
        assert entry.parameters == params

    @pytest.mark.asyncio
    async def test_defaults_outcome_to_success(self) -> None:
        """When outcome is not provided, it should default to 'success'."""
        db = _make_mock_db()
        entry = await log_action(
            db,
            user_login="user",
            action_type="test.action",
        )
        assert entry.outcome == "success"

    @pytest.mark.asyncio
    async def test_error_detail_stored(self) -> None:
        """Error detail should be stored when outcome is 'failure'."""
        db = _make_mock_db()
        entry = await log_action(
            db,
            user_login="user",
            action_type="test.action",
            outcome="failure",
            error_detail="Something went wrong",
        )
        assert entry.outcome == "failure"
        assert entry.error_detail == "Something went wrong"


# ─── get_request_meta unit tests ─────────────────────────────────────────────


class TestGetRequestMeta:
    @pytest.mark.asyncio
    async def test_extracts_ip_from_forwarded_header(self) -> None:
        """When x-forwarded-for is present, use the first IP."""
        request = _make_mock_request(forwarded_for="1.2.3.4")
        meta = await get_request_meta(request)
        assert meta["ip_address"] == "1.2.3.4"
        assert meta["user_agent"] == "TestAgent/1.0"

    @pytest.mark.asyncio
    async def test_extracts_first_ip_from_multiple_forwarded(self) -> None:
        """When x-forwarded-for has multiple IPs, use the first."""
        request = _make_mock_request(forwarded_for="1.2.3.4, 10.0.0.1, 192.168.1.1")
        meta = await get_request_meta(request)
        assert meta["ip_address"] == "1.2.3.4"

    @pytest.mark.asyncio
    async def test_falls_back_to_client_host(self) -> None:
        """When no x-forwarded-for, use request.client.host."""
        request = _make_mock_request(client_host="192.168.1.100")
        meta = await get_request_meta(request)
        assert meta["ip_address"] == "192.168.1.100"

    @pytest.mark.asyncio
    async def test_handles_no_client(self) -> None:
        """When no client info is available, ip_address should be None."""
        request = _make_mock_request()
        request.client = None
        meta = await get_request_meta(request)
        assert meta["ip_address"] is None


# ─── Router integration tests ────────────────────────────────────────────────
# These verify that audit log_action is called correctly in each router.


@dataclass
class FakeRuleModel:
    """Fake rule model compatible with RuleResponse.model_validate(from_attributes=True)."""

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


def _build_app_with_router(
    router_module: Any,
    valkey_session: str | None = None,
    prefix: str = "/api/v1",
) -> tuple[FastAPI, AsyncMock, AsyncMock]:
    """Build a FastAPI app wired with a single router and mock dependencies."""
    app = FastAPI()
    app.include_router(router_module.router, prefix=prefix)

    mock_db = _make_mock_db()
    mock_valkey = AsyncMock()
    mock_valkey.get = AsyncMock(return_value=valkey_session)

    async def override_db() -> Any:
        yield mock_db

    async def override_valkey() -> Any:
        yield mock_valkey

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_valkey] = override_valkey

    return app, mock_db, mock_valkey


class TestRulesAuditLogging:
    """Verify audit log_action is called for rules mutations."""

    def test_create_rule_calls_log_action(self) -> None:
        from app.routers import rules as rules_module

        token = _make_jwt()
        app, mock_db, _ = _build_app_with_router(
            rules_module,
            valkey_session=_make_session(roles=["rule_author"]),
        )
        fake_rule = FakeRuleModel()

        with (
            patch(
                "app.routers.rules.rule_service.get_rule_by_slug",
                AsyncMock(return_value=None),
            ),
            patch(
                "app.routers.rules.rule_service.create_rule",
                AsyncMock(return_value=fake_rule),
            ),
            patch("app.routers.rules.log_action", new_callable=AsyncMock) as mock_log,
        ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.post(
                "/api/v1/rules",
                json=VALID_RULE_PAYLOAD,
                cookies={"access_token": token, "csrf_token": "tok"},
                headers={"X-CSRF-Token": "tok"},
            )

        assert resp.status_code == 201
        mock_log.assert_awaited_once()
        call_kwargs = mock_log.call_args.kwargs
        assert call_kwargs["action_type"] == "rule.create"
        assert call_kwargs["resource_type"] == "rule"
        assert call_kwargs["resource_id"] == "1"
        assert call_kwargs["user_login"] == "testuser"
        assert call_kwargs["parameters"]["slug"] == "test-detection-rule"
        assert call_kwargs["parameters"]["name"] == "Test Detection Rule"

    def test_update_rule_calls_log_action(self) -> None:
        from app.routers import rules as rules_module

        token = _make_jwt()
        app, _, _ = _build_app_with_router(
            rules_module,
            valkey_session=_make_session(roles=["rule_author"]),
        )
        fake_rule = FakeRuleModel()

        with (
            patch(
                "app.routers.rules.rule_service.get_rule_by_id",
                AsyncMock(return_value=fake_rule),
            ),
            patch(
                "app.routers.rules.rule_service.update_rule",
                AsyncMock(return_value=fake_rule),
            ),
            patch("app.routers.rules.invalidate_rule_cache", AsyncMock()),
            patch("app.routers.rules.log_action", new_callable=AsyncMock) as mock_log,
        ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.put(
                "/api/v1/rules/1",
                json=VALID_RULE_PAYLOAD,
                cookies={"access_token": token, "csrf_token": "tok"},
                headers={"X-CSRF-Token": "tok"},
            )

        assert resp.status_code == 200
        mock_log.assert_awaited_once()
        call_kwargs = mock_log.call_args.kwargs
        assert call_kwargs["action_type"] == "rule.update"
        assert call_kwargs["resource_type"] == "rule"
        assert call_kwargs["resource_id"] == "1"

    def test_update_rule_includes_old_name_when_changed(self) -> None:
        from app.routers import rules as rules_module

        token = _make_jwt()
        app, _, _ = _build_app_with_router(
            rules_module,
            valkey_session=_make_session(roles=["rule_author"]),
        )
        fake_rule = FakeRuleModel(name="Old Name")
        updated_rule = FakeRuleModel(name="New Name")

        with (
            patch(
                "app.routers.rules.rule_service.get_rule_by_id",
                AsyncMock(return_value=fake_rule),
            ),
            patch(
                "app.routers.rules.rule_service.update_rule",
                AsyncMock(return_value=updated_rule),
            ),
            patch("app.routers.rules.invalidate_rule_cache", AsyncMock()),
            patch("app.routers.rules.log_action", new_callable=AsyncMock) as mock_log,
        ):
            payload = {**VALID_RULE_PAYLOAD, "name": "New Name"}
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.put(
                "/api/v1/rules/1",
                json=payload,
                cookies={"access_token": token, "csrf_token": "tok"},
                headers={"X-CSRF-Token": "tok"},
            )

        assert resp.status_code == 200
        call_kwargs = mock_log.call_args.kwargs
        assert call_kwargs["parameters"]["old_name"] == "Old Name"
        assert call_kwargs["parameters"]["name"] == "New Name"

    def test_update_rule_status_calls_log_action(self) -> None:
        from app.routers import rules as rules_module

        token = _make_jwt()
        app, _, _ = _build_app_with_router(
            rules_module,
            valkey_session=_make_session(roles=["rule_author"]),
        )
        fake_rule = FakeRuleModel(status="draft")

        with (
            patch(
                "app.routers.rules.rule_service.get_rule_by_id",
                AsyncMock(return_value=fake_rule),
            ),
            patch(
                "app.routers.rules.rule_service.update_rule_status",
                AsyncMock(return_value=FakeRuleModel(status="active")),
            ),
            patch("app.routers.rules.invalidate_rule_cache", AsyncMock()),
            patch("app.routers.rules.log_action", new_callable=AsyncMock) as mock_log,
        ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.patch(
                "/api/v1/rules/1/status",
                json={"status": "active"},
                cookies={"access_token": token, "csrf_token": "tok"},
                headers={"X-CSRF-Token": "tok"},
            )

        assert resp.status_code == 200
        call_kwargs = mock_log.call_args.kwargs
        assert call_kwargs["action_type"] == "rule.status_change"
        assert call_kwargs["parameters"]["new_status"] == "active"

    def test_delete_rule_calls_log_action(self) -> None:
        from app.routers import rules as rules_module

        token = _make_jwt()
        app, _, _ = _build_app_with_router(
            rules_module,
            valkey_session=_make_session(roles=["sys_admin"]),
        )
        fake_rule = FakeRuleModel()

        with (
            patch(
                "app.routers.rules.rule_service.get_rule_by_id",
                AsyncMock(return_value=fake_rule),
            ),
            patch("app.routers.rules.rule_service.delete_rule", AsyncMock()),
            patch("app.routers.rules.invalidate_rule_cache", AsyncMock()),
            patch("app.routers.rules.log_action", new_callable=AsyncMock) as mock_log,
        ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.delete(
                "/api/v1/rules/1",
                cookies={"access_token": token, "csrf_token": "tok"},
                headers={"X-CSRF-Token": "tok"},
            )

        assert resp.status_code == 204
        mock_log.assert_awaited_once()
        call_kwargs = mock_log.call_args.kwargs
        assert call_kwargs["action_type"] == "rule.delete"
        assert call_kwargs["resource_type"] == "rule"
        assert call_kwargs["resource_id"] == "1"


class TestAdminSettingsAuditLogging:
    """Verify audit log_action is called for admin-settings mutations."""

    def test_update_setting_calls_log_action(self) -> None:
        from app.routers import admin_settings as settings_module

        token = _make_jwt()
        app, _, _ = _build_app_with_router(
            settings_module,
            valkey_session=_make_session(roles=["sys_admin"]),
        )

        with (
            patch("app.routers.admin_settings.set_setting", AsyncMock()),
            patch("app.routers.admin_settings.load_settings_overlay", AsyncMock()),
            patch("app.routers.admin_settings.log_action", new_callable=AsyncMock) as mock_log,
        ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.put(
                "/api/v1/admin/settings/my_key",
                json={"value": "new_value"},
                cookies={"access_token": token, "csrf_token": "tok"},
                headers={"X-CSRF-Token": "tok"},
            )

        assert resp.status_code == 200
        mock_log.assert_awaited_once()
        call_kwargs = mock_log.call_args.kwargs
        assert call_kwargs["action_type"] == "setting.update"
        assert call_kwargs["resource_type"] == "setting"
        assert call_kwargs["resource_id"] == "my_key"

    def test_delete_setting_calls_log_action(self) -> None:
        from app.routers import admin_settings as settings_module

        token = _make_jwt()
        app, _, _ = _build_app_with_router(
            settings_module,
            valkey_session=_make_session(roles=["sys_admin"]),
        )

        with (
            patch("app.routers.admin_settings.delete_setting", AsyncMock(return_value=True)),
            patch("app.routers.admin_settings.load_settings_overlay", AsyncMock()),
            patch("app.routers.admin_settings.log_action", new_callable=AsyncMock) as mock_log,
        ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.delete(
                "/api/v1/admin/settings/my_key",
                cookies={"access_token": token, "csrf_token": "tok"},
                headers={"X-CSRF-Token": "tok"},
            )

        assert resp.status_code == 200
        mock_log.assert_awaited_once()
        call_kwargs = mock_log.call_args.kwargs
        assert call_kwargs["action_type"] == "setting.delete"
        assert call_kwargs["resource_type"] == "setting"
        assert call_kwargs["resource_id"] == "my_key"


class TestSyncAuditLogging:
    """Verify audit log_action is called for sync trigger."""

    def test_trigger_sync_calls_log_action(self) -> None:
        from app.routers import sync as sync_module

        token = _make_jwt()
        app, mock_db, _ = _build_app_with_router(
            sync_module,
            valkey_session=_make_session(roles=["sys_admin"]),
        )

        with (
            patch("app.routers.sync.log_action", new_callable=AsyncMock) as mock_log,
            patch(
                "app.workers.github_sync_worker.run_enterprise_sync.apply_async",
                MagicMock(),
            ),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.post(
                "/api/v1/sync/trigger",
                json={"scope": "full"},
                cookies={"access_token": token, "csrf_token": "tok"},
                headers={"X-CSRF-Token": "tok"},
            )

        assert resp.status_code == 202
        mock_log.assert_awaited_once()
        call_kwargs = mock_log.call_args.kwargs
        assert call_kwargs["action_type"] == "sync.trigger"
        assert call_kwargs["resource_type"] == "enterprise_sync_run"
        assert call_kwargs["parameters"]["scope"] == "full"
        assert call_kwargs["parameters"]["trigger_type"] == "manual"


class TestAuditLoggingIPExtraction:
    """Verify that IP address and user-agent are correctly extracted."""

    def test_x_forwarded_for_is_used(self) -> None:
        from app.routers import rules as rules_module

        token = _make_jwt()
        app, _, _ = _build_app_with_router(
            rules_module,
            valkey_session=_make_session(roles=["sys_admin"]),
        )
        fake_rule = FakeRuleModel()

        with (
            patch(
                "app.routers.rules.rule_service.get_rule_by_id",
                AsyncMock(return_value=fake_rule),
            ),
            patch("app.routers.rules.rule_service.delete_rule", AsyncMock()),
            patch("app.routers.rules.invalidate_rule_cache", AsyncMock()),
            patch("app.routers.rules.log_action", new_callable=AsyncMock) as mock_log,
        ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.delete(
                "/api/v1/rules/1",
                cookies={"access_token": token, "csrf_token": "tok"},
                headers={"X-Forwarded-For": "203.0.113.50, 10.0.0.1", "X-CSRF-Token": "tok"},
            )

        assert resp.status_code == 204
        call_kwargs = mock_log.call_args.kwargs
        assert call_kwargs["ip_address"] == "203.0.113.50"

    def test_user_agent_is_captured(self) -> None:
        from app.routers import rules as rules_module

        token = _make_jwt()
        app, _, _ = _build_app_with_router(
            rules_module,
            valkey_session=_make_session(roles=["sys_admin"]),
        )
        fake_rule = FakeRuleModel()

        with (
            patch(
                "app.routers.rules.rule_service.get_rule_by_id",
                AsyncMock(return_value=fake_rule),
            ),
            patch("app.routers.rules.rule_service.delete_rule", AsyncMock()),
            patch("app.routers.rules.invalidate_rule_cache", AsyncMock()),
            patch("app.routers.rules.log_action", new_callable=AsyncMock) as mock_log,
        ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.delete(
                "/api/v1/rules/1",
                cookies={"access_token": token, "csrf_token": "tok"},
                headers={"User-Agent": "OctoWatch-CLI/2.0", "X-CSRF-Token": "tok"},
            )

        assert resp.status_code == 204
        call_kwargs = mock_log.call_args.kwargs
        assert call_kwargs["user_agent"] == "OctoWatch-CLI/2.0"
