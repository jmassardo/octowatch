"""Tests for Epic 13: Copilot Adoption Analytics & AI Readiness.

Covers:
- New NDJSON API migration (#83)
- Per-user adoption drilldown (#84)
- Team-level breakdown (#76)
- Adoption blockers analysis (#77)
- Policy change timeline (#78)
- ROI report (#85)
- New router endpoints (teams, blockers, policy-changes, roi)
- Celery worker for daily metrics persistence (#80)
- NDJSON parsing
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, get_valkey
from app.routers import copilot as copilot_router_module
from app.services import copilot_metrics_service

# ── Sample data factories ────────────────────────────────────────────────────

_SAMPLE_DAY = {
    "date": "2025-01-20",
    "total_active_users": 42,
    "total_engaged_users": 38,
    "copilot_ide_code_completions": {
        "total_engaged_users": 35,
        "editors": [
            {
                "name": "VS Code",
                "total_engaged_users": 30,
                "models": [
                    {
                        "name": "GPT-4o",
                        "total_engaged_users": 25,
                        "languages": [
                            {
                                "name": "Python",
                                "total_code_suggestions": 200,
                                "total_code_acceptances": 60,
                                "total_code_lines_suggested": 400,
                                "total_code_lines_accepted": 120,
                            },
                        ],
                    },
                ],
            },
        ],
    },
    "copilot_ide_chat": {"total_engaged_users": 20, "editors": []},
    "copilot_dotcom_chat": {"total_engaged_users": 10},
    "copilot_dotcom_pull_requests": {"total_engaged_users": 5},
}


def _make_sample_days(count: int = 28) -> list[dict[str, Any]]:
    """Generate a list of sample daily metric objects."""
    days: list[dict[str, Any]] = []
    for i in range(count):
        day = json.loads(json.dumps(_SAMPLE_DAY))
        day["date"] = f"2025-01-{(i + 1):02d}"
        day["total_active_users"] = 40 + (i % 5)
        day["total_engaged_users"] = 36 + (i % 4)
        days.append(day)
    return days


def _make_sample_seats(count: int = 10) -> list[dict[str, Any]]:
    """Generate sample Copilot seat billing data."""
    seats: list[dict[str, Any]] = []
    now = datetime.now(UTC)
    for i in range(count):
        # First 3 are power users (active in last 3 days)
        # Next 3 are regular (active 5-14 days ago)
        # Next 2 are minimal (active 15-30 days ago)
        # Last 2 are inactive (no activity)
        if i < 3:
            last_activity = (now - timedelta(days=i)).isoformat()
            editor = "VS Code"
        elif i < 6:
            last_activity = (now - timedelta(days=5 + i)).isoformat()
            editor = "JetBrains"
        elif i < 8:
            last_activity = (now - timedelta(days=20 + i)).isoformat()
            editor = "VS Code"
        else:
            last_activity = None
            editor = None

        seats.append(
            {
                "assignee": {"login": f"user-{i}", "id": 1000 + i},
                "last_activity_at": last_activity,
                "last_activity_editor": editor,
                "plan_type": "business",
                "_org_slug": "test-org",
                "pending_cancellation_date": None,
            }
        )
    return seats


# ── NDJSON parsing tests (#83) ───────────────────────────────────────────────


class TestNdjsonParsing:
    """Test NDJSON (newline-delimited JSON) parsing."""

    def test_parse_single_line(self) -> None:
        text = '{"date": "2025-01-01", "total_active_users": 42}\n'
        result = copilot_metrics_service._parse_ndjson(text)
        assert len(result) == 1
        assert result[0]["date"] == "2025-01-01"

    def test_parse_multiple_lines(self) -> None:
        lines = [
            '{"date": "2025-01-01", "total_active_users": 42}',
            '{"date": "2025-01-02", "total_active_users": 45}',
            '{"date": "2025-01-03", "total_active_users": 40}',
        ]
        text = "\n".join(lines)
        result = copilot_metrics_service._parse_ndjson(text)
        assert len(result) == 3
        assert result[0]["date"] == "2025-01-01"
        assert result[2]["total_active_users"] == 40

    def test_parse_empty_lines_ignored(self) -> None:
        text = '{"date": "2025-01-01"}\n\n\n{"date": "2025-01-02"}\n'
        result = copilot_metrics_service._parse_ndjson(text)
        assert len(result) == 2

    def test_parse_whitespace_only(self) -> None:
        text = "   \n  \n"
        result = copilot_metrics_service._parse_ndjson(text)
        assert len(result) == 0

    def test_parse_trailing_newline(self) -> None:
        text = '{"date": "2025-01-01"}\n'
        result = copilot_metrics_service._parse_ndjson(text)
        assert len(result) == 1


# ── API version header tests (#83) ───────────────────────────────────────────


class TestApiVersionHeader:
    """Verify the service uses the new API version."""

    def test_api_version_constant(self) -> None:
        assert copilot_metrics_service._API_VERSION == "2022-11-28"


# ── Per-user adoption (#84) ─────────────────────────────────────────────────


class TestUserClassification:
    """Test user tier classification from seat data."""

    def test_power_user_recent_activity(self) -> None:
        now = datetime.now(UTC)
        seat = {"last_activity_at": (now - timedelta(days=1)).isoformat()}
        assert copilot_metrics_service._classify_user(seat) == "power"

    def test_regular_user_moderate_activity(self) -> None:
        now = datetime.now(UTC)
        seat = {"last_activity_at": (now - timedelta(days=7)).isoformat()}
        assert copilot_metrics_service._classify_user(seat) == "regular"

    def test_minimal_user_sparse_activity(self) -> None:
        now = datetime.now(UTC)
        seat = {"last_activity_at": (now - timedelta(days=20)).isoformat()}
        assert copilot_metrics_service._classify_user(seat) == "minimal"

    def test_inactive_user_no_activity(self) -> None:
        seat = {"last_activity_at": None}
        assert copilot_metrics_service._classify_user(seat) == "inactive"

    def test_inactive_user_old_activity(self) -> None:
        now = datetime.now(UTC)
        seat = {"last_activity_at": (now - timedelta(days=60)).isoformat()}
        assert copilot_metrics_service._classify_user(seat) == "inactive"

    def test_inactive_user_invalid_timestamp(self) -> None:
        seat = {"last_activity_at": "not-a-date"}
        assert copilot_metrics_service._classify_user(seat) == "inactive"


class TestDaysSinceActivity:
    """Test the _days_since_last_activity helper."""

    def test_empty_string_returns_999(self) -> None:
        assert copilot_metrics_service._days_since_last_activity("") == 999

    def test_recent_activity(self) -> None:
        now = datetime.now(UTC)
        result = copilot_metrics_service._days_since_last_activity(now.isoformat())
        assert result == 0

    def test_old_activity(self) -> None:
        old = datetime.now(UTC) - timedelta(days=30)
        result = copilot_metrics_service._days_since_last_activity(old.isoformat())
        assert result >= 29  # Allow for clock differences


class TestCountFeatures:
    """Test the _count_features helper."""

    def test_user_with_editor_and_activity(self) -> None:
        seat = {"last_activity_editor": "VS Code", "last_activity_at": "2025-01-01"}
        assert copilot_metrics_service._count_features(seat) >= 1

    def test_user_with_no_data(self) -> None:
        seat = {"last_activity_editor": "", "last_activity_at": None}
        assert copilot_metrics_service._count_features(seat) >= 1


class TestCopilotAdoptionWithSeats:
    """Test adoption endpoint with real seat data (#84)."""

    @pytest.mark.asyncio
    async def test_returns_power_users_with_seats(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        sample = _make_sample_days(7)
        seats = _make_sample_seats(10)

        with (
            patch.object(copilot_metrics_service, "_read_metrics_from_store", return_value=sample),
            patch.object(copilot_metrics_service, "_read_seats_from_store", return_value=seats),
        ):
            result = await copilot_metrics_service.get_copilot_adoption(db)

        assert len(result["power_users"]) > 0
        assert all("user" in u for u in result["power_users"])
        assert all("days_active" in u for u in result["power_users"])

    @pytest.mark.asyncio
    async def test_returns_minimal_users_with_seats(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        sample = _make_sample_days(7)
        seats = _make_sample_seats(10)

        with (
            patch.object(copilot_metrics_service, "_read_metrics_from_store", return_value=sample),
            patch.object(copilot_metrics_service, "_read_seats_from_store", return_value=seats),
        ):
            result = await copilot_metrics_service.get_copilot_adoption(db)

        assert len(result["minimal_users"]) > 0
        assert all("user" in u for u in result["minimal_users"])

    @pytest.mark.asyncio
    async def test_tier_counts_match_seats(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        sample = _make_sample_days(7)
        seats = _make_sample_seats(10)

        with (
            patch.object(copilot_metrics_service, "_read_metrics_from_store", return_value=sample),
            patch.object(copilot_metrics_service, "_read_seats_from_store", return_value=seats),
        ):
            result = await copilot_metrics_service.get_copilot_adoption(db)

        total = sum(t["count"] for t in result["tiers"])
        assert total == 10  # matches number of seats

    @pytest.mark.asyncio
    async def test_falls_back_when_seats_unavailable(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        sample = _make_sample_days(7)

        with (
            patch.object(copilot_metrics_service, "_read_metrics_from_store", return_value=sample),
            patch.object(
                copilot_metrics_service,
                "_read_seats_from_store",
                return_value={"error": "copilot_not_available", "message": "test"},
            ),
        ):
            result = await copilot_metrics_service.get_copilot_adoption(db)

        # Should still return valid tiers via heuristic fallback
        assert len(result["tiers"]) == 4
        assert result["power_users"] == []
        assert result["minimal_users"] == []


# ── Team-level breakdown (#76) ───────────────────────────────────────────────


class TestCopilotTeams:
    """Test team-level Copilot adoption breakdown."""

    @pytest.mark.asyncio
    async def test_returns_teams_with_adoption_data(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        seats = _make_sample_seats(6)

        # Mock DB queries for teams and members
        mock_team = MagicMock()
        mock_team.team_slug = "frontend"
        mock_team.name = "Frontend Team"
        mock_team.org = "test-org"

        mock_member1 = MagicMock()
        mock_member1.org = "test-org"
        mock_member1.team_slug = "frontend"
        mock_member1.github_login = "user-0"

        mock_member2 = MagicMock()
        mock_member2.org = "test-org"
        mock_member2.team_slug = "frontend"
        mock_member2.github_login = "user-1"

        team_result = MagicMock()
        team_result.scalars.return_value.all.return_value = [mock_team]

        member_result = MagicMock()
        member_result.scalars.return_value.all.return_value = [mock_member1, mock_member2]

        db.execute = AsyncMock(side_effect=[team_result, member_result])

        with patch.object(copilot_metrics_service, "_read_seats_from_store", return_value=seats):
            result = await copilot_metrics_service.get_copilot_teams(db)

        assert "teams" in result
        assert len(result["teams"]) == 1
        assert result["teams"][0]["team_slug"] == "frontend"
        assert result["teams"][0]["total_members"] == 2
        assert "adoption_pct" in result["teams"][0]
        assert "at_risk" in result["teams"][0]

    @pytest.mark.asyncio
    async def test_returns_error_when_seats_unavailable(self) -> None:
        db = AsyncMock(spec=AsyncSession)

        with patch.object(
            copilot_metrics_service,
            "_read_seats_from_store",
            return_value={"error": "copilot_not_available", "message": "test"},
        ):
            result = await copilot_metrics_service.get_copilot_teams(db)

        assert result["error"] == "copilot_not_available"

    @pytest.mark.asyncio
    async def test_at_risk_teams_flagged(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        # All inactive seats
        seats = [
            {
                "assignee": {"login": f"user-{i}", "id": i},
                "last_activity_at": None,
                "last_activity_editor": None,
                "plan_type": "business",
                "_org_slug": "test-org",
            }
            for i in range(5)
        ]

        mock_team = MagicMock()
        mock_team.team_slug = "backend"
        mock_team.name = "Backend Team"
        mock_team.org = "test-org"

        members = []
        for i in range(5):
            m = MagicMock()
            m.org = "test-org"
            m.team_slug = "backend"
            m.github_login = f"user-{i}"
            members.append(m)

        team_result = MagicMock()
        team_result.scalars.return_value.all.return_value = [mock_team]
        member_result = MagicMock()
        member_result.scalars.return_value.all.return_value = members

        db.execute = AsyncMock(side_effect=[team_result, member_result])

        with patch.object(copilot_metrics_service, "_read_seats_from_store", return_value=seats):
            result = await copilot_metrics_service.get_copilot_teams(db)

        assert result["at_risk_count"] >= 1
        assert result["teams"][0]["at_risk"] is True


# ── Adoption blockers (#77) ──────────────────────────────────────────────────


class TestCopilotBlockers:
    """Test adoption blockers analysis."""

    @pytest.mark.asyncio
    async def test_identifies_inactive_seats(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        seats = _make_sample_seats(10)

        # Mock DB queries
        member_result = MagicMock()
        member_result.scalars.return_value.all.return_value = []

        policy_result = MagicMock()
        policy_result.scalars.return_value.all.return_value = []

        db.execute = AsyncMock(side_effect=[member_result, policy_result])

        with patch.object(copilot_metrics_service, "_read_seats_from_store", return_value=seats):
            result = await copilot_metrics_service.get_copilot_blockers(db)

        assert "blockers" in result
        inactive_blockers = [b for b in result["blockers"] if b["category"] == "inactive_seat"]
        assert len(inactive_blockers) >= 1
        assert inactive_blockers[0]["count"] >= 2

    @pytest.mark.asyncio
    async def test_identifies_no_seat_members(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        seats = _make_sample_seats(3)  # Only 3 seats

        # Create members without seats
        members = []
        for i in range(5):
            m = MagicMock()
            m.github_login = f"no-seat-user-{i}"
            members.append(m)

        member_result = MagicMock()
        member_result.scalars.return_value.all.return_value = members

        policy_result = MagicMock()
        policy_result.scalars.return_value.all.return_value = []

        db.execute = AsyncMock(side_effect=[member_result, policy_result])

        with patch.object(copilot_metrics_service, "_read_seats_from_store", return_value=seats):
            result = await copilot_metrics_service.get_copilot_blockers(db)

        no_seat_blockers = [b for b in result["blockers"] if b["category"] == "no_seat"]
        assert len(no_seat_blockers) == 1
        assert no_seat_blockers[0]["count"] == 5

    @pytest.mark.asyncio
    async def test_quick_wins_generated(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        seats = _make_sample_seats(10)

        member_result = MagicMock()
        member_result.scalars.return_value.all.return_value = []

        policy_result = MagicMock()
        policy_result.scalars.return_value.all.return_value = []

        db.execute = AsyncMock(side_effect=[member_result, policy_result])

        with patch.object(copilot_metrics_service, "_read_seats_from_store", return_value=seats):
            result = await copilot_metrics_service.get_copilot_blockers(db)

        assert "quick_wins" in result
        assert len(result["quick_wins"]) >= 1

    @pytest.mark.asyncio
    async def test_summary_counts_correct(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        seats = _make_sample_seats(10)

        member_result = MagicMock()
        member_result.scalars.return_value.all.return_value = []

        policy_result = MagicMock()
        policy_result.scalars.return_value.all.return_value = []

        db.execute = AsyncMock(side_effect=[member_result, policy_result])

        with patch.object(copilot_metrics_service, "_read_seats_from_store", return_value=seats):
            result = await copilot_metrics_service.get_copilot_blockers(db)

        assert "summary" in result
        assert "total_blockers" in result["summary"]
        assert "inactive_count" in result["summary"]
        assert "no_seat_count" in result["summary"]

    @pytest.mark.asyncio
    async def test_identifies_policy_restrictions(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        seats = _make_sample_seats(3)

        member_result = MagicMock()
        member_result.scalars.return_value.all.return_value = []

        mock_policy = MagicMock()
        mock_policy.name = "No external repos"
        mock_policy.policy_type = "content_exclusion"

        policy_result = MagicMock()
        policy_result.scalars.return_value.all.return_value = [mock_policy]

        db.execute = AsyncMock(side_effect=[member_result, policy_result])

        with patch.object(copilot_metrics_service, "_read_seats_from_store", return_value=seats):
            result = await copilot_metrics_service.get_copilot_blockers(db)

        policy_blockers = [b for b in result["blockers"] if b["category"] == "policy_restricted"]
        assert len(policy_blockers) == 1
        assert policy_blockers[0]["count"] == 1


# ── Policy change timeline (#78) ─────────────────────────────────────────────


class TestCopilotPolicyChanges:
    """Test policy change timeline from audit events."""

    @pytest.mark.asyncio
    async def test_returns_timeline(self) -> None:
        db = AsyncMock(spec=AsyncSession)

        mock_event = MagicMock()
        mock_event.id = 1
        mock_event.action = "copilot.cfb_seat_assignment_created"
        mock_event.actor = "admin-user"
        mock_event.created_at = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)
        mock_event.org = "test-org"
        mock_event.data = {"new_value": "enabled"}

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [mock_event]
        db.execute = AsyncMock(return_value=result_mock)

        result = await copilot_metrics_service.get_copilot_policy_changes(db)

        assert "timeline" in result
        assert len(result["timeline"]) == 1
        assert result["timeline"][0]["action"] == "copilot.cfb_seat_assignment_created"
        assert result["timeline"][0]["actor"] == "admin-user"
        assert result["total_changes"] == 1

    @pytest.mark.asyncio
    async def test_empty_timeline(self) -> None:
        db = AsyncMock(spec=AsyncSession)

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=result_mock)

        result = await copilot_metrics_service.get_copilot_policy_changes(db)

        assert result["timeline"] == []
        assert result["total_changes"] == 0


class TestPolicyActionDescription:
    """Test human-readable policy action descriptions."""

    def test_seat_assignment(self) -> None:
        desc = copilot_metrics_service._describe_policy_action(
            "copilot.cfb_seat_assignment_created", {}
        )
        assert desc == "Copilot seat assigned"

    def test_seat_revoked(self) -> None:
        desc = copilot_metrics_service._describe_policy_action(
            "copilot.cfb_seat_assignment_revoked", {}
        )
        assert desc == "Copilot seat revoked"

    def test_unknown_action(self) -> None:
        desc = copilot_metrics_service._describe_policy_action("copilot.unknown_action", {})
        assert "copilot.unknown_action" in desc


# ── ROI & Cost Optimization (#85) ────────────────────────────────────────────


class TestCostForPlan:
    """Test per-tier cost calculation."""

    def test_business_default(self) -> None:
        assert copilot_metrics_service._cost_for_plan("business") == 19.0

    def test_enterprise_default(self) -> None:
        assert copilot_metrics_service._cost_for_plan("enterprise") == 39.0

    def test_override(self) -> None:
        assert copilot_metrics_service._cost_for_plan("business", 25.0) == 25.0

    def test_unknown_plan_defaults_to_business(self) -> None:
        assert copilot_metrics_service._cost_for_plan("unknown") == 19.0


class TestCopilotROI:
    """Test Copilot ROI report generation."""

    @pytest.mark.asyncio
    async def test_returns_roi_summary(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        seats = _make_sample_seats(10)
        days = _make_sample_days(7)

        # Mock org_config query
        config_result = MagicMock()
        config_result.scalars.return_value.first.return_value = None

        # Mock team queries (for recommendations)
        team_result = MagicMock()
        team_result.scalars.return_value.all.return_value = []
        member_result = MagicMock()
        member_result.scalars.return_value.all.return_value = []

        db.execute = AsyncMock(side_effect=[config_result, team_result, member_result])

        with (
            patch.object(copilot_metrics_service, "_read_seats_from_store", return_value=seats),
            patch.object(copilot_metrics_service, "_read_metrics_from_store", return_value=days),
        ):
            result = await copilot_metrics_service.get_copilot_roi(db)

        assert "summary" in result
        assert result["summary"]["total_seats"] == 10
        assert result["summary"]["active_seats"] > 0
        assert result["summary"]["inactive_seats"] > 0
        assert result["summary"]["total_monthly_cost"] > 0
        assert result["summary"]["wasted_monthly"] > 0

    @pytest.mark.asyncio
    async def test_returns_cost_trend(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        seats = _make_sample_seats(5)
        days = _make_sample_days(7)

        config_result = MagicMock()
        config_result.scalars.return_value.first.return_value = None
        team_result = MagicMock()
        team_result.scalars.return_value.all.return_value = []
        member_result = MagicMock()
        member_result.scalars.return_value.all.return_value = []

        db.execute = AsyncMock(side_effect=[config_result, team_result, member_result])

        with (
            patch.object(copilot_metrics_service, "_read_seats_from_store", return_value=seats),
            patch.object(copilot_metrics_service, "_read_metrics_from_store", return_value=days),
        ):
            result = await copilot_metrics_service.get_copilot_roi(db)

        assert "cost_trend" in result
        assert len(result["cost_trend"]) == 7
        for point in result["cost_trend"]:
            assert "date" in point
            assert "active_users" in point
            assert "acceptance_rate" in point

    @pytest.mark.asyncio
    async def test_returns_recommendations(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        seats = _make_sample_seats(10)
        days = _make_sample_days(7)

        config_result = MagicMock()
        config_result.scalars.return_value.first.return_value = None
        team_result = MagicMock()
        team_result.scalars.return_value.all.return_value = []
        member_result = MagicMock()
        member_result.scalars.return_value.all.return_value = []

        db.execute = AsyncMock(side_effect=[config_result, team_result, member_result])

        with (
            patch.object(copilot_metrics_service, "_read_seats_from_store", return_value=seats),
            patch.object(copilot_metrics_service, "_read_metrics_from_store", return_value=days),
        ):
            result = await copilot_metrics_service.get_copilot_roi(db)

        assert "recommendations" in result
        # Should recommend reclaiming inactive seats
        reclaim = [r for r in result["recommendations"] if r["type"] == "reclaim_seats"]
        assert len(reclaim) >= 1

    @pytest.mark.asyncio
    async def test_tier_breakdown_included(self) -> None:
        db = AsyncMock(spec=AsyncSession)
        seats = _make_sample_seats(10)
        days = _make_sample_days(7)

        config_result = MagicMock()
        config_result.scalars.return_value.first.return_value = None
        team_result = MagicMock()
        team_result.scalars.return_value.all.return_value = []
        member_result = MagicMock()
        member_result.scalars.return_value.all.return_value = []

        db.execute = AsyncMock(side_effect=[config_result, team_result, member_result])

        with (
            patch.object(copilot_metrics_service, "_read_seats_from_store", return_value=seats),
            patch.object(copilot_metrics_service, "_read_metrics_from_store", return_value=days),
        ):
            result = await copilot_metrics_service.get_copilot_roi(db)

        assert "tier_breakdown" in result
        assert "power" in result["tier_breakdown"]
        assert "inactive" in result["tier_breakdown"]

    @pytest.mark.asyncio
    async def test_returns_error_when_seats_unavailable(self) -> None:
        db = AsyncMock(spec=AsyncSession)

        with (
            patch.object(
                copilot_metrics_service,
                "_read_seats_from_store",
                return_value={"error": "copilot_not_available", "message": "no seats"},
            ),
            patch.object(
                copilot_metrics_service,
                "_read_metrics_from_store",
                return_value=_make_sample_days(7),
            ),
        ):
            result = await copilot_metrics_service.get_copilot_roi(db)

        assert result["error"] == "copilot_not_available"


# ── New router endpoint auth tests ───────────────────────────────────────────


def _build_copilot_app() -> FastAPI:
    """Build a minimal FastAPI app with the copilot router (no auth overrides)."""
    app = FastAPI()
    app.include_router(copilot_router_module.router, prefix="/api/v1")

    mock_db = AsyncMock(spec=AsyncSession)

    async def override_db() -> Any:
        yield mock_db

    mock_valkey = AsyncMock()
    mock_valkey.get = AsyncMock(return_value=None)
    mock_valkey.ping = AsyncMock(return_value=True)

    async def override_valkey() -> Any:
        yield mock_valkey

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_valkey] = override_valkey

    return app


class TestNewEndpointsAuth:
    """New endpoints must require authentication."""

    def test_teams_returns_401_unauthenticated(self) -> None:
        app = _build_copilot_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/copilot/teams")
        assert resp.status_code == 401

    def test_blockers_returns_401_unauthenticated(self) -> None:
        app = _build_copilot_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/copilot/blockers")
        assert resp.status_code == 401

    def test_policy_changes_returns_401_unauthenticated(self) -> None:
        app = _build_copilot_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/copilot/policy-changes")
        assert resp.status_code == 401

    def test_roi_returns_401_unauthenticated(self) -> None:
        app = _build_copilot_app()
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/copilot/roi")
        assert resp.status_code == 401


# ── Model tests (#80) ────────────────────────────────────────────────────────


class TestCopilotDailyMetricModel:
    """Test the CopilotDailyMetric SQLAlchemy model."""

    def test_table_name(self) -> None:
        from app.models.copilot_metrics import CopilotDailyMetric

        assert CopilotDailyMetric.__tablename__ == "copilot_daily_metrics"

    def test_columns_exist(self) -> None:
        from app.models.copilot_metrics import CopilotDailyMetric

        cols = {c.name for c in CopilotDailyMetric.__table__.columns}
        expected = {
            "id",
            "date",
            "org_slug",
            "metric_type",
            "language",
            "editor",
            "model",
            "active_users",
            "engaged_users",
            "total_suggestions",
            "total_acceptances",
            "total_lines_suggested",
            "total_lines_accepted",
            "acceptance_rate",
            "synced_at",
        }
        assert expected.issubset(cols)


class TestCopilotSeatSnapshotModel:
    """Test the CopilotSeatSnapshot SQLAlchemy model."""

    def test_table_name(self) -> None:
        from app.models.copilot_metrics import CopilotSeatSnapshot

        assert CopilotSeatSnapshot.__tablename__ == "copilot_seat_snapshots"

    def test_columns_exist(self) -> None:
        from app.models.copilot_metrics import CopilotSeatSnapshot

        cols = {c.name for c in CopilotSeatSnapshot.__table__.columns}
        expected = {
            "id",
            "snapshot_date",
            "org_slug",
            "github_login",
            "plan_type",
            "last_activity_at",
            "last_activity_editor",
            "created_at",
            "pending_cancellation_date",
        }
        assert expected.issubset(cols)


# ── Celery worker tests (#80) ────────────────────────────────────────────────


class TestCopilotMetricsWorker:
    """Test the Celery beat task for Copilot metrics persistence."""

    def test_task_registered(self) -> None:
        from app.celery_app import celery_app

        assert "sync-copilot-metrics" in celery_app.conf.beat_schedule

    def test_task_schedule(self) -> None:
        from app.celery_app import celery_app

        schedule = celery_app.conf.beat_schedule["sync-copilot-metrics"]
        assert schedule["task"] == "app.workers.copilot_metrics_worker.sync_copilot_metrics"
        assert schedule["options"]["queue"] == "github_sync"

    def test_task_module_included(self) -> None:
        from app.celery_app import celery_app

        assert "app.workers.copilot_metrics_worker" in celery_app.conf.include


# ── Model registration tests ─────────────────────────────────────────────────


class TestModelRegistration:
    """Verify new models are registered in __init__.py."""

    def test_copilot_daily_metric_importable(self) -> None:
        from app.models import CopilotDailyMetric

        assert CopilotDailyMetric is not None

    def test_copilot_seat_snapshot_importable(self) -> None:
        from app.models import CopilotSeatSnapshot

        assert CopilotSeatSnapshot is not None
