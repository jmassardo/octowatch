"""Tests for the playbook router endpoints.

Covers template CRUD (create, read, update, delete), execution listing,
step completion, step skipping, and execution completion.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import jwt as pyjwt
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps import get_db, get_valkey
from app.routers import playbooks as playbooks_module

SECRET = "testsecretkey_for_unit_tests_only_32ch"


# ─── Helpers ──────────────────────────────────────────────────────


def _make_jwt(sub: str = "testuser", jti: str = "test-jti") -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": sub,
        "github_id": 12345,
        "jti": jti,
        "exp": now + timedelta(hours=1),
        "iat": now,
    }
    return pyjwt.encode(payload, SECRET, algorithm="HS256")


def _make_session(
    login: str = "testuser",
    roles: list[str] | None = None,
) -> str:
    return json.dumps(
        {
            "github_login": login,
            "github_id": 12345,
            "roles": roles or ["sys_admin"],
            "scoped_orgs": ["my-org"],
            "scoped_repos": [],
            "scope_type": "scoped",
            "session_expires_at": "2099-01-01T00:00:00+00:00",
        }
    )


def _make_mock_db() -> AsyncMock:
    """Create a mock async DB session."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_result.fetchall.return_value = []
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalar.return_value = 0
    db = AsyncMock()
    db.execute = AsyncMock(return_value=mock_result)
    db.add = MagicMock()
    db.delete = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    return db


def _make_template_obj(
    template_id: int = 1,
    name: str = "Test Playbook",
    slug: str = "test-playbook",
) -> MagicMock:
    """Create a mock PlaybookTemplate ORM object."""
    t = MagicMock()
    t.id = template_id
    t.name = name
    t.slug = slug
    t.description = "Test description"
    t.detection_categories = ["account_compromise"]
    t.steps = [
        {"title": "Step 1", "description": "Do step 1", "action_type": "manual", "required": True},
        {"title": "Step 2", "description": "Do step 2", "action_type": "link", "required": True},
    ]
    t.created_by = "testuser"
    t.created_at = datetime(2025, 1, 1, tzinfo=UTC)
    t.updated_at = datetime(2025, 1, 1, tzinfo=UTC)
    return t


def _make_execution_obj(
    exec_id: int = 1,
    template_id: int = 1,
    detection_id: int = 10,
    exec_status: str = "in_progress",
) -> MagicMock:
    """Create a mock PlaybookExecution ORM object."""
    e = MagicMock()
    e.id = exec_id
    e.template_id = template_id
    e.detection_id = detection_id
    e.status = exec_status
    e.step_results = [
        {"step_index": 0, "title": "Step 1", "completed": False, "notes": ""},
        {"step_index": 1, "title": "Step 2", "completed": False, "notes": ""},
    ]
    e.started_by = "testuser"
    e.started_at = datetime(2025, 1, 1, tzinfo=UTC)
    e.completed_at = None
    return e


def _build_app(
    session_data: str | None = None,
    mock_db: AsyncMock | None = None,
) -> tuple[FastAPI, AsyncMock, AsyncMock]:
    """Build a test FastAPI app with the playbooks router."""
    app = FastAPI()
    app.include_router(playbooks_module.router, prefix="/api/v1")

    db = mock_db or _make_mock_db()
    mock_valkey = AsyncMock()
    mock_valkey.get = AsyncMock(return_value=session_data)
    mock_valkey.delete = AsyncMock(return_value=1)

    async def override_db():
        yield db

    async def override_valkey():
        yield mock_valkey

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_valkey] = override_valkey

    return app, db, mock_valkey


# ─── Tests: List templates ────────────────────────────────────────


