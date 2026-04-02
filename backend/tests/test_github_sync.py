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
    VALID_INTERVAL_HOURS,
    CursorRow,
    SyncConfigResponse,
    SyncConfigUpdateRequest,
    SyncRunDetail,
    SyncRunsResponse,
    SyncRunSummary,
    SyncScheduleResponse,
    SyncScheduleUpdateRequest,
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
            "outside_collaborators",
            "secret_scanning_alerts",
            "dependabot_alerts",
            "license_consumption",
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


class TestUpdateSyncConfig:
    """Tests for PUT /sync/config endpoint."""

    @patch("app.routers.sync.settings")
    def test_update_config_persists_all_fields(self, mock_settings: MagicMock) -> None:
        mock_settings.github_app.GITHUB_APP_ID = 42
        mock_settings.github_app.GITHUB_ENTERPRISE_SLUG = "test-corp"
        mock_settings.github_app.GITHUB_SYNC_ENABLED = False
        mock_settings.github_app.GITHUB_SYNC_INTERVAL_DAYS = 60
        mock_settings.github_app.GITHUB_SYNC_ORGS = []

        app, mock_db, _ = _build_sync_app(valkey_session=_make_admin_session())
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        client.cookies.set("access_token", token)

        # Mock the GET config call after update
        mock_configs_result = MagicMock()
        mock_configs_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_configs_result)

        resp = client.put(
            "/api/v1/admin/sync/config",
            json={"sync_enabled": True, "interval_days": 75, "orgs": ["acme", "widgets"]},
        )
        assert resp.status_code == 200

        # Verify in-memory settings were updated
        assert mock_settings.github_app.GITHUB_SYNC_ENABLED is True
        assert mock_settings.github_app.GITHUB_SYNC_INTERVAL_DAYS == 75
        assert mock_settings.github_app.GITHUB_SYNC_ORGS == ["acme", "widgets"]

    @patch("app.routers.sync.settings")
    def test_update_config_partial_update_interval_only(self, mock_settings: MagicMock) -> None:
        mock_settings.github_app.GITHUB_APP_ID = None
        mock_settings.github_app.GITHUB_ENTERPRISE_SLUG = None
        mock_settings.github_app.GITHUB_SYNC_ENABLED = False
        mock_settings.github_app.GITHUB_SYNC_INTERVAL_DAYS = 60
        mock_settings.github_app.GITHUB_SYNC_ORGS = []

        app, mock_db, _ = _build_sync_app(valkey_session=_make_admin_session())
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        client.cookies.set("access_token", token)

        mock_configs_result = MagicMock()
        mock_configs_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_configs_result)

        resp = client.put(
            "/api/v1/admin/sync/config",
            json={"interval_days": 80},
        )
        assert resp.status_code == 200

        # Only interval_days should change
        assert mock_settings.github_app.GITHUB_SYNC_INTERVAL_DAYS == 80
        # sync_enabled and orgs should remain unchanged
        assert mock_settings.github_app.GITHUB_SYNC_ENABLED is False
        assert mock_settings.github_app.GITHUB_SYNC_ORGS == []

    @patch("app.routers.sync.settings")
    def test_update_config_partial_update_orgs_only(self, mock_settings: MagicMock) -> None:
        mock_settings.github_app.GITHUB_APP_ID = None
        mock_settings.github_app.GITHUB_ENTERPRISE_SLUG = None
        mock_settings.github_app.GITHUB_SYNC_ENABLED = False
        mock_settings.github_app.GITHUB_SYNC_INTERVAL_DAYS = 60
        mock_settings.github_app.GITHUB_SYNC_ORGS = []

        app, mock_db, _ = _build_sync_app(valkey_session=_make_admin_session())
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        client.cookies.set("access_token", token)

        mock_configs_result = MagicMock()
        mock_configs_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_configs_result)

        resp = client.put(
            "/api/v1/admin/sync/config",
            json={"orgs": ["org-a", "org-b"]},
        )
        assert resp.status_code == 200
        assert mock_settings.github_app.GITHUB_SYNC_ORGS == ["org-a", "org-b"]
        assert mock_settings.github_app.GITHUB_SYNC_INTERVAL_DAYS == 60

    def test_update_config_rejects_invalid_interval(self) -> None:
        app, _, _ = _build_sync_app(valkey_session=_make_admin_session())
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        client.cookies.set("access_token", token)

        resp = client.put(
            "/api/v1/admin/sync/config",
            json={"interval_days": 30},
        )
        assert resp.status_code == 422

    def test_update_config_unauthenticated_returns_401(self) -> None:
        app, _, _ = _build_sync_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.put("/api/v1/admin/sync/config", json={"sync_enabled": True})
        assert resp.status_code == 401


# ─── Schedule Schema Tests ────────────────────────────────────────────────────


