"""Smoke test: verify all expected route prefixes are registered in the real app.

This test boots the actual application via create_app() and asserts that
every expected API route prefix has at least one registered route path.
It catches the class of bug where a router file exists but is never wired
into main.py with include_router().
"""

from __future__ import annotations

import pytest

from app.main import create_app

# Every route prefix that MUST be registered. If a new router is added,
# add its prefix here so the test fails if someone forgets include_router().
EXPECTED_ROUTE_PREFIXES = [
    "/api/v1/actors",
    "/api/v1/admin",
    "/api/v1/auth",
    "/api/v1/copilot",
    "/api/v1/correlations",
    "/api/v1/cross-org",
    "/api/v1/dashboard",
    "/api/v1/detections",
    "/api/v1/dev-activity",
    "/api/v1/events",
    "/api/v1/features",
    "/api/v1/health-signals",
    "/api/v1/ingest",
    "/api/v1/integrations",
    "/api/v1/notifications",
    "/api/v1/orgs",
    "/api/v1/packages",
    "/api/v1/playbooks",
    "/api/v1/posture",
    "/api/v1/query",
    "/api/v1/reports",
    "/api/v1/rules",
    "/api/v1/secret-scanning",
    "/api/v1/setup",
    "/api/v1/suggestions",
    "/api/v1/supply-chain",
    "/api/v1/telemetry",
    "/api/v1/threat-intel",
    "/api/v1/user",
    "/api/v1/user-classification",
    "/api/v1/workflow-metrics",
    "/api/v1/workflows",
    "/health",
    "/ready",
    "/services/collector",
]


@pytest.fixture(scope="module")
def registered_paths() -> set[str]:
    """Collect all route paths from the real application."""
    app = create_app()
    paths: set[str] = set()
    for route in app.routes:
        if hasattr(route, "path"):
            paths.add(route.path)
    return paths


@pytest.mark.parametrize("prefix", EXPECTED_ROUTE_PREFIXES)
def test_route_prefix_is_registered(registered_paths: set[str], prefix: str) -> None:
    """Assert that each expected prefix has at least one registered route.

    Inspects the app's route table directly rather than making HTTP requests,
    so it works regardless of auth requirements or HTTP method restrictions.
    """
    matching = [p for p in registered_paths if p.startswith(prefix)]
    assert matching, (
        f"No routes found with prefix {prefix!r} — is the router registered in app/main.py?"
    )
