"""Tests for the billing sync worker.

Covers:
- Skipping when no GitHub App credentials are configured
- _upsert_fact generates correct SQL params
- _fetch_api handles 404 and errors gracefully
- Main sync flow with mocked httpx and DB
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.workers.billing_sync_worker import (
    _fetch_api,
    _sync_billing,
    _sync_org_billing,
    _upsert_fact,
    sync_billing_data,
)


@pytest.mark.asyncio
async def test_sync_billing_skips_when_no_credentials() -> None:
    """Sync should return skipped=True when no private key is configured."""
    mock_settings = MagicMock()
    mock_settings.github_app.resolve_private_key.return_value = None

    with patch("app.workers.billing_sync_worker.settings", mock_settings):
        result = await _sync_billing()

    assert result["skipped"] is True
    assert result["synced"] == 0


@pytest.mark.asyncio
async def test_fetch_api_returns_none_on_404() -> None:
    """_fetch_api should return None for 404 responses."""
    mock_response = MagicMock()
    mock_response.status_code = 404

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    result = await _fetch_api(
        mock_client,
        "https://api.github.com/test",
        {"Authorization": "Bearer x"},
    )
    assert result is None


@pytest.mark.asyncio
async def test_fetch_api_returns_none_on_exception() -> None:
    """_fetch_api should return None when the request raises an exception."""
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("connection refused"))

    result = await _fetch_api(mock_client, "https://api.github.com/test", {})
    assert result is None


@pytest.mark.asyncio
async def test_fetch_api_returns_json_on_200() -> None:
    """_fetch_api should return parsed JSON for successful 200 responses."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"total_minutes_used": 42}

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    result = await _fetch_api(mock_client, "https://api.github.com/test", {})
    assert result == {"total_minutes_used": 42}


@pytest.mark.asyncio
async def test_fetch_api_returns_none_on_500() -> None:
    """_fetch_api should return None for server error responses."""
    mock_response = MagicMock()
    mock_response.status_code = 500

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    result = await _fetch_api(mock_client, "https://api.github.com/test", {})
    assert result is None


@pytest.mark.asyncio
async def test_upsert_fact_calls_db_execute_with_correct_params() -> None:
    """_upsert_fact should call db.execute with the correct SQL parameters."""
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock()

    metric_date = date(2026, 7, 19)

    await _upsert_fact(
        mock_db,
        org_slug="my-org",
        actor_login="testuser",
        feature_area="copilot",
        metric_date=metric_date,
        copilot_suggestions=100,
        copilot_acceptances=42,
    )

    mock_db.execute.assert_called_once()
    call_args = mock_db.execute.call_args
    params = call_args[0][1]  # Second positional arg is the params dict

    assert params["org_slug"] == "my-org"
    assert params["actor_login"] == "testuser"
    assert params["feature_area"] == "copilot"
    assert params["metric_date"] == metric_date
    assert params["copilot_suggestions"] == 100
    assert params["copilot_acceptances"] == 42
    assert params["actions_minutes"] is None
    assert params["storage_bytes"] is None


@pytest.mark.asyncio
async def test_upsert_fact_includes_all_columns_in_params() -> None:
    """_upsert_fact should include all utilization_facts columns."""
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock()

    await _upsert_fact(
        mock_db,
        org_slug="org1",
        actor_login="user1",
        feature_area="actions",
        metric_date=date(2026, 7, 19),
        actions_minutes=150.5,
        actions_runs=10,
        copilot_credits=3.5,
        ghas_alerts_dismissed=2,
        git_clones=50,
        git_pushes=20,
        packages_published=5,
        storage_bytes=1073741824,
    )

    params = mock_db.execute.call_args[0][1]
    assert params["actions_minutes"] == 150.5
    assert params["actions_runs"] == 10
    assert params["copilot_credits"] == 3.5
    assert params["ghas_alerts_dismissed"] == 2
    assert params["git_clones"] == 50
    assert params["git_pushes"] == 20
    assert params["packages_published"] == 5
    assert params["storage_bytes"] == 1073741824