class TestSyncScheduleResponse:
    def test_default_values(self) -> None:
        resp = SyncScheduleResponse()
        assert resp.enabled is False
        assert resp.interval_hours == 24
        assert resp.scope == "full"
        assert resp.next_run_at is None
        assert resp.last_completed_at is None

    def test_with_all_fields(self) -> None:
        now = datetime.now(UTC)
        resp = SyncScheduleResponse(
            enabled=True,
            interval_hours=12,
            scope="repositories",
            next_run_at=now,
            last_completed_at=now,
        )
        assert resp.enabled is True
        assert resp.interval_hours == 12
        assert resp.scope == "repositories"
        assert resp.next_run_at == now
        assert resp.last_completed_at == now


class TestSyncScheduleUpdateRequest:
    def test_all_fields_optional(self) -> None:
        req = SyncScheduleUpdateRequest()
        assert req.enabled is None
        assert req.interval_hours is None
        assert req.scope is None

    def test_valid_interval_values(self) -> None:
        for hours in sorted(VALID_INTERVAL_HOURS):
            req = SyncScheduleUpdateRequest(interval_hours=hours)
            assert req.interval_hours == hours

    def test_invalid_interval_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SyncScheduleUpdateRequest(interval_hours=10)

    def test_invalid_interval_rejected_zero(self) -> None:
        with pytest.raises(ValidationError):
            SyncScheduleUpdateRequest(interval_hours=0)

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
            "outside_collaborators",
            "secret_scanning_alerts",
            "dependabot_alerts",
            "license_consumption",
        ]:
            req = SyncScheduleUpdateRequest(scope=scope)
            assert req.scope == scope

    def test_invalid_scope_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SyncScheduleUpdateRequest(scope="invalid_scope")

    def test_partial_update(self) -> None:
        req = SyncScheduleUpdateRequest(enabled=True)
        assert req.enabled is True
        assert req.interval_hours is None
        assert req.scope is None


# ─── Schedule Router Tests ────────────────────────────────────────────────────


class TestGetSyncSchedule:
    """Tests for GET /sync/schedule endpoint."""

    def test_schedule_unauthenticated_returns_401(self) -> None:
        app, _, _ = _build_sync_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/admin/sync/schedule")
        assert resp.status_code == 401

    def test_schedule_non_admin_returns_403(self) -> None:
        app, _, _ = _build_sync_app(valkey_session=_make_analyst_session())
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt(sub="analyst", jti="analyst-jti")
        client.cookies.set("access_token", token)
        resp = client.get("/api/v1/admin/sync/schedule")
        assert resp.status_code == 403

    @patch("app.routers.sync.get_setting", new_callable=AsyncMock)
    def test_schedule_returns_defaults_when_no_db_settings(
        self, mock_get_setting: AsyncMock
    ) -> None:
        mock_get_setting.return_value = None

        app, mock_db, _ = _build_sync_app(valkey_session=_make_admin_session())
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        client.cookies.set("access_token", token)

        resp = client.get("/api/v1/admin/sync/schedule")
        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is False
        assert data["interval_hours"] == 24
        assert data["scope"] == "full"
        assert data["next_run_at"] is None
        assert data["last_completed_at"] is None

    @patch("app.routers.sync.get_setting", new_callable=AsyncMock)
    def test_schedule_returns_db_settings(self, mock_get_setting: AsyncMock) -> None:
        settings_map = {
            "sync_schedule_enabled": "true",
            "sync_schedule_interval_hours": "12",
            "sync_schedule_scope": "repositories",
        }
        mock_get_setting.side_effect = lambda db, key: settings_map.get(key)

        app, mock_db, _ = _build_sync_app(valkey_session=_make_admin_session())
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        client.cookies.set("access_token", token)

        resp = client.get("/api/v1/admin/sync/schedule")
        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is True
        assert data["interval_hours"] == 12
        assert data["scope"] == "repositories"


