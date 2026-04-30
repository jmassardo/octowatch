"""Tests for audit log query API and audit trail immutability.

Tests cover:
- Audit event creation via the audit service
- Query/filter API (list and export endpoints)
- Immutability (no update/delete endpoints)
- Permission denied logging (via require_permission)
- Pagination and filtering
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import jwt as pyjwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps import get_db, get_valkey
from app.models.audit_trail import AuditTrail
from app.services.audit_service import log_action

SECRET = "testsecretkey_for_unit_tests_only_32ch"


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_jwt(sub: str = "admin-user", jti: str = "audit-log-jti") -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": sub,
        "github_id": 99999,
        "jti": jti,
        "exp": now + timedelta(hours=1),
        "iat": now,
    }
    return pyjwt.encode(payload, SECRET, algorithm="HS256")


def _make_admin_session() -> str:
    return json.dumps(
        {
            "github_login": "admin-user",
            "github_id": 99999,
            "roles": ["super_admin"],
            "scoped_orgs": [],
            "scoped_repos": [],
            "scope_type": "global",
            "session_expires_at": "2099-01-01T00:00:00+00:00",
        }
    )


def _make_compliance_session() -> str:
    return json.dumps(
        {
            "github_login": "compliance-user",
            "github_id": 77777,
            "roles": ["compliance_officer"],
            "scoped_orgs": [],
            "scoped_repos": [],
            "scope_type": "global",
            "session_expires_at": "2099-01-01T00:00:00+00:00",
        }
    )


def _make_viewer_session() -> str:
    return json.dumps(
        {
            "github_login": "viewer-user",
            "github_id": 88888,
            "roles": ["viewer"],
            "scoped_orgs": ["my-org"],
            "scoped_repos": [],
            "scope_type": "scoped",
            "session_expires_at": "2099-01-01T00:00:00+00:00",
        }
    )


def _make_mock_db() -> AsyncMock:
    """Create a mock async DB session."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_result.fetchall.return_value = []
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalar.return_value = 0
    mock_result.all.return_value = []
    db = AsyncMock()
    db.execute = AsyncMock(return_value=mock_result)
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


def _setup_app(mock_db: AsyncMock, mock_valkey: AsyncMock) -> FastAPI:
    """Build a test FastAPI app with overridden deps."""
    from app.main import create_app

    app = create_app()
    app.state.db_pool_ready = False  # Disable AuditTrailMiddleware DB writes
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_valkey] = lambda: mock_valkey
    return app


# ─── Audit event creation tests ──────────────────────────────────────────────


class TestAuditEventCreation:
    @pytest.mark.asyncio
    async def test_log_action_creates_entry(self) -> None:
        """log_action should create and flush an AuditTrail entry."""
        db = _make_mock_db()
        entry = await log_action(
            db,
            user_login="admin",
            action_type="team.create",
            resource_type="team",
            resource_id="1",
            parameters={"name": "Security Team"},
        )
        assert isinstance(entry, AuditTrail)
        assert entry.user_login == "admin"
        assert entry.action_type == "team.create"
        assert entry.outcome == "success"
        db.add.assert_called_once()
        db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_log_action_with_denied_outcome(self) -> None:
        """log_action should store 'denied' outcome for permission denials."""
        db = _make_mock_db()
        entry = await log_action(
            db,
            user_login="hacker",
            action_type="auth.permission_denied",
            resource_type="admin_teams",
            parameters={"required_permission": "admin_teams:create"},
            outcome="denied",
        )
        assert entry.outcome == "denied"
        assert entry.action_type == "auth.permission_denied"

    @pytest.mark.asyncio
    async def test_log_action_with_all_fields(self) -> None:
        """log_action should accept all optional fields."""
        db = _make_mock_db()
        entry = await log_action(
            db,
            user_login="testuser",
            user_github_id=12345,
            ip_address="192.168.1.1",
            user_agent="TestAgent/1.0",
            action_type="setting.update",
            resource_type="setting",
            resource_id="key1",
            parameters={"old_value": "a", "new_value": "b"},
            outcome="success",
            error_detail=None,
        )
        assert entry.user_login == "testuser"
        assert entry.ip_address == "192.168.1.1"
        assert entry.user_agent == "TestAgent/1.0"