class TestListTemplates:
    """Tests for GET /playbooks/templates."""

    def test_returns_empty_list(self) -> None:
        session = _make_session()
        app, _, _ = _build_app(session_data=session)
        client = TestClient(app)
        token = _make_jwt()
        resp = client.get(
            "/api/v1/playbooks/templates",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_templates(self) -> None:
        session = _make_session()
        mock_db = _make_mock_db()
        t = _make_template_obj()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [t]
        mock_db.execute = AsyncMock(return_value=mock_result)

        app, _, _ = _build_app(session_data=session, mock_db=mock_db)
        client = TestClient(app)
        token = _make_jwt()
        resp = client.get(
            "/api/v1/playbooks/templates",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "Test Playbook"

    def test_requires_auth(self) -> None:
        app, _, _ = _build_app(session_data=None)
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/api/v1/playbooks/templates")
        assert resp.status_code == 401


# ─── Tests: Get template ─────────────────────────────────────────


class TestGetTemplate:
    """Tests for GET /playbooks/templates/{id}."""

    def test_returns_template(self) -> None:
        session = _make_session()
        mock_db = _make_mock_db()
        t = _make_template_obj()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = t
        mock_db.execute = AsyncMock(return_value=mock_result)

        app, _, _ = _build_app(session_data=session, mock_db=mock_db)
        client = TestClient(app)
        token = _make_jwt()
        resp = client.get(
            "/api/v1/playbooks/templates/1",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Test Playbook"

    def test_not_found(self) -> None:
        session = _make_session()
        app, _, _ = _build_app(session_data=session)
        client = TestClient(app)
        token = _make_jwt()
        resp = client.get(
            "/api/v1/playbooks/templates/999",
            cookies={"access_token": token},
        )
        assert resp.status_code == 404


# ─── Tests: Create template ──────────────────────────────────────


class TestCreateTemplate:
    """Tests for POST /playbooks/templates."""

    def test_creates_template(self) -> None:
        session = _make_session()
        mock_db = _make_mock_db()
        # First call for slug check returns None (no conflict), refresh is a no-op
        app, db, _ = _build_app(session_data=session, mock_db=mock_db)

        # After flush + refresh, simulate the created template
        db.refresh = AsyncMock(side_effect=lambda obj: setattr(obj, "id", 1) or None)

        client = TestClient(app)
        token = _make_jwt()
        resp = client.post(
            "/api/v1/playbooks/templates",
            json={
                "name": "New Playbook",
                "description": "A new playbook",
                "detection_categories": ["account_compromise"],
                "steps": [{"title": "Step 1", "description": "Do it", "action_type": "manual"}],
            },
            cookies={"access_token": token, "csrf_token": "test-csrf"},
            headers={"X-CSRF-Token": "test-csrf"},
        )
        assert resp.status_code == 201

    def test_slug_conflict(self) -> None:
        session = _make_session()
        mock_db = _make_mock_db()
        existing = _make_template_obj()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        mock_db.execute = AsyncMock(return_value=mock_result)

        app, _, _ = _build_app(session_data=session, mock_db=mock_db)
        client = TestClient(app)
        token = _make_jwt()
        resp = client.post(
            "/api/v1/playbooks/templates",
            json={
                "name": "Test Playbook",
                "steps": [{"title": "S1", "description": "D"}],
            },
            cookies={"access_token": token, "csrf_token": "test-csrf"},
            headers={"X-CSRF-Token": "test-csrf"},
        )
        assert resp.status_code == 409

    def test_empty_steps_rejected(self) -> None:
        session = _make_session()
        app, _, _ = _build_app(session_data=session)
        client = TestClient(app)
        token = _make_jwt()
        resp = client.post(
            "/api/v1/playbooks/templates",
            json={
                "name": "Bad Playbook",
                "steps": [],
            },
            cookies={"access_token": token, "csrf_token": "test-csrf"},
            headers={"X-CSRF-Token": "test-csrf"},
        )
        assert resp.status_code == 422


# ─── Tests: Update template ──────────────────────────────────────


class TestUpdateTemplate:
    """Tests for PUT /playbooks/templates/{id}."""

    def test_updates_template(self) -> None:
        session = _make_session()
        mock_db = _make_mock_db()
        t = _make_template_obj()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = t
        mock_db.execute = AsyncMock(return_value=mock_result)

        app, _, _ = _build_app(session_data=session, mock_db=mock_db)
        client = TestClient(app)
        token = _make_jwt()
        resp = client.put(
            "/api/v1/playbooks/templates/1",
            json={"name": "Updated Name"},
            cookies={"access_token": token, "csrf_token": "test-csrf"},
            headers={"X-CSRF-Token": "test-csrf"},
        )
        assert resp.status_code == 200

    def test_update_not_found(self) -> None:
        session = _make_session()
        app, _, _ = _build_app(session_data=session)
        client = TestClient(app)
        token = _make_jwt()
        resp = client.put(
            "/api/v1/playbooks/templates/999",
            json={"name": "Nope"},
            cookies={"access_token": token, "csrf_token": "test-csrf"},
            headers={"X-CSRF-Token": "test-csrf"},
        )
        assert resp.status_code == 404


# ─── Tests: Delete template ──────────────────────────────────────


class TestDeleteTemplate:
    """Tests for DELETE /playbooks/templates/{id}."""

    def test_deletes_template(self) -> None:
        session = _make_session()
        mock_db = _make_mock_db()
        t = _make_template_obj()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = t
        mock_db.execute = AsyncMock(return_value=mock_result)

        app, _, _ = _build_app(session_data=session, mock_db=mock_db)
        client = TestClient(app)
        token = _make_jwt()
        resp = client.delete(
            "/api/v1/playbooks/templates/1",
            cookies={"access_token": token, "csrf_token": "test-csrf"},
            headers={"X-CSRF-Token": "test-csrf"},
        )
        assert resp.status_code == 204

    def test_delete_not_found(self) -> None:
        session = _make_session()
        app, _, _ = _build_app(session_data=session)
        client = TestClient(app)
        token = _make_jwt()
        resp = client.delete(
            "/api/v1/playbooks/templates/999",
            cookies={"access_token": token, "csrf_token": "test-csrf"},
            headers={"X-CSRF-Token": "test-csrf"},
        )
        assert resp.status_code == 404


# ─── Tests: List executions ──────────────────────────────────────


class TestListExecutions:
    """Tests for GET /playbooks/executions."""

    def test_returns_empty_list(self) -> None:
        session = _make_session()
        app, _, _ = _build_app(session_data=session)
        client = TestClient(app)
        token = _make_jwt()
        resp = client.get(
            "/api/v1/playbooks/executions",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_returns_executions(self) -> None:
        session = _make_session()
        mock_db = _make_mock_db()
        e = _make_execution_obj()

        # First call returns executions, second returns count
        result1 = MagicMock()
        result1.scalars.return_value.all.return_value = [e]
        result2 = MagicMock()
        result2.scalar.return_value = 1

        mock_db.execute = AsyncMock(side_effect=[result1, result2])

        app, _, _ = _build_app(session_data=session, mock_db=mock_db)
        client = TestClient(app)
        token = _make_jwt()
        resp = client.get(
            "/api/v1/playbooks/executions",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["total"] == 1


# ─── Tests: Get execution ────────────────────────────────────────


class TestGetExecution:
    """Tests for GET /playbooks/executions/{id}."""

    def test_returns_execution(self) -> None:
        session = _make_session()
        mock_db = _make_mock_db()
        e = _make_execution_obj()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = e
        mock_db.execute = AsyncMock(return_value=mock_result)

        app, _, _ = _build_app(session_data=session, mock_db=mock_db)
        client = TestClient(app)
        token = _make_jwt()
        resp = client.get(
            "/api/v1/playbooks/executions/1",
            cookies={"access_token": token},
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == 1

    def test_not_found(self) -> None:
        session = _make_session()
        app, _, _ = _build_app(session_data=session)
        client = TestClient(app)
        token = _make_jwt()
        resp = client.get(
            "/api/v1/playbooks/executions/999",
            cookies={"access_token": token},
        )
        assert resp.status_code == 404


# ─── Tests: Skip step ────────────────────────────────────────────


class TestSkipStep:
    """Tests for POST /playbooks/executions/{id}/skip-step."""

    def test_skips_step(self) -> None:
        session = _make_session()
        mock_db = _make_mock_db()
        e = _make_execution_obj()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = e
        mock_db.execute = AsyncMock(return_value=mock_result)

        app, _, _ = _build_app(session_data=session, mock_db=mock_db)
        client = TestClient(app)
        token = _make_jwt()
        resp = client.post(
            "/api/v1/playbooks/executions/1/skip-step?step_index=0",
            json={"reason": "Not applicable"},
            cookies={"access_token": token, "csrf_token": "test-csrf"},
            headers={"X-CSRF-Token": "test-csrf"},
        )
        assert resp.status_code == 200

    def test_skip_invalid_index(self) -> None:
        session = _make_session()
        mock_db = _make_mock_db()
        e = _make_execution_obj()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = e
        mock_db.execute = AsyncMock(return_value=mock_result)

        app, _, _ = _build_app(session_data=session, mock_db=mock_db)
        client = TestClient(app)
        token = _make_jwt()
        resp = client.post(
            "/api/v1/playbooks/executions/1/skip-step?step_index=99",
            json={"reason": "Test"},
            cookies={"access_token": token, "csrf_token": "test-csrf"},
            headers={"X-CSRF-Token": "test-csrf"},
        )
        assert resp.status_code == 400

    def test_skip_completed_execution_rejected(self) -> None:
        session = _make_session()
        mock_db = _make_mock_db()
        e = _make_execution_obj(exec_status="completed")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = e
        mock_db.execute = AsyncMock(return_value=mock_result)

        app, _, _ = _build_app(session_data=session, mock_db=mock_db)
        client = TestClient(app)
        token = _make_jwt()
        resp = client.post(
            "/api/v1/playbooks/executions/1/skip-step?step_index=0",
            json={"reason": "Test"},
            cookies={"access_token": token, "csrf_token": "test-csrf"},
            headers={"X-CSRF-Token": "test-csrf"},
        )
        assert resp.status_code == 400

    def test_skip_empty_reason_rejected(self) -> None:
        session = _make_session()
        app, _, _ = _build_app(session_data=session)
        client = TestClient(app)
        token = _make_jwt()
        resp = client.post(
            "/api/v1/playbooks/executions/1/skip-step?step_index=0",
            json={"reason": ""},
            cookies={"access_token": token, "csrf_token": "test-csrf"},
            headers={"X-CSRF-Token": "test-csrf"},
        )
        assert resp.status_code == 422


# ─── Tests: Complete execution ────────────────────────────────────


class TestCompleteExecution:
    """Tests for POST /playbooks/executions/{id}/complete."""

    def test_completes_execution(self) -> None:
        session = _make_session()
        mock_db = _make_mock_db()
        e = _make_execution_obj()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = e
        mock_db.execute = AsyncMock(return_value=mock_result)

        app, _, _ = _build_app(session_data=session, mock_db=mock_db)
        client = TestClient(app)
        token = _make_jwt()
        resp = client.post(
            "/api/v1/playbooks/executions/1/complete",
            cookies={"access_token": token, "csrf_token": "test-csrf"},
            headers={"X-CSRF-Token": "test-csrf"},
        )
        assert resp.status_code == 200

    def test_complete_already_completed(self) -> None:
        session = _make_session()
        mock_db = _make_mock_db()
        e = _make_execution_obj(exec_status="completed")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = e
        mock_db.execute = AsyncMock(return_value=mock_result)

        app, _, _ = _build_app(session_data=session, mock_db=mock_db)
        client = TestClient(app)
        token = _make_jwt()
        resp = client.post(
            "/api/v1/playbooks/executions/1/complete",
            cookies={"access_token": token, "csrf_token": "test-csrf"},
            headers={"X-CSRF-Token": "test-csrf"},
        )
        assert resp.status_code == 400


# ─── Tests: Slugify helper ───────────────────────────────────────


class TestSlugify:
    """Tests for the _slugify helper function."""

    def test_basic_slugify(self) -> None:
        from app.routers.playbooks import _slugify

        assert _slugify("Hello World") == "hello-world"

    def test_special_chars(self) -> None:
        from app.routers.playbooks import _slugify

        assert _slugify("CI/CD Threat Response!") == "cicd-threat-response"

    def test_extra_spaces(self) -> None:
        from app.routers.playbooks import _slugify

        assert _slugify("  multiple   spaces  ") == "multiple-spaces"
