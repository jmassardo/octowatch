"""Unit tests for telemetry service and router."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps import AuthenticatedUser, get_current_user, get_db
from app.routers import telemetry as telemetry_module
from app.services import telemetry_service


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
    *result_sets: list[dict[str, object]],
) -> AsyncMock:
    """Return an ``AsyncSession`` mock with mapping results."""
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


def _build_app(mock_db: AsyncMock, user: AuthenticatedUser) -> FastAPI:
    app = FastAPI()
    app.include_router(telemetry_module.router, prefix="/api/v1")

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: user
    return app


@pytest.mark.asyncio
async def test_get_telemetry_summary() -> None:
    summary_row = {
        "events_today": 1200,
        "events_last_minute": 12,
        "events_per_second": 1.25,
        "last_event_at": "2025-01-01T12:00:00+00:00",
        "active_workers": 3,
    }
    error_row = {"error_count": 2, "total_count": 8}
    session = _mock_session_with_mappings([summary_row], [error_row])

    result = await telemetry_service.get_telemetry_summary(session, scoped_orgs=["test-org"])

    assert result["events_per_second"] == 1.25
    assert result["events_today"] == 1200
    assert result["active_workers"] == 3
    assert result["queue_depth"] == 0
    assert result["last_event_at"] == "2025-01-01T12:00:00+00:00"
    assert result["error_rate"] == 0.25


@pytest.mark.asyncio
async def test_get_stream_status() -> None:
    rows = [
        {
            "org": "test-org",
            "ingestion_source": "webhook",
            "last_event_at": "2025-01-01T12:00:00+00:00",
            "events_last_hour": 60,
            "events_per_minute": 1.0,
            "avg_latency_seconds": 2.5,
            "minutes_since_last": 4,
        }
    ]
    session = _mock_session_with_mappings(rows)

    result = await telemetry_service.get_stream_status(
        session,
        scoped_orgs=["test-org"],
        limit=10,
    )

    assert result == rows


@pytest.mark.asyncio
async def test_get_worker_health() -> None:
    health_events = [
        {
            "signal_type": "worker.webhook",
            "severity": "warning",
            "org": "test-org",
            "occurred_at": "2025-01-01T12:00:00+00:00",
            "detail": {"message": "lagging"},
            "resolved_at": None,
        }
    ]
    active_workers = [
        {
            "worker_type": "webhook",
            "tasks_processed_24h": 240,
            "last_heartbeat": "2025-01-01T12:01:00+00:00",
            "first_seen_24h": "2025-01-01T00:00:00+00:00",
        }
    ]
    session = _mock_session_with_mappings(health_events, active_workers)

    result = await telemetry_service.get_worker_health(session, scoped_orgs=["test-org"])

    assert result["health_events"] == health_events
    assert result["active_workers"] == active_workers


@pytest.mark.asyncio
async def test_get_event_volume() -> None:
    volume_rows = [
        {
            "bucket_time": "2025-01-01T12:00:00+00:00",
            "category": "github.audit",
            "event_count": 42,
        }
    ]
    top_actions = [{"action": "repo.create", "count": 10}]
    session = _mock_session_with_mappings(volume_rows, top_actions)

    result = await telemetry_service.get_event_volume(
        session,
        scoped_orgs=["test-org"],
        bucket="hour",
        hours=24,
    )

    assert result["volume"] == volume_rows
    assert result["top_actions"] == top_actions


@pytest.mark.asyncio
async def test_get_ingestion_errors() -> None:
    error_rows = [
        {
            "id": 1,
            "occurred_at": "2025-01-01T12:00:00+00:00",
            "org": "test-org",
            "signal_type": "ingestion.failure",
            "severity": "error",
            "detail": {"message": "bad payload"},
            "resolved_at": None,
        }
    ]
    gap_rows = [
        {
            "org": "test-org",
            "last_event_at": "2025-01-01T11:00:00+00:00",
            "minutes_since_last": 75,
        }
    ]
    session = _mock_session_with_mappings(error_rows, gap_rows)

    result = await telemetry_service.get_ingestion_errors(
        session,
        scoped_orgs=["test-org"],
        limit=25,
    )

    assert result["errors"] == error_rows
    assert result["gaps"] == gap_rows


@pytest.mark.asyncio
async def test_get_telemetry_summary_empty() -> None:
    session = _mock_session_with_mappings([], [])

    result = await telemetry_service.get_telemetry_summary(session, scoped_orgs=["test-org"])

    assert result == {
        "events_per_second": 0,
        "events_today": 0,
        "active_workers": 0,
        "queue_depth": 0,
        "last_event_at": None,
        "error_rate": 0.0,
    }


@pytest.mark.asyncio
async def test_get_stream_status_empty() -> None:
    session = _mock_session_with_mappings([])

    result = await telemetry_service.get_stream_status(session, scoped_orgs=["test-org"])

    assert result == []


def test_summary_endpoint() -> None:
    app = _build_app(AsyncMock(), _make_user())
    response_data = {
        "events_per_second": 1.0,
        "events_today": 100,
        "active_workers": 2,
        "queue_depth": 0,
        "last_event_at": "2025-01-01T12:00:00+00:00",
        "error_rate": 0.1,
    }

    with patch(
        "app.routers.telemetry.rbac_service.get_scoped_orgs",
        new_callable=AsyncMock,
        return_value=["test-org"],
    ):
        with patch(
            "app.routers.telemetry.telemetry_service.get_telemetry_summary",
            new_callable=AsyncMock,
            return_value=response_data,
        ):
            client = TestClient(app)
            response = client.get("/api/v1/telemetry/summary")
            assert response.status_code == 200
            assert response.json() == response_data


def test_stream_status_endpoint() -> None:
    app = _build_app(AsyncMock(), _make_user())
    response_data = {
        "streams": [
            {
                "org": "test-org",
                "ingestion_source": "webhook",
                "last_event_at": "2025-01-01T12:00:00+00:00",
                "events_last_hour": 30,
                "events_per_minute": 0.5,
                "avg_latency_seconds": 1.5,
                "minutes_since_last": 2,
            }
        ]
    }

    with patch(
        "app.routers.telemetry.rbac_service.get_scoped_orgs",
        new_callable=AsyncMock,
        return_value=["test-org"],
    ):
        with patch(
            "app.routers.telemetry.telemetry_service.get_stream_status",
            new_callable=AsyncMock,
            return_value=response_data["streams"],
        ):
            client = TestClient(app)
            response = client.get("/api/v1/telemetry/stream-status?limit=10")
            assert response.status_code == 200
            assert response.json() == response_data


def test_worker_health_endpoint() -> None:
    app = _build_app(AsyncMock(), _make_user())
    response_data = {
        "health_events": [],
        "active_workers": [{"worker_type": "webhook", "tasks_processed_24h": 10}],
    }

    with patch(
        "app.routers.telemetry.rbac_service.get_scoped_orgs",
        new_callable=AsyncMock,
        return_value=["test-org"],
    ):
        with patch(
            "app.routers.telemetry.telemetry_service.get_worker_health",
            new_callable=AsyncMock,
            return_value=response_data,
        ):
            client = TestClient(app)
            response = client.get("/api/v1/telemetry/worker-health")
            assert response.status_code == 200
            assert response.json() == response_data


def test_event_volume_endpoint() -> None:
    app = _build_app(AsyncMock(), _make_user())
    response_data = {
        "volume": [
            {
                "bucket_time": "2025-01-01T12:00:00+00:00",
                "category": "audit",
                "event_count": 8,
            }
        ],
        "top_actions": [{"action": "repo.create", "count": 3}],
    }

    with patch(
        "app.routers.telemetry.rbac_service.get_scoped_orgs",
        new_callable=AsyncMock,
        return_value=["test-org"],
    ):
        with patch(
            "app.routers.telemetry.telemetry_service.get_event_volume",
            new_callable=AsyncMock,
            return_value=response_data,
        ):
            client = TestClient(app)
            response = client.get("/api/v1/telemetry/event-volume?bucket=hour&hours=24")
            assert response.status_code == 200
            assert response.json() == response_data


def test_errors_endpoint() -> None:
    app = _build_app(AsyncMock(), _make_user())
    response_data = {
        "errors": [{"id": 1, "signal_type": "ingestion.failure", "severity": "error"}],
        "gaps": [{"org": "test-org", "minutes_since_last": 12}],
    }

    with patch(
        "app.routers.telemetry.rbac_service.get_scoped_orgs",
        new_callable=AsyncMock,
        return_value=["test-org"],
    ):
        with patch(
            "app.routers.telemetry.telemetry_service.get_ingestion_errors",
            new_callable=AsyncMock,
            return_value=response_data,
        ):
            client = TestClient(app)
            response = client.get("/api/v1/telemetry/errors?limit=25")
            assert response.status_code == 200
            assert response.json() == response_data


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/telemetry/summary",
        "/api/v1/telemetry/stream-status",
        "/api/v1/telemetry/worker-health",
        "/api/v1/telemetry/event-volume",
        "/api/v1/telemetry/errors",
    ],
)
def test_endpoints_require_auth(path: str) -> None:
    app = FastAPI()
    app.include_router(telemetry_module.router, prefix="/api/v1")

    async def override_db():
        yield AsyncMock()

    app.dependency_overrides[get_db] = override_db

    client = TestClient(app)
    response = client.get(path)
    assert response.status_code in (401, 403)


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/telemetry/summary",
        "/api/v1/telemetry/stream-status",
        "/api/v1/telemetry/worker-health",
        "/api/v1/telemetry/event-volume",
        "/api/v1/telemetry/errors",
    ],
)
def test_no_org_access_returns_403(path: str) -> None:
    app = _build_app(AsyncMock(), _make_user(scoped_orgs=[]))

    with patch(
        "app.routers.telemetry.rbac_service.get_scoped_orgs",
        new_callable=AsyncMock,
        return_value=[],
    ):
        client = TestClient(app)
        response = client.get(path)
        assert response.status_code == 403
        assert response.json()["detail"] == "No org access"