@pytest.mark.asyncio
async def test_sync_billing_no_orgs_returns_zero() -> None:
    """Sync should return synced=0 when no orgs are configured."""
    mock_settings = MagicMock()
    mock_settings.github_app.resolve_private_key.return_value = "fake-pem"

    mock_result = MagicMock()
    mock_result.fetchall.return_value = []

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_session_cls = MagicMock(return_value=mock_session)

    with (
        patch("app.workers.billing_sync_worker.settings", mock_settings),
        patch(
            "app.workers.billing_sync_worker.AsyncSessionLocal",
            mock_session_cls,
        ),
    ):
        result = await _sync_billing()

    assert result["synced"] == 0
    assert result["orgs"] == 0


@pytest.mark.asyncio
async def test_sync_org_billing_actions_upsert() -> None:
    """_sync_org_billing should upsert Actions minutes data."""
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock()

    mock_valkey = AsyncMock()
    mock_valkey.aclose = AsyncMock()

    mock_token_manager = MagicMock()
    mock_token_manager.get_installation_token = AsyncMock(return_value="ghp_test123")

    # Mock HTTP responses
    actions_response = MagicMock()
    actions_response.status_code = 200
    actions_response.json.return_value = {
        "total_minutes_used": 500,
        "total_paid_minutes_used": 100,
    }

    not_found_response = MagicMock()
    not_found_response.status_code = 404

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(
        side_effect=[
            actions_response,
            not_found_response,
            not_found_response,
            not_found_response,
        ]
    )

    mock_settings = MagicMock()
    mock_settings.VALKEY_URL = "redis://localhost:6379/0"
    mock_settings.github_app.GITHUB_APP_ID = 12345

    with (
        patch(
            "app.workers.billing_sync_worker.GitHubAppTokenManager",
            return_value=mock_token_manager,
        ),
        patch(
            "redis.asyncio.Redis.from_url",
            return_value=mock_valkey,
        ),
    ):
        result = await _sync_org_billing(
            mock_db,
            mock_client,
            "test-org",
            999,
            date(2026, 7, 19),
            mock_settings,
            "fake-key",
        )

    assert result >= 1
    first_call_params = mock_db.execute.call_args_list[0][0][1]
    assert first_call_params["org_slug"] == "test-org"
    assert first_call_params["feature_area"] == "actions"
    assert first_call_params["actions_minutes"] == 600.0


@pytest.mark.asyncio
async def test_sync_org_billing_copilot_seats() -> None:
    """_sync_org_billing should upsert per-user Copilot seat data."""
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock()

    mock_valkey = AsyncMock()
    mock_valkey.aclose = AsyncMock()

    mock_token_manager = MagicMock()
    mock_token_manager.get_installation_token = AsyncMock(return_value="ghp_test123")

    not_found = MagicMock()
    not_found.status_code = 404

    copilot_response = MagicMock()
    copilot_response.status_code = 200
    copilot_response.json.return_value = {
        "seats": [
            {
                "assignee": {"login": "dev1"},
                "last_activity_at": "2026-07-19T10:00:00Z",
                "last_activity_editor_suggestions_count": 50,
                "last_activity_editor_acceptances_count": 20,
            },
            {
                "assignee": {"login": "dev2"},
                "last_activity_at": None,
            },
        ]
    }

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=[not_found, copilot_response, not_found, not_found])

    mock_settings = MagicMock()
    mock_settings.VALKEY_URL = "redis://localhost:6379/0"
    mock_settings.github_app.GITHUB_APP_ID = 12345

    with (
        patch(
            "app.workers.billing_sync_worker.GitHubAppTokenManager",
            return_value=mock_token_manager,
        ),
        patch(
            "redis.asyncio.Redis.from_url",
            return_value=mock_valkey,
        ),
    ):
        result = await _sync_org_billing(
            mock_db,
            mock_client,
            "test-org",
            999,
            date(2026, 7, 19),
            mock_settings,
            "fake-key",
        )

    # Only dev1 should be upserted (dev2 has no activity)
    assert result == 1
    params = mock_db.execute.call_args_list[0][0][1]
    assert params["actor_login"] == "dev1"
    assert params["copilot_suggestions"] == 50
    assert params["copilot_acceptances"] == 20


