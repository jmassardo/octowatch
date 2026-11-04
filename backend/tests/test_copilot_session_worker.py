"""Tests for the Copilot Chat session ingestion worker (#507)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# ── Fake async DB session / factory helpers ─────────────────────────────────


class _FakeResult:
    def __init__(self, rowcount: int) -> None:
        self.rowcount = rowcount

    def fetchall(self) -> list[Any]:
        return []


class _FakeSession:
    """Minimal stand-in for an AsyncSession that records executed statements."""

    def __init__(self) -> None:
        self.executed: list[tuple[str, Any]] = []
        self.committed = False

    async def execute(self, stmt: Any, params: Any = None) -> _FakeResult:
        self.executed.append((str(stmt), params))
        count = len(params) if isinstance(params, list) else 1
        return _FakeResult(rowcount=count)

    async def commit(self) -> None:
        self.committed = True


class _FakeSessionCtx:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    async def __aenter__(self) -> _FakeSession:
        return self._session

    async def __aexit__(self, *exc_info: object) -> bool:
        return False


class _FakeSessionFactory:
    """Callable that hands out a fresh ``_FakeSession`` per ``async with`` block."""

    def __init__(self) -> None:
        self.sessions: list[_FakeSession] = []

    def __call__(self) -> _FakeSessionCtx:
        session = _FakeSession()
        self.sessions.append(session)
        return _FakeSessionCtx(session)

    def all_executed(self) -> list[tuple[str, Any]]:
        return [stmt for session in self.sessions for stmt in session.executed]


def _session_payload(session_id: str, created_at: str, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": session_id,
        "created_at": created_at,
        "organization": "acme-org",
        "user": {"login": "alice", "id": 42},
        "editor": "vscode",
        "editor_version": "1.90.0",
        "client_version": "1.2.3",
        "model": "gpt-4",
        "language": "python",
        "repository": "acme/repo",
        "turn_count": 1,
        "tool_call_count": 1,
        "total_tokens_in": 100,
        "total_tokens_out": 50,
        "duration_seconds": 12,
        "started_at": created_at,
        "ended_at": created_at,
    }
    payload.update(overrides)
    return payload


def _turn_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "index": 0,
        "created_at": "2026-01-01T00:00:00Z",
        "prompt": {"text": "hello", "tokens": 5},
        "response": {"text": "hi", "tokens": 5},
        "model": "gpt-4",
        "finish_reason": "stop",
        "latency_ms": 200,
        "tool_calls": [
            {
                "name": "search_code",
                "input": {"query": "foo"},
                "output_summary": "found 1 result",
                "duration_ms": 50,
                "success": True,
                "created_at": "2026-01-01T00:00:00Z",
            }
        ],
        "references": [],
        "annotations": [],
    }
    payload.update(overrides)
    return payload


# ── _dedupe_sessions ─────────────────────────────────────────────────────────


class TestDedupeSessions:
    def test_keeps_first_occurrence_of_duplicate_session_id(self):
        from app.workers.ingestion.copilot_session_worker import _dedupe_sessions

        sessions = [
            _session_payload("sess-1", "2026-01-01T00:00:00Z", model="first"),
            _session_payload("sess-2", "2026-01-01T00:01:00Z"),
            _session_payload("sess-1", "2026-01-01T00:00:00Z", model="duplicate"),
        ]

        deduped = _dedupe_sessions(sessions)

        assert [s["id"] for s in deduped] == ["sess-1", "sess-2"]
        assert deduped[0]["model"] == "first"

    def test_skips_entries_without_an_id(self):
        from app.workers.ingestion.copilot_session_worker import _dedupe_sessions

        sessions = [{"created_at": "2026-01-01T00:00:00Z"}, _session_payload("sess-1", "x")]
        deduped = _dedupe_sessions(sessions)
        assert len(deduped) == 1
        assert deduped[0]["id"] == "sess-1"

    def test_empty_input_returns_empty_list(self):
        from app.workers.ingestion.copilot_session_worker import _dedupe_sessions

        assert _dedupe_sessions([]) == []


# ── _next_link / pagination ──────────────────────────────────────────────────


class TestNextLink:
    def test_parses_rel_next_url(self):
        from app.workers.ingestion.copilot_session_worker import _next_link

        headers = httpx.Headers(
            {
                "link": (
                    '<https://api.github.com/x?page=2>; rel="next", '
                    '<https://api.github.com/x?page=5>; rel="last"'
                )
            }
        )
        assert _next_link(headers) == "https://api.github.com/x?page=2"

    def test_returns_none_when_no_link_header(self):
        from app.workers.ingestion.copilot_session_worker import _next_link

        assert _next_link(httpx.Headers({})) is None

    def test_returns_none_when_no_next_rel(self):
        from app.workers.ingestion.copilot_session_worker import _next_link

        headers = httpx.Headers({"link": '<https://api.github.com/x?page=1>; rel="last"'})
        assert _next_link(headers) is None


class TestFetchPaginated:
    @pytest.mark.asyncio
    async def test_follows_link_header_across_pages(self):
        from app.workers.ingestion.copilot_session_worker import _fetch_paginated

        page1 = httpx.Response(
            200,
            json=[{"id": "a"}],
            headers={"link": '<https://api.github.com/next?page=2>; rel="next"'},
            request=httpx.Request("GET", "https://api.github.com/next?page=1"),
        )
        page2 = httpx.Response(
            200,
            json=[{"id": "b"}],
            headers={},
            request=httpx.Request("GET", "https://api.github.com/next?page=2"),
        )

        client = MagicMock()
        client.get = AsyncMock(side_effect=[page1, page2])

        results = await _fetch_paginated(
            client, "https://api.github.com/next", {}, {"per_page": 100}
        )

        assert [r["id"] for r in results] == ["a", "b"]
        assert client.get.await_count == 2

    @pytest.mark.asyncio
    async def test_stops_when_no_next_link(self):
        from app.workers.ingestion.copilot_session_worker import _fetch_paginated

        page1 = httpx.Response(
            200,
            json=[{"id": "only"}],
            headers={},
            request=httpx.Request("GET", "https://api.github.com/x"),
        )
        client = MagicMock()
        client.get = AsyncMock(return_value=page1)

        results = await _fetch_paginated(client, "https://api.github.com/x", {}, {})

        assert len(results) == 1
        assert client.get.await_count == 1


# ── Normalization ─────────────────────────────────────────────────────────────


class TestNormalizeSession:
    def test_maps_expected_fields(self):
        from app.workers.ingestion.copilot_session_worker import _normalize_session

        raw = _session_payload("sess-1", "2026-01-01T00:00:00Z")
        normalized = _normalize_session(raw, enterprise="acme")

        assert normalized["session_id"] == "sess-1"
        assert normalized["enterprise"] == "acme"
        assert normalized["org"] == "acme-org"
        assert normalized["actor"] == "alice"
        assert normalized["actor_id"] == 42
        assert normalized["model"] == "gpt-4"
        assert normalized["copilot_version"] == "1.2.3"
        assert normalized["ingestion_source"] == "copilot_session_api"
        assert normalized["data"] == raw


class TestNormalizeTurnAndToolCall:
    def test_normalize_turn_maps_prompt_and_response(self):
        from app.workers.ingestion.copilot_session_worker import _normalize_turn

        turn = _normalize_turn(_turn_payload(), session_id="sess-1", org="acme-org")

        assert turn["session_id"] == "sess-1"
        assert turn["turn_index"] == 0
        assert turn["prompt_text"] == "hello"
        assert turn["prompt_tokens"] == 5
        assert turn["response_text"] == "hi"
        assert turn["response_tokens"] == 5
        assert turn["org"] == "acme-org"

    def test_normalize_tool_call_maps_fields(self):
        from app.workers.ingestion.copilot_session_worker import _normalize_tool_call

        raw_tool_call = _turn_payload()["tool_calls"][0]
        tool_call = _normalize_tool_call(
            raw_tool_call, session_id="sess-1", turn_index=0, org="acme-org"
        )

        assert tool_call["session_id"] == "sess-1"
        assert tool_call["turn_index"] == 0
        assert tool_call["tool_name"] == "search_code"
        assert tool_call["tool_input"] == {"query": "foo"}
        assert tool_call["success"] is True


# ── _poll_single_copilot_cursor ──────────────────────────────────────────────


class TestPollSingleCopilotCursor:
    @pytest.mark.asyncio
    async def test_dedupes_and_advances_cursor(self):
        from app.workers.ingestion import copilot_session_worker as worker

        sessions_page = [
            _session_payload("sess-1", "2026-01-01T00:00:00Z"),
            _session_payload("sess-1", "2026-01-01T00:00:00Z"),  # duplicate
            _session_payload("sess-2", "2026-01-02T00:00:00Z"),
        ]

        async def fake_fetch_paginated(client, url, headers, params):
            if "/sessions/" in url and url.endswith("/turns"):
                return [_turn_payload()]
            return sessions_page

        session_factory = _FakeSessionFactory()

        with patch.object(worker, "_fetch_paginated", AsyncMock(side_effect=fake_fetch_paginated)):
            sessions, turns, tool_calls = await worker._poll_single_copilot_cursor(
                cursor_id=1,
                enterprise="acme",
                since=None,
                token="tok",
                client=MagicMock(),
                session_factory=session_factory,
            )

        # Only 2 distinct sessions inserted despite 3 raw entries (1 duplicate).
        assert sessions == 2
        assert turns == 2  # one turn per unique session
        assert tool_calls == 2  # one tool call per turn

        # Cursor was advanced to the latest created_at seen (sess-2).
        cursor_updates = [
            params
            for stmt, params in session_factory.all_executed()
            if isinstance(params, dict) and "last_file" in params
        ]
        assert len(cursor_updates) == 1
        assert cursor_updates[0]["last_file"] == "2026-01-02T00:00:00Z"
        assert cursor_updates[0]["id"] == 1

    @pytest.mark.asyncio
    async def test_partial_failure_in_turns_fetch_does_not_abort_poll(self):
        from app.workers.ingestion import copilot_session_worker as worker

        sessions_page = [
            _session_payload("sess-ok", "2026-01-01T00:00:00Z"),
            _session_payload("sess-broken", "2026-01-02T00:00:00Z"),
        ]

        async def fake_fetch_paginated(client, url, headers, params):
            if "/sessions/sess-broken/turns" in url:
                raise httpx.ConnectTimeout("boom")
            if "/sessions/sess-ok/turns" in url:
                return [_turn_payload()]
            return sessions_page

        session_factory = _FakeSessionFactory()

        with patch.object(worker, "_fetch_paginated", AsyncMock(side_effect=fake_fetch_paginated)):
            sessions, turns, tool_calls = await worker._poll_single_copilot_cursor(
                cursor_id=7,
                enterprise="acme",
                since=None,
                token="tok",
                client=MagicMock(),
                session_factory=session_factory,
            )

        # Both sessions are inserted (metadata fetch succeeded for both)...
        assert sessions == 2
        # ...but only the session whose turns fetch succeeded contributes turns.
        assert turns == 1
        assert tool_calls == 1

        # The cursor still advances past the failed session — its metadata
        # was captured even though its turns were not.
        cursor_updates = [
            params
            for stmt, params in session_factory.all_executed()
            if isinstance(params, dict) and "last_file" in params
        ]
        assert cursor_updates[0]["last_file"] == "2026-01-02T00:00:00Z"

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_sessions(self):
        from app.workers.ingestion import copilot_session_worker as worker

        with patch.object(worker, "_fetch_paginated", AsyncMock(return_value=[])):
            sessions, turns, tool_calls = await worker._poll_single_copilot_cursor(
                cursor_id=1,
                enterprise="acme",
                since="2026-01-01T00:00:00Z",
                token="tok",
                client=MagicMock(),
                session_factory=_FakeSessionFactory(),
            )

        assert (sessions, turns, tool_calls) == (0, 0, 0)

    @pytest.mark.asyncio
    async def test_list_fetch_failure_propagates_and_does_not_update_cursor(self):
        """A failure fetching the *sessions list itself* aborts this cursor's poll.

        (Caught one level up in ``_poll_all_copilot_sessions``, which logs and
        increments the cursor's error_count rather than silently continuing.)
        """
        from app.workers.ingestion import copilot_session_worker as worker

        session_factory = _FakeSessionFactory()

        with patch.object(
            worker, "_fetch_paginated", AsyncMock(side_effect=httpx.ConnectTimeout("down"))
        ):
            with pytest.raises(httpx.ConnectTimeout):
                await worker._poll_single_copilot_cursor(
                    cursor_id=1,
                    enterprise="acme",
                    since=None,
                    token="tok",
                    client=MagicMock(),
                    session_factory=session_factory,
                )

        assert session_factory.sessions == []
