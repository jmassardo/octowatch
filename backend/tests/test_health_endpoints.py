"""Integration-style tests for the FastAPI health endpoints (no DB required)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create a minimal test app with only the health router mounted."""
    from app.routers.health import router

    # Build a minimal FastAPI app with just the health endpoints
    test_app = FastAPI()
    test_app.include_router(router)

    with TestClient(test_app) as c:
        yield c


class TestHealthEndpoints:
    def test_liveness_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_health_includes_status_key(self, client):
        resp = client.get("/health")
        assert "status" in resp.json()
