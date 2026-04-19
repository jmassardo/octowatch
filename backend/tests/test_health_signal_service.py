"""Unit tests for health signal service and router.

Covers all 10 service functions and all 6 router endpoints.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps import AuthenticatedUser, get_current_user, get_db
from app.routers import health_signals as health_signals_module
from app.services import health_signal_service

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(
    *,
    scoped_orgs: list[str] | None = None,
    roles: list[str] | None = None,
    scope_type: str = "org",
) -> AuthenticatedUser:
    """Create a minimal ``AuthenticatedUser`` for testing."""
    return AuthenticatedUser(
        github_login="testuser",
        github_id=42,
        roles=roles or ["analyst"],
        scoped_orgs=scoped_orgs or ["test-org"],
        scoped_repos=[],
        scope_type=scope_type,
        jti="test-jti",
        session_expires_at="2099-01-01T00:00:00+00:00",
    )


def _mock_session_with_mappings(
    *result_sets: list[dict],
) -> AsyncMock:
    """Return an ``AsyncSession`` mock.

    Each call to ``.execute()`` yields a result whose ``.mappings().all()``
    returns the corresponding dicts, and ``.mappings().first()`` returns
    the first dict or ``None``.
    """
    session = AsyncMock()
    mocks = []
    for rows in result_sets:
        mapping_mock = MagicMock()
        mapping_mock.all.return_value = rows
        mapping_mock.first.return_value = rows[0] if rows else None
        mock_result = MagicMock()
        mock_result.mappings.return_value = mapping_mock
        mock_result.fetchall.return_value = rows
        mock_result.fetchone.return_value = rows[0] if rows else None
        mocks.append(mock_result)
    session.execute = AsyncMock(side_effect=mocks)
    return session


def _build_app_no_access() -> FastAPI:
    """Build app where get_scoped_orgs returns empty list (no access)."""
    app = FastAPI()
    app.include_router(health_signals_module.router, prefix="/api/v1")

    user = _make_user(scoped_orgs=[])
    mock_db = AsyncMock()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: user

    return app


def _build_app_with_access() -> FastAPI:
    """Build app where user has org access."""
    app = FastAPI()
    app.include_router(health_signals_module.router, prefix="/api/v1")

    user = _make_user()
    mock_db = AsyncMock()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: user

    return app


# ===========================================================================
# Service layer tests
# ===========================================================================


class TestGetHealthSummary:
    """Test ``get_health_summary`` which aggregates multiple CTEs."""

    @pytest.mark.asyncio
    async def test_returns_dict_with_expected_keys(self) -> None:
        summary_row = {
            "stale_repos": 5,
            "pat_no_expiry": 3,
            "pat_stale": 1,
            "bypass_offenders": 2,
            "ext_collab_total": 10,
            "ext_collab_elevated": 1,
        }
        session = _mock_session_with_mappings([summary_row])
        result = await health_signal_service.get_health_summary(session, scoped_orgs=["test-org"])
        assert isinstance(result, dict)
        assert "stale_repos" in result
        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_result_returns_zeroes(self) -> None:
        session = _mock_session_with_mappings([])
        result = await health_signal_service.get_health_summary(session, scoped_orgs=["test-org"])
        assert isinstance(result, dict)
        assert result["stale_repos"] == 0


class TestGetPATHealthSummary:
    """Test ``get_pat_health_summary``."""

    @pytest.mark.asyncio
    async def test_returns_counts(self) -> None:
        row = {"no_expiry_count": 10, "expired_count": 3, "stale_90d_count": 5}
        session = _mock_session_with_mappings([row])
        result = await health_signal_service.get_pat_health_summary(
            session, scoped_orgs=["test-org"]
        )
        assert result["no_expiry_count"] == 10
        assert result["expired_count"] == 3

    @pytest.mark.asyncio
    async def test_empty_result(self) -> None:
        session = _mock_session_with_mappings([], [])
        result = await health_signal_service.get_pat_health_summary(
            session, scoped_orgs=["test-org"]
        )
        assert result["no_expiry_count"] == 0


class TestGetPATTokenAgeSignals:
    """Test ``get_pat_token_age_signals``."""

    @pytest.mark.asyncio
    async def test_returns_list_of_dicts(self) -> None:
        rows = [
            {
                "github_login": "alice",
                "token_name": "ci-token",
                "token_id": "1",
                "token_type": "classic",
                "created_at": "2024-01-01T00:00:00",
                "age_days": 100,
                "signal_type": "no_expiry",
            }
        ]
        session = _mock_session_with_mappings(rows)
        result = await health_signal_service.get_pat_token_age_signals(
            session, scoped_orgs=["test-org"], limit=10
        )
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["github_login"] == "alice"

    @pytest.mark.asyncio
    async def test_empty_result(self) -> None:
        session = _mock_session_with_mappings([], [])
        result = await health_signal_service.get_pat_token_age_signals(
            session, scoped_orgs=["test-org"]
        )
        assert result == []


class TestGetDormantTokens:
    """Test ``get_dormant_tokens``."""

    @pytest.mark.asyncio
    async def test_returns_dormant_list(self) -> None:
        rows = [
            {
                "github_login": "bob",
                "token_id": "42",
                "token_name": "old-token",
                "token_type": "fine_grained",
                "created_at": "2024-01-01T00:00:00",
                "age_days": 90,
                "last_used_at": None,
            }
        ]
        session = _mock_session_with_mappings(rows)
        result = await health_signal_service.get_dormant_tokens(
            session, scoped_orgs=["test-org"], limit=25
        )
        assert len(result) == 1
        assert result[0]["token_id"] == "42"

    @pytest.mark.asyncio
    async def test_empty_result(self) -> None:
        session = _mock_session_with_mappings([])
        result = await health_signal_service.get_dormant_tokens(session, scoped_orgs=["test-org"])
        assert result == []


class TestGetBypassOffenders:
    """Test ``get_bypass_offenders``."""

    @pytest.mark.asyncio
    async def test_returns_offender_list(self) -> None:
        rows = [
            {
                "actor": "charlie",
                "total_bypasses": 5,
                "push_protection_bypasses": 3,
                "branch_protection_overrides": 2,
                "first_bypass_at": "2024-01-01T00:00:00",
                "last_bypass_at": "2024-03-15T00:00:00",
                "active_days": 4,
            }
        ]
        session = _mock_session_with_mappings(rows)
        result = await health_signal_service.get_bypass_offenders(
            session, scoped_orgs=["test-org"], lookback_days=90, limit=20
        )
        assert len(result) == 1
        assert result[0]["total_bypasses"] == 5

    @pytest.mark.asyncio
    async def test_custom_lookback(self) -> None:
        session = _mock_session_with_mappings([])
        result = await health_signal_service.get_bypass_offenders(
            session, scoped_orgs=["test-org"], lookback_days=30
        )
        assert result == []
        call_args = session.execute.call_args
        assert call_args[0][1]["lookback_days"] == 30


class TestGetStaleRepositories:
    """Test ``get_stale_repositories``."""

    @pytest.mark.asyncio
    async def test_returns_stale_repos(self) -> None:
        rows = [
            {
                "org": "test-org",
                "repo": "old-repo",
                "last_event_at": "2023-01-01T00:00:00",
                "days_since_activity": 400,
            }
        ]
        session = _mock_session_with_mappings(rows)
        result = await health_signal_service.get_stale_repositories(
            session, scoped_orgs=["test-org"], stale_threshold_days=90, limit=50
        )
        assert len(result) == 1
        assert result[0]["repo"] == "old-repo"

    @pytest.mark.asyncio
    async def test_custom_threshold(self) -> None:
        session = _mock_session_with_mappings([])
        await health_signal_service.get_stale_repositories(
            session, scoped_orgs=["test-org"], stale_threshold_days=180
        )
        call_args = session.execute.call_args
        assert call_args[0][1]["threshold_days"] == 180


class TestGetArchivedRepositories:
    """Test ``get_archived_repositories``."""

    @pytest.mark.asyncio
    async def test_returns_archived_repos(self) -> None:
        rows = [
            {
                "org": "test-org",
                "repo": "archived-repo",
                "archived_at": "2023-06-01T00:00:00",
                "archived_by": "admin-user",
                "days_since_archived": 200,
            }
        ]
        session = _mock_session_with_mappings(rows)
        result = await health_signal_service.get_archived_repositories(
            session, scoped_orgs=["test-org"], limit=50
        )
        assert len(result) == 1
        assert result[0]["archived_by"] == "admin-user"


class TestGetAbandonedForks:
    """Test ``get_abandoned_forks``."""

    @pytest.mark.asyncio
    async def test_returns_abandoned_forks(self) -> None:
        rows = [
            {
                "actor": "forker",
                "org": "test-org",
                "repo": "abandoned-fork",
                "forked_at": "2024-01-01T00:00:00",
                "days_since_fork": 60,
            }
        ]
        session = _mock_session_with_mappings(rows)
        result = await health_signal_service.get_abandoned_forks(
            session, scoped_orgs=["test-org"], limit=50
        )
        assert len(result) == 1
        assert result[0]["actor"] == "forker"


class TestGetExternalCollaborators:
    """Test ``get_external_collaborators``."""

    @pytest.mark.asyncio
    async def test_returns_collaborators_with_idp(self) -> None:
        rows = [
            {
                "github_login": "ext-user",
                "org": "test-org",
                "repo": "some-repo",
                "role": "write",
                "granted_at": "2024-01-01T00:00:00",
                "granted_by": "admin",
                "last_event_at": "2024-06-01T00:00:00",
                "days_since_last_event": 30,
                "idp_email": "ext@example.com",
                "idp_employment_status": "active",
            }
        ]
        session = _mock_session_with_mappings(rows)
        result = await health_signal_service.get_external_collaborators(
            session, scoped_orgs=["test-org"], limit=50
        )
        assert len(result) == 1
        assert result[0]["idp_email"] == "ext@example.com"


class TestGetExternalCollaboratorSummary:
    """Test ``get_external_collaborator_summary``."""

    @pytest.mark.asyncio
    async def test_returns_summary_counts(self) -> None:
        row = {
            "total_active": 15,
            "org_level_count": 2,
            "elevated_count": 3,
            "dormant_count": 5,
        }
        session = _mock_session_with_mappings([row])
        result = await health_signal_service.get_external_collaborator_summary(
            session, scoped_orgs=["test-org"]
        )
        assert result["total_active"] == 15
        assert result["elevated_count"] == 3

    @pytest.mark.asyncio
    async def test_empty_result(self) -> None:
        session = _mock_session_with_mappings([], [])
        result = await health_signal_service.get_external_collaborator_summary(
            session, scoped_orgs=["test-org"]
        )
        assert result["total_active"] == 0


class TestGetDormantCollaborators:
    """Test ``get_dormant_collaborators``."""

    @pytest.mark.asyncio
    async def test_returns_dormant_list(self) -> None:
        rows = [
            {
                "github_login": "sleepy-user",
                "org": "test-org",
                "repo": None,
                "role": "read",
                "granted_at": "2023-01-01T00:00:00",
                "last_event_at": None,
                "days_inactive": 300,
            }
        ]
        session = _mock_session_with_mappings(rows)
        result = await health_signal_service.get_dormant_collaborators(
            session, scoped_orgs=["test-org"], dormancy_days=60, limit=50
        )
        assert len(result) == 1
        assert result[0]["days_inactive"] == 300

    @pytest.mark.asyncio
    async def test_custom_dormancy_days(self) -> None:
        session = _mock_session_with_mappings([], [])
        await health_signal_service.get_dormant_collaborators(
            session, scoped_orgs=["test-org"], dormancy_days=120
        )
        # Check the first (primary) query which carries the dormancy_days param.
        first_call_args = session.execute.call_args_list[0][0][1]
        assert first_call_args["dormancy_days"] == 120


class TestScopedOrgsPassedAsParam:
    """Verify scoped_orgs is always passed as a bound parameter, never interpolated."""

    @pytest.mark.asyncio
    async def test_pat_health_summary_binds_orgs(self) -> None:
        session = _mock_session_with_mappings([], [])
        await health_signal_service.get_pat_health_summary(session, scoped_orgs=["org-a", "org-b"])
        call_args = session.execute.call_args
        assert call_args[0][1]["scoped_orgs"] == ["org-a", "org-b"]

    @pytest.mark.asyncio
    async def test_bypass_offenders_binds_orgs(self) -> None:
        session = _mock_session_with_mappings([])
        await health_signal_service.get_bypass_offenders(session, scoped_orgs=["org-x"])
        call_args = session.execute.call_args
        assert call_args[0][1]["scoped_orgs"] == ["org-x"]

    @pytest.mark.asyncio
    async def test_stale_repos_binds_orgs(self) -> None:
        session = _mock_session_with_mappings([])
        await health_signal_service.get_stale_repositories(session, scoped_orgs=["org-z"])
        call_args = session.execute.call_args
        assert call_args[0][1]["scoped_orgs"] == ["org-z"]

    @pytest.mark.asyncio
    async def test_external_collaborators_binds_orgs(self) -> None:
        session = _mock_session_with_mappings([], [])
        await health_signal_service.get_external_collaborators(session, scoped_orgs=["org-1"])
        call_args = session.execute.call_args
        assert call_args[0][1]["scoped_orgs"] == ["org-1"]

    @pytest.mark.asyncio
    async def test_dormant_collaborators_binds_orgs(self) -> None:
        session = _mock_session_with_mappings([], [])
        await health_signal_service.get_dormant_collaborators(session, scoped_orgs=["org-2"])
        call_args = session.execute.call_args
        assert call_args[0][1]["scoped_orgs"] == ["org-2"]


# ===========================================================================
# Router layer tests
# ===========================================================================


class TestRouterAuth:
    """Verify every endpoint returns 403 when user has no org access."""

    def test_summary_403_when_no_orgs(self) -> None:
        app = _build_app_no_access()
        with patch(
            "app.routers.health_signals.rbac_service.get_scoped_orgs",
            new_callable=AsyncMock,
            return_value=[],
        ):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/api/v1/health-signals/summary")
            assert resp.status_code == 403

    def test_pat_health_403_when_no_orgs(self) -> None:
        app = _build_app_no_access()
        with patch(
            "app.routers.health_signals.rbac_service.get_scoped_orgs",
            new_callable=AsyncMock,
            return_value=[],
        ):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/api/v1/health-signals/pat-health")
            assert resp.status_code == 403

    def test_bypass_offenders_403_when_no_orgs(self) -> None:
        app = _build_app_no_access()
        with patch(
            "app.routers.health_signals.rbac_service.get_scoped_orgs",
            new_callable=AsyncMock,
            return_value=[],
        ):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/api/v1/health-signals/bypass-offenders")
            assert resp.status_code == 403

    def test_repo_health_403_when_no_orgs(self) -> None:
        app = _build_app_no_access()
        with patch(
            "app.routers.health_signals.rbac_service.get_scoped_orgs",
            new_callable=AsyncMock,
            return_value=[],
        ):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/api/v1/health-signals/repo-health")
            assert resp.status_code == 403

    def test_ext_collaborators_403_when_no_orgs(self) -> None:
        app = _build_app_no_access()
        with patch(
            "app.routers.health_signals.rbac_service.get_scoped_orgs",
            new_callable=AsyncMock,
            return_value=[],
        ):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/api/v1/health-signals/external-collaborators")
            assert resp.status_code == 403

    def test_dormant_collaborators_403_when_no_orgs(self) -> None:
        app = _build_app_no_access()
        with patch(
            "app.routers.health_signals.rbac_service.get_scoped_orgs",
            new_callable=AsyncMock,
            return_value=[],
        ):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/api/v1/health-signals/dormant-collaborators")
            assert resp.status_code == 403


class TestRouterEndpoints:
    """Verify endpoints return expected data shapes for authorised users."""

    def test_summary_returns_data(self) -> None:
        app = _build_app_with_access()
        summary_data = {
            "stale_repos": 2,
            "pat_no_expiry": 5,
            "pat_stale": 1,
            "bypass_offenders": 3,
            "ext_collab_total": 8,
            "ext_collab_elevated": 1,
        }
        with patch(
            "app.routers.health_signals.rbac_service.get_scoped_orgs",
            new_callable=AsyncMock,
            return_value=["test-org"],
        ):
            with patch(
                "app.routers.health_signals.health_signal_service.get_health_summary",
                new_callable=AsyncMock,
                return_value=summary_data,
            ):
                with patch(
                    "app.routers.health_signals.health_signal_service"
                    ".get_secret_scanning_alert_health",
                    new_callable=AsyncMock,
                    return_value=[],
                ):
                    with patch(
                        "app.routers.health_signals.health_signal_service.get_security_coverage",
                        new_callable=AsyncMock,
                        return_value=[],
                    ):
                        with patch(
                            "app.routers.health_signals.health_signal_service.get_sso_health",
                            new_callable=AsyncMock,
                            return_value=[],
                        ):
                            client = TestClient(app)
                            resp = client.get("/api/v1/health-signals/summary")
                            assert resp.status_code == 200
                            data = resp.json()
                            assert data["stale_repos"] == 2
                            assert data["secret_scanning_unresolved"] == 0
                            assert data["security_features_disabled_7d"] == 0
                            assert data["sso_disabled_orgs"] == 0

    def test_pat_health_returns_composite_response(self) -> None:
        app = _build_app_with_access()
        with patch(
            "app.routers.health_signals.rbac_service.get_scoped_orgs",
            new_callable=AsyncMock,
            return_value=["test-org"],
        ):
            with patch(
                "app.routers.health_signals.health_signal_service.get_pat_health_summary",
                new_callable=AsyncMock,
                return_value={"no_expiry_count": 1, "expired_count": 0, "stale_90d_count": 0},
            ):
                with patch(
                    "app.routers.health_signals.health_signal_service.get_pat_token_age_signals",
                    new_callable=AsyncMock,
                    return_value=[],
                ):
                    with patch(
                        "app.routers.health_signals.health_signal_service.get_dormant_tokens",
                        new_callable=AsyncMock,
                        return_value=[],
                    ):
                        client = TestClient(app)
                        resp = client.get("/api/v1/health-signals/pat-health")
                        assert resp.status_code == 200
                        data = resp.json()
                        assert "summary" in data
                        assert "tokens" in data
                        assert "dormant" in data

    def test_bypass_offenders_returns_offenders(self) -> None:
        app = _build_app_with_access()
        with patch(
            "app.routers.health_signals.rbac_service.get_scoped_orgs",
            new_callable=AsyncMock,
            return_value=["test-org"],
        ):
            with patch(
                "app.routers.health_signals.health_signal_service.get_bypass_offenders",
                new_callable=AsyncMock,
                return_value=[],
            ):
                client = TestClient(app)
                resp = client.get(
                    "/api/v1/health-signals/bypass-offenders?lookback_days=30&limit=10"
                )
                assert resp.status_code == 200
                assert "offenders" in resp.json()

    def test_repo_health_returns_all_sections(self) -> None:
        app = _build_app_with_access()
        with patch(
            "app.routers.health_signals.rbac_service.get_scoped_orgs",
            new_callable=AsyncMock,
            return_value=["test-org"],
        ):
            with patch(
                "app.routers.health_signals.health_signal_service.get_stale_repositories",
                new_callable=AsyncMock,
                return_value=[],
            ):
                with patch(
                    "app.routers.health_signals.health_signal_service.get_archived_repositories",
                    new_callable=AsyncMock,
                    return_value=[],
                ):
                    with patch(
                        "app.routers.health_signals.health_signal_service.get_abandoned_forks",
                        new_callable=AsyncMock,
                        return_value=[],
                    ):
                        client = TestClient(app)
                        resp = client.get("/api/v1/health-signals/repo-health")
                        assert resp.status_code == 200
                        data = resp.json()
                        assert "stale" in data
                        assert "archived" in data
                        assert "abandoned_forks" in data

    def test_ext_collaborators_returns_summary_and_list(self) -> None:
        app = _build_app_with_access()
        with patch(
            "app.routers.health_signals.rbac_service.get_scoped_orgs",
            new_callable=AsyncMock,
            return_value=["test-org"],
        ):
            with patch(
                "app.routers.health_signals.health_signal_service.get_external_collaborator_summary",
                new_callable=AsyncMock,
                return_value={
                    "total_active": 5,
                    "org_level_count": 1,
                    "elevated_count": 2,
                    "dormant_count": 1,
                },
            ):
                with patch(
                    "app.routers.health_signals.health_signal_service.get_external_collaborators",
                    new_callable=AsyncMock,
                    return_value=[],
                ):
                    client = TestClient(app)
                    resp = client.get("/api/v1/health-signals/external-collaborators")
                    assert resp.status_code == 200
                    data = resp.json()
                    assert "summary" in data
                    assert "collaborators" in data

    def test_dormant_collaborators_returns_list(self) -> None:
        app = _build_app_with_access()
        with patch(
            "app.routers.health_signals.rbac_service.get_scoped_orgs",
            new_callable=AsyncMock,
            return_value=["test-org"],
        ):
            with patch(
                "app.routers.health_signals.health_signal_service.get_dormant_collaborators",
                new_callable=AsyncMock,
                return_value=[],
            ):
                client = TestClient(app)
                resp = client.get("/api/v1/health-signals/dormant-collaborators?dormancy_days=90")
                assert resp.status_code == 200
                assert "dormant" in resp.json()


class TestRouterQueryParamValidation:
    """Verify FastAPI validates query params within bounds."""

    def test_limit_below_min_rejected(self) -> None:
        app = _build_app_with_access()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/health-signals/pat-health?limit=0")
        assert resp.status_code == 422

    def test_limit_above_max_rejected(self) -> None:
        app = _build_app_with_access()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/health-signals/pat-health?limit=200")
        assert resp.status_code == 422

    def test_lookback_days_below_min_rejected(self) -> None:
        app = _build_app_with_access()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/health-signals/bypass-offenders?lookback_days=3")
        assert resp.status_code == 422

    def test_lookback_days_above_max_rejected(self) -> None:
        app = _build_app_with_access()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/health-signals/bypass-offenders?lookback_days=500")
        assert resp.status_code == 422

    def test_dormancy_days_below_min_rejected(self) -> None:
        app = _build_app_with_access()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/health-signals/dormant-collaborators?dormancy_days=1")
        assert resp.status_code == 422

    def test_stale_threshold_below_min_rejected(self) -> None:
        app = _build_app_with_access()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/health-signals/repo-health?stale_threshold_days=2")
        assert resp.status_code == 422


class TestRbacServiceIntegration:
    """Verify the router correctly calls ``rbac_service.get_scoped_orgs``."""

    def test_calls_get_scoped_orgs(self) -> None:
        app = _build_app_with_access()
        mock_get_scoped_orgs = AsyncMock(return_value=["test-org"])
        summary_data = {
            "stale_repos": 0,
            "pat_no_expiry": 0,
            "pat_stale": 0,
            "bypass_offenders": 0,
            "ext_collab_total": 0,
            "ext_collab_elevated": 0,
        }

        with patch(
            "app.routers.health_signals.rbac_service.get_scoped_orgs",
            mock_get_scoped_orgs,
        ):
            with patch(
                "app.routers.health_signals.health_signal_service.get_health_summary",
                new_callable=AsyncMock,
                return_value=summary_data,
            ):
                with patch(
                    "app.routers.health_signals.health_signal_service"
                    ".get_secret_scanning_alert_health",
                    new_callable=AsyncMock,
                    return_value=[],
                ):
                    with patch(
                        "app.routers.health_signals.health_signal_service.get_security_coverage",
                        new_callable=AsyncMock,
                        return_value=[],
                    ):
                        with patch(
                            "app.routers.health_signals.health_signal_service.get_sso_health",
                            new_callable=AsyncMock,
                            return_value=[],
                        ):
                            client = TestClient(app)
                            resp = client.get("/api/v1/health-signals/summary")
                            assert resp.status_code == 200
                            mock_get_scoped_orgs.assert_called_once()

    def test_passes_scoped_orgs_to_service(self) -> None:
        """Verify the resolved orgs are forwarded to the service function."""
        app = _build_app_with_access()
        mock_service = AsyncMock(return_value={"stale_repos": 0})

        with patch(
            "app.routers.health_signals.rbac_service.get_scoped_orgs",
            new_callable=AsyncMock,
            return_value=["org-a", "org-b"],
        ):
            with patch(
                "app.routers.health_signals.health_signal_service.get_health_summary",
                mock_service,
            ):
                with patch(
                    "app.routers.health_signals.health_signal_service"
                    ".get_secret_scanning_alert_health",
                    new_callable=AsyncMock,
                    return_value=[],
                ):
                    with patch(
                        "app.routers.health_signals.health_signal_service.get_security_coverage",
                        new_callable=AsyncMock,
                        return_value=[],
                    ):
                        with patch(
                            "app.routers.health_signals.health_signal_service.get_sso_health",
                            new_callable=AsyncMock,
                            return_value=[],
                        ):
                            client = TestClient(app)
                            resp = client.get("/api/v1/health-signals/summary")
                            assert resp.status_code == 200
                            call_kwargs = mock_service.call_args
                            assert call_kwargs[1]["scoped_orgs"] == ["org-a", "org-b"]
