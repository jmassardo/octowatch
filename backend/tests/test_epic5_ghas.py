"""Tests for Epic 5: GHAS Alert Ingestion.

Covers:
  - Individual alert model creation and constraints
  - Sync worker upsert functions with mock GitHub API responses
  - Health signal service queries against new alert tables
  - Router endpoint responses
  - Unified security endpoint
  - Aging calculation accuracy
  - 90-day critical aging vulnerability signal generation
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ═══════════════════════════════════════════════════════════════════════════════
# Model Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestSecretScanningAlertModel:
    """Tests for the SecretScanningAlert ORM model."""

    def test_tablename(self) -> None:
        from app.models.github_sync import SecretScanningAlert

        assert SecretScanningAlert.__tablename__ == "secret_scanning_alerts"

    def test_unique_constraint_name(self) -> None:
        from app.models.github_sync import SecretScanningAlert

        constraints = {
            c.name for c in SecretScanningAlert.__table__.constraints if hasattr(c, "name")
        }
        assert "uq_secret_scanning_alert" in constraints

    def test_columns_exist(self) -> None:
        from app.models.github_sync import SecretScanningAlert

        cols = {c.name for c in SecretScanningAlert.__table__.columns}
        expected = {
            "id",
            "org_slug",
            "alert_number",
            "repo_full_name",
            "secret_type",
            "secret_type_display",
            "file_path",
            "commit_sha",
            "state",
            "resolution",
            "push_protection_bypassed",
            "push_protection_bypassed_by",
            "created_at",
            "resolved_at",
            "synced_at",
        }
        assert expected.issubset(cols)

    def test_indexes_exist(self) -> None:
        from app.models.github_sync import SecretScanningAlert

        idx_names = {idx.name for idx in SecretScanningAlert.__table__.indexes}
        assert "idx_secret_scanning_alert_org_state" in idx_names
        assert "idx_secret_scanning_alert_repo" in idx_names


class TestCodeScanningAlertModel:
    """Tests for the CodeScanningAlert ORM model."""

    def test_tablename(self) -> None:
        from app.models.github_sync import CodeScanningAlert

        assert CodeScanningAlert.__tablename__ == "code_scanning_alerts"

    def test_unique_constraint_name(self) -> None:
        from app.models.github_sync import CodeScanningAlert

        constraints = {
            c.name for c in CodeScanningAlert.__table__.constraints if hasattr(c, "name")
        }
        assert "uq_code_scanning_alert" in constraints

    def test_columns_exist(self) -> None:
        from app.models.github_sync import CodeScanningAlert

        cols = {c.name for c in CodeScanningAlert.__table__.columns}
        expected = {
            "id",
            "org_slug",
            "alert_number",
            "repo_full_name",
            "rule_id",
            "rule_description",
            "severity",
            "security_severity",
            "cwe_ids",
            "tool_name",
            "file_path",
            "start_line",
            "state",
            "dismissed_by",
            "dismissed_reason",
            "dismissed_at",
            "created_at",
            "fixed_at",
            "synced_at",
        }
        assert expected.issubset(cols)

    def test_indexes_exist(self) -> None:
        from app.models.github_sync import CodeScanningAlert

        idx_names = {idx.name for idx in CodeScanningAlert.__table__.indexes}
        assert "idx_code_scanning_alert_org_state" in idx_names
        assert "idx_code_scanning_alert_repo" in idx_names


class TestDependabotAlertModel:
    """Tests for the DependabotAlert ORM model."""

    def test_tablename(self) -> None:
        from app.models.github_sync import DependabotAlert

        assert DependabotAlert.__tablename__ == "dependabot_alerts"

    def test_unique_constraint_name(self) -> None:
        from app.models.github_sync import DependabotAlert

        constraints = {c.name for c in DependabotAlert.__table__.constraints if hasattr(c, "name")}
        assert "uq_dependabot_alert" in constraints

    def test_columns_exist(self) -> None:
        from app.models.github_sync import DependabotAlert

        cols = {c.name for c in DependabotAlert.__table__.columns}
        expected = {
            "id",
            "org_slug",
            "alert_number",
            "repo_full_name",
            "package_name",
            "package_ecosystem",
            "severity",
            "cvss_score",
            "cve_id",
            "cwe_ids",
            "vulnerable_version_range",
            "patched_version",
            "state",
            "dismissed_by",
            "dismissed_reason",
            "created_at",
            "fixed_at",
            "auto_dismissed_at",
            "synced_at",
        }
        assert expected.issubset(cols)

    def test_indexes_exist(self) -> None:
        from app.models.github_sync import DependabotAlert

        idx_names = {idx.name for idx in DependabotAlert.__table__.indexes}
        assert "idx_dependabot_alert_org_state" in idx_names
        assert "idx_dependabot_alert_repo" in idx_names


# ═══════════════════════════════════════════════════════════════════════════════
# Model Export Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestGHASModelExports:
    """Verify new GHAS models are exported from __init__.py."""

    def test_secret_scanning_alert_exported(self) -> None:
        from app.models import SecretScanningAlert

        assert SecretScanningAlert is not None

    def test_code_scanning_alert_exported(self) -> None:
        from app.models import CodeScanningAlert

        assert CodeScanningAlert is not None

    def test_dependabot_alert_exported(self) -> None:
        from app.models import DependabotAlert

        assert DependabotAlert is not None


# ═══════════════════════════════════════════════════════════════════════════════
# Schema Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestGHASSchemas:
    """Tests for new GHAS Pydantic schemas."""

    def test_secret_scanning_alert_item(self) -> None:
        from app.schemas.health_signal import SecretScanningAlertItem

        item = SecretScanningAlertItem(
            id=1,
            org_slug="test-org",
            alert_number=42,
            repo_full_name="test-org/repo",
            secret_type="github_personal_access_token",
            state="open",
            created_at="2024-01-01T00:00:00Z",
        )
        assert item.alert_number == 42
        assert item.state == "open"
        assert item.push_protection_bypassed is False

    def test_code_scanning_alert_item(self) -> None:
        from app.schemas.health_signal import CodeScanningAlertItem

        item = CodeScanningAlertItem(
            id=1,
            org_slug="test-org",
            alert_number=10,
            repo_full_name="test-org/repo",
            rule_id="js/sql-injection",
            state="open",
            created_at="2024-01-01T00:00:00Z",
        )
        assert item.rule_id == "js/sql-injection"
        assert item.cwe_ids is None

    def test_dependabot_alert_item(self) -> None:
        from app.schemas.health_signal import DependabotAlertItem

        item = DependabotAlertItem(
            id=1,
            org_slug="test-org",
            alert_number=5,
            repo_full_name="test-org/repo",
            package_name="lodash",
            state="open",
            created_at="2024-01-01T00:00:00Z",
        )
        assert item.package_name == "lodash"
        assert item.cvss_score is None

    def test_unified_security_response(self) -> None:
        from app.schemas.health_signal import UnifiedSecurityResponse

        resp = UnifiedSecurityResponse()
        assert resp.secret_scanning.open == 0
        assert resp.code_scanning.total == 0
        assert resp.dependabot.critical_aging_gt_90d == 0
        assert resp.detections.active == 0
        assert resp.trend_30d == []


# ═══════════════════════════════════════════════════════════════════════════════
# Sync Worker Upsert Function Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestUpsertSecretScanningAlerts:
    """Tests for _upsert_secret_scanning_alerts."""

    @pytest.mark.asyncio
    async def test_upserts_individual_alerts(self) -> None:
        from app.workers.github_sync_worker import _upsert_secret_scanning_alerts

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()

        items = [
            {
                "number": 1,
                "repository": {"full_name": "test-org/repo1"},
                "secret_type": "github_personal_access_token",
                "secret_type_display_name": "GitHub PAT",
                "state": "open",
                "resolution": None,
                "push_protection_bypassed": False,
                "push_protection_bypassed_by": None,
                "created_at": "2024-01-01T00:00:00Z",
                "resolved_at": None,
                "locations": [{"details": {"path": "config.yml", "commit_sha": "abc123"}}],
            },
            {
                "number": 2,
                "repository": {"full_name": "test-org/repo2"},
                "secret_type": "aws_access_key_id",
                "secret_type_display_name": "AWS Key",
                "state": "resolved",
                "resolution": "revoked",
                "push_protection_bypassed": True,
                "push_protection_bypassed_by": {"login": "alice"},
                "created_at": "2024-01-05T00:00:00Z",
                "resolved_at": "2024-01-06T12:00:00Z",
                "locations": [],
            },
        ]

        await _upsert_secret_scanning_alerts(mock_session, "test-org", items)

        assert mock_session.execute.call_count == 2
        assert mock_session.commit.call_count == 1

        # Verify first call parameters
        first_call_params = mock_session.execute.call_args_list[0][0][1]
        assert first_call_params["org_slug"] == "test-org"
        assert first_call_params["alert_number"] == 1
        assert first_call_params["secret_type"] == "github_personal_access_token"
        assert first_call_params["file_path"] == "config.yml"
        assert first_call_params["commit_sha"] == "abc123"

        # Verify second call includes bypassed info
        second_call_params = mock_session.execute.call_args_list[1][0][1]
        assert second_call_params["push_protection_bypassed"] is True
        assert second_call_params["push_protection_bypassed_by"] == "alice"
        assert second_call_params["resolution"] == "revoked"


class TestUpsertCodeScanningAlerts:
    """Tests for _upsert_code_scanning_alerts."""

    @pytest.mark.asyncio
    async def test_upserts_individual_alerts(self) -> None:
        from app.workers.github_sync_worker import _upsert_code_scanning_alerts

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()

        items = [
            {
                "number": 10,
                "repository": {"full_name": "test-org/repo1"},
                "rule": {
                    "id": "js/sql-injection",
                    "description": "SQL injection",
                    "severity": "error",
                    "security_severity_level": "high",
                    "tags": ["external/cwe/cwe-89", "security"],
                },
                "tool": {"name": "CodeQL"},
                "most_recent_instance": {
                    "location": {"path": "src/db.js", "start_line": 42},
                },
                "state": "open",
                "dismissed_by": None,
                "dismissed_reason": None,
                "dismissed_at": None,
                "created_at": "2024-03-01T00:00:00Z",
                "fixed_at": None,
            },
        ]

        await _upsert_code_scanning_alerts(mock_session, "test-org", items)

        assert mock_session.execute.call_count == 1
        assert mock_session.commit.call_count == 1

        params = mock_session.execute.call_args_list[0][0][1]
        assert params["org_slug"] == "test-org"
        assert params["alert_number"] == 10
        assert params["rule_id"] == "js/sql-injection"
        assert params["severity"] == "error"
        assert params["security_severity"] == "high"
        assert params["cwe_ids"] == ["CWE-89"]
        assert params["tool_name"] == "CodeQL"
        assert params["file_path"] == "src/db.js"
        assert params["start_line"] == 42

    @pytest.mark.asyncio
    async def test_dismissed_alert_mapping(self) -> None:
        from app.workers.github_sync_worker import _upsert_code_scanning_alerts

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()

        items = [
            {
                "number": 20,
                "repository": {"full_name": "test-org/repo1"},
                "rule": {"id": "py/hardcoded-credentials", "description": "Hardcoded creds"},
                "tool": {"name": "CodeQL"},
                "most_recent_instance": {"location": {}},
                "state": "dismissed",
                "dismissed_by": {"login": "bob"},
                "dismissed_reason": "won't fix",
                "dismissed_at": "2024-03-15T10:00:00Z",
                "created_at": "2024-03-01T00:00:00Z",
                "fixed_at": None,
            },
        ]

        await _upsert_code_scanning_alerts(mock_session, "test-org", items)

        params = mock_session.execute.call_args_list[0][0][1]
        from datetime import UTC, datetime

        assert params["dismissed_by"] == "bob"
        assert params["dismissed_reason"] == "won't fix"
        assert params["dismissed_at"] == datetime(2024, 3, 15, 10, 0, 0, tzinfo=UTC)


class TestUpsertDependabotAlerts:
    """Tests for _upsert_dependabot_alerts."""

    @pytest.mark.asyncio
    async def test_upserts_individual_alerts(self) -> None:
        from app.workers.github_sync_worker import _upsert_dependabot_alerts

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()

        items = [
            {
                "number": 5,
                "repository": {"full_name": "test-org/repo1"},
                "security_vulnerability": {
                    "package": {"name": "lodash", "ecosystem": "npm"},
                    "severity": "critical",
                    "vulnerable_version_range": "< 4.17.21",
                    "first_patched_version": {"identifier": "4.17.21"},
                },
                "security_advisory": {
                    "cve_id": "CVE-2021-23337",
                    "cvss": {"score": 9.8},
                    "cwes": [{"cwe_id": "CWE-94"}],
                },
                "state": "open",
                "dismissed_by": None,
                "dismissed_reason": None,
                "created_at": "2024-01-01T00:00:00Z",
                "fixed_at": None,
                "auto_dismissed_at": None,
            },
        ]

        await _upsert_dependabot_alerts(mock_session, "test-org", items)

        assert mock_session.execute.call_count == 1
        assert mock_session.commit.call_count == 1

        params = mock_session.execute.call_args_list[0][0][1]
        assert params["org_slug"] == "test-org"
        assert params["alert_number"] == 5
        assert params["package_name"] == "lodash"
        assert params["package_ecosystem"] == "npm"
        assert params["severity"] == "critical"
        assert params["cvss_score"] == 9.8
        assert params["cve_id"] == "CVE-2021-23337"
        assert params["cwe_ids"] == ["CWE-94"]
        assert params["vulnerable_version_range"] == "< 4.17.21"
        assert params["patched_version"] == "4.17.21"

    @pytest.mark.asyncio
    async def test_handles_missing_advisory_fields(self) -> None:
        from app.workers.github_sync_worker import _upsert_dependabot_alerts

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()

        items = [
            {
                "number": 10,
                "repository": {"full_name": "test-org/repo2"},
                "security_vulnerability": {
                    "package": {"name": "express"},
                    "severity": "low",
                },
                "security_advisory": {},
                "state": "dismissed",
                "dismissed_by": {"login": "charlie"},
                "dismissed_reason": "tolerable_risk",
                "created_at": "2024-02-01T00:00:00Z",
                "fixed_at": None,
                "auto_dismissed_at": None,
            },
        ]

        await _upsert_dependabot_alerts(mock_session, "test-org", items)

        params = mock_session.execute.call_args_list[0][0][1]
        assert params["package_name"] == "express"
        assert params["cvss_score"] is None
        assert params["cve_id"] is None
        assert params["patched_version"] is None
        assert params["dismissed_by"] == "charlie"


# ═══════════════════════════════════════════════════════════════════════════════
# _upsert_items Integration Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestUpsertItemsGHASDispatch:
    """Tests that _upsert_items dispatches to both summary and individual alert upserts."""

    @pytest.mark.asyncio
    async def test_secret_scanning_alerts_dispatches_both(self) -> None:
        from app.workers.github_sync_worker import _upsert_items

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()

        raw_alerts = [
            {
                "number": 1,
                "repository": {"full_name": "org/repo"},
                "secret_type": "token",
                "state": "open",
                "created_at": "2024-01-01T00:00:00Z",
            }
        ]
        items: list[dict[str, object]] = [
            {
                "_enterprise_slug": "org",
                "_org": "org",
                "open_count": 1,
                "resolved_count": 0,
                "total_count": 1,
                "_raw_alerts": raw_alerts,
            }
        ]

        with (
            patch(
                "app.workers.github_sync_worker._upsert_secret_scanning_summary",
                new_callable=AsyncMock,
            ) as mock_summary,
            patch(
                "app.workers.github_sync_worker._upsert_secret_scanning_alerts",
                new_callable=AsyncMock,
            ) as mock_alerts,
        ):
            await _upsert_items(mock_session, "secret_scanning_alerts", "org", items)
            mock_summary.assert_called_once_with(mock_session, "org", items)
            mock_alerts.assert_called_once_with(mock_session, "org", raw_alerts)

    @pytest.mark.asyncio
    async def test_dependabot_alerts_dispatches_both(self) -> None:
        from app.workers.github_sync_worker import _upsert_items

        mock_session = AsyncMock()

        raw_alerts = [
            {
                "number": 1,
                "repository": {"full_name": "org/repo"},
                "security_vulnerability": {"package": {"name": "pkg"}},
                "state": "open",
                "created_at": "2024-01-01T00:00:00Z",
            }
        ]
        items: list[dict[str, object]] = [
            {
                "_enterprise_slug": "org",
                "_org": "org",
                "open_count": 1,
                "fixed_count": 0,
                "dismissed_count": 0,
                "total_count": 1,
                "critical_count": 0,
                "high_count": 0,
                "medium_count": 0,
                "low_count": 0,
                "_raw_alerts": raw_alerts,
            }
        ]

        with (
            patch(
                "app.workers.github_sync_worker._upsert_dependabot_summary",
                new_callable=AsyncMock,
            ) as mock_summary,
            patch(
                "app.workers.github_sync_worker._upsert_dependabot_alerts",
                new_callable=AsyncMock,
            ) as mock_alerts,
        ):
            await _upsert_items(mock_session, "dependabot_alerts", "org", items)
            mock_summary.assert_called_once_with(mock_session, "org", items)
            mock_alerts.assert_called_once_with(mock_session, "org", raw_alerts)

    @pytest.mark.asyncio
    async def test_code_scanning_alerts_dispatches_both(self) -> None:
        from app.workers.github_sync_worker import _upsert_items

        mock_session = AsyncMock()

        raw_alerts = [
            {
                "number": 1,
                "repository": {"full_name": "org/repo"},
                "rule": {"id": "test"},
                "state": "open",
                "created_at": "2024-01-01T00:00:00Z",
            }
        ]
        items: list[dict[str, object]] = [
            {
                "_enterprise_slug": "org",
                "_org": "org",
                "open_count": 1,
                "fixed_count": 0,
                "dismissed_count": 0,
                "total_count": 1,
                "error_count": 0,
                "warning_count": 0,
                "note_count": 0,
                "_raw_alerts": raw_alerts,
            }
        ]

        with (
            patch(
                "app.workers.github_sync_worker._upsert_code_scanning_summary",
                new_callable=AsyncMock,
            ) as mock_summary,
            patch(
                "app.workers.github_sync_worker._upsert_code_scanning_alerts",
                new_callable=AsyncMock,
            ) as mock_alerts,
        ):
            await _upsert_items(mock_session, "code_scanning_alerts", "org", items)
            mock_summary.assert_called_once_with(mock_session, "org", items)
            mock_alerts.assert_called_once_with(mock_session, "org", raw_alerts)

    @pytest.mark.asyncio
    async def test_no_raw_alerts_skips_individual_upsert(self) -> None:
        """When _raw_alerts is empty, the individual upsert should not be called."""
        from app.workers.github_sync_worker import _upsert_items

        mock_session = AsyncMock()

        items: list[dict[str, object]] = [
            {
                "_enterprise_slug": "org",
                "_org": "org",
                "open_count": 0,
                "resolved_count": 0,
                "total_count": 0,
                "_raw_alerts": [],
            }
        ]

        with (
            patch(
                "app.workers.github_sync_worker._upsert_secret_scanning_summary",
                new_callable=AsyncMock,
            ) as mock_summary,
            patch(
                "app.workers.github_sync_worker._upsert_secret_scanning_alerts",
                new_callable=AsyncMock,
            ) as mock_alerts,
        ):
            await _upsert_items(mock_session, "secret_scanning_alerts", "org", items)
            mock_summary.assert_called_once()
            mock_alerts.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════════
# Health Signal Service Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestHealthSignalServiceGHAS:
    """Tests for updated health signal service queries."""

    @pytest.mark.asyncio
    async def test_secret_scanning_alert_health_returns_resolution_metrics(self) -> None:
        """Verify the service function calls the right SQL and returns proper structure."""
        from app.services.health_signal_service import get_secret_scanning_alert_health

        mock_mapping = MagicMock()
        mock_mapping.keys.return_value = [
            "org",
            "unresolved_total",
            "unresolved_gt_7d",
            "unresolved_gt_30d",
            "push_protection_bypassed_count",
            "avg_hours_to_resolve",
            "resolved_count",
            "total_count",
            "resolution_rate_pct",
        ]
        mock_mapping.__getitem__ = lambda self, key: {
            "org": "test-org",
            "unresolved_total": 5,
            "unresolved_gt_7d": 3,
            "unresolved_gt_30d": 1,
            "push_protection_bypassed_count": 2,
            "avg_hours_to_resolve": 24.5,
            "resolved_count": 10,
            "total_count": 15,
            "resolution_rate_pct": 66.7,
        }[key]

        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = [mock_mapping]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await get_secret_scanning_alert_health(mock_session, scoped_orgs=["test-org"])

        assert len(result) == 1
        mock_session.execute.assert_called_once()

        # Verify the SQL references secret_scanning_alerts table
        sql_call = mock_session.execute.call_args[0][0]
        assert "secret_scanning_alerts" in str(sql_call)

    @pytest.mark.asyncio
    async def test_code_scanning_health_queries_new_table(self) -> None:
        """Verify code scanning health queries the code_scanning_alerts table."""
        from app.services.health_signal_service import get_code_scanning_health

        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = []

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await get_code_scanning_health(mock_session, scoped_orgs=["test-org"])

        assert result == []
        sql_call = mock_session.execute.call_args[0][0]
        assert "code_scanning_alerts" in str(sql_call)

    @pytest.mark.asyncio
    async def test_vulnerability_aging_queries_new_table(self) -> None:
        """Verify vulnerability aging queries the dependabot_alerts table."""
        from app.services.health_signal_service import get_vulnerability_aging

        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = []

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await get_vulnerability_aging(mock_session, scoped_orgs=["test-org"])

        assert result == []
        sql_call = mock_session.execute.call_args[0][0]
        assert "dependabot_alerts" in str(sql_call)

    @pytest.mark.asyncio
    async def test_vulnerability_aging_has_90d_bucket(self) -> None:
        """Verify aging query includes age_gt_90d bucket."""
        from app.services.health_signal_service import get_vulnerability_aging

        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = []

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        await get_vulnerability_aging(mock_session, scoped_orgs=["test-org"])

        sql_call = str(mock_session.execute.call_args[0][0])
        assert "age_gt_90d" in sql_call
        assert "age_0_30d" in sql_call
        assert "age_30_60d" in sql_call
        assert "age_60_90d" in sql_call

    @pytest.mark.asyncio
    async def test_vulnerability_aging_critical_aging_signal(self) -> None:
        """Verify critical aging > 90d signal is included."""
        from app.services.health_signal_service import get_vulnerability_aging

        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = []

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        await get_vulnerability_aging(mock_session, scoped_orgs=["test-org"])

        sql_call = str(mock_session.execute.call_args[0][0])
        assert "critical_aging_gt_90d" in sql_call


# ═══════════════════════════════════════════════════════════════════════════════
# Unified Security Summary Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestUnifiedSecuritySummary:
    """Tests for the get_unified_security_summary service function."""

    @pytest.mark.asyncio
    async def test_returns_all_sections(self) -> None:
        from app.services.health_signal_service import get_unified_security_summary

        # Create mock results for each query
        def make_mock_result(data: dict[str, object]) -> MagicMock:
            mock_mapping = MagicMock()
            mock_mapping.keys.return_value = list(data.keys())
            mock_mapping.__getitem__ = lambda self, key: data[key]
            mock_mapping.get = lambda key, default=None: data.get(key, default)
            mock_first = MagicMock()
            mock_first.return_value = mock_mapping
            mock_result = MagicMock()
            mock_result.mappings.return_value.first = mock_first
            return mock_result

        def make_trend_result() -> MagicMock:
            mock_result = MagicMock()
            mock_result.mappings.return_value.all.return_value = []
            return mock_result

        call_count = 0

        async def mock_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:  # secret scanning
                return make_mock_result(
                    {
                        "open_secret_alerts": 3,
                        "resolved_secret_alerts": 7,
                        "total_secret_alerts": 10,
                        "bypassed_open": 1,
                    }
                )
            elif call_count == 2:  # code scanning
                return make_mock_result(
                    {
                        "open_code_alerts": 5,
                        "code_critical": 2,
                        "code_high": 1,
                        "code_medium": 1,
                        "code_low": 1,
                        "total_code_alerts": 20,
                    }
                )
            elif call_count == 3:  # dependabot
                return make_mock_result(
                    {
                        "open_dependabot_alerts": 8,
                        "dep_critical": 3,
                        "dep_high": 2,
                        "dep_medium": 2,
                        "dep_low": 1,
                        "total_dependabot_alerts": 30,
                        "critical_aging_gt_90d": 2,
                    }
                )
            elif call_count == 4:  # detections
                return make_mock_result(
                    {
                        "active_detections": 4,
                        "det_critical": 1,
                        "det_high": 2,
                        "det_medium": 1,
                        "det_low": 0,
                    }
                )
            else:  # trend
                return make_trend_result()

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=mock_execute)

        result = await get_unified_security_summary(mock_session, scoped_orgs=["test-org"])

        # Verify structure
        assert "secret_scanning" in result
        assert "code_scanning" in result
        assert "dependabot" in result
        assert "detections" in result
        assert "trend_30d" in result

        # Verify values
        assert result["secret_scanning"]["open"] == 3
        assert result["code_scanning"]["critical"] == 2
        assert result["dependabot"]["critical_aging_gt_90d"] == 2
        assert result["detections"]["active"] == 4


# ═══════════════════════════════════════════════════════════════════════════════
# Migration Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestAlembicMigration:
    """Tests for the Alembic migration file structure."""

    def test_migration_file_exists(self) -> None:
        from pathlib import Path

        migration_path = (
            Path(__file__).parent.parent / "alembic" / "versions" / "0030_add_ghas_alert_tables.py"
        )
        assert migration_path.exists(), f"Migration file not found at {migration_path}"

    def test_migration_revision_chain(self) -> None:
        from pathlib import Path

        migration_path = (
            Path(__file__).parent.parent / "alembic" / "versions" / "0030_add_ghas_alert_tables.py"
        )
        content = migration_path.read_text()
        assert 'revision = "0030"' in content
        assert 'down_revision = "0029"' in content

    def test_migration_creates_all_tables(self) -> None:
        from pathlib import Path

        migration_path = (
            Path(__file__).parent.parent / "alembic" / "versions" / "0030_add_ghas_alert_tables.py"
        )
        content = migration_path.read_text()
        assert "CREATE TABLE IF NOT EXISTS secret_scanning_alerts" in content
        assert "CREATE TABLE IF NOT EXISTS code_scanning_alerts" in content
        assert "CREATE TABLE IF NOT EXISTS dependabot_alerts" in content

    def test_migration_has_downgrade(self) -> None:
        from pathlib import Path

        migration_path = (
            Path(__file__).parent.parent / "alembic" / "versions" / "0030_add_ghas_alert_tables.py"
        )
        content = migration_path.read_text()
        assert "DROP TABLE IF EXISTS dependabot_alerts CASCADE" in content
        assert "DROP TABLE IF EXISTS code_scanning_alerts CASCADE" in content
        assert "DROP TABLE IF EXISTS secret_scanning_alerts CASCADE" in content


# ═══════════════════════════════════════════════════════════════════════════════
# Fetch Page Raw Alert Collection Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestFetchPageRawAlerts:
    """Tests that _fetch_page collects raw alerts for GHAS entity types."""

    @pytest.mark.asyncio
    async def test_secret_scanning_returns_raw_alerts(self) -> None:
        from app.workers.github_sync_worker import _fetch_page

        mock_rate_limiter = MagicMock()
        mock_rate_limiter.acquire = AsyncMock()
        mock_rate_limiter.release = MagicMock()
        mock_rate_limiter.update_from_headers = MagicMock()

        open_alert = {
            "number": 1,
            "state": "open",
            "secret_type": "github_pat",
            "repository": {"full_name": "org/repo"},
        }
        resolved_alert = {
            "number": 2,
            "state": "resolved",
            "secret_type": "aws_key",
            "repository": {"full_name": "org/repo"},
        }

        call_count = 0

        async def mock_get(url, headers, params, rate_limiter, **kwargs):
            nonlocal call_count
            call_count += 1
            resp = MagicMock()
            resp.status_code = 200
            resp.raise_for_status = MagicMock()
            # Empty headers → _has_next_page returns False, stopping pagination
            resp.headers = {}

            if call_count == 1:
                # First call: open alerts (state=open param) - returns 1 open alert
                resp.json = MagicMock(return_value=[open_alert])
            elif call_count == 2:
                # Second call: resolved alerts (state=resolved param) - returns 1 resolved alert
                resp.json = MagicMock(return_value=[resolved_alert])
            else:
                resp.json = MagicMock(return_value=[])
            return resp

        with patch("app.workers.github_sync_worker._github_get", side_effect=mock_get):
            items, cursor = await _fetch_page(
                "secret_scanning_alerts", "org", "fake-token", None, mock_rate_limiter
            )

        assert len(items) == 1
        summary = items[0]
        assert summary["open_count"] == 1
        assert summary["resolved_count"] == 1
        assert summary["total_count"] == 2
        assert "_raw_alerts" in summary
        assert len(summary["_raw_alerts"]) == 2
        assert cursor == "_done"

    @pytest.mark.asyncio
    async def test_dependabot_returns_raw_alerts(self) -> None:
        from app.workers.github_sync_worker import _fetch_page

        mock_rate_limiter = MagicMock()
        mock_rate_limiter.acquire = AsyncMock()
        mock_rate_limiter.release = MagicMock()
        mock_rate_limiter.update_from_headers = MagicMock()

        alert = {
            "number": 1,
            "state": "open",
            "security_vulnerability": {"severity": "critical", "package": {"name": "test"}},
        }

        async def mock_get(url, headers, params, rate_limiter, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            resp.raise_for_status = MagicMock()
            resp.headers = {}

            if params.get("page", 1) == 1:
                resp.json = MagicMock(return_value=[alert])
            else:
                resp.json = MagicMock(return_value=[])
            return resp

        with patch("app.workers.github_sync_worker._github_get", side_effect=mock_get):
            items, cursor = await _fetch_page(
                "dependabot_alerts", "org", "fake-token", None, mock_rate_limiter
            )

        assert len(items) == 1
        summary = items[0]
        assert "_raw_alerts" in summary
        assert len(summary["_raw_alerts"]) == 1
        assert summary["_raw_alerts"][0]["number"] == 1

    @pytest.mark.asyncio
    async def test_code_scanning_returns_raw_alerts(self) -> None:
        from app.workers.github_sync_worker import _fetch_page

        mock_rate_limiter = MagicMock()
        mock_rate_limiter.acquire = AsyncMock()
        mock_rate_limiter.release = MagicMock()
        mock_rate_limiter.update_from_headers = MagicMock()

        alert = {
            "number": 1,
            "state": "open",
            "rule": {"id": "test-rule", "severity": "error"},
        }

        async def mock_get(url, headers, params, rate_limiter, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            resp.raise_for_status = MagicMock()
            resp.headers = {}

            if params.get("page", 1) == 1:
                resp.json = MagicMock(return_value=[alert])
            else:
                resp.json = MagicMock(return_value=[])
            return resp

        with patch("app.workers.github_sync_worker._github_get", side_effect=mock_get):
            items, cursor = await _fetch_page(
                "code_scanning_alerts", "org", "fake-token", None, mock_rate_limiter
            )

        assert len(items) == 1
        summary = items[0]
        assert "_raw_alerts" in summary
        assert len(summary["_raw_alerts"]) == 1
        assert summary["error_count"] == 1


# ═══════════════════════════════════════════════════════════════════════════════
# Edge Case Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Tests for edge cases in GHAS data handling."""

    @pytest.mark.asyncio
    async def test_upsert_secret_alert_missing_repository(self) -> None:
        """Handle alerts with missing or null repository field."""
        from app.workers.github_sync_worker import _upsert_secret_scanning_alerts

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()

        items: list[dict[str, object]] = [
            {
                "number": 1,
                "repository": None,
                "secret_type": "generic",
                "state": "open",
                "created_at": "2024-01-01T00:00:00Z",
            }
        ]

        await _upsert_secret_scanning_alerts(mock_session, "org", items)
        params = mock_session.execute.call_args_list[0][0][1]
        assert params["repo_full_name"] == ""

    @pytest.mark.asyncio
    async def test_upsert_code_alert_no_rule_tags(self) -> None:
        """Handle code scanning alerts with no tags in rule."""
        from app.workers.github_sync_worker import _upsert_code_scanning_alerts

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()

        items = [
            {
                "number": 1,
                "repository": {"full_name": "org/repo"},
                "rule": {"id": "test", "description": "test rule"},
                "tool": {},
                "most_recent_instance": {},
                "state": "open",
                "created_at": "2024-01-01T00:00:00Z",
            }
        ]

        await _upsert_code_scanning_alerts(mock_session, "org", items)
        params = mock_session.execute.call_args_list[0][0][1]
        assert params["cwe_ids"] is None

    @pytest.mark.asyncio
    async def test_upsert_dependabot_no_security_vulnerability(self) -> None:
        """Handle dependabot alerts with empty security_vulnerability."""
        from app.workers.github_sync_worker import _upsert_dependabot_alerts

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()

        items = [
            {
                "number": 1,
                "repository": {"full_name": "org/repo"},
                "security_vulnerability": None,
                "security_advisory": None,
                "state": "open",
                "created_at": "2024-01-01T00:00:00Z",
            }
        ]

        await _upsert_dependabot_alerts(mock_session, "org", items)
        params = mock_session.execute.call_args_list[0][0][1]
        assert params["package_name"] == "unknown"
        assert params["severity"] is None
