"""Unit tests for expanded health signal service functions and router endpoints.

Covers all 19 new service functions (Phase 1-4), the 14 new router endpoints,
the updated /summary endpoint, the ingestion health worker, and the threat
intel service.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps import AuthenticatedUser, get_current_user, get_db
from app.routers import health_signals as health_signals_module
from app.services import health_signal_service, threat_intel_service

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(
    *,
    scoped_orgs: list[str] | None = None,
    roles: list[str] | None = None,
) -> AuthenticatedUser:
    return AuthenticatedUser(
        github_login="testuser",
        github_id=42,
        roles=roles or ["analyst"],
        scoped_orgs=scoped_orgs or ["test-org"],
        scoped_repos=[],
        scope_type="org",
        jti="test-jti",
        session_expires_at="2099-01-01T00:00:00+00:00",
    )


def _mock_session_with_mappings(
    *result_sets: list[dict],
) -> AsyncMock:
    """Return an AsyncSession mock with pre-configured result sets."""
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


def _build_app_with_access() -> FastAPI:
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
# Phase 1 service tests
# ===========================================================================


class TestGetAuditStreamStatus:
    """Test ``get_audit_stream_status``."""

    @pytest.mark.asyncio
    async def test_returns_list(self) -> None:
        rows = [
            {
                "org": "test-org",
                "action": "audit_log_streaming.create",
                "actor": "admin",
                "created_at": "2024-01-01T00:00:00",
                "hours_ago": 5,
            }
        ]
        session = _mock_session_with_mappings(rows)
        result = await health_signal_service.get_audit_stream_status(
            session, scoped_orgs=["test-org"]
        )
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["org"] == "test-org"

    @pytest.mark.asyncio
    async def test_empty_result(self) -> None:
        session = _mock_session_with_mappings([])
        result = await health_signal_service.get_audit_stream_status(
            session, scoped_orgs=["test-org"]
        )
        assert result == []


class TestGetSecurityCoverage:
    """Test ``get_security_coverage``."""

    @pytest.mark.asyncio
    async def test_returns_coverage_data(self) -> None:
        rows = [
            {
                "org": "test-org",
                "total_repos": 10,
                "secret_scanning_enabled": 8,
                "dependabot_enabled": 9,
                "codeql_enabled": 5,
                "ghas_enabled": 5,
                "any_feature_disabled": 2,
            }
        ]
        session = _mock_session_with_mappings(rows)
        result = await health_signal_service.get_security_coverage(
            session, scoped_orgs=["test-org"]
        )
        assert len(result) == 1
        assert result[0]["total_repos"] == 10
        assert result[0]["any_feature_disabled"] == 2

    @pytest.mark.asyncio
    async def test_empty_result(self) -> None:
        session = _mock_session_with_mappings([])
        result = await health_signal_service.get_security_coverage(
            session, scoped_orgs=["test-org"]
        )
        assert result == []


class TestGetSecretScanningAlertHealth:
    """Test ``get_secret_scanning_alert_health``."""

    @pytest.mark.asyncio
    async def test_returns_mttr_data(self) -> None:
        rows = [
            {
                "org": "test-org",
                "unresolved_total": 5,
                "unresolved_gt_7d": 3,
                "unresolved_gt_30d": 1,
                "publicly_leaked_count": 0,
                "avg_hours_to_resolve": 48.5,
                "resolved_count": 12,
            }
        ]
        session = _mock_session_with_mappings(rows)
        result = await health_signal_service.get_secret_scanning_alert_health(
            session, scoped_orgs=["test-org"]
        )
        assert len(result) == 1
        assert result[0]["unresolved_total"] == 5
        assert result[0]["avg_hours_to_resolve"] == 48.5

    @pytest.mark.asyncio
    async def test_empty_result(self) -> None:
        session = _mock_session_with_mappings([])
        result = await health_signal_service.get_secret_scanning_alert_health(
            session, scoped_orgs=["test-org"]
        )
        assert result == []


class TestGetSSOHealth:
    """Test ``get_sso_health``."""

    @pytest.mark.asyncio
    async def test_returns_sso_state(self) -> None:
        rows = [
            {
                "org": "test-org",
                "action": "org.enable_saml",
                "actor": "admin",
                "created_at": "2024-06-01T00:00:00",
                "sso_state": "enabled",
            }
        ]
        session = _mock_session_with_mappings(rows)
        result = await health_signal_service.get_sso_health(session, scoped_orgs=["test-org"])
        assert len(result) == 1
        assert result[0]["sso_state"] == "enabled"

    @pytest.mark.asyncio
    async def test_disabled_state(self) -> None:
        rows = [
            {
                "org": "test-org",
                "action": "org.disable_saml",
                "actor": "admin",
                "created_at": "2024-06-01T00:00:00",
                "sso_state": "disabled",
            }
        ]
        session = _mock_session_with_mappings(rows)
        result = await health_signal_service.get_sso_health(session, scoped_orgs=["test-org"])
        assert result[0]["sso_state"] == "disabled"


class TestGetPrivilegeChangeSummary:
    """Test ``get_privilege_change_summary``."""

    @pytest.mark.asyncio
    async def test_returns_privilege_counts(self) -> None:
        rows = [
            {
                "org": "test-org",
                "admin_promotions": 3,
                "integration_mgr_grants": 1,
                "custom_role_changes": 2,
                "earliest_event": "2024-06-01T00:00:00",
                "latest_event": "2024-06-15T00:00:00",
            }
        ]
        session = _mock_session_with_mappings(rows)
        result = await health_signal_service.get_privilege_change_summary(
            session, scoped_orgs=["test-org"]
        )
        assert len(result) == 1
        assert result[0]["admin_promotions"] == 3

    @pytest.mark.asyncio
    async def test_empty_result(self) -> None:
        session = _mock_session_with_mappings([])
        result = await health_signal_service.get_privilege_change_summary(
            session, scoped_orgs=["test-org"]
        )
        assert result == []


class TestGetRepoVisibilityTrends:
    """Test ``get_repo_visibility_trends``."""

    @pytest.mark.asyncio
    async def test_returns_visibility_changes(self) -> None:
        rows = [
            {
                "week": "2024-06-10T00:00:00",
                "org": "test-org",
                "from_visibility": "private",
                "to_visibility": "public",
                "change_count": 2,
                "repos_changed": ["repo-a", "repo-b"],
            }
        ]
        session = _mock_session_with_mappings(rows)
        result = await health_signal_service.get_repo_visibility_trends(
            session, scoped_orgs=["test-org"]
        )
        assert len(result) == 1
        assert result[0]["change_count"] == 2

    @pytest.mark.asyncio
    async def test_empty_result(self) -> None:
        session = _mock_session_with_mappings([])
        result = await health_signal_service.get_repo_visibility_trends(
            session, scoped_orgs=["test-org"]
        )
        assert result == []


# ===========================================================================
# Phase 2 service tests
# ===========================================================================


class TestGetCodeScanningHealth:
    """Test ``get_code_scanning_health``."""

    @pytest.mark.asyncio
    async def test_returns_alert_data(self) -> None:
        rows = [
            {
                "org": "test-org",
                "repo": "test-org/repo-a",
                "total_alerts_30d": 15,
                "avg_hours_to_close": 72.0,
                "dismissed_30d": 3,
                "reappeared_30d": 1,
            }
        ]
        session = _mock_session_with_mappings(rows)
        result = await health_signal_service.get_code_scanning_health(
            session, scoped_orgs=["test-org"], limit=10
        )
        assert len(result) == 1
        assert result[0]["total_alerts_30d"] == 15

    @pytest.mark.asyncio
    async def test_empty_result(self) -> None:
        session = _mock_session_with_mappings([])
        result = await health_signal_service.get_code_scanning_health(
            session, scoped_orgs=["test-org"]
        )
        assert result == []


class TestGetVulnerabilityAging:
    """Test ``get_vulnerability_aging``."""

    @pytest.mark.asyncio
    async def test_returns_aging_data(self) -> None:
        rows = [
            {
                "org": "test-org",
                "total_open": 20,
                "open_critical": 3,
                "open_high": 5,
                "open_gt_30d": 10,
                "critical_open_gt_14d": 2,
                "avg_open_days": 45.5,
            }
        ]
        session = _mock_session_with_mappings(rows)
        result = await health_signal_service.get_vulnerability_aging(
            session, scoped_orgs=["test-org"]
        )
        assert len(result) == 1
        assert result[0]["total_open"] == 20
        assert result[0]["open_critical"] == 3

    @pytest.mark.asyncio
    async def test_empty_result(self) -> None:
        session = _mock_session_with_mappings([])
        result = await health_signal_service.get_vulnerability_aging(
            session, scoped_orgs=["test-org"]
        )
        assert result == []


class TestGetAppGovernanceSummary:
    """Test ``get_app_governance_summary``."""

    @pytest.mark.asyncio
    async def test_returns_app_data(self) -> None:
        rows = [
            {
                "org": "test-org",
                "apps_installed_90d": 5,
                "apps_removed_90d": 1,
                "oauth_apps_approved_90d": 3,
                "oauth_apps_denied_90d": 2,
                "token_revocations_90d": 0,
            }
        ]
        session = _mock_session_with_mappings(rows)
        result = await health_signal_service.get_app_governance_summary(
            session, scoped_orgs=["test-org"]
        )
        assert len(result) == 1
        assert result[0]["apps_installed_90d"] == 5

    @pytest.mark.asyncio
    async def test_empty_result(self) -> None:
        session = _mock_session_with_mappings([])
        result = await health_signal_service.get_app_governance_summary(
            session, scoped_orgs=["test-org"]
        )
        assert result == []


class TestGetWebhookActivity:
    """Test ``get_webhook_activity``."""

    @pytest.mark.asyncio
    async def test_returns_webhook_data(self) -> None:
        rows = [
            {
                "org": "test-org",
                "webhooks_created_30d": 3,
                "webhooks_removed_30d": 1,
                "webhooks_modified_30d": 2,
            }
        ]
        session = _mock_session_with_mappings(rows)
        result = await health_signal_service.get_webhook_activity(session, scoped_orgs=["test-org"])
        assert len(result) == 1
        assert result[0]["webhooks_created_30d"] == 3

    @pytest.mark.asyncio
    async def test_empty_result(self) -> None:
        session = _mock_session_with_mappings([])
        result = await health_signal_service.get_webhook_activity(session, scoped_orgs=["test-org"])
        assert result == []


# ===========================================================================
# Phase 3 service tests
# ===========================================================================


class TestGetWorkflowHealth:
    """Test ``get_workflow_health``."""

    @pytest.mark.asyncio
    async def test_returns_workflow_data(self) -> None:
        rows = [
            {
                "org": "test-org",
                "repo": "test-org/ci-repo",
                "workflow_name": "CI",
                "total_runs": 100,
                "successes": 90,
                "failures": 8,
                "cancelled": 2,
                "failure_rate_pct": 8.0,
                "last_run_at": "2024-06-15T00:00:00",
            }
        ]
        session = _mock_session_with_mappings(rows)
        result = await health_signal_service.get_workflow_health(
            session, scoped_orgs=["test-org"], limit=10
        )
        assert len(result) == 1
        assert result[0]["failure_rate_pct"] == 8.0

    @pytest.mark.asyncio
    async def test_empty_result(self) -> None:
        session = _mock_session_with_mappings([])
        result = await health_signal_service.get_workflow_health(session, scoped_orgs=["test-org"])
        assert result == []


class TestGetWorkflowSecretUsage:
    """Test ``get_workflow_secret_usage``."""

    @pytest.mark.asyncio
    async def test_returns_secret_usage_data(self) -> None:
        rows = [
            {
                "org": "test-org",
                "repo": "test-org/repo",
                "job_name": "deploy",
                "workflow_run_id": "123",
                "secrets_count": 10,
                "created_at": "2024-06-15T00:00:00",
            }
        ]
        session = _mock_session_with_mappings(rows)
        result = await health_signal_service.get_workflow_secret_usage(
            session, scoped_orgs=["test-org"], threshold=5
        )
        assert len(result) == 1
        assert result[0]["secrets_count"] == 10

    @pytest.mark.asyncio
    async def test_empty_result(self) -> None:
        session = _mock_session_with_mappings([])
        result = await health_signal_service.get_workflow_secret_usage(
            session, scoped_orgs=["test-org"]
        )
        assert result == []


class TestGetBranchProtectionHealth:
    """Test ``get_branch_protection_health``."""

    @pytest.mark.asyncio
    async def test_returns_protection_data(self) -> None:
        rows = [
            {
                "org": "test-org",
                "protections_removed_30d": 1,
                "policy_overrides_30d": 3,
                "protections_modified_30d": 5,
                "distinct_actors": 2,
                "distinct_repos_affected": 4,
            }
        ]
        session = _mock_session_with_mappings(rows)
        result = await health_signal_service.get_branch_protection_health(
            session, scoped_orgs=["test-org"]
        )
        assert len(result) == 1
        assert result[0]["policy_overrides_30d"] == 3

    @pytest.mark.asyncio
    async def test_empty_result(self) -> None:
        session = _mock_session_with_mappings([])
        result = await health_signal_service.get_branch_protection_health(
            session, scoped_orgs=["test-org"]
        )
        assert result == []


class TestGetCopilotSeatHealth:
    """Test ``get_copilot_seat_health``."""

    @pytest.mark.asyncio
    async def test_returns_seat_data(self) -> None:
        rows = [
            {
                "org": "test-org",
                "seats_granted_90d": 50,
                "seats_removed_90d": 5,
                "unique_users_granted": 45,
                "last_policy_change_at": None,
            }
        ]
        session = _mock_session_with_mappings(rows)
        result = await health_signal_service.get_copilot_seat_health(
            session, scoped_orgs=["test-org"]
        )
        assert len(result) == 1
        assert result[0]["seats_granted_90d"] == 50

    @pytest.mark.asyncio
    async def test_empty_result(self) -> None:
        session = _mock_session_with_mappings([])
        result = await health_signal_service.get_copilot_seat_health(
            session, scoped_orgs=["test-org"]
        )
        assert result == []


class TestGetCodespaceCostSignals:
    """Test ``get_codespace_cost_signals``."""

    @pytest.mark.asyncio
    async def test_returns_cost_data(self) -> None:
        rows = [
            {
                "org": "test-org",
                "active_never_suspended": 3,
                "large_machine_count": 1,
                "unique_users_with_codespaces": 5,
                "most_recent_create": "2024-06-15T00:00:00",
            }
        ]
        session = _mock_session_with_mappings(rows)
        result = await health_signal_service.get_codespace_cost_signals(
            session, scoped_orgs=["test-org"]
        )
        assert len(result) == 1
        assert result[0]["active_never_suspended"] == 3

    @pytest.mark.asyncio
    async def test_empty_result(self) -> None:
        session = _mock_session_with_mappings([])
        result = await health_signal_service.get_codespace_cost_signals(
            session, scoped_orgs=["test-org"]
        )
        assert result == []


class TestGetRunnerFleetHealth:
    """Test ``get_runner_fleet_health``."""

    @pytest.mark.asyncio
    async def test_returns_runner_data(self) -> None:
        rows = [
            {
                "org": "test-org",
                "repo": "test-org/repo",
                "runner_id": "42",
                "runner_name": "runner-1",
                "source_version": "2.300.0",
                "target_version": "2.310.0",
                "runner_group": "default",
                "action": "org.self_hosted_runner_updated",
                "created_at": "2024-06-15T00:00:00",
            }
        ]
        session = _mock_session_with_mappings(rows)
        result = await health_signal_service.get_runner_fleet_health(
            session, scoped_orgs=["test-org"], limit=10
        )
        assert len(result) == 1
        assert result[0]["runner_name"] == "runner-1"

    @pytest.mark.asyncio
    async def test_empty_result(self) -> None:
        session = _mock_session_with_mappings([], [])
        result = await health_signal_service.get_runner_fleet_health(
            session, scoped_orgs=["test-org"]
        )
        assert result == []


# ===========================================================================
# Phase 4 service tests
# ===========================================================================


class TestGetIngestionGapStatus:
    """Test ``get_ingestion_gap_status``."""

    @pytest.mark.asyncio
    async def test_returns_gap_data(self) -> None:
        rows = [
            {
                "org": "test-org",
                "last_event_at": "2024-06-15T10:00:00",
                "minutes_since_last": 45,
            }
        ]
        session = _mock_session_with_mappings(rows)
        result = await health_signal_service.get_ingestion_gap_status(
            session, scoped_orgs=["test-org"]
        )
        assert len(result) == 1
        assert result[0]["minutes_since_last"] == 45

    @pytest.mark.asyncio
    async def test_empty_result(self) -> None:
        session = _mock_session_with_mappings([])
        result = await health_signal_service.get_ingestion_gap_status(
            session, scoped_orgs=["test-org"]
        )
        assert result == []


class TestGetSystemHealthEvents:
    """Test ``get_system_health_events``."""

    @pytest.mark.asyncio
    async def test_returns_events(self) -> None:
        rows = [
            {
                "id": 1,
                "occurred_at": "2024-06-15T10:00:00",
                "org": "test-org",
                "signal_type": "ingestion_gap",
                "severity": "warning",
                "detail": {"minutes_gap": 120},
            }
        ]
        session = _mock_session_with_mappings(rows)
        result = await health_signal_service.get_system_health_events(
            session, scoped_orgs=["test-org"]
        )
        assert len(result) == 1
        assert result[0]["signal_type"] == "ingestion_gap"

    @pytest.mark.asyncio
    async def test_empty_result(self) -> None:
        session = _mock_session_with_mappings([])
        result = await health_signal_service.get_system_health_events(
            session, scoped_orgs=["test-org"]
        )
        assert result == []


class TestGetThreatIntelSummary:
    """Test ``get_threat_intel_summary``."""

    @pytest.mark.asyncio
    async def test_returns_summary(self) -> None:
        row = {
            "total_domains": 100,
            "active_domains": 80,
            "expired_domains": 5,
            "last_added_at": "2024-06-15T00:00:00",
        }
        session = _mock_session_with_mappings([row])
        result = await health_signal_service.get_threat_intel_summary(
            session, scoped_orgs=["test-org"]
        )
        assert isinstance(result, dict)
        assert result["total_domains"] == 100

    @pytest.mark.asyncio
    async def test_empty_result(self) -> None:
        session = _mock_session_with_mappings([])
        result = await health_signal_service.get_threat_intel_summary(
            session, scoped_orgs=["test-org"]
        )
        assert result["total_domains"] == 0
        assert result["last_added_at"] is None


# ===========================================================================
# Router endpoint tests
# ===========================================================================

_SUMMARY_MOCK_PATCHES = [
    (
        "app.routers.health_signals.health_signal_service.get_secret_scanning_alert_health",
        [],
    ),
    (
        "app.routers.health_signals.health_signal_service.get_security_coverage",
        [],
    ),
    (
        "app.routers.health_signals.health_signal_service.get_sso_health",
        [],
    ),
]


def _patch_rbac_and_service(
    service_name: str,
    return_value: object,
) -> tuple:
    """Return a tuple of patch contexts for rbac + a single service function."""
    rbac_patch = patch(
        "app.routers.health_signals.rbac_service.get_scoped_orgs",
        new_callable=AsyncMock,
        return_value=["test-org"],
    )
    svc_patch = patch(
        f"app.routers.health_signals.health_signal_service.{service_name}",
        new_callable=AsyncMock,
        return_value=return_value,
    )
    return rbac_patch, svc_patch


class TestNewRouterEndpoints:
    """Test all 14 new router endpoints return 200 with expected shapes."""

    def test_security_posture_returns_200(self) -> None:
        app = _build_app_with_access()
        rbac_p, svc_p = _patch_rbac_and_service("get_security_coverage", [])
        with rbac_p, svc_p:
            client = TestClient(app)
            resp = client.get("/api/v1/health-signals/security-posture")
            assert resp.status_code == 200
            assert "coverage" in resp.json()

    def test_secret_scanning_returns_200(self) -> None:
        app = _build_app_with_access()
        rbac_p, svc_p = _patch_rbac_and_service("get_secret_scanning_alert_health", [])
        with rbac_p, svc_p:
            client = TestClient(app)
            resp = client.get("/api/v1/health-signals/secret-scanning")
            assert resp.status_code == 200
            assert "alerts" in resp.json()

    def test_sso_returns_200(self) -> None:
        app = _build_app_with_access()
        rbac_p, svc_p = _patch_rbac_and_service("get_sso_health", [])
        with rbac_p, svc_p:
            client = TestClient(app)
            resp = client.get("/api/v1/health-signals/sso")
            assert resp.status_code == 200
            assert "sso" in resp.json()

    def test_ip_allowlist_returns_200(self) -> None:
        app = _build_app_with_access()
        rbac_p, svc_p = _patch_rbac_and_service("get_audit_stream_status", [])
        with rbac_p, svc_p:
            client = TestClient(app)
            resp = client.get("/api/v1/health-signals/ip-allowlist")
            assert resp.status_code == 200
            assert "stream_status" in resp.json()

    def test_privilege_changes_returns_200(self) -> None:
        app = _build_app_with_access()
        rbac_p, svc_p = _patch_rbac_and_service("get_privilege_change_summary", [])
        with rbac_p, svc_p:
            client = TestClient(app)
            resp = client.get("/api/v1/health-signals/privilege-changes")
            assert resp.status_code == 200
            assert "changes" in resp.json()

    def test_code_scanning_returns_200(self) -> None:
        app = _build_app_with_access()
        rbac_p, svc_p = _patch_rbac_and_service("get_code_scanning_health", [])
        with rbac_p, svc_p:
            client = TestClient(app)
            resp = client.get("/api/v1/health-signals/code-scanning")
            assert resp.status_code == 200
            assert "alerts" in resp.json()

    def test_vulnerabilities_returns_200(self) -> None:
        app = _build_app_with_access()
        rbac_p, svc_p = _patch_rbac_and_service("get_vulnerability_aging", [])
        with rbac_p, svc_p:
            client = TestClient(app)
            resp = client.get("/api/v1/health-signals/vulnerabilities")
            assert resp.status_code == 200
            assert "aging" in resp.json()

    def test_app_governance_returns_200(self) -> None:
        app = _build_app_with_access()
        rbac_p, svc_p = _patch_rbac_and_service("get_app_governance_summary", [])
        with rbac_p, svc_p:
            client = TestClient(app)
            resp = client.get("/api/v1/health-signals/app-governance")
            assert resp.status_code == 200
            assert "governance" in resp.json()

    def test_workflows_returns_200(self) -> None:
        app = _build_app_with_access()
        rbac_p, svc_p = _patch_rbac_and_service("get_workflow_health", [])
        with rbac_p, svc_p:
            client = TestClient(app)
            resp = client.get("/api/v1/health-signals/workflows")
            assert resp.status_code == 200
            assert "workflows" in resp.json()

    def test_copilot_governance_returns_200(self) -> None:
        app = _build_app_with_access()
        rbac_p, svc_p = _patch_rbac_and_service("get_copilot_seat_health", [])
        with rbac_p, svc_p:
            client = TestClient(app)
            resp = client.get("/api/v1/health-signals/copilot-governance")
            assert resp.status_code == 200
            assert "seats" in resp.json()

    def test_codespaces_returns_200(self) -> None:
        app = _build_app_with_access()
        rbac_p, svc_p = _patch_rbac_and_service("get_codespace_cost_signals", [])
        with rbac_p, svc_p:
            client = TestClient(app)
            resp = client.get("/api/v1/health-signals/codespaces")
            assert resp.status_code == 200
            assert "codespaces" in resp.json()

    def test_runners_returns_200(self) -> None:
        app = _build_app_with_access()
        rbac_p, svc_p = _patch_rbac_and_service("get_runner_fleet_health", [])
        with rbac_p, svc_p:
            client = TestClient(app)
            resp = client.get("/api/v1/health-signals/runners")
            assert resp.status_code == 200
            assert "runners" in resp.json()

    def test_branch_protection_returns_200(self) -> None:
        app = _build_app_with_access()
        rbac_p, svc_p = _patch_rbac_and_service("get_branch_protection_health", [])
        with rbac_p, svc_p:
            client = TestClient(app)
            resp = client.get("/api/v1/health-signals/branch-protection")
            assert resp.status_code == 200
            assert "protection" in resp.json()

    def test_system_health_returns_200(self) -> None:
        app = _build_app_with_access()
        rbac = patch(
            "app.routers.health_signals.rbac_service.get_scoped_orgs",
            new_callable=AsyncMock,
            return_value=["test-org"],
        )
        gap_p = patch(
            "app.routers.health_signals.health_signal_service.get_ingestion_gap_status",
            new_callable=AsyncMock,
            return_value=[],
        )
        evt_p = patch(
            "app.routers.health_signals.health_signal_service.get_system_health_events",
            new_callable=AsyncMock,
            return_value=[],
        )
        stream_p = patch(
            "app.routers.health_signals.health_signal_service.get_audit_stream_status",
            new_callable=AsyncMock,
            return_value=[],
        )
        with rbac, gap_p, evt_p, stream_p:
            client = TestClient(app)
            resp = client.get("/api/v1/health-signals/system")
            assert resp.status_code == 200
            data = resp.json()
            assert "ingestion_gaps" in data
            assert "health_events" in data
            assert "stream_status" in data


class TestUpdatedSummaryEndpoint:
    """Verify the updated /summary endpoint includes expanded fields."""

    def test_summary_includes_new_fields(self) -> None:
        app = _build_app_with_access()
        summary_data = {
            "stale_repos": 2,
            "pat_no_expiry": 5,
            "pat_stale": 1,
            "bypass_offenders": 3,
            "ext_collab_total": 8,
            "ext_collab_elevated": 1,
        }
        rbac = patch(
            "app.routers.health_signals.rbac_service.get_scoped_orgs",
            new_callable=AsyncMock,
            return_value=["test-org"],
        )
        health_p = patch(
            "app.routers.health_signals.health_signal_service.get_health_summary",
            new_callable=AsyncMock,
            return_value=summary_data,
        )
        scanning_p = patch(
            "app.routers.health_signals.health_signal_service.get_secret_scanning_alert_health",
            new_callable=AsyncMock,
            return_value=[{"unresolved_total": 7}],
        )
        coverage_p = patch(
            "app.routers.health_signals.health_signal_service.get_security_coverage",
            new_callable=AsyncMock,
            return_value=[{"any_feature_disabled": 3}],
        )
        sso_p = patch(
            "app.routers.health_signals.health_signal_service.get_sso_health",
            new_callable=AsyncMock,
            return_value=[{"sso_state": "disabled"}, {"sso_state": "enabled"}],
        )
        with rbac, health_p, scanning_p, coverage_p, sso_p:
            client = TestClient(app)
            resp = client.get("/api/v1/health-signals/summary")
            assert resp.status_code == 200
            data = resp.json()
            assert data["stale_repos"] == 2
            assert data["secret_scanning_unresolved"] == 7
            assert data["security_features_disabled_7d"] == 3
            assert data["sso_disabled_orgs"] == 1

    def test_summary_zero_values_when_no_data(self) -> None:
        app = _build_app_with_access()
        summary_data = {
            "stale_repos": 0,
            "pat_no_expiry": 0,
            "pat_stale": 0,
            "bypass_offenders": 0,
            "ext_collab_total": 0,
            "ext_collab_elevated": 0,
        }
        rbac = patch(
            "app.routers.health_signals.rbac_service.get_scoped_orgs",
            new_callable=AsyncMock,
            return_value=["test-org"],
        )
        health_p = patch(
            "app.routers.health_signals.health_signal_service.get_health_summary",
            new_callable=AsyncMock,
            return_value=summary_data,
        )
        scanning_p = patch(
            "app.routers.health_signals.health_signal_service.get_secret_scanning_alert_health",
            new_callable=AsyncMock,
            return_value=[],
        )
        coverage_p = patch(
            "app.routers.health_signals.health_signal_service.get_security_coverage",
            new_callable=AsyncMock,
            return_value=[],
        )
        sso_p = patch(
            "app.routers.health_signals.health_signal_service.get_sso_health",
            new_callable=AsyncMock,
            return_value=[],
        )
        with rbac, health_p, scanning_p, coverage_p, sso_p:
            client = TestClient(app)
            resp = client.get("/api/v1/health-signals/summary")
            assert resp.status_code == 200
            data = resp.json()
            assert data["secret_scanning_unresolved"] == 0
            assert data["security_features_disabled_7d"] == 0
            assert data["sso_disabled_orgs"] == 0


# ===========================================================================
# Threat intel service tests
# ===========================================================================


class TestIsMaliciousDomain:
    """Test ``threat_intel_service.is_malicious_domain``."""

    @pytest.mark.asyncio
    async def test_match_found(self) -> None:
        session = _mock_session_with_mappings(
            [
                {
                    "domain": "*.evil.com",
                    "source": "blocklist-v1",
                    "confidence": 0.95,
                }
            ]
        )
        is_bad, source = await threat_intel_service.is_malicious_domain(
            session, "https://sub.evil.com/path"
        )
        assert is_bad is True
        assert source == "blocklist-v1"

    @pytest.mark.asyncio
    async def test_no_match(self) -> None:
        session = _mock_session_with_mappings(
            [
                {
                    "domain": "*.evil.com",
                    "source": "blocklist-v1",
                    "confidence": 0.95,
                }
            ]
        )
        is_bad, source = await threat_intel_service.is_malicious_domain(
            session, "https://safe.example.com"
        )
        assert is_bad is False
        assert source is None

    @pytest.mark.asyncio
    async def test_no_hostname(self) -> None:
        session = _mock_session_with_mappings([])
        is_bad, source = await threat_intel_service.is_malicious_domain(session, "not-a-url")
        assert is_bad is False
        assert source is None

    @pytest.mark.asyncio
    async def test_empty_domain_list(self) -> None:
        session = _mock_session_with_mappings([])
        is_bad, source = await threat_intel_service.is_malicious_domain(
            session, "https://any.com/path"
        )
        assert is_bad is False
        assert source is None


class TestGetDomainList:
    """Test ``threat_intel_service.get_domain_list``."""

    @pytest.mark.asyncio
    async def test_returns_list(self) -> None:
        rows = [
            {
                "id": 1,
                "domain": "evil.com",
                "source": "manual",
                "confidence": 0.9,
                "active": True,
                "added_at": "2024-01-01",
                "added_by": "admin",
                "expires_at": None,
                "notes": "test",
            }
        ]
        session = _mock_session_with_mappings(rows)
        result = await threat_intel_service.get_domain_list(session, active_only=True)
        assert len(result) == 1
        assert result[0]["domain"] == "evil.com"

    @pytest.mark.asyncio
    async def test_inactive_domains(self) -> None:
        session = _mock_session_with_mappings([])
        result = await threat_intel_service.get_domain_list(session, active_only=False)
        assert result == []


# ===========================================================================
# Ingestion worker normalization test
# ===========================================================================


class TestSecretsPassedNormalization:
    """Test that _normalize_event strips secrets_passed for workflow jobs."""

    def _get_worker_instance(self):
        """Create a minimal worker for testing _normalize_event."""
        from app.workers.ingestion.base import AbstractIngestWorker

        class FakeWorker(AbstractIngestWorker):
            ingestion_source = "test"

            async def run(self) -> None:
                pass

        return FakeWorker.__new__(FakeWorker)

    def test_secrets_passed_stripped_and_counted(self) -> None:
        worker = self._get_worker_instance()
        worker.ingestion_source = "test"
        raw = {
            "action": "workflows.prepared_workflow_job",
            "@timestamp": 1700000000000,
            "org": "test-org",
            "actor": "ci-bot",
            "secrets_passed": ["SECRET_A", "SECRET_B", "SECRET_C"],
        }
        result = worker._normalize_event(raw, dedup_hash="abc123")
        assert result is not None
        import json

        data = json.loads(result["data"])
        assert "secrets_passed" not in data
        assert data["secrets_passed_count"] == 3

    def test_non_workflow_event_preserves_data(self) -> None:
        worker = self._get_worker_instance()
        worker.ingestion_source = "test"
        raw = {
            "action": "repo.create",
            "@timestamp": 1700000000000,
            "org": "test-org",
            "actor": "admin",
            "some_field": "value",
        }
        result = worker._normalize_event(raw, dedup_hash="def456")
        assert result is not None
        import json

        data = json.loads(result["data"])
        assert data.get("some_field") == "value"

    def test_secrets_passed_empty_list(self) -> None:
        worker = self._get_worker_instance()
        worker.ingestion_source = "test"
        raw = {
            "action": "workflows.prepared_workflow_job",
            "@timestamp": 1700000000000,
            "org": "test-org",
            "secrets_passed": [],
        }
        result = worker._normalize_event(raw, dedup_hash="ghi789")
        assert result is not None
        import json

        data = json.loads(result["data"])
        assert "secrets_passed" not in data
        assert data["secrets_passed_count"] == 0

    def test_secrets_passed_not_list(self) -> None:
        worker = self._get_worker_instance()
        worker.ingestion_source = "test"
        raw = {
            "action": "workflows.prepared_workflow_job",
            "@timestamp": 1700000000000,
            "org": "test-org",
            "secrets_passed": "not-a-list",
        }
        result = worker._normalize_event(raw, dedup_hash="jkl012")
        assert result is not None
        import json

        data = json.loads(result["data"])
        assert data["secrets_passed_count"] == 0


# ===========================================================================
# Celery beat schedule test
# ===========================================================================


class TestCeleryBeatSchedule:
    """Verify the ingestion gap check is in the beat schedule."""

    def test_ingestion_gap_task_in_schedule(self) -> None:
        from app.celery_app import celery_app

        schedule = celery_app.conf.beat_schedule
        assert "check-ingestion-gaps" in schedule
        entry = schedule["check-ingestion-gaps"]
        assert entry["task"] == "app.workers.ingestion_health.check_ingestion_gaps"
        assert entry["schedule"] == 3600.0
        assert entry["options"]["queue"] == "baseline"


# ===========================================================================
# Scoped orgs parameter tests for new functions
# ===========================================================================


class TestNewFunctionsScopedOrgsParam:
    """Verify all new service functions pass scoped_orgs to SQL."""

    @pytest.mark.asyncio
    async def test_audit_stream_status_passes_scoped_orgs(self) -> None:
        session = _mock_session_with_mappings([])
        await health_signal_service.get_audit_stream_status(session, scoped_orgs=["org-a", "org-b"])
        call_args = session.execute.call_args
        # Positional args: (text_clause, params_dict)
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]
        assert params["scoped_orgs"] == ["org-a", "org-b"]

    @pytest.mark.asyncio
    async def test_security_coverage_passes_scoped_orgs(self) -> None:
        session = _mock_session_with_mappings([])
        await health_signal_service.get_security_coverage(session, scoped_orgs=["org-x"])
        call_args = session.execute.call_args
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]
        assert params["scoped_orgs"] == ["org-x"]

    @pytest.mark.asyncio
    async def test_ingestion_gap_status_passes_scoped_orgs(self) -> None:
        session = _mock_session_with_mappings([])
        await health_signal_service.get_ingestion_gap_status(session, scoped_orgs=["org-z"])
        call_args = session.execute.call_args
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]
        assert params["scoped_orgs"] == ["org-z"]
