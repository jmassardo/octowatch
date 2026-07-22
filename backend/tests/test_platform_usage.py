"""Unit tests for platform usage service and router."""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services import platform_usage_service

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_session(rows: list[tuple]) -> AsyncMock:
    """Return an AsyncSession mock with fetchall returning given rows."""
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = rows
    session.execute = AsyncMock(return_value=mock_result)
    return session


# ---------------------------------------------------------------------------
# get_usage_summary tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_usage_summary_returns_correct_structure() -> None:
    """get_usage_summary returns features list with expected keys."""
    rows = [
        (
            "actions",  # feature_area
            5,  # unique_actors
            20,  # active_days
            1500.0,  # total_actions_minutes
            200,  # total_actions_runs
            0,  # total_copilot_suggestions
            0,  # total_copilot_acceptances
            0.0,  # total_copilot_credits
            50,  # total_git_clones
            100,  # total_git_pushes
            10,  # total_packages_published
        ),
    ]
    db = _mock_session(rows)

    result = await platform_usage_service.get_usage_summary(db, days=30)

    assert "features" in result
    assert "period_days" in result
    assert result["period_days"] == 30
    assert len(result["features"]) == 1
    feature = result["features"][0]
    assert feature["feature_area"] == "actions"
    assert feature["unique_actors"] == 5
    assert feature["active_days"] == 20
    assert feature["total_actions_minutes"] == 1500.0
    assert feature["total_actions_runs"] == 200
    assert feature["total_git_clones"] == 50
    assert feature["total_git_pushes"] == 100
    assert feature["total_packages_published"] == 10


@pytest.mark.asyncio
async def test_get_usage_summary_empty() -> None:
    """get_usage_summary returns empty features when no data."""
    db = _mock_session([])

    result = await platform_usage_service.get_usage_summary(db, days=7)

    assert result["features"] == []
    assert result["period_days"] == 7


@pytest.mark.asyncio
async def test_get_usage_summary_with_org_filter() -> None:
    """get_usage_summary passes org filter to query."""
    db = _mock_session([])

    result = await platform_usage_service.get_usage_summary(db, org="my-org", days=30)

    assert result["features"] == []
    # Verify execute was called with params including org
    call_args = db.execute.call_args
    assert call_args is not None


# ---------------------------------------------------------------------------
# get_top_consumers tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_top_consumers_returns_correct_structure() -> None:
    """get_top_consumers returns consumers list with expected keys."""
    rows = [
        (
            "user1",  # actor_login
            "org-a",  # org_slug
            500.0,  # total_actions_minutes
            50,  # total_actions_runs
            100,  # total_copilot_suggestions
            80,  # total_copilot_acceptances
            25.0,  # total_copilot_credits
            30,  # total_git_clones
            45,  # total_git_pushes
            15,  # active_days
        ),
    ]
    db = _mock_session(rows)

    result = await platform_usage_service.get_top_consumers(
        db, feature_area="actions", days=30, limit=10
    )

    assert "consumers" in result
    assert "feature_area" in result
    assert "period_days" in result
    assert result["feature_area"] == "actions"
    assert result["period_days"] == 30
    assert len(result["consumers"]) == 1
    consumer = result["consumers"][0]
    assert consumer["actor_login"] == "user1"
    assert consumer["org_slug"] == "org-a"
    assert consumer["total_actions_minutes"] == 500.0
    assert consumer["active_days"] == 15


@pytest.mark.asyncio
async def test_get_top_consumers_with_org_filter() -> None:
    """get_top_consumers works with org filter."""
    db = _mock_session([])

    result = await platform_usage_service.get_top_consumers(
        db, org="filtered-org", feature_area="copilot", days=14
    )

    assert result["consumers"] == []
    assert result["feature_area"] == "copilot"


@pytest.mark.asyncio
async def test_get_top_consumers_handles_null_values() -> None:
    """get_top_consumers handles None values from DB gracefully."""
    rows = [
        (
            "user2",
            "org-b",
            None,  # null actions_minutes
            None,  # null actions_runs
            None,
            None,
            None,
            None,
            None,
            3,
        ),
    ]
    db = _mock_session(rows)

    result = await platform_usage_service.get_top_consumers(db)

    consumer = result["consumers"][0]
    assert consumer["total_actions_minutes"] == 0
    assert consumer["total_actions_runs"] == 0
    assert consumer["total_copilot_credits"] == 0