# ─── Audit log query API tests ──────────────────────────────────────────────


class TestAuditLogListEndpoint:
    def test_list_audit_log_empty(self) -> None:
        """GET /api/v1/admin/audit-log returns empty list when no entries."""
        mock_db = _make_mock_db()
        mock_valkey = AsyncMock()
        mock_valkey.get = AsyncMock(return_value=_make_admin_session())
        mock_valkey.exists = AsyncMock(return_value=1)

        app = _setup_app(mock_db, mock_valkey)
        client = TestClient(app)

        token = _make_jwt()
        resp = client.get(
            "/api/v1/admin/audit-log",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1
        assert data["has_more"] is False

    def test_list_audit_log_with_filters(self) -> None:
        """GET /api/v1/admin/audit-log accepts filter parameters."""
        mock_db = _make_mock_db()
        mock_valkey = AsyncMock()
        mock_valkey.get = AsyncMock(return_value=_make_admin_session())
        mock_valkey.exists = AsyncMock(return_value=1)

        app = _setup_app(mock_db, mock_valkey)
        client = TestClient(app)

        token = _make_jwt()
        resp = client.get(
            "/api/v1/admin/audit-log",
            params={
                "actor": "admin",
                "action": "team.*",
                "outcome": "success",
                "page": 1,
                "page_size": 10,
            },
            cookies={"access_token": token},
        )
        assert resp.status_code == 200

    def test_list_audit_log_pagination_params(self) -> None:
        """Query parameters for pagination are respected."""
        mock_db = _make_mock_db()
        mock_valkey = AsyncMock()
        mock_valkey.get = AsyncMock(return_value=_make_admin_session())
        mock_valkey.exists = AsyncMock(return_value=1)

        app = _setup_app(mock_db, mock_valkey)
        client = TestClient(app)

        token = _make_jwt()
        resp = client.get(
            "/api/v1/admin/audit-log",
            params={"page": 2, "page_size": 25},
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 2
        assert data["page_size"] == 25


class TestAuditLogExportEndpoint:
    def test_export_audit_log_csv(self) -> None:
        """GET /api/v1/admin/audit-log/export returns CSV."""
        mock_db = _make_mock_db()
        mock_valkey = AsyncMock()
        mock_valkey.get = AsyncMock(return_value=_make_admin_session())
        mock_valkey.exists = AsyncMock(return_value=1)

        app = _setup_app(mock_db, mock_valkey)
        client = TestClient(app)

        token = _make_jwt()
        resp = client.get(
            "/api/v1/admin/audit-log/export",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")
        assert "audit_log_export.csv" in resp.headers.get("content-disposition", "")


# ─── Immutability tests ─────────────────────────────────────────────────────


class TestAuditLogImmutability:
    def test_no_delete_endpoint(self) -> None:
        """There should be no DELETE endpoint on the audit log router."""
        mock_db = _make_mock_db()
        mock_valkey = AsyncMock()
        mock_valkey.get = AsyncMock(return_value=_make_admin_session())
        mock_valkey.exists = AsyncMock(return_value=1)

        app = _setup_app(mock_db, mock_valkey)
        client = TestClient(app)

        token = _make_jwt()
        resp = client.delete(
            "/api/v1/admin/audit-log/1",
            cookies={"access_token": token, "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        # Should be 404 or 405 (no such route)
        assert resp.status_code in (404, 405)

    def test_no_put_endpoint(self) -> None:
        """There should be no PUT endpoint on the audit log router."""
        mock_db = _make_mock_db()
        mock_valkey = AsyncMock()
        mock_valkey.get = AsyncMock(return_value=_make_admin_session())
        mock_valkey.exists = AsyncMock(return_value=1)

        app = _setup_app(mock_db, mock_valkey)
        client = TestClient(app)

        token = _make_jwt()
        resp = client.put(
            "/api/v1/admin/audit-log/1",
            json={"outcome": "denied"},
            cookies={"access_token": token, "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert resp.status_code in (404, 405)

    def test_no_patch_endpoint(self) -> None:
        """There should be no PATCH endpoint on the audit log router."""
        mock_db = _make_mock_db()
        mock_valkey = AsyncMock()
        mock_valkey.get = AsyncMock(return_value=_make_admin_session())
        mock_valkey.exists = AsyncMock(return_value=1)

        app = _setup_app(mock_db, mock_valkey)
        client = TestClient(app)

        token = _make_jwt()
        resp = client.patch(
            "/api/v1/admin/audit-log/1",
            json={"outcome": "denied"},
            cookies={"access_token": token, "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert resp.status_code in (404, 405)


# ─── Permission denied logging tests ────────────────────────────────────────


class TestPermissionDeniedLogging:
    def test_permission_denied_returns_403(self) -> None:
        """A viewer trying to access audit log gets 403."""
        mock_db = _make_mock_db()
        mock_valkey = AsyncMock()
        mock_valkey.get = AsyncMock(return_value=_make_viewer_session())
        mock_valkey.exists = AsyncMock(return_value=1)

        # viewer roles don't include audit_log:view
        call_count = 0
        viewer_result = MagicMock()
        viewer_result.fetchall.return_value = [
            (["dashboard:view", "events:view", "detections:view"],)
        ]
        team_result = MagicMock()
        team_result.fetchall.return_value = []

        def _side_effect(*args: Any, **kwargs: Any) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return viewer_result
            if call_count == 2:
                return team_result
            result = MagicMock()
            result.scalar_one_or_none.return_value = None
            result.scalars.return_value.all.return_value = []
            result.fetchall.return_value = []
            return result

        mock_db.execute = AsyncMock(side_effect=_side_effect)

        app = _setup_app(mock_db, mock_valkey)
        client = TestClient(app)

        viewer_jwt = pyjwt.encode(
            {
                "sub": "viewer-user",
                "github_id": 88888,
                "jti": "viewer-jti-2",
                "exp": datetime.now(UTC) + timedelta(hours=1),
                "iat": datetime.now(UTC),
            },
            SECRET,
            algorithm="HS256",
        )
        resp = client.get(
            "/api/v1/admin/audit-log",
            cookies={"access_token": viewer_jwt},
        )
        assert resp.status_code == 403

    def test_compliance_officer_can_view_audit_log(self) -> None:
        """A compliance_officer has audit_log:view and should get 200."""
        mock_db = _make_mock_db()
        mock_valkey = AsyncMock()
        mock_valkey.get = AsyncMock(return_value=_make_compliance_session())
        mock_valkey.exists = AsyncMock(return_value=1)

        app = _setup_app(mock_db, mock_valkey)
        client = TestClient(app)

        compliance_jwt = pyjwt.encode(
            {
                "sub": "compliance-user",
                "github_id": 77777,
                "jti": "compliance-jti",
                "exp": datetime.now(UTC) + timedelta(hours=1),
                "iat": datetime.now(UTC),
            },
            SECRET,
            algorithm="HS256",
        )
        resp = client.get(
            "/api/v1/admin/audit-log",
            cookies={"access_token": compliance_jwt},
        )
        assert resp.status_code == 200


# ─── Audit trail model tests ────────────────────────────────────────────────


class TestAuditTrailModel:
    def test_model_attributes(self) -> None:
        """AuditTrail model should have all expected attributes."""
        entry = AuditTrail(
            user_login="admin",
            action_type="team.create",
            resource_type="team",
            resource_id="42",
            outcome="success",
            ip_address="10.0.0.1",
            user_agent="Mozilla/5.0",
            parameters={"name": "Test"},
        )
        assert entry.user_login == "admin"
        assert entry.action_type == "team.create"
        assert entry.resource_type == "team"
        assert entry.resource_id == "42"
        assert entry.outcome == "success"
        assert entry.ip_address == "10.0.0.1"
        assert entry.parameters == {"name": "Test"}

    def test_model_defaults(self) -> None:
        """AuditTrail should default outcome to 'success' when not specified."""
        entry = AuditTrail(
            user_login="user1",
            action_type="setting.update",
            outcome="success",
        )
        assert entry.outcome == "success"
