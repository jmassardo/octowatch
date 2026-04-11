"""Tests for Epic 10: Onboarding & Developer Experience.

Covers:
- Rule library endpoint returns 20+ rules in correct categories
- Enable library rule creates active rule with defaults
- Customize endpoint returns pre-filled rule payload
- Library doesn't overwrite existing customized rules (409 conflict)
- Seed data script generates expected event types
- API docs endpoints return valid OpenAPI spec
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps import get_db, get_valkey
from app.routers import rule_library as rule_library_module

SECRET = "testsecretkey_for_unit_tests_only_32ch"


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_jwt(sub: str = "testuser", jti: str = "epic10-jti") -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": sub,
        "github_id": 12345,
        "jti": jti,
        "exp": now + timedelta(hours=1),
        "iat": now,
    }
    return pyjwt.encode(payload, SECRET, algorithm="HS256")


def _make_session(roles: list[str] | None = None) -> str:
    return json.dumps(
        {
            "github_login": "testuser",
            "github_id": 12345,
            "roles": roles or ["analyst"],
            "scoped_orgs": ["my-org"],
            "scoped_repos": [],
            "scope_type": "scoped",
            "session_expires_at": "2099-01-01T00:00:00+00:00",
        }
    )


def _make_mock_db() -> AsyncMock:
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_result.fetchall.return_value = []
    mock_result.scalar_one_or_none.return_value = None
    db = AsyncMock()
    db.execute = AsyncMock(return_value=mock_result)
    db.add = MagicMock()
    return db


@dataclass
class FakeRuleModel:
    """Fake rule model compatible with RuleResponse.model_validate(from_attributes=True)."""

    id: int = 99
    name: str = "Test Library Rule"
    slug: str = "test-library-rule"
    description: str | None = "Created from library"
    category: str = "account_compromise"
    default_severity: str = "high"
    default_confidence: str = "high"
    logic_type: str = "pattern"
    logic_config: dict[str, Any] = field(
        default_factory=lambda: {"action_filters": ["auth.login"], "field_conditions": []}
    )
    enabled: bool = True
    status: str = "active"
    version: int = 1
    git_commit_sha: str | None = None
    created_by: str = "testuser"
    updated_by: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


def _build_library_app(
    valkey_session: str | None = None,
) -> tuple[FastAPI, AsyncMock, AsyncMock]:
    app = FastAPI()
    app.include_router(rule_library_module.router, prefix="/api/v1")

    mock_db = _make_mock_db()
    mock_valkey = AsyncMock()
    mock_valkey.get = AsyncMock(return_value=valkey_session)

    async def override_db() -> AsyncIterator[AsyncMock]:
        yield mock_db

    async def override_valkey() -> AsyncIterator[AsyncMock]:
        yield mock_valkey

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_valkey] = override_valkey

    return app, mock_db, mock_valkey


# ─── Rule library fixture tests ──────────────────────────────────────────────


class TestRuleLibraryFixture:
    """Test the rule_library.json fixture file directly."""

    def test_library_json_is_valid(self) -> None:
        """The library JSON file loads and parses correctly."""
        rules = rule_library_module._load_library()
        assert isinstance(rules, list)
        assert len(rules) >= 20

    def test_library_has_correct_categories(self) -> None:
        """The library contains rules in all required categories."""
        rules = rule_library_module._load_library()
        categories = {r["category"] for r in rules}
        required = {
            "account_compromise",
            "privilege_escalation",
            "data_exfiltration",
            "supply_chain",
            "defense_evasion",
        }
        assert required.issubset(categories)

    def test_library_has_minimum_rules_per_category(self) -> None:
        """Each required category has the minimum number of rules."""
        rules = rule_library_module._load_library()
        category_counts: dict[str, int] = {}
        for rule in rules:
            cat = rule["category"]
            category_counts[cat] = category_counts.get(cat, 0) + 1

        assert category_counts.get("account_compromise", 0) >= 4
        assert category_counts.get("privilege_escalation", 0) >= 4
        assert category_counts.get("data_exfiltration", 0) >= 3
        assert category_counts.get("supply_chain", 0) >= 3
        assert category_counts.get("defense_evasion", 0) >= 4

    def test_library_rules_have_required_fields(self) -> None:
        """Every rule has all required fields."""
        rules = rule_library_module._load_library()
        required_keys = {
            "name",
            "slug",
            "description",
            "category",
            "default_severity",
            "logic_type",
            "logic_config",
        }
        for rule in rules:
            missing = required_keys - rule.keys()
            assert not missing, f"Rule '{rule.get('slug', '?')}' is missing keys: {missing}"

    def test_library_slugs_are_unique(self) -> None:
        """All slugs in the library are unique."""
        rules = rule_library_module._load_library()
        slugs = [r["slug"] for r in rules]
        assert len(slugs) == len(set(slugs)), f"Duplicate slugs found: {slugs}"

    def test_library_group_by_category(self) -> None:
        """_group_by_category produces correctly structured output."""
        rules = rule_library_module._load_library()
        categories = rule_library_module._group_by_category(rules)
        assert len(categories) >= 5
        for cat in categories:
            assert cat.category
            assert cat.display_name
            assert len(cat.rules) > 0


# ─── Rule library API endpoint tests ─────────────────────────────────────────


class TestRuleLibraryAPI:
    """Test the rule library REST API endpoints."""

    def test_list_library_returns_200(self) -> None:
        """GET /rules/library returns 200 with rules grouped by category."""
        token = _make_jwt()
        app, _, _ = _build_library_app(valkey_session=_make_session(roles=["analyst"]))
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get("/api/v1/rules/library", cookies={"access_token": token})
        assert resp.status_code == 200
        data = resp.json()
        assert "categories" in data
        assert "total_rules" in data
        assert data["total_rules"] >= 20
        assert len(data["categories"]) >= 5

    def test_list_library_unauthenticated_returns_401(self) -> None:
        """GET /rules/library without auth returns 401."""
        app, _, _ = _build_library_app(valkey_session=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/rules/library")
        assert resp.status_code == 401

    def test_enable_library_rule_creates_active_rule(self) -> None:
        """POST /rules/library/{slug}/enable creates a rule with defaults."""
        token = _make_jwt()
        session = _make_session(roles=["rule_author"])
        app, mock_db, _ = _build_library_app(valkey_session=session)

        fake_rule = FakeRuleModel()

        with (
            patch(
                "app.routers.rule_library.rule_service.get_rule_by_slug",
                AsyncMock(return_value=None),
            ),
            patch(
                "app.routers.rule_library.rule_service.create_rule",
                AsyncMock(return_value=fake_rule),
            ),
        ):
            client = TestClient(app, raise_server_exceptions=True)
            resp = client.post(
                "/api/v1/rules/library/impossible-travel-login/enable",
                json={},
                cookies={"access_token": token, "csrf_token": "tok"},
                headers={"X-CSRF-Token": "tok"},
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Test Library Rule"
        assert data["status"] == "active"

    def test_enable_existing_slug_returns_409(self) -> None:
        """POST /rules/library/{slug}/enable returns 409 if slug exists."""
        token = _make_jwt()
        session = _make_session(roles=["rule_author"])
        app, mock_db, _ = _build_library_app(valkey_session=session)

        existing_rule = MagicMock()
        existing_rule.id = 42

        with patch(
            "app.routers.rule_library.rule_service.get_rule_by_slug",
            AsyncMock(return_value=existing_rule),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post(
                "/api/v1/rules/library/impossible-travel-login/enable",
                json={},
                cookies={"access_token": token, "csrf_token": "tok"},
                headers={"X-CSRF-Token": "tok"},
            )
        assert resp.status_code == 409

    def test_enable_nonexistent_slug_returns_404(self) -> None:
        """POST /rules/library/nonexistent/enable returns 404."""
        token = _make_jwt()
        session = _make_session(roles=["rule_author"])
        app, _, _ = _build_library_app(valkey_session=session)

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/v1/rules/library/nonexistent-slug/enable",
            json={},
            cookies={"access_token": token, "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert resp.status_code == 404

    def test_customize_returns_prefilled_payload(self) -> None:
        """GET /rules/library/{slug}/customize returns a pre-filled RuleCreate."""
        token = _make_jwt()
        app, _, _ = _build_library_app(valkey_session=_make_session(roles=["analyst"]))
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get(
            "/api/v1/rules/library/impossible-travel-login/customize",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "rule" in data
        rule = data["rule"]
        assert rule["slug"] == "impossible-travel-login"
        assert rule["name"] == "Impossible Travel Login"
        assert rule["logic_type"] in ("statistical", "pattern", "threshold", "sequence")
        assert "logic_config" in rule

    def test_customize_nonexistent_slug_returns_404(self) -> None:
        """GET /rules/library/nonexistent/customize returns 404."""
        token = _make_jwt()
        app, _, _ = _build_library_app(valkey_session=_make_session(roles=["analyst"]))
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get(
            "/api/v1/rules/library/nonexistent-slug/customize",
            cookies={"access_token": token},
        )
        assert resp.status_code == 404

    def test_enable_requires_rule_author_role(self) -> None:
        """POST /rules/library/{slug}/enable requires rule_author role."""
        token = _make_jwt()
        session = _make_session(roles=["viewer"])
        app, _, _ = _build_library_app(valkey_session=session)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/v1/rules/library/impossible-travel-login/enable",
            json={},
            cookies={"access_token": token, "csrf_token": "tok"},
            headers={"X-CSRF-Token": "tok"},
        )
        assert resp.status_code == 403


# ─── Seed data generator tests ───────────────────────────────────────────────


class TestSeedDataGenerator:
    """Test the seed data generator produces expected outputs."""

    def test_generates_events(self) -> None:
        """generate_all_events produces a non-empty list."""
        from scripts.seed_data import generate_all_events

        events = generate_all_events(num_days=3, events_per_day=50)
        assert len(events) > 0

    def test_events_have_required_fields(self) -> None:
        """Every generated event has required fields."""
        from scripts.seed_data import generate_all_events

        events = generate_all_events(num_days=2, events_per_day=10)
        required_keys = {"document_id", "action", "actor", "org", "created_at", "source"}
        for event in events[:20]:  # Check first 20 events
            missing = required_keys - event.keys()
            assert not missing, f"Event missing keys: {missing}"

    def test_events_sorted_by_timestamp(self) -> None:
        """Events are sorted chronologically."""
        from scripts.seed_data import generate_all_events

        events = generate_all_events(num_days=3, events_per_day=50)
        timestamps = [e["created_at"] for e in events]
        assert timestamps == sorted(timestamps)

    def test_generates_diverse_event_types(self) -> None:
        """Generated events cover multiple action namespaces."""
        from scripts.seed_data import generate_all_events

        events = generate_all_events(num_days=5, events_per_day=100)
        namespaces = {e["action"].split(".")[0] for e in events}
        # Must include at least these namespaces
        expected = {"auth", "repo", "team", "workflows", "org"}
        assert expected.issubset(namespaces), f"Missing namespaces: {expected - namespaces}"

    def test_generates_suspicious_patterns(self) -> None:
        """Generated data includes events from suspicious actors."""
        from scripts.seed_data import generate_all_events

        events = generate_all_events(num_days=10, events_per_day=100)
        suspicious_actors = {
            e["actor"] for e in events if e["actor"] in ("eve-attacker", "frank-contractor")
        }
        assert "eve-attacker" in suspicious_actors
        assert "frank-contractor" in suspicious_actors

    def test_generates_impossible_travel_pattern(self) -> None:
        """Generates impossible travel events (same user, distant cities, short window)."""
        from scripts.seed_data import generate_impossible_travel

        base = datetime.now(UTC)
        events = generate_impossible_travel(base)
        assert len(events) >= 4
        # All from same actor
        assert all(e["actor"] == "eve-attacker" for e in events)
        # All are login events
        assert all(e["action"] == "auth.login" for e in events)

    def test_generates_mass_repo_deletion(self) -> None:
        """Generates mass repo deletion events."""
        from scripts.seed_data import generate_mass_repo_deletion

        base = datetime.now(UTC)
        events = generate_mass_repo_deletion(base)
        assert len(events) == 8
        assert all(e["action"] == "repo.destroy" for e in events)
        assert all(e["actor"] == "eve-attacker" for e in events)

    def test_generates_branch_protection_disable(self) -> None:
        """Generates branch protection disable events."""
        from scripts.seed_data import generate_branch_protection_disable

        base = datetime.now(UTC)
        events = generate_branch_protection_disable(base)
        assert len(events) == 2
        assert all(e["action"] == "protected_branch.destroy" for e in events)

    def test_seed_source_marker(self) -> None:
        """All generated events have the seed_generator source marker."""
        from scripts.seed_data import generate_all_events

        events = generate_all_events(num_days=2, events_per_day=10)
        for event in events:
            assert event["source"] == "seed_generator"

    def test_realistic_geolocations(self) -> None:
        """Events have realistic geolocation data."""
        from scripts.seed_data import generate_all_events

        events = generate_all_events(num_days=2, events_per_day=50)
        for event in events[:10]:
            assert "geo_city" in event
            assert "geo_country_code" in event
            assert len(event["geo_country_code"]) == 2

    def test_events_per_day_scaling(self) -> None:
        """More events_per_day produces proportionally more events."""
        from scripts.seed_data import generate_all_events

        small = generate_all_events(num_days=5, events_per_day=10)
        large = generate_all_events(num_days=5, events_per_day=100)
        assert len(large) > len(small)


# ─── API docs tests ──────────────────────────────────────────────────────────


class TestAPIDocumentation:
    """Test the OpenAPI documentation endpoints."""

    def test_openapi_spec_accessible(self) -> None:
        """GET /api/openapi.json returns a valid OpenAPI spec."""
        from app.main import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get("/api/openapi.json")
        assert resp.status_code == 200
        spec = resp.json()
        assert "openapi" in spec
        assert "info" in spec
        assert spec["info"]["title"] == "OctoWatch API"
        assert spec["info"]["version"] == "1.0.0"

    def test_openapi_has_paths(self) -> None:
        """The OpenAPI spec contains API paths."""
        from app.main import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get("/api/openapi.json")
        spec = resp.json()
        assert "paths" in spec
        assert len(spec["paths"]) > 10

    def test_openapi_has_tag_descriptions(self) -> None:
        """The OpenAPI spec includes tag metadata."""
        from app.main import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get("/api/openapi.json")
        spec = resp.json()
        tags = spec.get("tags", [])
        assert len(tags) > 0
        tag_names = {t["name"] for t in tags}
        assert "rules" in tag_names
        assert "rule-library" in tag_names

    def test_openapi_has_rule_library_endpoints(self) -> None:
        """The OpenAPI spec includes rule library endpoints."""
        from app.main import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get("/api/openapi.json")
        spec = resp.json()
        paths = spec["paths"]
        library_paths = [p for p in paths if "library" in p]
        assert len(library_paths) >= 1

    def test_swagger_ui_accessible(self) -> None:
        """GET /api/docs returns the Swagger UI page."""
        from app.main import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get("/api/docs")
        assert resp.status_code == 200
        assert "swagger" in resp.text.lower() or "text/html" in resp.headers.get("content-type", "")

    def test_openapi_has_contact_info(self) -> None:
        """The OpenAPI spec includes contact information."""
        from app.main import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get("/api/openapi.json")
        spec = resp.json()
        assert "contact" in spec["info"]
        assert spec["info"]["contact"]["name"] == "OctoWatch Team"

    def test_openapi_has_license_info(self) -> None:
        """The OpenAPI spec includes license information."""
        from app.main import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get("/api/openapi.json")
        spec = resp.json()
        assert "license" in spec["info"]
        assert spec["info"]["license"]["name"] == "Apache 2.0"
