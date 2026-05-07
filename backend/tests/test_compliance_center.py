"""Tests for the Compliance Center service and router."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_row(**kwargs: object) -> MagicMock:
    """Create a MagicMock that behaves like a SQLAlchemy Row with named attrs."""
    row = MagicMock()
    for key, value in kwargs.items():
        setattr(row, key, value)
    return row


def _mock_session() -> AsyncMock:
    """Return an ``AsyncSession`` mock with a default empty result set."""
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = []
    mock_result.fetchone.return_value = _make_row(cnt=0)
    session.execute = AsyncMock(return_value=mock_result)
    return session


def _mock_session_with_data(count: int = 5) -> AsyncMock:
    """Return an ``AsyncSession`` mock that returns non-zero counts."""
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = []
    mock_result.fetchone.return_value = _make_row(cnt=count)
    session.execute = AsyncMock(return_value=mock_result)
    return session


# ---------------------------------------------------------------------------
# Compliance Service Tests
# ---------------------------------------------------------------------------


class TestComplianceSummary:
    """Tests for get_compliance_summary."""

    @pytest.mark.asyncio
    async def test_summary_structure(self) -> None:
        """Summary should have all required fields."""
        from app.services.compliance_service import get_compliance_summary

        session = _mock_session()
        result = await get_compliance_summary(session)

        assert "overall_score" in result
        assert "frameworks_tracked" in result
        assert "controls_passing" in result
        assert "controls_total" in result
        assert "critical_gaps" in result
        assert "last_assessment_date" in result
        assert "frameworks" in result

    @pytest.mark.asyncio
    async def test_summary_framework_count(self) -> None:
        """Summary should track 4 frameworks."""
        from app.services.compliance_service import get_compliance_summary

        session = _mock_session()
        result = await get_compliance_summary(session)

        assert result["frameworks_tracked"] == 4
        assert len(result["frameworks"]) == 4

    @pytest.mark.asyncio
    async def test_summary_framework_names(self) -> None:
        """All expected frameworks should be present."""
        from app.services.compliance_service import get_compliance_summary

        session = _mock_session()
        result = await get_compliance_summary(session)

        names = {f["name"] for f in result["frameworks"]}
        assert names == {"soc2", "iso27001", "nist_csf", "gdpr"}

    @pytest.mark.asyncio
    async def test_summary_scores_range(self) -> None:
        """All scores should be between 0 and 100."""
        from app.services.compliance_service import get_compliance_summary

        session = _mock_session()
        result = await get_compliance_summary(session)

        assert 0 <= result["overall_score"] <= 100
        for fw in result["frameworks"]:
            assert 0 <= fw["score"] <= 100

    @pytest.mark.asyncio
    async def test_summary_with_org_filter(self) -> None:
        """Summary should accept org filter without error."""
        from app.services.compliance_service import get_compliance_summary

        session = _mock_session()
        result = await get_compliance_summary(session, org="acme")

        assert result["frameworks_tracked"] == 4

    @pytest.mark.asyncio
    async def test_summary_critical_gaps_calculation(self) -> None:
        """Critical gaps should equal total - passing."""
        from app.services.compliance_service import get_compliance_summary

        session = _mock_session()
        result = await get_compliance_summary(session)

        assert result["critical_gaps"] == result["controls_total"] - result["controls_passing"]


class TestFrameworkControls:
    """Tests for get_framework_controls."""

    @pytest.mark.asyncio
    async def test_soc2_controls(self) -> None:
        """SOC 2 framework should return controls."""
        from app.services.compliance_service import get_framework_controls

        session = _mock_session()
        result = await get_framework_controls(session, "soc2")

        assert result["name"] == "soc2"
        assert result["display_name"] == "SOC 2 Type II"
        assert "controls" in result
        assert len(result["controls"]) > 0

    @pytest.mark.asyncio
    async def test_iso27001_controls(self) -> None:
        """ISO 27001 framework should return controls."""
        from app.services.compliance_service import get_framework_controls

        session = _mock_session()
        result = await get_framework_controls(session, "iso27001")

        assert result["name"] == "iso27001"
        assert result["display_name"] == "ISO 27001"
        assert len(result["controls"]) > 0

    @pytest.mark.asyncio
    async def test_nist_csf_controls(self) -> None:
        """NIST CSF framework should return controls."""
        from app.services.compliance_service import get_framework_controls

        session = _mock_session()
        result = await get_framework_controls(session, "nist_csf")

        assert result["name"] == "nist_csf"
        assert result["display_name"] == "NIST CSF"
        assert len(result["controls"]) > 0

    @pytest.mark.asyncio
    async def test_gdpr_controls(self) -> None:
        """GDPR framework should return structured controls."""
        from app.services.compliance_service import get_framework_controls

        session = _mock_session()
        result = await get_framework_controls(session, "gdpr")

        assert result["name"] == "gdpr"
        assert result["display_name"] == "GDPR"
        assert len(result["controls"]) == 5

    @pytest.mark.asyncio
    async def test_gdpr_control_structure(self) -> None:
        """Each GDPR control should have required fields."""
        from app.services.compliance_service import get_framework_controls

        session = _mock_session()
        result = await get_framework_controls(session, "gdpr")

        for ctrl in result["controls"]:
            assert "control_id" in ctrl
            assert "title" in ctrl
            assert "description" in ctrl
            assert "status" in ctrl
            assert ctrl["status"] in ("pass", "fail", "partial", "not_assessed")

    @pytest.mark.asyncio
    async def test_unknown_framework_raises(self) -> None:
        """Unknown framework name should raise ValueError."""
        from app.services.compliance_service import get_framework_controls

        session = _mock_session()
        with pytest.raises(ValueError, match="Unknown framework"):
            await get_framework_controls(session, "unknown")

    @pytest.mark.asyncio
    async def test_control_fields(self) -> None:
        """Each control should have all required fields."""
        from app.services.compliance_service import get_framework_controls

        session = _mock_session()
        result = await get_framework_controls(session, "soc2")

        for ctrl in result["controls"]:
            assert "control_id" in ctrl
            assert "title" in ctrl
            assert "description" in ctrl
            assert "status" in ctrl
            assert "evidence_summary" in ctrl
            assert "last_checked" in ctrl


class TestPolicyChecks:
    """Tests for policy check operations."""

    @pytest.mark.asyncio
    async def test_run_policy_checks_structure(self) -> None:
        """Policy checks should return proper structure."""
        from app.services.compliance_service import run_policy_checks

        session = _mock_session()
        result = await run_policy_checks(session)

        assert "checks" in result
        assert "last_run" in result
        assert "checks_passing" in result
        assert "checks_total" in result

    @pytest.mark.asyncio
    async def test_policy_check_count(self) -> None:
        """Should have 7 policy checks defined."""
        from app.services.compliance_service import run_policy_checks

        session = _mock_session()
        result = await run_policy_checks(session)

        assert result["checks_total"] == 7
        assert len(result["checks"]) == 7

    @pytest.mark.asyncio
    async def test_policy_check_fields(self) -> None:
        """Each check should have all required fields."""
        from app.services.compliance_service import run_policy_checks

        session = _mock_session()
        result = await run_policy_checks(session)

        for check in result["checks"]:
            assert "check_name" in check
            assert "display_name" in check
            assert "status" in check
            assert check["status"] in ("pass", "fail")
            assert "scope" in check
            assert check["scope"] in ("org", "repo")
            assert "last_checked" in check
            assert "details" in check

    @pytest.mark.asyncio
    async def test_policy_checks_with_evidence(self) -> None:
        """Checks with event evidence should pass."""
        from app.services.compliance_service import run_policy_checks

        session = _mock_session_with_data(10)
        result = await run_policy_checks(session)

        assert result["checks_passing"] == 7
        for check in result["checks"]:
            assert check["status"] == "pass"

    @pytest.mark.asyncio
    async def test_policy_checks_without_evidence(self) -> None:
        """Checks without event evidence should fail."""
        from app.services.compliance_service import run_policy_checks

        session = _mock_session()
        result = await run_policy_checks(session)

        assert result["checks_passing"] == 0
        for check in result["checks"]:
            assert check["status"] == "fail"

    @pytest.mark.asyncio
    async def test_policy_checks_with_org_filter(self) -> None:
        """Policy checks should accept org filter."""
        from app.services.compliance_service import run_policy_checks

        session = _mock_session()
        result = await run_policy_checks(session, org="acme")

        assert result["checks_total"] == 7

    @pytest.mark.asyncio
    async def test_get_policy_check_results_delegates(self) -> None:
        """get_policy_check_results should delegate to run_policy_checks."""
        from app.services.compliance_service import get_policy_check_results

        session = _mock_session()
        result = await get_policy_check_results(session)

        assert "checks" in result
        assert result["checks_total"] == 7


class TestGDPRSummary:
    """Tests for GDPR summary."""

    @pytest.mark.asyncio
    async def test_gdpr_summary_structure(self) -> None:
        """GDPR summary should have all required fields."""
        from app.services.compliance_service import get_gdpr_summary

        session = _mock_session()
        result = await get_gdpr_summary(session)

        assert "data_processing_activities" in result
        assert "consent_tracking_enabled" in result
        assert "dsr_requests_total" in result
        assert "dsr_requests_completed" in result
        assert "dsr_requests_pending" in result
        assert "breach_notification_readiness" in result
        assert "data_retention_compliant" in result
        assert "erasure_requests_processed" in result
        assert "last_updated" in result

    @pytest.mark.asyncio
    async def test_gdpr_processing_activities(self) -> None:
        """Should list data processing activities."""
        from app.services.compliance_service import get_gdpr_summary

        session = _mock_session()
        result = await get_gdpr_summary(session)

        activities = result["data_processing_activities"]
        assert len(activities) == 3
        for act in activities:
            assert "activity_name" in act
            assert "purpose" in act
            assert "legal_basis" in act
            assert "data_categories" in act
            assert "retention_period" in act

    @pytest.mark.asyncio
    async def test_gdpr_breach_checklist(self) -> None:
        """Should have breach notification readiness checklist."""
        from app.services.compliance_service import get_gdpr_summary

        session = _mock_session()
        result = await get_gdpr_summary(session)

        checklist = result["breach_notification_readiness"]
        assert len(checklist) == 5
        for item in checklist:
            assert "item" in item
            assert "complete" in item


# ---------------------------------------------------------------------------
# Score helper tests
# ---------------------------------------------------------------------------


class TestScoreHelpers:
    """Tests for internal score computation helpers."""

    def test_score_from_report_empty(self) -> None:
        """Empty report should return zero score."""
        from app.services.compliance_service import _score_from_report

        report: dict[str, object] = {
            "executive_summary": {},
            "controls": [],
        }
        score, passing, total = _score_from_report(report)
        assert score == 0.0
        assert passing == 0
        assert total == 0

    def test_score_from_report_with_evidence(self) -> None:
        """Controls with evidence should count as passing."""
        from app.services.compliance_service import _score_from_report

        report: dict[str, object] = {
            "executive_summary": {},
            "controls": [
                {"evidence": {"count": 10}},
                {"evidence": {"count": 0}},
                {"evidence": {"count": 5}},
            ],
        }
        score, passing, total = _score_from_report(report)
        assert total == 3
        assert passing == 2
        assert score == pytest.approx(66.7, abs=0.1)

    def test_score_from_report_uses_executive_summary(self) -> None:
        """Should prefer compliance_score_pct from executive summary."""
        from app.services.compliance_service import _score_from_report

        report: dict[str, object] = {
            "executive_summary": {"compliance_score_pct": 85.0},
            "controls": [
                {"evidence": {"count": 10}},
            ],
        }
        score, passing, total = _score_from_report(report)
        assert score == 85.0

    def test_controls_from_report(self) -> None:
        """Should normalise controls into flat list."""
        from app.services.compliance_service import _controls_from_report

        report: dict[str, object] = {
            "generated_at": "2024-01-01T00:00:00",
            "controls": [
                {
                    "control_id": "CC6.1",
                    "title": "Test Control",
                    "description": "Test description",
                    "evidence": {"role_changes": 10, "sso_events": 5},
                },
            ],
        }
        result = _controls_from_report(report, "soc2")
        assert len(result) == 1
        assert result[0]["control_id"] == "CC6.1"
        assert result[0]["status"] == "pass"
        assert result[0]["category"] == "soc2"
        assert "role_changes: 10" in result[0]["evidence_summary"]

    def test_controls_from_functions(self) -> None:
        """Should handle NIST-style 'functions' key."""
        from app.services.compliance_service import _controls_from_report

        report: dict[str, object] = {
            "generated_at": "2024-01-01T00:00:00",
            "functions": [
                {
                    "function_id": "ID",
                    "title": "Identify",
                    "description": "Asset identification",
                    "evidence": {"repos": 50},
                },
            ],
        }
        result = _controls_from_report(report, "nist_csf")
        assert len(result) == 1
        assert result[0]["control_id"] == "ID"
        assert result[0]["status"] == "pass"


# ---------------------------------------------------------------------------
# Router tests
# ---------------------------------------------------------------------------


class TestComplianceRouter:
    """Tests for compliance router endpoints."""

    @pytest.mark.asyncio
    async def test_compliance_summary_endpoint(self) -> None:
        """GET /compliance/summary should return 200."""
        from unittest.mock import patch

        from app.routers.compliance import compliance_summary

        mock_result = {
            "overall_score": 72.5,
            "frameworks_tracked": 4,
            "controls_passing": 15,
            "controls_total": 20,
            "critical_gaps": 5,
            "last_assessment_date": "2024-01-01T00:00:00",
            "frameworks": [],
        }

        with patch(
            "app.routers.compliance.get_compliance_summary",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            session = _mock_session()
            result = await compliance_summary(org=None, db=session, _user="test")  # type: ignore[arg-type]
            assert result["overall_score"] == 72.5

    @pytest.mark.asyncio
    async def test_framework_detail_endpoint(self) -> None:
        """GET /compliance/framework/{name} should return 200 for valid framework."""
        from app.routers.compliance import framework_detail

        mock_result = {
            "name": "soc2",
            "display_name": "SOC 2 Type II",
            "score": 80.0,
            "controls": [],
            "last_generated": "2024-01-01T00:00:00",
        }

        with patch(
            "app.routers.compliance.get_framework_controls",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            session = _mock_session()
            result = await framework_detail(name="soc2", org=None, db=session, _user="test")  # type: ignore[arg-type]
            assert result["name"] == "soc2"

    @pytest.mark.asyncio
    async def test_framework_detail_invalid_name(self) -> None:
        """GET /compliance/framework/{name} should 400 for unknown framework."""
        from fastapi import HTTPException

        from app.routers.compliance import framework_detail

        session = _mock_session()
        with pytest.raises(HTTPException) as exc_info:
            await framework_detail(name="invalid", org=None, db=session, _user="test")  # type: ignore[arg-type]
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_policy_checks_endpoint(self) -> None:
        """GET /compliance/policy-checks should return results."""
        from app.routers.compliance import policy_checks

        mock_result = {
            "checks": [],
            "last_run": "2024-01-01T00:00:00",
            "checks_passing": 0,
            "checks_total": 7,
        }

        with patch(
            "app.routers.compliance.get_policy_check_results",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            session = _mock_session()
            result = await policy_checks(org=None, db=session, _user="test")  # type: ignore[arg-type]
            assert result["checks_total"] == 7

    @pytest.mark.asyncio
    async def test_gdpr_summary_endpoint(self) -> None:
        """GET /compliance/gdpr/summary should return GDPR data."""
        from app.routers.compliance import gdpr_summary

        mock_result = {
            "data_processing_activities": [],
            "consent_tracking_enabled": True,
            "dsr_requests_total": 0,
            "dsr_requests_completed": 0,
            "dsr_requests_pending": 0,
            "breach_notification_readiness": [],
            "data_retention_compliant": True,
            "erasure_requests_processed": 0,
            "last_updated": "2024-01-01T00:00:00",
        }

        with patch(
            "app.routers.compliance.get_gdpr_summary",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            session = _mock_session()
            result = await gdpr_summary(org=None, db=session, _user="test")  # type: ignore[arg-type]
            assert result["consent_tracking_enabled"] is True
