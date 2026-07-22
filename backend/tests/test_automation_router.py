"""Tests for the automation router.

Tests cover:
- Unauthenticated requests → 401
- CRUD operations on automation targets
- Validation rules (webhook_url required for webhook type, etc.)
- Delivery listing with filters
- Test target endpoint
- Retry delivery endpoint
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
from app.routers import automation as automation_module

SECRET = "testsecretkey_for_unit_tests_only_32ch"


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_jwt(sub: str = "testuser", jti: str = "auto-jti") -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": sub,
        "github_id": 99,
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
            "github_id": 99,
            "roles": roles or ["super_admin"],
            "scoped_orgs": orgs or ["my-org"],
            "scoped_repos": [],
            "scope_type": "scoped",
            "session_expires_at": "2099-01-01T00:00:00+00:00",
        }
    )


def _make_mock_db(
    fetchone_return: tuple | None = None,
    fetchall_return: list | None = None,
) -> AsyncMock:
    """Create a mock DB session with configurable results."""
    mock_result = MagicMock()
    mock_result.fetchone.return_value = fetchone_return
    mock_result.fetchall.return_value = fetchall_return or []
    db = AsyncMock()
    db.execute = AsyncMock(return_value=mock_result)
    db.commit = AsyncMock(return_value=None)
    return db


def _make_mock_db_with_mapping(
    rows: list[dict] | None = None,
    single_row: dict | None = None,
) -> AsyncMock:
    """Create a mock DB session that returns rows with _mapping attribute."""
    mock_rows = []
    if rows:
        for row_data in rows:
            mock_row = MagicMock()
            mock_row._mapping = row_data
            mock_rows.append(mock_row)

    mock_result = MagicMock()
    mock_result.fetchall.return_value = mock_rows

    if single_row:
        single_mock = MagicMock()
        single_mock._mapping = single_row
        mock_result.fetchone.return_value = single_mock
    else:
        mock_result.fetchone.return_value = None

    db = AsyncMock()
    db.execute = AsyncMock(return_value=mock_result)
    db.commit = AsyncMock(return_value=None)
    return db


def _build_app(
    valkey_session: str | None = None,
    db_mock: AsyncMock | None = None,
) -> tuple[FastAPI, AsyncMock, AsyncMock]:
    app = FastAPI()
    app.include_router(automation_module.router, prefix="/api/v1")

    mock_db = db_mock or _make_mock_db()
    mock_valkey = AsyncMock()
    mock_valkey.get = AsyncMock(return_value=valkey_session)
    mock_valkey.setex = AsyncMock(return_value=True)

    async def override_db() -> AsyncGenerator[AsyncMock, None]:
        yield mock_db

    async def override_valkey() -> AsyncGenerator[AsyncMock, None]:
        yield mock_valkey

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_valkey] = override_valkey

    return app, mock_db, mock_valkey


# ── Unauthenticated ───────────────────────────────────────────────────────────


class TestUnauthenticated:
    """Verify that unauthenticated requests are rejected."""

    def test_list_targets_no_auth_returns_401(self) -> None:
        app, _, _ = _build_app(valkey_session=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/automation/targets")
        assert resp.status_code == 401

    def test_create_target_no_auth_returns_401(self) -> None:
        app, _, _ = _build_app(valkey_session=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/v1/automation/targets",
            json={"name": "test", "target_type": "webhook", "webhook_url": "https://x.io"},
        )
        assert resp.status_code == 401

    def test_list_deliveries_no_auth_returns_401(self) -> None:
        app, _, _ = _build_app(valkey_session=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/automation/deliveries")
        assert resp.status_code == 401


# ── Authenticated - List Targets ──────────────────────────────────────────────


class TestListTargets:
    """Test list_targets endpoint."""

    def test_list_targets_returns_empty_list(self) -> None:
        session_data = _make_session(roles=["super_admin"])
        mock_db = _make_mock_db_with_mapping(rows=[])
        app, _, _ = _build_app(valkey_session=session_data, db_mock=mock_db)
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        resp = client.get(
            "/api/v1/automation/targets",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        assert resp.json() == {"targets": []}

    def test_list_targets_returns_targets_without_secrets(self) -> None:
        session_data = _make_session(roles=["super_admin"])
        rows = [
            {
                "id": 1,
                "name": "My Webhook",
                "target_type": "webhook",
                "webhook_url": "https://example.com/hook",
                "webhook_secret": "super-secret",
                "dispatch_repo": None,
                "dispatch_event_type": None,
                "rule_ids": None,
                "rule_categories": None,
                "severity_filter": None,
                "org_filter": None,
                "is_catch_all": False,
                "rate_limit_per_minute": 100,
                "max_retries": 3,
                "enabled": True,
                "created_by": "admin",
                "created_at": "2025-01-01T00:00:00",
                "updated_at": None,
            }
        ]
        mock_db = _make_mock_db_with_mapping(rows=rows)
        app, _, _ = _build_app(valkey_session=session_data, db_mock=mock_db)
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        resp = client.get(
            "/api/v1/automation/targets",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["targets"]) == 1
        # webhook_secret must not be exposed
        assert "webhook_secret" not in data["targets"][0]


# ── Authenticated - Create Target ─────────────────────────────────────────────


class TestCreateTarget:
    """Test create_target endpoint."""

    def test_create_webhook_target_success(self) -> None:
        session_data = _make_session(roles=["super_admin"])
        mock_db = _make_mock_db(fetchone_return=(42,))
        app, db, _ = _build_app(valkey_session=session_data, db_mock=mock_db)
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        resp = client.post(
            "/api/v1/automation/targets",
            json={
                "name": "My Webhook",
                "target_type": "webhook",
                "webhook_url": "https://example.com/hook",
            },
            cookies={"access_token": token},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == 42
        assert data["status"] == "created"

    def test_create_repository_dispatch_target_success(self) -> None:
        session_data = _make_session(roles=["super_admin"])
        mock_db = _make_mock_db(fetchone_return=(7,))
        app, _, _ = _build_app(valkey_session=session_data, db_mock=mock_db)
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        resp = client.post(
            "/api/v1/automation/targets",
            json={
                "name": "Dispatch Target",
                "target_type": "repository_dispatch",
                "dispatch_repo": "org/repo",
                "dispatch_event_type": "alert",
            },
            cookies={"access_token": token},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == 7
        assert data["status"] == "created"

    def test_create_webhook_target_missing_url_returns_400(self) -> None:
        session_data = _make_session(roles=["super_admin"])
        mock_db = _make_mock_db()
        app, _, _ = _build_app(valkey_session=session_data, db_mock=mock_db)
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        resp = client.post(
            "/api/v1/automation/targets",
            json={
                "name": "Bad Webhook",
                "target_type": "webhook",
                # No webhook_url
            },
            cookies={"access_token": token},
        )
        assert resp.status_code == 400
        assert "webhook_url" in resp.json()["detail"]

    def test_create_dispatch_target_missing_repo_returns_400(self) -> None:
        session_data = _make_session(roles=["super_admin"])
        mock_db = _make_mock_db()
        app, _, _ = _build_app(valkey_session=session_data, db_mock=mock_db)
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        resp = client.post(
            "/api/v1/automation/targets",
            json={
                "name": "Bad Dispatch",
                "target_type": "repository_dispatch",
                # No dispatch_repo
            },
            cookies={"access_token": token},
        )
        assert resp.status_code == 400
        assert "dispatch_repo" in resp.json()["detail"]

    def test_create_target_invalid_type_returns_422(self) -> None:
        session_data = _make_session(roles=["super_admin"])
        mock_db = _make_mock_db()
        app, _, _ = _build_app(valkey_session=session_data, db_mock=mock_db)
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        resp = client.post(
            "/api/v1/automation/targets",
            json={
                "name": "Invalid",
                "target_type": "invalid_type",
            },
            cookies={"access_token": token},
        )
        assert resp.status_code == 422


# ── Authenticated - Get Target ────────────────────────────────────────────────


class TestGetTarget:
    """Test get_target endpoint."""

    def test_get_target_found(self) -> None:
        session_data = _make_session(roles=["super_admin"])
        single_row = {
            "id": 1,
            "name": "My Webhook",
            "target_type": "webhook",
            "webhook_url": "https://example.com/hook",
            "webhook_secret": "should-be-hidden",
            "enabled": True,
        }
        mock_db = _make_mock_db_with_mapping(single_row=single_row)
        app, _, _ = _build_app(valkey_session=session_data, db_mock=mock_db)
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        resp = client.get(
            "/api/v1/automation/targets/1",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == 1
        assert "webhook_secret" not in data

    def test_get_target_not_found(self) -> None:
        session_data = _make_session(roles=["super_admin"])
        mock_db = _make_mock_db_with_mapping(single_row=None)
        app, _, _ = _build_app(valkey_session=session_data, db_mock=mock_db)
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        resp = client.get(
            "/api/v1/automation/targets/999",
            cookies={"access_token": token},
        )
        assert resp.status_code == 404


# ── Authenticated - Update Target ─────────────────────────────────────────────


class TestUpdateTarget:
    """Test update_target endpoint."""

    def test_update_target_success(self) -> None:
        session_data = _make_session(roles=["super_admin"])
        mock_db = _make_mock_db(fetchone_return=(1,))
        app, _, _ = _build_app(valkey_session=session_data, db_mock=mock_db)
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        resp = client.patch(
            "/api/v1/automation/targets/1",
            json={"name": "Updated Name", "enabled": False},
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == 1
        assert data["status"] == "updated"

    def test_update_target_no_fields_returns_400(self) -> None:
        session_data = _make_session(roles=["super_admin"])
        mock_db = _make_mock_db()
        app, _, _ = _build_app(valkey_session=session_data, db_mock=mock_db)
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        resp = client.patch(
            "/api/v1/automation/targets/1",
            json={},
            cookies={"access_token": token},
        )
        assert resp.status_code == 400

    def test_update_target_not_found(self) -> None:
        session_data = _make_session(roles=["super_admin"])
        mock_db = _make_mock_db(fetchone_return=None)
        app, _, _ = _build_app(valkey_session=session_data, db_mock=mock_db)
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        resp = client.patch(
            "/api/v1/automation/targets/999",
            json={"name": "No such target"},
            cookies={"access_token": token},
        )
        assert resp.status_code == 404


# ── Authenticated - Delete Target ─────────────────────────────────────────────


class TestDeleteTarget:
    """Test delete_target endpoint."""

    def test_delete_target_success(self) -> None:
        session_data = _make_session(roles=["super_admin"])
        mock_db = _make_mock_db(fetchone_return=(5,))
        app, _, _ = _build_app(valkey_session=session_data, db_mock=mock_db)
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        resp = client.delete(
            "/api/v1/automation/targets/5",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == 5
        assert data["status"] == "deleted"

    def test_delete_target_not_found(self) -> None:
        session_data = _make_session(roles=["super_admin"])
        mock_db = _make_mock_db(fetchone_return=None)
        app, _, _ = _build_app(valkey_session=session_data, db_mock=mock_db)
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        resp = client.delete(
            "/api/v1/automation/targets/999",
            cookies={"access_token": token},
        )
        assert resp.status_code == 404


# ── Authenticated - List Deliveries ───────────────────────────────────────────


class TestListDeliveries:
    """Test list_deliveries endpoint."""

    def test_list_deliveries_empty(self) -> None:
        session_data = _make_session(roles=["super_admin"])
        mock_db = _make_mock_db_with_mapping(rows=[])
        app, _, _ = _build_app(valkey_session=session_data, db_mock=mock_db)
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        resp = client.get(
            "/api/v1/automation/deliveries",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        assert resp.json() == {"deliveries": []}

    def test_list_deliveries_with_filters(self) -> None:
        session_data = _make_session(roles=["super_admin"])
        rows = [
            {
                "id": 1,
                "target_id": 10,
                "detection_id": 100,
                "status": "delivered",
                "attempts": 1,
                "last_attempt_at": "2025-01-01T00:00:00",
                "next_retry_at": None,
                "response_code": 200,
                "error_message": None,
                "payload_hash": "abc123",
                "is_dry_run": False,
                "created_at": "2025-01-01T00:00:00",
                "target_name": "My Target",
                "target_type": "webhook",
            }
        ]
        mock_db = _make_mock_db_with_mapping(rows=rows)
        app, _, _ = _build_app(valkey_session=session_data, db_mock=mock_db)
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        resp = client.get(
            "/api/v1/automation/deliveries?target_id=10&status=delivered&limit=10",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["deliveries"]) == 1
        assert data["deliveries"][0]["target_id"] == 10


# ── Authenticated - Retry Delivery ────────────────────────────────────────────


class TestRetryDelivery:
    """Test retry_delivery endpoint."""

    @patch("app.routers.automation.retry_failed_deliveries_task", create=True)
    def test_retry_delivery_success(self, mock_task: MagicMock) -> None:
        session_data = _make_session(roles=["super_admin"])
        mock_db = _make_mock_db(fetchone_return=(100,))
        app, _, _ = _build_app(valkey_session=session_data, db_mock=mock_db)
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()

        with patch("app.workers.automation_worker.retry_failed_deliveries_task") as mocked_task:
            mocked_task.delay = MagicMock()
            resp = client.post(
                "/api/v1/automation/deliveries/1/retry",
                cookies={"access_token": token},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "retry_queued"

    def test_retry_delivery_not_found(self) -> None:
        session_data = _make_session(roles=["super_admin"])
        mock_db = _make_mock_db(fetchone_return=None)
        app, _, _ = _build_app(valkey_session=session_data, db_mock=mock_db)
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        resp = client.post(
            "/api/v1/automation/deliveries/999/retry",
            cookies={"access_token": token},
        )
        assert resp.status_code == 404


# ── Authenticated - Test Target ───────────────────────────────────────────────


class TestTestTarget:
    """Test test_target endpoint."""

    @patch("app.services.automation_service.deliver_webhook")
    @patch("app.services.automation_service.build_alert_payload")
    def test_test_target_webhook(self, mock_build: MagicMock, mock_deliver: MagicMock) -> None:
        session_data = _make_session(roles=["super_admin"])
        target_row = {
            "id": 1,
            "name": "Test Webhook",
            "target_type": "webhook",
            "webhook_url": "https://example.com/hook",
            "webhook_secret": None,
            "webhook_headers": None,
            "enabled": True,
        }
        mock_db = _make_mock_db_with_mapping(single_row=target_row)
        app, _, _ = _build_app(valkey_session=session_data, db_mock=mock_db)
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()

        mock_build.return_value = {"test": "payload"}
        mock_deliver.return_value = (200, None)

        resp = client.post(
            "/api/v1/automation/targets/1/test",
            json={},
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "test_sent"
        assert data["response_code"] == 200
        assert data["error"] is None


# ── Router Metadata ───────────────────────────────────────────────────────────


class TestRouterMetadata:
    """Verify router configuration."""

    def test_router_prefix(self) -> None:
        assert automation_module.router.prefix == "/automation"

    def test_router_tags(self) -> None:
        assert "automation" in automation_module.router.tags
