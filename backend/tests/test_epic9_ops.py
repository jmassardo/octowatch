"""Tests for Epic 9: Operational Maturity — Prometheus metrics, health, metrics service."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ── Helpers ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def client() -> TestClient:
    """Create a TestClient for the OctoWatch FastAPI app."""
    from app.main import create_app

    app = create_app()
    return TestClient(app)


# ── /metrics endpoint ───────────────────────────────────────────────────────


class TestMetricsEndpoint:
    """Tests for the /metrics Prometheus endpoint."""

    def test_metrics_endpoint_returns_200(self, client: TestClient) -> None:
        """The /metrics endpoint must return HTTP 200."""
        response = client.get("/metrics")
        assert response.status_code == 200

    def test_metrics_endpoint_returns_prometheus_format(self, client: TestClient) -> None:
        """Response must contain Prometheus text exposition format markers."""
        response = client.get("/metrics")
        body = response.text
        # Prometheus text format contains TYPE and HELP directives
        assert "# HELP" in body
        assert "# TYPE" in body

    def test_metrics_contains_http_request_metrics(self, client: TestClient) -> None:
        """Auto-instrumented HTTP request metrics must be present."""
        # Make a request first to generate metrics
        client.get("/health")
        response = client.get("/metrics")
        body = response.text
        # prometheus-fastapi-instrumentator exposes http_ prefixed metrics
        assert "http_request" in body or "http_requests" in body

    def test_metrics_contains_custom_octowatch_metrics(self, client: TestClient) -> None:
        """Custom OctoWatch metrics must be registered in the default registry."""
        response = client.get("/metrics")
        body = response.text
        # Our custom metrics should appear in the output
        assert "octowatch" in body.lower()

    def test_metrics_endpoint_not_in_openapi_schema(self, client: TestClient) -> None:
        """The /metrics endpoint should be excluded from the OpenAPI schema."""
        response = client.get("/api/openapi.json")
        if response.status_code == 200:
            schema = response.json()
            paths = schema.get("paths", {})
            assert "/metrics" not in paths


# ── Health endpoints still work ─────────────────────────────────────────────


class TestHealthWithMetrics:
    """Ensure health endpoints still function correctly alongside metrics."""

    def test_health_endpoint_still_works(self, client: TestClient) -> None:
        """GET /health must still return 200 with metrics middleware active."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_health_not_counted_in_metrics(self, client: TestClient) -> None:
        """Health checks should be excluded from Prometheus request metrics."""
        # Hit health a few times
        for _ in range(3):
            client.get("/health")
        response = client.get("/metrics")
        body = response.text
        # The /health path should not appear as a tracked handler in metrics
        # (it's in excluded_handlers)
        lines = [line for line in body.split("\n") if "/health" in line and "http_request" in line]
        assert len(lines) == 0, f"Health endpoint should be excluded from metrics, found: {lines}"


# ── Custom metrics registration ─────────────────────────────────────────────


class TestMetricsServiceRegistration:
    """Verify custom OctoWatch metrics are properly defined and usable."""

    def test_detection_pipeline_histogram_exists(self) -> None:
        """DETECTION_PIPELINE_DURATION histogram must be importable and functional."""
        from app.services.metrics_service import DETECTION_PIPELINE_DURATION

        # Observe a value — should not raise
        DETECTION_PIPELINE_DURATION.observe(0.42)

    def test_ingestion_counter_exists(self) -> None:
        """INGESTION_EVENTS_TOTAL counter must accept label values."""
        from app.services.metrics_service import INGESTION_EVENTS_TOTAL

        INGESTION_EVENTS_TOTAL.labels(source="hec").inc()

    def test_detection_count_counter_exists(self) -> None:
        """DETECTION_COUNT counter must accept severity labels."""
        from app.services.metrics_service import DETECTION_COUNT

        DETECTION_COUNT.labels(severity="critical").inc()

    def test_celery_queue_depth_gauge_exists(self) -> None:
        """CELERY_QUEUE_DEPTH gauge must accept queue labels."""
        from app.services.metrics_service import CELERY_QUEUE_DEPTH

        CELERY_QUEUE_DEPTH.labels(queue="ingestion").set(42)
        # Verify it was set
        assert CELERY_QUEUE_DEPTH.labels(queue="ingestion")._value.get() == 42.0

    def test_db_connections_active_gauge_exists(self) -> None:
        """DB_CONNECTIONS_ACTIVE gauge must be settable."""
        from app.services.metrics_service import DB_CONNECTIONS_ACTIVE

        DB_CONNECTIONS_ACTIVE.set(5)

    def test_cache_hit_rate_gauge_exists(self) -> None:
        """CACHE_HIT_RATE gauge must be settable."""
        from app.services.metrics_service import CACHE_HIT_RATE

        CACHE_HIT_RATE.set(0.85)

    def test_ingestion_throughput_gauge_exists(self) -> None:
        """INGESTION_THROUGHPUT gauge must be settable."""
        from app.services.metrics_service import INGESTION_THROUGHPUT

        INGESTION_THROUGHPUT.set(150.5)

    def test_app_info_exists(self) -> None:
        """APP_INFO Info metric must be settable."""
        from app.services.metrics_service import APP_INFO

        APP_INFO.info({"version": "test", "environment": "test"})

    def test_set_app_info_function(self) -> None:
        """set_app_info helper must populate the Info metric."""
        from app.services.metrics_service import set_app_info

        # Should not raise
        set_app_info(version="1.0.0-test", environment="testing")