@pytest.mark.asyncio
async def test_sync_org_billing_ghas_committers() -> None:
    """_sync_org_billing should upsert GHAS committer data."""
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock()

    mock_valkey = AsyncMock()
    mock_valkey.aclose = AsyncMock()

    mock_token_manager = MagicMock()
    mock_token_manager.get_installation_token = AsyncMock(return_value="ghp_test123")

    not_found = MagicMock()
    not_found.status_code = 404

    ghas_response = MagicMock()
    ghas_response.status_code = 200
    ghas_response.json.return_value = {
        "repositories": [
            {
                "name": "repo1",
                "advanced_security_committers_breakdown": [
                    {"user_login": "alice"},
                    {"user_login": "bob"},
                ],
            },
            {
                "name": "repo2",
                "advanced_security_committers_breakdown": [
                    {"user_login": "alice"},
                    {"user_login": "charlie"},
                ],
            },
        ]
    }

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=[not_found, not_found, ghas_response, not_found])

    mock_settings = MagicMock()
    mock_settings.VALKEY_URL = "redis://localhost:6379/0"
    mock_settings.github_app.GITHUB_APP_ID = 12345

    with (
        patch(
            "app.workers.billing_sync_worker.GitHubAppTokenManager",
            return_value=mock_token_manager,
        ),
        patch(
            "redis.asyncio.Redis.from_url",
            return_value=mock_valkey,
        ),
    ):
        result = await _sync_org_billing(
            mock_db,
            mock_client,
            "test-org",
            999,
            date(2026, 7, 19),
            mock_settings,
            "fake-key",
        )

    # alice, bob, charlie = 3 unique committers
    assert result == 3
    actor_logins = {call[0][1]["actor_login"] for call in mock_db.execute.call_args_list}
    assert actor_logins == {"alice", "bob", "charlie"}


@pytest.mark.asyncio
async def test_sync_org_billing_token_failure_returns_zero() -> None:
    """_sync_org_billing should return 0 if token acquisition fails."""
    mock_db = AsyncMock()
    mock_client = AsyncMock()

    mock_valkey = AsyncMock()
    mock_valkey.aclose = AsyncMock()

    mock_token_manager = MagicMock()
    mock_token_manager.get_installation_token = AsyncMock(side_effect=RuntimeError("token error"))

    mock_settings = MagicMock()
    mock_settings.VALKEY_URL = "redis://localhost:6379/0"
    mock_settings.github_app.GITHUB_APP_ID = 12345

    with (
        patch(
            "app.workers.billing_sync_worker.GitHubAppTokenManager",
            return_value=mock_token_manager,
        ),
        patch(
            "redis.asyncio.Redis.from_url",
            return_value=mock_valkey,
        ),
    ):
        result = await _sync_org_billing(
            mock_db,
            mock_client,
            "test-org",
            999,
            date(2026, 7, 19),
            mock_settings,
            "fake-key",
        )

    assert result == 0


def test_sync_billing_data_task_exists() -> None:
    """The Celery task should be registered with the correct name."""
    assert sync_billing_data.name == "app.workers.billing_sync_worker.sync_billing_data"


def test_beat_schedule_includes_billing_sync() -> None:
    """The beat schedule should include the billing-sync-daily entry."""
    from app.celery_app import celery_app

    assert "billing-sync-daily" in celery_app.conf.beat_schedule
    entry = celery_app.conf.beat_schedule["billing-sync-daily"]
    assert entry["task"] == "app.workers.billing_sync_worker.sync_billing_data"
