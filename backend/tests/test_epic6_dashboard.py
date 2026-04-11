"""Tests for Epic 6 — Dashboard & Visualization Improvements.

Covers:
- Actors router: profile, events, detections, locations
- Detection timeline endpoint
- Executive summary endpoint
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps import get_db, get_valkey
from app.routers import actors as actors_module
from app.routers import detections as detections_module
from app.routers import reports as reports_module
from app.services.rbac_service import OrgRepoScope

SECRET = "testsecretkey_for_unit_tests_only_32ch"


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_jwt(sub: str = "testuser", jti: str = "e6-jti") -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": sub,
        "github_id": 12345,
        "jti": jti,
        "exp": now + timedelta(hours=1),
        "iat": now,
    }
    return pyjwt.encode(payload, SECRET, algorithm="HS256")


def _make_session(orgs: list[str] | None = None, roles: list[str] | None = None) -> str:
    return json.dumps(
        {
            "github_login": "testuser",
            "github_id": 12345,
            "roles": roles or ["analyst"],
            "scoped_orgs": orgs or ["my-org"],
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
    mock_result.scalar_one.return_value = 0
    db = AsyncMock()
    db.execute = AsyncMock(return_value=mock_result)
    return db


def _build_actors_app(valkey_session: str | None = None) -> tuple[FastAPI, AsyncMock, AsyncMock]:
    app = FastAPI()
    app.include_router(actors_module.router, prefix="/api/v1")

    mock_db = _make_mock_db()
    mock_valkey = AsyncMock()
    mock_valkey.get = AsyncMock(return_value=valkey_session)

    async def override_db():
        yield mock_db

    async def override_valkey():
        yield mock_valkey

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_valkey] = override_valkey

    return app, mock_db, mock_valkey


def _build_detections_app(
    valkey_session: str | None = None,
) -> tuple[FastAPI, AsyncMock, AsyncMock]:
    app = FastAPI()
    app.include_router(detections_module.router, prefix="/api/v1")

    mock_db = _make_mock_db()
    mock_valkey = AsyncMock()
    mock_valkey.get = AsyncMock(return_value=valkey_session)

    async def override_db():
        yield mock_db

    async def override_valkey():
        yield mock_valkey

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_valkey] = override_valkey

    return app, mock_db, mock_valkey


def _build_reports_app(
    valkey_session: str | None = None,
) -> tuple[FastAPI, AsyncMock, AsyncMock]:
    app = FastAPI()
    app.include_router(reports_module.router, prefix="/api/v1")

    mock_db = _make_mock_db()
    mock_valkey = AsyncMock()
    mock_valkey.get = AsyncMock(return_value=valkey_session)

    async def override_db():
        yield mock_db

    async def override_valkey():
        yield mock_valkey

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_valkey] = override_valkey

    return app, mock_db, mock_valkey


# ─── Actor profile schemas ──────────────────────────────────────────────────


class TestActorSchemas:
    def test_actor_profile_defaults(self):
        from app.schemas.actor import ActorProfile

        p = ActorProfile(login="octocat", avatar_url="https://github.com/octocat.png")
        assert p.login == "octocat"
        assert p.risk_score == 0.0
        assert p.risk_level == "low"
        assert p.detection_count == 0
        assert p.org_memberships == []

    def test_timeline_event_defaults(self):
        from app.schemas.actor import TimelineEvent

        e = TimelineEvent(
            id=1,
            created_at=datetime.now(UTC),
            action="repos.create",
        )
        assert e.is_sequence_step is False
        assert e.sequence_index is None

    def test_detection_timeline_defaults(self):
        from app.schemas.actor import DetectionTimeline

        t = DetectionTimeline(
            detection_id=1,
            detection_title="Test",
            detection_severity="high",
        )
        assert t.events == []
        assert t.sequence_steps == []


# ─── Risk score computation ──────────────────────────────────────────────────


class TestRiskScore:
    def test_zero_detections_gives_zero_score(self):
        from app.routers.actors import _compute_risk_score

        score, level = _compute_risk_score(0, {})
        assert score == 0.0
        assert level == "low"

    def test_high_severity_detections_give_high_score(self):
        from app.routers.actors import _compute_risk_score

        score, level = _compute_risk_score(5, {"critical": 3, "high": 2})
        assert score > 50
        assert level in ("high", "critical")

    def test_low_severity_detections_give_low_score(self):
        from app.routers.actors import _compute_risk_score

        score, level = _compute_risk_score(2, {"low": 2})
        assert score <= 25
        assert level == "low"

    def test_score_capped_at_100(self):
        from app.routers.actors import _compute_risk_score

        score, _ = _compute_risk_score(100, {"critical": 100})
        assert score <= 100


# ─── Actor endpoints — unauthenticated ───────────────────────────────────────


class TestActorUnauthenticated:
    def test_profile_without_auth_returns_401(self):
        app, _, _ = _build_actors_app(valkey_session=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/actors/octocat")
        assert resp.status_code == 401

    def test_events_without_auth_returns_401(self):
        app, _, _ = _build_actors_app(valkey_session=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/actors/octocat/events")
        assert resp.status_code == 401

    def test_detections_without_auth_returns_401(self):
        app, _, _ = _build_actors_app(valkey_session=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/actors/octocat/detections")
        assert resp.status_code == 401

    def test_locations_without_auth_returns_401(self):
        app, _, _ = _build_actors_app(valkey_session=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/actors/octocat/locations")
        assert resp.status_code == 401


# ─── Actor endpoints — authenticated ─────────────────────────────────────────


class TestActorAuthenticated:
    def test_profile_returns_200(self):
        token = _make_jwt()
        app, _, _ = _build_actors_app(valkey_session=_make_session())

        # Mock the aggregate queries
        event_row = MagicMock()
        event_row.event_count = 42
        event_row.first_seen = datetime(2024, 1, 1, tzinfo=UTC)
        event_row.last_seen = datetime(2024, 3, 15, tzinfo=UTC)

        det_row = MagicMock()
        det_row.detection_count = 3
        det_row.critical_count = 1
        det_row.high_count = 1
        det_row.medium_count = 1
        det_row.low_count = 0

        org_mock = MagicMock()
        org_mock.all.return_value = [("my-org",)]

        # Build mock results for sequential db calls
        event_result = MagicMock()
        event_result.one.return_value = event_row

        org_result = MagicMock()
        org_result.all.return_value = [("my-org",)]

        det_result = MagicMock()
        det_result.one.return_value = det_row

        mock_results_iter = iter([event_result, org_result, det_result])

        async def mock_execute(stmt):
            return next(mock_results_iter)

        with patch(
            "app.routers.actors.get_user_scope",
            AsyncMock(return_value=OrgRepoScope(scoped_orgs=["my-org"], scope_type="org")),
        ):
            # Inject mock execute
            app_db = _make_mock_db()
            app_db.execute = AsyncMock(side_effect=mock_execute)

            async def override_db():
                yield app_db

            app.dependency_overrides[get_db] = override_db

            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get("/api/v1/actors/octocat", cookies={"access_token": token})

        assert resp.status_code == 200
        data = resp.json()
        assert data["login"] == "octocat"
        assert data["event_count"] == 42
        assert data["detection_count"] == 3
        assert data["risk_score"] > 0
        assert "avatar_url" in data

    def test_events_returns_200(self):
        token = _make_jwt()
        app, _, _ = _build_actors_app(valkey_session=_make_session())

        count_result = MagicMock()
        count_result.scalar_one.return_value = 0

        events_result = MagicMock()
        events_result.scalars.return_value.all.return_value = []

        mock_results_iter = iter([count_result, events_result])

        async def mock_execute(stmt):
            return next(mock_results_iter)

        with patch(
            "app.routers.actors.get_user_scope",
            AsyncMock(return_value=OrgRepoScope(scope_type="global")),
        ):
            app_db = _make_mock_db()
            app_db.execute = AsyncMock(side_effect=mock_execute)

            async def override_db():
                yield app_db

            app.dependency_overrides[get_db] = override_db

            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get("/api/v1/actors/octocat/events", cookies={"access_token": token})

        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert data["total"] == 0

    def test_locations_returns_200(self):
        token = _make_jwt()
        app, _, _ = _build_actors_app(valkey_session=_make_session())

        loc_result = MagicMock()
        loc_result.all.return_value = []

        async def mock_execute(stmt):
            return loc_result

        with patch(
            "app.routers.actors.get_user_scope",
            AsyncMock(return_value=OrgRepoScope(scope_type="global")),
        ):
            app_db = _make_mock_db()
            app_db.execute = AsyncMock(side_effect=mock_execute)

            async def override_db():
                yield app_db

            app.dependency_overrides[get_db] = override_db

            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get("/api/v1/actors/octocat/locations", cookies={"access_token": token})

        assert resp.status_code == 200
        data = resp.json()
        assert "locations" in data
        assert data["total_events"] == 0


# ─── Detection timeline — unauthenticated ────────────────────────────────────


class TestDetectionTimelineUnauthenticated:
    def test_timeline_without_auth_returns_401(self):
        app, _, _ = _build_detections_app(valkey_session=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/detections/1/timeline")
        assert resp.status_code == 401


# ─── Detection timeline — authenticated ──────────────────────────────────────


class TestDetectionTimelineAuthenticated:
    def test_timeline_not_found_returns_404(self):
        token = _make_jwt()
        app, _, _ = _build_detections_app(valkey_session=_make_session())

        # Mock detection lookup to return None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        async def mock_execute(stmt):
            return mock_result

        with patch(
            "app.routers.detections.get_user_scope",
            AsyncMock(return_value=OrgRepoScope(scope_type="global")),
        ):
            app_db = _make_mock_db()
            app_db.execute = AsyncMock(side_effect=mock_execute)

            async def override_db():
                yield app_db

            app.dependency_overrides[get_db] = override_db

            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/api/v1/detections/999/timeline", cookies={"access_token": token})

        assert resp.status_code == 404

    def test_timeline_returns_empty_events(self):
        token = _make_jwt()
        app, _, _ = _build_detections_app(valkey_session=_make_session())

        # Mock detection
        mock_detection = MagicMock()
        mock_detection.id = 1
        mock_detection.title = "Test Detection"
        mock_detection.severity = "high"
        mock_detection.event_ids = []
        mock_detection.context_data = {}
        mock_detection.rule = MagicMock()
        mock_detection.rule.name = "test-rule"
        mock_detection.rule.category = "access_control"

        # First call: detection lookup. Second: event query (shouldn't happen since empty)
        det_result = MagicMock()
        det_result.scalar_one_or_none.return_value = mock_detection

        async def mock_execute(stmt):
            return det_result

        with patch(
            "app.routers.detections.get_user_scope",
            AsyncMock(return_value=OrgRepoScope(scope_type="global")),
        ):
            app_db = _make_mock_db()
            app_db.execute = AsyncMock(side_effect=mock_execute)

            async def override_db():
                yield app_db

            app.dependency_overrides[get_db] = override_db

            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get("/api/v1/detections/1/timeline", cookies={"access_token": token})

        assert resp.status_code == 200
        data = resp.json()
        assert data["detection_id"] == 1
        assert data["detection_title"] == "Test Detection"
        assert data["events"] == []

    def test_timeline_with_events_and_sequence(self):
        token = _make_jwt()
        app, _, _ = _build_detections_app(valkey_session=_make_session())

        # Mock detection with sequence context
        mock_detection = MagicMock()
        mock_detection.id = 2
        mock_detection.title = "Sequence Detection"
        mock_detection.severity = "critical"
        mock_detection.event_ids = [10, 11]
        mock_detection.context_data = {
            "sequence": [{"action": "repos.create"}, {"action": "repos.delete"}]
        }
        mock_detection.rule = MagicMock()
        mock_detection.rule.name = "seq-rule"
        mock_detection.rule.category = "data_exfiltration"

        # Mock events
        mock_event1 = MagicMock()
        mock_event1.id = 10
        mock_event1.created_at = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        mock_event1.action = "repos.create"
        mock_event1.actor = "octocat"
        mock_event1.org = "my-org"
        mock_event1.repo = "my-org/hello"
        mock_event1.source_ip = "1.2.3.4"
        mock_event1.geo_country_code = "US"
        mock_event1.geo_city = "San Francisco"
        mock_event1.geo_latitude = 37.77
        mock_event1.geo_longitude = -122.42
        mock_event1.data = {"action": "repos.create"}

        mock_event2 = MagicMock()
        mock_event2.id = 11
        mock_event2.created_at = datetime(2024, 1, 15, 13, 0, 0, tzinfo=UTC)
        mock_event2.action = "repos.delete"
        mock_event2.actor = "octocat"
        mock_event2.org = "my-org"
        mock_event2.repo = "my-org/hello"
        mock_event2.source_ip = "5.6.7.8"
        mock_event2.geo_country_code = "DE"
        mock_event2.geo_city = "Berlin"
        mock_event2.geo_latitude = 52.52
        mock_event2.geo_longitude = 13.40
        mock_event2.data = {"action": "repos.delete"}

        det_result = MagicMock()
        det_result.scalar_one_or_none.return_value = mock_detection

        events_result = MagicMock()
        events_result.scalars.return_value.all.return_value = [mock_event1, mock_event2]

        call_count = 0
        results = [det_result, events_result]

        async def mock_execute(stmt):
            nonlocal call_count
            r = results[min(call_count, len(results) - 1)]
            call_count += 1
            return r

        with patch(
            "app.routers.detections.get_user_scope",
            AsyncMock(return_value=OrgRepoScope(scope_type="global")),
        ):
            app_db = _make_mock_db()
            app_db.execute = AsyncMock(side_effect=mock_execute)

            async def override_db():
                yield app_db

            app.dependency_overrides[get_db] = override_db

            client = TestClient(app, raise_server_exceptions=True)
            resp = client.get("/api/v1/detections/2/timeline", cookies={"access_token": token})

        assert resp.status_code == 200
        data = resp.json()
        assert data["detection_id"] == 2
        assert len(data["events"]) == 2
        assert data["events"][0]["action"] == "repos.create"
        assert data["events"][0]["is_sequence_step"] is True
        assert data["events"][0]["sequence_index"] == 0
        assert data["events"][1]["is_sequence_step"] is True
        assert data["sequence_steps"] == ["repos.create", "repos.delete"]


# ─── Executive summary — unauthenticated ──────────────────────────────────────


class TestExecutiveSummaryUnauthenticated:
    def test_summary_without_auth_returns_401(self):
        app, _, _ = _build_reports_app(valkey_session=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/reports/executive-summary")
        assert resp.status_code == 401

    def test_pdf_without_auth_returns_401(self):
        app, _, _ = _build_reports_app(valkey_session=None)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/reports/executive-summary/pdf")
        assert resp.status_code == 401


# ─── Executive summary — authenticated ────────────────────────────────────────


class TestExecutiveSummaryAuthenticated:
    def test_summary_returns_200_with_expected_keys(self):
        token = _make_jwt()
        app, _, _ = _build_reports_app(valkey_session=_make_session(roles=["report_admin"]))

        # Mock all DB queries to return scalar 0 or empty results
        scalar_result = MagicMock()
        scalar_result.all.return_value = []
        scalar_result.scalar_one.return_value = 0

        async def mock_execute(stmt):
            return scalar_result

        with patch(
            "app.services.rbac_service.get_user_scope",
            AsyncMock(return_value=OrgRepoScope(scope_type="global")),
        ):
            with patch(
                "app.routers.reports.generate_soc2_report",
                AsyncMock(
                    return_value={
                        "executive_summary": {
                            "controls_assessed": 10,
                            "controls_with_evidence": 8,
                        }
                    }
                ),
            ):
                with patch(
                    "app.routers.reports.generate_iso27001_report",
                    AsyncMock(
                        return_value={
                            "executive_summary": {
                                "controls_assessed": 12,
                                "controls_with_evidence": 9,
                            }
                        }
                    ),
                ):
                    with patch(
                        "app.routers.reports.generate_nist_csf_report",
                        AsyncMock(
                            return_value={
                                "executive_summary": {
                                    "functions_assessed": 5,
                                    "functions_with_evidence": 4,
                                }
                            }
                        ),
                    ):
                        app_db = _make_mock_db()
                        app_db.execute = AsyncMock(side_effect=mock_execute)

                        async def override_db():
                            yield app_db

                        app.dependency_overrides[get_db] = override_db

                        client = TestClient(app, raise_server_exceptions=True)
                        resp = client.get(
                            "/api/v1/reports/executive-summary",
                            cookies={"access_token": token},
                        )

        assert resp.status_code == 200
        data = resp.json()
        assert "posture_score" in data
        assert "score_delta" in data
        assert "detection_trend" in data
        assert "compliance_summary" in data
        assert "top_risks" in data
        assert "month_over_month" in data
        assert len(data["compliance_summary"]) == 3

    def test_pdf_returns_html(self):
        token = _make_jwt()
        app, _, _ = _build_reports_app(valkey_session=_make_session(roles=["report_admin"]))

        scalar_result = MagicMock()
        scalar_result.all.return_value = []
        scalar_result.scalar_one.return_value = 0

        async def mock_execute(stmt):
            return scalar_result

        with patch(
            "app.services.rbac_service.get_user_scope",
            AsyncMock(return_value=OrgRepoScope(scope_type="global")),
        ):
            with patch(
                "app.routers.reports.generate_soc2_report",
                AsyncMock(
                    return_value={
                        "executive_summary": {
                            "controls_assessed": 0,
                            "controls_with_evidence": 0,
                        }
                    }
                ),
            ):
                with patch(
                    "app.routers.reports.generate_iso27001_report",
                    AsyncMock(
                        return_value={
                            "executive_summary": {
                                "controls_assessed": 0,
                                "controls_with_evidence": 0,
                            }
                        }
                    ),
                ):
                    with patch(
                        "app.routers.reports.generate_nist_csf_report",
                        AsyncMock(
                            return_value={
                                "executive_summary": {
                                    "functions_assessed": 0,
                                    "functions_with_evidence": 0,
                                }
                            }
                        ),
                    ):
                        app_db = _make_mock_db()
                        app_db.execute = AsyncMock(side_effect=mock_execute)

                        async def override_db():
                            yield app_db

                        app.dependency_overrides[get_db] = override_db

                        client = TestClient(app, raise_server_exceptions=True)
                        resp = client.get(
                            "/api/v1/reports/executive-summary/pdf",
                            cookies={"access_token": token},
                        )

        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "OctoWatch Executive" in resp.text


# ─── Executive summary HTML renderer ─────────────────────────────────────────


class TestExecutiveHtmlRenderer:
    def test_render_produces_valid_html(self):
        from app.routers.reports import _render_executive_html

        summary = {
            "posture_score": 85.0,
            "posture_score_previous": 90.0,
            "score_delta": -5.0,
            "score_delta_pct": -5.6,
            "detection_trend": {"7d": 3, "30d": 12, "90d": 45},
            "severity_breakdown": {"critical": 1, "high": 2},
            "compliance_summary": [
                {
                    "framework": "SOC 2",
                    "controls_assessed": 10,
                    "controls_with_evidence": 8,
                    "compliance_pct": 80.0,
                }
            ],
            "top_risks": [
                {
                    "title": "Branch protection disabled",
                    "severity": "critical",
                    "count": 3,
                    "actor": "badactor",
                }
            ],
            "month_over_month": {
                "current_detections": 12,
                "previous_detections": 8,
                "current_events": 5000,
                "previous_events": 4200,
                "detection_change_pct": 50.0,
                "event_change_pct": 19.0,
            },
        }

        html = _render_executive_html(summary)
        assert "<!DOCTYPE html>" in html
        assert "85" in html  # posture score
        assert "SOC 2" in html
        assert "Branch protection disabled" in html