class TestUpdateSyncSchedule:
    """Tests for PUT /sync/schedule endpoint."""

    def test_schedule_update_unauthenticated_returns_401(self) -> None:
        app, _, _ = _build_sync_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.put("/api/v1/admin/sync/schedule", json={"enabled": True})
        assert resp.status_code == 401

    @patch("app.routers.sync.get_setting", new_callable=AsyncMock)
    @patch("app.routers.sync.set_setting", new_callable=AsyncMock)
    def test_schedule_update_enabled(
        self,
        mock_set_setting: AsyncMock,
        mock_get_setting: AsyncMock,
    ) -> None:
        # After update, get_setting returns the new values for the GET call
        settings_map = {
            "sync_schedule_enabled": "true",
            "sync_schedule_interval_hours": "24",
            "sync_schedule_scope": "full",
        }
        mock_get_setting.side_effect = lambda db, key: settings_map.get(key)

        app, mock_db, _ = _build_sync_app(valkey_session=_make_admin_session())
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        client.cookies.set("access_token", token)

        resp = client.put(
            "/api/v1/admin/sync/schedule",
            json={"enabled": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is True

        # Verify set_setting was called
        mock_set_setting.assert_called_once()
        call_args = mock_set_setting.call_args
        assert call_args[0][1] == "sync_schedule_enabled"
        assert call_args[0][2] == "true"

    @patch("app.routers.sync.get_setting", new_callable=AsyncMock)
    @patch("app.routers.sync.set_setting", new_callable=AsyncMock)
    def test_schedule_update_all_fields(
        self,
        mock_set_setting: AsyncMock,
        mock_get_setting: AsyncMock,
    ) -> None:
        settings_map = {
            "sync_schedule_enabled": "true",
            "sync_schedule_interval_hours": "48",
            "sync_schedule_scope": "teams",
        }
        mock_get_setting.side_effect = lambda db, key: settings_map.get(key)

        app, mock_db, _ = _build_sync_app(valkey_session=_make_admin_session())
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        client.cookies.set("access_token", token)

        resp = client.put(
            "/api/v1/admin/sync/schedule",
            json={"enabled": True, "interval_hours": 48, "scope": "teams"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["interval_hours"] == 48
        assert data["scope"] == "teams"

        # set_setting called 3 times (enabled, interval_hours, scope)
        assert mock_set_setting.call_count == 3

    def test_schedule_update_invalid_interval_returns_422(self) -> None:
        app, _, _ = _build_sync_app(valkey_session=_make_admin_session())
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        client.cookies.set("access_token", token)

        resp = client.put(
            "/api/v1/admin/sync/schedule",
            json={"interval_hours": 15},
        )
        assert resp.status_code == 422

    def test_schedule_update_invalid_scope_returns_422(self) -> None:
        app, _, _ = _build_sync_app(valkey_session=_make_admin_session())
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        client.cookies.set("access_token", token)

        resp = client.put(
            "/api/v1/admin/sync/schedule",
            json={"scope": "invalid_scope"},
        )
        assert resp.status_code == 422

    @patch("app.routers.sync.get_setting", new_callable=AsyncMock)
    @patch("app.routers.sync.set_setting", new_callable=AsyncMock)
    def test_schedule_update_empty_body_no_settings_changed(
        self,
        mock_set_setting: AsyncMock,
        mock_get_setting: AsyncMock,
    ) -> None:
        mock_get_setting.return_value = None

        app, mock_db, _ = _build_sync_app(valkey_session=_make_admin_session())
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        client.cookies.set("access_token", token)

        resp = client.put(
            "/api/v1/admin/sync/schedule",
            json={},
        )
        assert resp.status_code == 200
        # No settings should have been written
        mock_set_setting.assert_not_called()


# ─── Sync Log Schema Tests ───────────────────────────────────────────────────


class TestSyncLogEntryResponse:
    def test_from_attributes(self):
        from app.schemas.github_sync import SyncLogEntryResponse

        class FakeEntry:
            seq = 1
            timestamp = datetime(2025, 1, 1, tzinfo=UTC)
            level = "info"
            message = "Starting enterprise sync"
            entity_type = None
            org = None
            details = None

        entry = SyncLogEntryResponse.model_validate(FakeEntry())
        assert entry.seq == 1
        assert entry.level == "info"
        assert entry.message == "Starting enterprise sync"
        assert entry.entity_type is None
        assert entry.org is None
        assert entry.details is None

    def test_from_attributes_with_all_fields(self):
        from app.schemas.github_sync import SyncLogEntryResponse

        class FakeEntry:
            seq = 5
            timestamp = datetime(2025, 6, 1, 8, 5, 0, tzinfo=UTC)
            level = "error"
            message = "Failed to sync repos"
            entity_type = "repositories"
            org = "acme"
            details = {"error": "rate limited", "retry_after": 60}

        entry = SyncLogEntryResponse.model_validate(FakeEntry())
        assert entry.seq == 5
        assert entry.level == "error"
        assert entry.entity_type == "repositories"
        assert entry.org == "acme"
        assert entry.details == {"error": "rate limited", "retry_after": 60}


class TestSyncLogsResponse:
    def test_empty_response(self):
        from app.schemas.github_sync import SyncLogsResponse

        resp = SyncLogsResponse(entries=[], last_seq=0)
        assert resp.entries == []
        assert resp.last_seq == 0

    def test_response_with_entries(self):
        from app.schemas.github_sync import SyncLogEntryResponse, SyncLogsResponse

        entries = [
            SyncLogEntryResponse(
                seq=1,
                timestamp=datetime(2025, 1, 1, tzinfo=UTC),
                level="info",
                message="Starting sync",
            ),
            SyncLogEntryResponse(
                seq=2,
                timestamp=datetime(2025, 1, 1, 0, 1, tzinfo=UTC),
                level="warn",
                message="Rate limited",
                entity_type="repos",
                org="acme",
            ),
        ]
        resp = SyncLogsResponse(entries=entries, last_seq=2)
        assert len(resp.entries) == 2
        assert resp.last_seq == 2
        assert resp.entries[0].message == "Starting sync"
        assert resp.entries[1].entity_type == "repos"


# ─── SyncLogEntry Model Tests ────────────────────────────────────────────────


class TestSyncLogEntryModel:
    def test_model_has_expected_columns(self):
        from app.models.github_sync import SyncLogEntry

        assert SyncLogEntry.__tablename__ == "enterprise_sync_log_entries"
        # Verify columns exist on the mapped class
        mapper = SyncLogEntry.__mapper__
        column_names = {c.key for c in mapper.column_attrs}
        expected = {
            "id",
            "run_id",
            "seq",
            "timestamp",
            "level",
            "message",
            "entity_type",
            "org",
            "details",
        }
        assert expected.issubset(column_names)

    def test_model_table_args(self):
        from app.models.github_sync import SyncLogEntry

        # Should have the composite index
        table = SyncLogEntry.__table__
        index_names = {idx.name for idx in table.indexes}
        assert "idx_sync_log_entries_run_id_seq" in index_names


# ─── Sync Logs Router Tests ──────────────────────────────────────────────────


class TestGetSyncLogs:
    def test_logs_returns_404_when_run_not_found(self):
        app, mock_db, _ = _build_sync_app(valkey_session=_make_admin_session())
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        client.cookies.set("access_token", token)

        # Mock: run not found
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        run_id = str(uuid.uuid4())
        resp = client.get(f"/api/v1/admin/sync/runs/{run_id}/logs")
        assert resp.status_code == 404

    def test_logs_returns_empty_entries(self):
        app, mock_db, _ = _build_sync_app(valkey_session=_make_admin_session())
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        client.cookies.set("access_token", token)

        # First execute: run exists. Second execute: empty logs.
        mock_run_result = MagicMock()
        mock_run_result.scalar_one_or_none.return_value = MagicMock()  # run exists

        mock_entries_result = MagicMock()
        mock_entries_result.scalars.return_value.all.return_value = []

        mock_db.execute = AsyncMock(side_effect=[mock_run_result, mock_entries_result])

        run_id = str(uuid.uuid4())
        resp = client.get(f"/api/v1/admin/sync/runs/{run_id}/logs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["entries"] == []
        assert data["last_seq"] == 0

    def test_logs_returns_entries_with_after_parameter(self):
        app, mock_db, _ = _build_sync_app(valkey_session=_make_admin_session())
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt()
        client.cookies.set("access_token", token)

        mock_run_result = MagicMock()
        mock_run_result.scalar_one_or_none.return_value = MagicMock()

        # Simulate log entries
        class FakeLogEntry:
            def __init__(self, seq, level, message):
                self.seq = seq
                self.timestamp = datetime(2025, 6, 1, 8, 0, seq, tzinfo=UTC)
                self.level = level
                self.message = message
                self.entity_type = None
                self.org = None
                self.details = None

        fake_entries = [
            FakeLogEntry(3, "info", "Page 1 fetched"),
            FakeLogEntry(4, "info", "Page 2 fetched"),
        ]
        mock_entries_result = MagicMock()
        mock_entries_result.scalars.return_value.all.return_value = fake_entries

        mock_db.execute = AsyncMock(side_effect=[mock_run_result, mock_entries_result])

        run_id = str(uuid.uuid4())
        resp = client.get(f"/api/v1/admin/sync/runs/{run_id}/logs?after=2")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["entries"]) == 2
        assert data["last_seq"] == 4
        assert data["entries"][0]["message"] == "Page 1 fetched"
        assert data["entries"][1]["message"] == "Page 2 fetched"

    def test_logs_unauthenticated_returns_401(self):
        app, _, _ = _build_sync_app()
        client = TestClient(app, raise_server_exceptions=False)
        run_id = str(uuid.uuid4())
        resp = client.get(f"/api/v1/admin/sync/runs/{run_id}/logs")
        assert resp.status_code == 401

    def test_logs_non_admin_returns_403(self):
        app, _, _ = _build_sync_app(valkey_session=_make_analyst_session())
        client = TestClient(app, raise_server_exceptions=False)
        token = _make_jwt(sub="analyst", jti="analyst-jti")
        client.cookies.set("access_token", token)
        run_id = str(uuid.uuid4())
        resp = client.get(f"/api/v1/admin/sync/runs/{run_id}/logs")
        assert resp.status_code == 403