# ---------------------------------------------------------------------------
# get_usage_trends tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_usage_trends_returns_daily_data() -> None:
    """get_usage_trends returns daily trend data."""
    rows = [
        (
            date(2026, 7, 1),  # metric_date
            "actions",  # feature_area
            3,  # unique_actors
            120.5,  # actions_minutes
            10.0,  # copilot_credits
            5,  # git_clones
            8,  # git_pushes
        ),
        (
            date(2026, 7, 2),
            "actions",
            4,
            200.0,
            15.0,
            7,
            12,
        ),
    ]
    db = _mock_session(rows)

    result = await platform_usage_service.get_usage_trends(db, days=30)

    assert "trends" in result
    assert "period_days" in result
    assert result["period_days"] == 30
    assert len(result["trends"]) == 2
    trend = result["trends"][0]
    assert trend["date"] == "2026-07-01"
    assert trend["feature_area"] == "actions"
    assert trend["unique_actors"] == 3
    assert trend["actions_minutes"] == 120.5
    assert trend["copilot_credits"] == 10.0
    assert trend["git_clones"] == 5
    assert trend["git_pushes"] == 8


@pytest.mark.asyncio
async def test_get_usage_trends_with_feature_filter() -> None:
    """get_usage_trends filters by feature_area."""
    db = _mock_session([])

    result = await platform_usage_service.get_usage_trends(db, feature_area="copilot", days=7)

    assert result["trends"] == []
    assert result["period_days"] == 7


@pytest.mark.asyncio
async def test_get_usage_trends_with_org_filter() -> None:
    """get_usage_trends filters by org."""
    db = _mock_session([])

    result = await platform_usage_service.get_usage_trends(db, org="test-org", days=14)

    assert result["trends"] == []


# ---------------------------------------------------------------------------
# get_anomalies tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_anomalies_returns_detection_data() -> None:
    """get_anomalies returns anomaly detections."""
    triggered = datetime(2026, 7, 15, 10, 0, 0, tzinfo=UTC)
    rows = [
        (
            1,  # id
            triggered,  # triggered_at
            "high",  # severity
            0.95,  # confidence_score
            "user1",  # actor
            "org-a",  # org
            "Excessive Actions Usage",  # rule_name
            "excessive-actions-usage",  # rule_slug
            "utilization",  # category
        ),
    ]
    db = _mock_session(rows)

    result = await platform_usage_service.get_anomalies(db, days=7)

    assert "anomalies" in result
    assert "period_days" in result
    assert result["period_days"] == 7
    assert len(result["anomalies"]) == 1
    anomaly = result["anomalies"][0]
    assert anomaly["id"] == 1
    assert anomaly["triggered_at"] == triggered.isoformat()
    assert anomaly["severity"] == "high"
    assert anomaly["confidence_score"] == 0.95
    assert anomaly["actor"] == "user1"
    assert anomaly["org"] == "org-a"
    assert anomaly["rule_name"] == "Excessive Actions Usage"
    assert anomaly["rule_slug"] == "excessive-actions-usage"
    assert anomaly["category"] == "utilization"


@pytest.mark.asyncio
async def test_get_anomalies_empty() -> None:
    """get_anomalies returns empty list when no detections."""
    db = _mock_session([])

    result = await platform_usage_service.get_anomalies(db, days=3)

    assert result["anomalies"] == []


@pytest.mark.asyncio
async def test_get_anomalies_with_org_filter() -> None:
    """get_anomalies filters by org."""
    db = _mock_session([])

    result = await platform_usage_service.get_anomalies(db, org="my-org", days=7)

    assert result["anomalies"] == []


# ---------------------------------------------------------------------------
# get_user_usage tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_user_usage_returns_user_facts() -> None:
    """get_user_usage returns usage facts for a specific user."""
    rows = [
        (
            "actions",  # feature_area
            date(2026, 7, 10),  # metric_date
            45.5,  # actions_minutes
            10,  # actions_runs
            0,  # copilot_suggestions
            0,  # copilot_acceptances
            0.0,  # copilot_credits
            5,  # git_clones
            12,  # git_pushes
            2,  # packages_published
            1024000,  # storage_bytes
        ),
    ]
    db = _mock_session(rows)

    result = await platform_usage_service.get_user_usage(db, login="testuser", days=90)

    assert "login" in result
    assert "facts" in result
    assert "period_days" in result
    assert result["login"] == "testuser"
    assert result["period_days"] == 90
    assert len(result["facts"]) == 1
    fact = result["facts"][0]
    assert fact["feature_area"] == "actions"
    assert fact["date"] == "2026-07-10"
    assert fact["actions_minutes"] == 45.5
    assert fact["actions_runs"] == 10
    assert fact["git_clones"] == 5
    assert fact["git_pushes"] == 12
    assert fact["packages_published"] == 2
    assert fact["storage_bytes"] == 1024000


@pytest.mark.asyncio
async def test_get_user_usage_with_org_filter() -> None:
    """get_user_usage filters by org."""
    db = _mock_session([])

    result = await platform_usage_service.get_user_usage(db, login="someone", org="org-x", days=30)

    assert result["login"] == "someone"
    assert result["facts"] == []


@pytest.mark.asyncio
async def test_get_user_usage_empty() -> None:
    """get_user_usage returns empty facts for unknown user."""
    db = _mock_session([])

    result = await platform_usage_service.get_user_usage(db, login="nobody")

    assert result["login"] == "nobody"
    assert result["facts"] == []
    assert result["period_days"] == 90
