"""Unit tests for GHAS Active Committers service and API endpoint."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps import AuthenticatedUser, get_current_user, get_db
from app.routers.health_signals import router
from app.services import health_signal_service

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_user(scope: str = "global") -> AuthenticatedUser:
    return AuthenticatedUser(
        github_login="testuser",
        github_id=1,
        scope_type=scope,
        scoped_orgs=["test-org"],
        scoped_repos=[],
        roles=["admin"],
        jti="test-jti",
        session_expires_at="2099-01-01T00:00:00Z",
    )


def _build_app(db_session: AsyncMock) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: _make_user()
    return app


# ── Service tests ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_ghas_active_committers_returns_aggregated_counts() -> None:
    """Service returns summed committer counts from the database."""
    mock_session = AsyncMock()
    mock_row = MagicMock()
    mock_row._mapping = {
        "total_active": 150,
        "maximum": 200,
        "purchased": 250,
    }
    mock_result = MagicMock()
    mock_mappings = MagicMock()
    mock_mappings.first.return_value = mock_row._mapping
    mock_result.mappings.return_value = mock_mappings
    mock_session.execute.return_value = mock_result

    result = await health_signal_service.get_ghas_active_committers(
        mock_session,
        scoped_orgs=["org-a", "org-b"],
    )

    assert result["total_active_committers"] == 150
    assert result["maximum_active_committers"] == 200
    assert result["purchased_committers"] == 250
    mock_session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_ghas_active_committers_empty_result() -> None:
    """Service returns zeros when no rows match."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_mappings = MagicMock()
    mock_mappings.first.return_value = None
    mock_result.mappings.return_value = mock_mappings
    mock_session.execute.return_value = mock_result

    result = await health_signal_service.get_ghas_active_committers(
        mock_session,
        scoped_orgs=["no-such-org"],
    )

    assert result["total_active_committers"] == 0
    assert result["maximum_active_committers"] == 0
    assert result["purchased_committers"] == 0


# ── Router / API tests ──────────────────────────────────────────────────────


def test_ghas_active_committers_endpoint_returns_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /health-signals/ghas-active-committers returns 200 with data."""
    mock_db = AsyncMock()
    app = _build_app(mock_db)
    client = TestClient(app)

    async def mock_get_scoped_orgs(*_args: Any, **_kwargs: Any) -> list[str]:
        return ["test-org"]

    async def mock_get_committers(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "total_active_committers": 42,
            "maximum_active_committers": 60,
            "purchased_committers": 100,
        }

    monkeypatch.setattr(
        "app.routers.health_signals.rbac_service.get_scoped_orgs",
        mock_get_scoped_orgs,
    )
    monkeypatch.setattr(
        "app.routers.health_signals.health_signal_service.get_ghas_active_committers",
        mock_get_committers,
    )

    response = client.get("/health-signals/ghas-active-committers")
    assert response.status_code == 200
    data = response.json()
    assert data["total_active_committers"] == 42
    assert data["maximum_active_committers"] == 60
    assert data["purchased_committers"] == 100


def test_ghas_active_committers_endpoint_403_no_orgs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /health-signals/ghas-active-committers returns 403 when user has no orgs."""
    mock_db = AsyncMock()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: mock_db

    non_global_user = AuthenticatedUser(
        github_login="limited",
        github_id=2,
        scope_type="org",
        scoped_orgs=[],
        scoped_repos=[],
        roles=["viewer"],
        jti="test-jti-2",
        session_expires_at="2099-01-01T00:00:00Z",
    )
    app.dependency_overrides[get_current_user] = lambda: non_global_user

    async def mock_get_scoped_orgs(*_args: Any, **_kwargs: Any) -> list[str]:
        return []

    monkeypatch.setattr(
        "app.routers.health_signals.rbac_service.get_scoped_orgs",
        mock_get_scoped_orgs,
    )

    client = TestClient(app)
    response = client.get("/health-signals/ghas-active-committers")
    assert response.status_code == 403
