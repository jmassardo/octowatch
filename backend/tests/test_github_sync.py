"""Unit tests for the GitHub sync schemas, config, and router."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, get_valkey
from app.routers import sync as sync_router_module
from app.schemas.github_sync import (
    CursorRow,
    SyncConfigResponse,
    SyncConfigUpdateRequest,
    SyncRunDetail,
    SyncRunsResponse,
    SyncRunSummary,
    SyncTriggerRequest,
    SyncTriggerResponse,
)

SECRET = "testsecretkey_for_unit_tests_only_32ch"


# ─── Schema Tests ─────────────────────────────────────────────────────────────


class TestSyncTriggerRequest:
    def test_default_scope_is_full(self) -> None:
        req = SyncTriggerRequest()
        assert req.scope == "full"

    def test_valid_scope_values(self) -> None:
        for scope in [
            "full",
            "orgs",
            "enterprise_members",
            "org_members",
            "repositories",
            "teams",
            "team_members",
            "branch_protections",
            "installations",
        ]:
            req = SyncTriggerRequest(scope=scope)
            assert req.scope == scope

    def test_invalid_scope_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SyncTriggerRequest(scope="invalid")


class TestSyncConfigUpdateRequest:
    def test_all_fields_optional(self) -> None:
        req = SyncConfigUpdateRequest()
        assert req.sync_enabled is None
        assert req.interval_days is None
        assert req.orgs is None

    def test_valid_interval(self) -> None:
        req = SyncConfigUpdateRequest(interval_days=75)
        assert req.interval_days == 75

    def test_interval_too_low_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SyncConfigUpdateRequest(interval_days=30)

    def test_interval_too_high_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SyncConfigUpdateRequest(interval_days=100)

    def test_interval_min_boundary(self) -> None:
        req = SyncConfigUpdateRequest(interval_days=60)
        assert req.interval_days == 60

    def test_interval_max_boundary(self) -> None:
        req = SyncConfigUpdateRequest(interval_days=90)
        assert req.interval_days == 90


class TestSyncTriggerResponse:
    def test_create_response(self) -> None:
        run_id = uuid.uuid4()
        resp = SyncTriggerResponse(run_id=run_id, status="pending")
        assert resp.run_id == run_id
        assert resp.status == "pending"


class TestCursorRow:
    def test_from_attributes(self) -> None:
        """CursorRow must be constructable from ORM-like objects."""

        class FakeCursor:
            entity_type = "orgs"
            org = None
            last_cursor = "abc123"
            items_synced = 42
            status = "completed"

        cursor = CursorRow.model_validate(FakeCursor())
        assert cursor.entity_type == "orgs"
        assert cursor.org is None
        assert cursor.items_synced == 42


class TestSyncRunDetail:
    def test_from_attributes_with_cursors(self) -> None:

        class FakeRun:
            id = uuid.uuid4()
            status = "completed"
            trigger_type = "manual"
            triggered_by = "testuser"
            scope = "full"
            started_at = datetime(2024, 1, 1, tzinfo=UTC)
            completed_at = datetime(2024, 1, 1, 1, 0, tzinfo=UTC)
            error_message = None
            entity_counts = {"orgs": 5}

        detail = SyncRunDetail.model_validate(FakeRun())
        assert detail.status == "completed"
        assert detail.cursors == []


class TestSyncRunSummary:
    def test_minimal_summary(self) -> None:

        class FakeRun:
            id = uuid.uuid4()
            status = "pending"
            trigger_type = "scheduled"
            triggered_by = None
            started_at = None
            completed_at = None

        summary = SyncRunSummary.model_validate(FakeRun())
        assert summary.trigger_type == "scheduled"
        assert summary.triggered_by is None


class TestSyncRunsResponse:
    def test_pagination_fields(self) -> None:
        resp = SyncRunsResponse(items=[], total=0, page=1, page_size=20, has_next=False)
        assert resp.total == 0
        assert resp.has_next is False


class TestSyncConfigResponse:
    def test_never_includes_private_key(self) -> None:
        resp = SyncConfigResponse(
            app_id=123,
            enterprise_slug="my-corp",
            installation_ids=[{"org": "acme", "installation_id": 456}],
            sync_enabled=True,
            interval_days=60,
            orgs=["acme"],
        )
        dumped = resp.model_dump()
        # Ensure no private key field exists
        assert "private_key" not in dumped
        assert "private_key_path" not in dumped
        assert resp.app_id == 123


# ─── Config Tests ─────────────────────────────────────────────────────────────


class TestGitHubAppSettings:
    def test_default_values(self) -> None:
        from app.config import GitHubAppSettings

        s = GitHubAppSettings()
        assert s.GITHUB_APP_ID is None
        assert s.GITHUB_APP_PRIVATE_KEY_PATH is None
        assert s.GITHUB_ENTERPRISE_SLUG is None
        assert s.GITHUB_SYNC_INTERVAL_DAYS == 60
        assert s.GITHUB_SYNC_ENABLED is False
        assert s.GITHUB_SYNC_ORGS == []

    def test_valid_enterprise_slug(self) -> None:
        from app.config import GitHubAppSettings

        s = GitHubAppSettings(GITHUB_ENTERPRISE_SLUG="my-company")
        assert s.GITHUB_ENTERPRISE_SLUG == "my-company"

    def test_alphanumeric_slug(self) -> None:
        from app.config import GitHubAppSettings

        s = GitHubAppSettings(GITHUB_ENTERPRISE_SLUG="MyCompany123")
        assert s.GITHUB_ENTERPRISE_SLUG == "MyCompany123"

    def test_invalid_slug_with_spaces_rejected(self) -> None:
        from app.config import GitHubAppSettings

        with pytest.raises(ValidationError):
            GitHubAppSettings(GITHUB_ENTERPRISE_SLUG="my company")

    def test_invalid_slug_with_special_chars_rejected(self) -> None:
        from app.config import GitHubAppSettings

        with pytest.raises(ValidationError):
            GitHubAppSettings(GITHUB_ENTERPRISE_SLUG="my_company@!")

    def test_interval_min_boundary(self) -> None:
        from app.config import GitHubAppSettings

        s = GitHubAppSettings(GITHUB_SYNC_INTERVAL_DAYS=60)
        assert s.GITHUB_SYNC_INTERVAL_DAYS == 60

    def test_interval_max_boundary(self) -> None:
        from app.config import GitHubAppSettings

        s = GitHubAppSettings(GITHUB_SYNC_INTERVAL_DAYS=90)
        assert s.GITHUB_SYNC_INTERVAL_DAYS == 90

    def test_interval_below_min_rejected(self) -> None:
        from app.config import GitHubAppSettings

        with pytest.raises(ValidationError):
            GitHubAppSettings(GITHUB_SYNC_INTERVAL_DAYS=59)

    def test_interval_above_max_rejected(self) -> None:
        from app.config import GitHubAppSettings

        with pytest.raises(ValidationError):
            GitHubAppSettings(GITHUB_SYNC_INTERVAL_DAYS=91)

    def test_nonexistent_key_path_rejected(self) -> None:
        from app.config import GitHubAppSettings

        with pytest.raises(ValidationError):
            GitHubAppSettings(GITHUB_APP_PRIVATE_KEY_PATH="/nonexistent/key.pem")

    def test_none_key_path_accepted(self) -> None:
        from app.config import GitHubAppSettings

        s = GitHubAppSettings(GITHUB_APP_PRIVATE_KEY_PATH=None)
        assert s.GITHUB_APP_PRIVATE_KEY_PATH is None

    def test_none_slug_accepted(self) -> None:
        from app.config import GitHubAppSettings

        s = GitHubAppSettings(GITHUB_ENTERPRISE_SLUG=None)
        assert s.GITHUB_ENTERPRISE_SLUG is None

    def test_settings_has_github_app(self) -> None:
        """Verify the github_app property exists on the main Settings object."""
        from app.config import settings

        assert hasattr(settings, "github_app")
        assert settings.github_app is not None
        assert settings.github_app.GITHUB_SYNC_ENABLED is False


# ─── Router Tests ─────────────────────────────────────────────────────────────


def _make_jwt(sub: str = "admin", jti: str = "sync-jti") -> str:
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
            "github_login": "admin",
            "github_id": 99999,
            "roles": ["sys_admin"],
            "scoped_orgs": [],
            "scoped_repos": [],
            "scope_type": "global",
            "session_expires_at": "2099-01-01T00:00:00+00:00",
        }
    )


def _make_analyst_session() -> str:
    return json.dumps(
        {
            "github_login": "analyst",
            "github_id": 11111,
            "roles": ["analyst"],
            "scoped_orgs": ["my-org"],
            "scoped_repos": [],
            "scope_type": "scoped",
            "session_expires_at": "2099-01-01T00:00:00+00:00",
        }
    )


def _make_mock_db() -> AsyncMock:
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalar_one.return_value = 0
    db = AsyncMock(spec=AsyncSession)
    db.execute = AsyncMock(return_value=mock_result)
    db.add = MagicMock()
    db.commit = AsyncMock()
    return db


def _build_sync_app(
    valkey_session: str | None = None,
) -> tuple[FastAPI, AsyncMock, AsyncMock]:
    app = FastAPI()
    app.include_router(sync_router_module.router, prefix="/api/v1/admin")

    mock_db = _make_mock_db()
    mock_valkey = AsyncMock()
    mock_valkey.get = AsyncMock(return_value=valkey_session)
    mock_valkey.ping = AsyncMock(return_value=True)
    mock_valkey.aclose = AsyncMock()

    async def override_db() -> AsyncSession:  # type: ignore[misc]
        yield mock_db  # type: ignore[misc]

    async def override_valkey() -> AsyncMock:  # type: ignore[misc]
        yield mock_valkey  # type: ignore[misc]

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_valkey] = override_valkey

    return app, mock_db, mock_valkey


class TestSyncRouterAuth:
    """Verify that all sync endpoints require sys_admin role."""

    def test_trigger_unauthenticated_returns_401(self) -> None:
        app, _, _ = _build_sync_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/api/v1/admin/sync/trigger", json={"scope": "full"})
        assert resp.status_code == 401

    def test_trigger_non_admin_returns_403(self) -> None:
        app, _, _ = _build_sync_app(valkey_session=_make_analyst_session())
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt(sub="analyst", jti="analyst-jti")
        client.cookies.set("access_token", token)
        resp = client.post("/api/v1/admin/sync/trigger", json={"scope": "full"})
        assert resp.status_code == 403

    def test_status_unauthenticated_returns_401(self) -> None:
        app, _, _ = _build_sync_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/admin/sync/status")
        assert resp.status_code == 401

    def test_runs_unauthenticated_returns_401(self) -> None:
        app, _, _ = _build_sync_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/admin/sync/runs")
        assert resp.status_code == 401

    def test_config_unauthenticated_returns_401(self) -> None:
        app, _, _ = _build_sync_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/admin/sync/config")
        assert resp.status_code == 401


class TestTriggerSync:
    """Tests for POST /sync/trigger endpoint."""

    @patch("app.routers.sync.settings")
    def test_trigger_returns_202_when_no_active_run(self, mock_settings: MagicMock) -> None:
        mock_settings.github_app.GITHUB_APP_ID = None
        mock_settings.github_app.GITHUB_ENTERPRISE_SLUG = None
        mock_settings.github_app.GITHUB_SYNC_ENABLED = False
        mock_settings.github_app.GITHUB_SYNC_INTERVAL_DAYS = 60
        mock_settings.github_app.GITHUB_SYNC_ORGS = []

        app, mock_db, _ = _build_sync_app(valkey_session=_make_admin_session())
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        client.cookies.set("access_token", token)

        # Mock: no active run found
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("app.workers.github_sync_worker.run_enterprise_sync") as mock_task:
            mock_task.apply_async = MagicMock()
            resp = client.post("/api/v1/admin/sync/trigger", json={"scope": "full"})

        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "pending"
        assert "run_id" in data

    def test_trigger_conflict_when_run_active(self) -> None:
        app, mock_db, _ = _build_sync_app(valkey_session=_make_admin_session())
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        client.cookies.set("access_token", token)

        # Mock: an active run exists
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = MagicMock(status="running")
        mock_db.execute = AsyncMock(return_value=mock_result)

        resp = client.post("/api/v1/admin/sync/trigger", json={"scope": "full"})
        assert resp.status_code == 409


class TestGetSyncStatus:
    """Tests for GET /sync/status endpoint."""

    def test_status_returns_404_when_no_runs(self) -> None:
        app, mock_db, _ = _build_sync_app(valkey_session=_make_admin_session())
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        client.cookies.set("access_token", token)

        # Mock: no runs found
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        resp = client.get("/api/v1/admin/sync/status")
        assert resp.status_code == 404


class TestListSyncRuns:
    """Tests for GET /sync/runs endpoint."""

    def test_runs_returns_empty_list(self) -> None:
        app, mock_db, _ = _build_sync_app(valkey_session=_make_admin_session())
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        client.cookies.set("access_token", token)

        # Mock: count returns 0, runs returns empty list
        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 0
        mock_runs_result = MagicMock()
        mock_runs_result.scalars.return_value.all.return_value = []

        call_count = 0

        async def mock_execute(*args: object, **kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_count_result
            return mock_runs_result

        mock_db.execute = AsyncMock(side_effect=mock_execute)

        resp = client.get("/api/v1/admin/sync/runs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []
        assert data["has_next"] is False


class TestGetRunDetail:
    """Tests for GET /sync/runs/{run_id} endpoint."""

    def test_run_not_found_returns_404(self) -> None:
        app, mock_db, _ = _build_sync_app(valkey_session=_make_admin_session())
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        client.cookies.set("access_token", token)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        run_id = uuid.uuid4()
        resp = client.get(f"/api/v1/admin/sync/runs/{run_id}")
        assert resp.status_code == 404


class TestCancelRun:
    """Tests for DELETE /sync/runs/{run_id}/cancel endpoint."""

    def test_cancel_not_found_returns_404(self) -> None:
        app, mock_db, _ = _build_sync_app(valkey_session=_make_admin_session())
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        client.cookies.set("access_token", token)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        run_id = uuid.uuid4()
        resp = client.delete(f"/api/v1/admin/sync/runs/{run_id}/cancel")
        assert resp.status_code == 404

    def test_cancel_terminal_state_returns_409(self) -> None:
        app, mock_db, _ = _build_sync_app(valkey_session=_make_admin_session())
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        client.cookies.set("access_token", token)

        # Mock: run exists but is completed
        mock_run = MagicMock()
        mock_run.status = "completed"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_run
        mock_db.execute = AsyncMock(return_value=mock_result)

        run_id = uuid.uuid4()
        resp = client.delete(f"/api/v1/admin/sync/runs/{run_id}/cancel")
        assert resp.status_code == 409