# ── collect_infrastructure_metrics ──────────────────────────────────────────


class TestCollectInfrastructureMetrics:
    """Test the periodic infrastructure metrics collection."""

    @pytest.mark.asyncio
    async def test_collect_metrics_returns_dict(self) -> None:
        """collect_infrastructure_metrics returns a summary dict, even on failure."""
        from app.services.metrics_service import collect_infrastructure_metrics

        # In test env, Valkey/DB aren't available, but the function should
        # handle errors gracefully and return a dict (possibly empty)
        result = await collect_infrastructure_metrics()
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_collect_metrics_sets_queue_depths(self) -> None:
        """When Valkey is available, queue depths are set on the gauge."""
        from app.services.metrics_service import (
            CELERY_QUEUE_DEPTH,
            collect_infrastructure_metrics,
        )

        mock_redis_inst = MagicMock()
        mock_redis_inst.llen = MagicMock(return_value=7)
        mock_redis_inst.close = MagicMock()
        mock_redis_inst.info = MagicMock(
            return_value={"keyspace_hits": 100, "keyspace_misses": 20},
        )

        _patch_target = "app.services.metrics_service.sync_redis.Redis.from_url"
        with patch(_patch_target, return_value=mock_redis_inst):
            result = await collect_infrastructure_metrics()

        # Check that queue depths were set
        assert result.get("queue_ingestion") == 7
        assert CELERY_QUEUE_DEPTH.labels(queue="ingestion")._value.get() == 7.0

    @pytest.mark.asyncio
    async def test_collect_metrics_sets_cache_hit_rate(self) -> None:
        """When Valkey is reachable, cache hit rate is computed and set."""
        from app.services.metrics_service import (
            CACHE_HIT_RATE,
            collect_infrastructure_metrics,
        )

        mock_redis_inst = MagicMock()
        mock_redis_inst.llen = MagicMock(return_value=0)
        mock_redis_inst.close = MagicMock()
        mock_redis_inst.info = MagicMock(
            return_value={"keyspace_hits": 80, "keyspace_misses": 20},
        )

        _patch_target = "app.services.metrics_service.sync_redis.Redis.from_url"
        with patch(_patch_target, return_value=mock_redis_inst):
            result = await collect_infrastructure_metrics()

        assert result.get("cache_hit_rate") == 0.8
        assert CACHE_HIT_RATE._value.get() == 0.8


# ── Instrumentator configuration ────────────────────────────────────────────


class TestInstrumentatorConfig:
    """Verify the Prometheus instrumentator is configured correctly on the app."""

    def test_app_has_metrics_route(self, client: TestClient) -> None:
        """The FastAPI app must have a /metrics route registered."""
        from app.main import create_app

        test_app = create_app()
        route_paths = [r.path for r in test_app.routes if hasattr(r, "path")]
        assert "/metrics" in route_paths

    def test_metrics_excluded_from_self_instrumentation(self, client: TestClient) -> None:
        """Hitting /metrics should not create recursive metric entries for /metrics."""
        # Hit metrics twice
        client.get("/metrics")
        response = client.get("/metrics")
        body = response.text
        # /metrics should not appear as a tracked handler
        metric_handler_lines = [
            line for line in body.split("\n") if '"/metrics"' in line and "http_request" in line
        ]
        assert len(metric_handler_lines) == 0
