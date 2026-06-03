"""Tests for the enterprise audit log sync feature.

Covers:
- ScopeType and schema inclusion of ``audit_log``
- ``_ENTERPRISE_ENTITIES`` set membership
- ``_fetch_page`` handler for ``audit_log`` entity type
- ``_upsert_items`` dispatch to ``_upsert_audit_log_events``
- ``_upsert_audit_log_events`` normalization and dedup logic
- Edge cases: 403/404 responses, empty results, pagination cursors
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.github_sync import SyncTriggerRequest

# ─── Schema and Scope Tests ──────────────────────────────────────────────────


class TestAuditLogScopeType:
    """Verify audit_log is a valid scope in the sync trigger schema."""

    def test_audit_log_is_valid_scope(self) -> None:
        req = SyncTriggerRequest(scope="audit_log")
        assert req.scope == "audit_log"

    def test_full_scope_still_valid(self) -> None:
        req = SyncTriggerRequest(scope="full")
        assert req.scope == "full"

    def test_scope_type_literal_includes_audit_log(self) -> None:
        """Verify the ScopeType Literal in github_sync_worker includes audit_log."""
        # ScopeType is a Literal — verify by checking its __args__
        import typing

        from app.workers.github_sync_worker import ScopeType

        args = typing.get_args(ScopeType)
        assert "audit_log" in args


class TestEnterpriseEntitiesSet:
    """Verify audit_log is in the _ENTERPRISE_ENTITIES set used by the orchestrator."""

    def test_enterprise_entities_includes_audit_log(self) -> None:
        import pathlib

        worker_path = (
            pathlib.Path(__file__).parent.parent / "app" / "workers" / "github_sync_worker.py"
        )
        source = worker_path.read_text()

        # Find the _ENTERPRISE_ENTITIES block and verify audit_log is inside it
        idx_start = source.index("_ENTERPRISE_ENTITIES = {")
        idx_end = source.index("}", idx_start)
        enterprise_block = source[idx_start:idx_end]
        assert "audit_log" in enterprise_block


# ─── Fetch Page Tests ────────────────────────────────────────────────────────


class TestFetchAuditLogPage:
    """Tests for _fetch_page handling of the audit_log entity type."""

    @pytest.mark.asyncio
    async def test_fetch_audit_log_returns_events(self) -> None:
        """First page of audit log returns events and a cursor."""
        from app.workers.github_sync_worker import _fetch_page

        mock_rate_limiter = MagicMock()
        mock_rate_limiter.acquire = AsyncMock()
        mock_rate_limiter.release = MagicMock()
        mock_rate_limiter.update_from_headers = MagicMock()

        events = [
            {
                "action": "repo.create",
                "actor": "octocat",
                "org": "my-enterprise-org",
                "@timestamp": 1700000000000,
                "@ip": "1.2.3.4",
                "_document_id": "abc123",
            },
            {
                "action": "team.add_member",
                "actor": "admin-user",
                "org": "my-enterprise-org",
                "@timestamp": 1700000001000,
                "@ip": "5.6.7.8",
                "_document_id": "def456",
            },
        ]

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = events
        mock_resp.headers = {}

        with patch(
            "app.workers.github_sync_worker._github_get",
            new=AsyncMock(return_value=mock_resp),
        ):
            items, next_cursor = await _fetch_page(
                entity_type="audit_log",
                org="my-enterprise",
                token="test-token",
                cursor=None,
                rate_limiter=mock_rate_limiter,
            )

        assert len(items) == 2
        assert items[0]["action"] == "repo.create"
        assert items[1]["action"] == "team.add_member"
        # Only 2 items (< page_size=100), so no more pages
        assert next_cursor is None

    @pytest.mark.asyncio
    async def test_fetch_audit_log_full_page_returns_cursor(self) -> None:
        """A full page of results indicates more data is available."""
        from app.workers.github_sync_worker import _fetch_page

        mock_rate_limiter = MagicMock()
        mock_rate_limiter.acquire = AsyncMock()
        mock_rate_limiter.release = MagicMock()
        mock_rate_limiter.update_from_headers = MagicMock()

        # Generate exactly page_size events
        events = [
            {
                "action": f"event.action_{i}",
                "actor": "user",
                "@timestamp": 1700000000000 + i * 1000,
                "_document_id": f"doc_{i}",
            }
            for i in range(100)
        ]

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = events
        mock_resp.headers = {}  # No Link header

        with patch(
            "app.workers.github_sync_worker._github_get",
            new=AsyncMock(return_value=mock_resp),
        ):
            items, next_cursor = await _fetch_page(
                entity_type="audit_log",
                org="my-enterprise",
                token="test-token",
                cursor=None,
                rate_limiter=mock_rate_limiter,
            )

        assert len(items) == 100
        assert next_cursor is not None
        # Cursor should be a JSON object with after and timestamp
        cursor_data = json.loads(next_cursor)
        assert "after" in cursor_data
        assert "timestamp" in cursor_data
        assert cursor_data["after"] == "doc_99"

    @pytest.mark.asyncio
    async def test_fetch_audit_log_link_header_pagination(self) -> None:
        """Link header with rel=next indicates more pages."""
        from app.workers.github_sync_worker import _fetch_page

        mock_rate_limiter = MagicMock()
        mock_rate_limiter.acquire = AsyncMock()
        mock_rate_limiter.release = MagicMock()
        mock_rate_limiter.update_from_headers = MagicMock()

        events = [
            {
                "action": "repo.create",
                "actor": "user",
                "@timestamp": 1700000000000,
                "_document_id": "doc_1",
            },
        ]

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = events
        mock_resp.headers = {
            "link": '<https://api.github.com/enterprises/slug/audit-log?after=abc>; rel="next"'
        }

        with patch(
            "app.workers.github_sync_worker._github_get",
            new=AsyncMock(return_value=mock_resp),
        ):
            items, next_cursor = await _fetch_page(
                entity_type="audit_log",
                org="my-enterprise",
                token="test-token",
                cursor=None,
                rate_limiter=mock_rate_limiter,
            )

        assert len(items) == 1
        assert next_cursor is not None
        cursor_data = json.loads(next_cursor)
        assert cursor_data["after"] == "doc_1"

    @pytest.mark.asyncio
    async def test_fetch_audit_log_403_returns_empty(self) -> None:
        """403 response gracefully returns empty (permission denied)."""
        from app.workers.github_sync_worker import _fetch_page

        mock_rate_limiter = MagicMock()
        mock_rate_limiter.acquire = AsyncMock()
        mock_rate_limiter.release = MagicMock()
        mock_rate_limiter.update_from_headers = MagicMock()

        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.text = "Forbidden"

        with patch(
            "app.workers.github_sync_worker._github_get",
            new=AsyncMock(return_value=mock_resp),
        ):
            items, next_cursor = await _fetch_page(
                entity_type="audit_log",
                org="my-enterprise",
                token="test-token",
                cursor=None,
                rate_limiter=mock_rate_limiter,
            )

        assert items == []
        assert next_cursor is None

    @pytest.mark.asyncio
    async def test_fetch_audit_log_404_returns_empty(self) -> None:
        """404 response gracefully returns empty (enterprise not found)."""
        from app.workers.github_sync_worker import _fetch_page

        mock_rate_limiter = MagicMock()
        mock_rate_limiter.acquire = AsyncMock()
        mock_rate_limiter.release = MagicMock()
        mock_rate_limiter.update_from_headers = MagicMock()

        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = "Not Found"

        with patch(
            "app.workers.github_sync_worker._github_get",
            new=AsyncMock(return_value=mock_resp),
        ):
            items, next_cursor = await _fetch_page(
                entity_type="audit_log",
                org="my-enterprise",
                token="test-token",
                cursor=None,
                rate_limiter=mock_rate_limiter,
            )

        assert items == []
        assert next_cursor is None

    @pytest.mark.asyncio
    async def test_fetch_audit_log_empty_response(self) -> None:
        """Empty JSON array response returns no items and no cursor."""
        from app.workers.github_sync_worker import _fetch_page

        mock_rate_limiter = MagicMock()
        mock_rate_limiter.acquire = AsyncMock()
        mock_rate_limiter.release = MagicMock()
        mock_rate_limiter.update_from_headers = MagicMock()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []
        mock_resp.headers = {}

        with patch(
            "app.workers.github_sync_worker._github_get",
            new=AsyncMock(return_value=mock_resp),
        ):
            items, next_cursor = await _fetch_page(
                entity_type="audit_log",
                org="my-enterprise",
                token="test-token",
                cursor=None,
                rate_limiter=mock_rate_limiter,
            )

        assert items == []
        assert next_cursor is None

    @pytest.mark.asyncio
    async def test_fetch_audit_log_no_enterprise_slug(self) -> None:
        """Missing enterprise slug (org=None) returns empty gracefully."""
        from app.workers.github_sync_worker import _fetch_page

        mock_rate_limiter = MagicMock()

        items, next_cursor = await _fetch_page(
            entity_type="audit_log",
            org=None,
            token="test-token",
            cursor=None,
            rate_limiter=mock_rate_limiter,
        )

        assert items == []
        assert next_cursor is None

    @pytest.mark.asyncio
    async def test_fetch_audit_log_with_cursor_uses_after(self) -> None:
        """Resuming with a cursor passes the 'after' parameter to the API."""
        from app.workers.github_sync_worker import _fetch_page

        mock_rate_limiter = MagicMock()
        mock_rate_limiter.acquire = AsyncMock()
        mock_rate_limiter.release = MagicMock()
        mock_rate_limiter.update_from_headers = MagicMock()

        cursor_json = json.dumps(
            {
                "after": "prev_doc_id",
                "timestamp": "2024-03-15T10:00:00+00:00",
            }
        )

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []
        mock_resp.headers = {}

        with patch(
            "app.workers.github_sync_worker._github_get",
            new=AsyncMock(return_value=mock_resp),
        ) as mock_get:
            await _fetch_page(
                entity_type="audit_log",
                org="my-enterprise",
                token="test-token",
                cursor=cursor_json,
                rate_limiter=mock_rate_limiter,
            )

        # Verify only 'after' is used — GitHub's audit log API returns 400
        # when both 'after' and 'phrase' are provided simultaneously.
        call_args = mock_get.call_args
        params = call_args.kwargs.get("params") or call_args[0][2]
        assert params.get("after") == "prev_doc_id"
        assert "phrase" not in params

    @pytest.mark.asyncio
    async def test_fetch_audit_log_delta_since_uses_timestamp(self) -> None:
        """Delta sync passes a created:>= phrase filter."""
        from app.workers.github_sync_worker import _fetch_page

        mock_rate_limiter = MagicMock()
        mock_rate_limiter.acquire = AsyncMock()
        mock_rate_limiter.release = MagicMock()
        mock_rate_limiter.update_from_headers = MagicMock()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []
        mock_resp.headers = {}

        delta = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

        with patch(
            "app.workers.github_sync_worker._github_get",
            new=AsyncMock(return_value=mock_resp),
        ) as mock_get:
            await _fetch_page(
                entity_type="audit_log",
                org="my-enterprise",
                token="test-token",
                cursor=None,
                rate_limiter=mock_rate_limiter,
                delta_since=delta,
            )

        call_args = mock_get.call_args
        params = call_args.kwargs.get("params") or call_args[0][2]
        assert params.get("phrase") == "created:>=2024-06-01T12:00:00Z"
        assert params.get("include") == "all"

    @pytest.mark.asyncio
    async def test_fetch_audit_log_first_sync_limits_lookback(self) -> None:
        """First sync (no cursor, no delta_since) limits lookback to 90 days."""
        from app.workers.github_sync_worker import _fetch_page

        mock_rate_limiter = MagicMock()
        mock_rate_limiter.acquire = AsyncMock()
        mock_rate_limiter.release = MagicMock()
        mock_rate_limiter.update_from_headers = MagicMock()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []
        mock_resp.headers = {}

        with patch(
            "app.workers.github_sync_worker._github_get",
            new=AsyncMock(return_value=mock_resp),
        ) as mock_get:
            await _fetch_page(
                entity_type="audit_log",
                org="my-enterprise",
                token="test-token",
                cursor=None,
                rate_limiter=mock_rate_limiter,
            )

        call_args = mock_get.call_args
        params = call_args.kwargs.get("params") or call_args[0][2]
        phrase = params.get("phrase", "")
        assert phrase.startswith("created:>=")

    @pytest.mark.asyncio
    async def test_fetch_audit_log_url_uses_enterprise_slug(self) -> None:
        """Verify the request URL contains the enterprise slug."""
        from app.workers.github_sync_worker import _fetch_page

        mock_rate_limiter = MagicMock()
        mock_rate_limiter.acquire = AsyncMock()
        mock_rate_limiter.release = MagicMock()
        mock_rate_limiter.update_from_headers = MagicMock()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []
        mock_resp.headers = {}

        with patch(
            "app.workers.github_sync_worker._github_get",
            new=AsyncMock(return_value=mock_resp),
        ) as mock_get:
            await _fetch_page(
                entity_type="audit_log",
                org="acme-corp",
                token="test-token",
                cursor=None,
                rate_limiter=mock_rate_limiter,
            )

        call_args = mock_get.call_args
        url = call_args.kwargs.get("url") or call_args[0][0]
        assert "/enterprises/acme-corp/audit-log" in url

    @pytest.mark.asyncio
    async def test_fetch_audit_log_include_all_param(self) -> None:
        """Verify include=all is passed to get web+git+api events."""
        from app.workers.github_sync_worker import _fetch_page

        mock_rate_limiter = MagicMock()
        mock_rate_limiter.acquire = AsyncMock()
        mock_rate_limiter.release = MagicMock()
        mock_rate_limiter.update_from_headers = MagicMock()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []
        mock_resp.headers = {}

        with patch(
            "app.workers.github_sync_worker._github_get",
            new=AsyncMock(return_value=mock_resp),
        ) as mock_get:
            await _fetch_page(
                entity_type="audit_log",
                org="my-enterprise",
                token="test-token",
                cursor=None,
                rate_limiter=mock_rate_limiter,
            )

        call_args = mock_get.call_args
        params = call_args.kwargs.get("params") or call_args[0][2]
        assert params["include"] == "all"
        assert params["per_page"] == 100

    @pytest.mark.asyncio
    async def test_fetch_audit_log_legacy_cursor_format(self) -> None:
        """A plain ISO timestamp cursor is treated as a phrase filter (legacy)."""
        from app.workers.github_sync_worker import _fetch_page

        mock_rate_limiter = MagicMock()
        mock_rate_limiter.acquire = AsyncMock()
        mock_rate_limiter.release = MagicMock()
        mock_rate_limiter.update_from_headers = MagicMock()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []
        mock_resp.headers = {}

        legacy_cursor = "2024-03-15T10:00:00+00:00"

        with patch(
            "app.workers.github_sync_worker._github_get",
            new=AsyncMock(return_value=mock_resp),
        ) as mock_get:
            await _fetch_page(
                entity_type="audit_log",
                org="my-enterprise",
                token="test-token",
                cursor=legacy_cursor,
                rate_limiter=mock_rate_limiter,
            )

        call_args = mock_get.call_args
        params = call_args.kwargs.get("params") or call_args[0][2]
        assert params.get("phrase") == f"created:>={legacy_cursor}"

    @pytest.mark.asyncio
    async def test_fetch_audit_log_iso_timestamp_in_events(self) -> None:
        """Events with ISO string timestamps produce valid cursor timestamps."""
        from app.workers.github_sync_worker import _fetch_page

        mock_rate_limiter = MagicMock()
        mock_rate_limiter.acquire = AsyncMock()
        mock_rate_limiter.release = MagicMock()
        mock_rate_limiter.update_from_headers = MagicMock()

        events = [
            {
                "action": "repo.create",
                "actor": "user",
                "created_at": "2024-07-01T08:30:00Z",
                "_document_id": "iso_doc_1",
            },
        ]

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = events
        # Link header to force cursor creation
        mock_resp.headers = {
            "link": '<https://api.github.com/enterprises/slug/audit-log?after=x>; rel="next"'
        }

        with patch(
            "app.workers.github_sync_worker._github_get",
            new=AsyncMock(return_value=mock_resp),
        ):
            items, next_cursor = await _fetch_page(
                entity_type="audit_log",
                org="my-enterprise",
                token="test-token",
                cursor=None,
                rate_limiter=mock_rate_limiter,
            )

        assert len(items) == 1
        assert next_cursor is not None
        cursor_data = json.loads(next_cursor)
        assert cursor_data["timestamp"] == "2024-07-01T08:30:00Z"


# ─── Upsert Dispatch Tests ──────────────────────────────────────────────────


class TestUpsertItemsDispatchAuditLog:
    """Tests that _upsert_items dispatches to _upsert_audit_log_events."""

    @pytest.mark.asyncio
    async def test_upsert_items_dispatches_audit_log(self) -> None:
        """Verify _upsert_items calls _upsert_audit_log_events for audit_log."""
        from app.workers.github_sync_worker import _upsert_items

        with patch(
            "app.workers.github_sync_worker._upsert_audit_log_events",
            new=AsyncMock(),
        ) as mock_handler:
            mock_session = AsyncMock()
            items: list[dict[str, object]] = [
                {"action": "repo.create", "actor": "user", "@timestamp": 1700000000000}
            ]
            await _upsert_items(mock_session, "audit_log", "my-enterprise", items)

        mock_handler.assert_called_once_with(mock_session, "my-enterprise", items)


# ─── Upsert Audit Log Events Tests ──────────────────────────────────────────


class TestUpsertAuditLogEvents:
    """Tests for _upsert_audit_log_events normalization and dedup logic."""

    @pytest.mark.asyncio
    async def test_inserts_event_with_correct_fields(self) -> None:
        """Verify a raw event is normalized and INSERT SQL is executed."""
        from app.workers.github_sync_worker import _upsert_audit_log_events

        mock_session = AsyncMock()

        # Simulate no existing dedup record
        mock_dedup_result = MagicMock()
        mock_dedup_result.fetchone.return_value = None

        # Simulate successful insert returning an event ID
        mock_insert_result = MagicMock()
        mock_insert_result.fetchone.return_value = (42,)

        # Route calls: first call = dedup check, second = insert, third = dedup insert
        mock_session.execute.side_effect = [
            mock_dedup_result,
            mock_insert_result,
            MagicMock(),  # dedup insert result
        ]

        events = [
            {
                "action": "repo.create",
                "actor": "octocat",
                "actor_id": 583231,
                "org": "my-org",
                "repo": "my-org/hello-world",
                "@ip": "192.168.1.100",
                "@timestamp": 1700000000000,
                "_document_id": "gh_doc_123",
                "user_agent": "GitHub-Desktop/3.0",
            },
        ]

        await _upsert_audit_log_events(mock_session, "acme-corp", events)

        # Should have called execute 3 times: dedup check, insert, dedup insert
        assert mock_session.execute.call_count == 3
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_duplicate_events(self) -> None:
        """Events with existing dedup records are skipped."""
        from app.workers.github_sync_worker import _upsert_audit_log_events

        mock_session = AsyncMock()

        # Simulate existing dedup record
        mock_dedup_result = MagicMock()
        mock_dedup_result.fetchone.return_value = (1,)  # exists

        mock_session.execute.return_value = mock_dedup_result

        events = [
            {
                "action": "repo.create",
                "actor": "octocat",
                "@timestamp": 1700000000000,
                "_document_id": "already_exists",
            },
        ]

        await _upsert_audit_log_events(mock_session, "acme-corp", events)

        # Only one execute call (the dedup check), no insert
        assert mock_session.execute.call_count == 1
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_events_without_action(self) -> None:
        """Events missing the 'action' field are skipped."""
        from app.workers.github_sync_worker import _upsert_audit_log_events

        mock_session = AsyncMock()

        events = [
            {
                "actor": "octocat",
                "@timestamp": 1700000000000,
                "_document_id": "no_action",
            },
        ]

        await _upsert_audit_log_events(mock_session, "acme-corp", events)

        # No execute calls since event was skipped before dedup check
        mock_session.execute.assert_not_called()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_event_list(self) -> None:
        """Empty event list returns immediately without DB operations."""
        from app.workers.github_sync_worker import _upsert_audit_log_events

        mock_session = AsyncMock()

        await _upsert_audit_log_events(mock_session, "acme-corp", [])

        mock_session.execute.assert_not_called()
        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_uses_document_id_from_github(self) -> None:
        """When _document_id is present in the event, it's used as the dedup key."""
        from app.workers.github_sync_worker import _upsert_audit_log_events

        mock_session = AsyncMock()

        mock_dedup_result = MagicMock()
        mock_dedup_result.fetchone.return_value = None

        mock_insert_result = MagicMock()
        mock_insert_result.fetchone.return_value = (1,)

        mock_session.execute.side_effect = [
            mock_dedup_result,
            mock_insert_result,
            MagicMock(),
        ]

        events = [
            {
                "action": "repo.create",
                "actor": "user",
                "@timestamp": 1700000000000,
                "_document_id": "github_provided_id",
            },
        ]

        await _upsert_audit_log_events(mock_session, "acme-corp", events)

        # First call should be dedup check with github_provided_id
        first_call = mock_session.execute.call_args_list[0]
        dedup_params = first_call[0][1] if len(first_call[0]) > 1 else first_call[1]
        assert dedup_params["doc_id"] == "github_provided_id"

    @pytest.mark.asyncio
    async def test_computes_hash_when_no_document_id(self) -> None:
        """When _document_id is absent, a SHA-256 hash is computed."""
        from app.workers.github_sync_worker import _upsert_audit_log_events

        mock_session = AsyncMock()

        mock_dedup_result = MagicMock()
        mock_dedup_result.fetchone.return_value = None

        mock_insert_result = MagicMock()
        mock_insert_result.fetchone.return_value = (1,)

        mock_session.execute.side_effect = [
            mock_dedup_result,
            mock_insert_result,
            MagicMock(),
        ]

        events = [
            {
                "action": "repo.delete",
                "actor": "admin",
                "org": "test-org",
                "repo": "test-org/repo1",
                "created_at": "2024-01-01T00:00:00Z",
                "@ip": "10.0.0.1",
                # No _document_id
            },
        ]

        await _upsert_audit_log_events(mock_session, "acme-corp", events)

        # Dedup check should use a 64-char hex hash
        first_call = mock_session.execute.call_args_list[0]
        dedup_params = first_call[0][1] if len(first_call[0]) > 1 else first_call[1]
        doc_id = dedup_params["doc_id"]
        assert len(doc_id) == 64
        assert all(c in "0123456789abcdef" for c in doc_id)

    @pytest.mark.asyncio
    async def test_handles_millisecond_epoch_timestamp(self) -> None:
        """Millisecond epoch timestamps are correctly parsed."""
        from app.workers.github_sync_worker import _upsert_audit_log_events

        mock_session = AsyncMock()

        mock_dedup_result = MagicMock()
        mock_dedup_result.fetchone.return_value = None

        mock_insert_result = MagicMock()
        mock_insert_result.fetchone.return_value = (1,)

        mock_session.execute.side_effect = [
            mock_dedup_result,
            mock_insert_result,
            MagicMock(),
        ]

        # 2023-11-14T22:13:20Z in milliseconds
        epoch_ms = 1700000000000

        events = [
            {
                "action": "repo.create",
                "actor": "user",
                "@timestamp": epoch_ms,
                "_document_id": "ts_test",
            },
        ]

        await _upsert_audit_log_events(mock_session, "acme-corp", events)

        # Check the INSERT call parameters for correct timestamp
        insert_call = mock_session.execute.call_args_list[1]
        insert_params = insert_call[0][1] if len(insert_call[0]) > 1 else insert_call[1]
        created_at = insert_params["created_at"]
        assert created_at.year == 2023
        assert created_at.tzinfo is not None

    @pytest.mark.asyncio
    async def test_handles_iso_string_timestamp(self) -> None:
        """ISO string timestamps (with Z suffix) are correctly parsed."""
        from app.workers.github_sync_worker import _upsert_audit_log_events

        mock_session = AsyncMock()

        mock_dedup_result = MagicMock()
        mock_dedup_result.fetchone.return_value = None

        mock_insert_result = MagicMock()
        mock_insert_result.fetchone.return_value = (1,)

        mock_session.execute.side_effect = [
            mock_dedup_result,
            mock_insert_result,
            MagicMock(),
        ]

        events = [
            {
                "action": "repo.create",
                "actor": "user",
                "created_at": "2024-07-01T08:30:00Z",
                "_document_id": "iso_test",
            },
        ]

        await _upsert_audit_log_events(mock_session, "acme-corp", events)

        insert_call = mock_session.execute.call_args_list[1]
        insert_params = insert_call[0][1] if len(insert_call[0]) > 1 else insert_call[1]
        created_at = insert_params["created_at"]
        assert created_at.year == 2024
        assert created_at.month == 7
        assert created_at.day == 1

    @pytest.mark.asyncio
    async def test_strips_at_prefixed_fields_from_data(self) -> None:
        """Fields starting with @ are stripped from the data blob."""
        from app.workers.github_sync_worker import _upsert_audit_log_events

        mock_session = AsyncMock()

        mock_dedup_result = MagicMock()
        mock_dedup_result.fetchone.return_value = None

        mock_insert_result = MagicMock()
        mock_insert_result.fetchone.return_value = (1,)

        mock_session.execute.side_effect = [
            mock_dedup_result,
            mock_insert_result,
            MagicMock(),
        ]

        events = [
            {
                "action": "repo.create",
                "actor": "user",
                "@timestamp": 1700000000000,
                "@ip": "1.2.3.4",
                "_document_id": "strip_test",
                "custom_field": "kept",
            },
        ]

        await _upsert_audit_log_events(mock_session, "acme-corp", events)

        insert_call = mock_session.execute.call_args_list[1]
        insert_params = insert_call[0][1] if len(insert_call[0]) > 1 else insert_call[1]
        data_json = json.loads(insert_params["data"])
        assert "@timestamp" not in data_json
        assert "@ip" not in data_json
        assert data_json["custom_field"] == "kept"
        assert data_json["action"] == "repo.create"

    @pytest.mark.asyncio
    async def test_ingestion_source_is_github_enterprise_sync(self) -> None:
        """Ingestion source is set to 'github_enterprise_sync'."""
        from app.workers.github_sync_worker import _upsert_audit_log_events

        mock_session = AsyncMock()

        mock_dedup_result = MagicMock()
        mock_dedup_result.fetchone.return_value = None

        mock_insert_result = MagicMock()
        mock_insert_result.fetchone.return_value = (1,)

        mock_session.execute.side_effect = [
            mock_dedup_result,
            mock_insert_result,
            MagicMock(),
        ]

        events = [
            {
                "action": "repo.create",
                "actor": "user",
                "@timestamp": 1700000000000,
                "_document_id": "source_test",
            },
        ]

        await _upsert_audit_log_events(mock_session, "acme-corp", events)

        insert_call = mock_session.execute.call_args_list[1]
        insert_params = insert_call[0][1] if len(insert_call[0]) > 1 else insert_call[1]
        assert insert_params["ingestion_source"] == "github_enterprise_sync"
        assert "acme-corp" in insert_params["source_file_path"]

    @pytest.mark.asyncio
    async def test_handles_insert_conflict_gracefully(self) -> None:
        """When INSERT returns no row (ON CONFLICT DO NOTHING), skip dedup insert."""
        from app.workers.github_sync_worker import _upsert_audit_log_events

        mock_session = AsyncMock()

        mock_dedup_result = MagicMock()
        mock_dedup_result.fetchone.return_value = None

        # Insert returns None (conflict — already exists via document_id)
        mock_insert_result = MagicMock()
        mock_insert_result.fetchone.return_value = None

        mock_session.execute.side_effect = [
            mock_dedup_result,
            mock_insert_result,
        ]

        events = [
            {
                "action": "repo.create",
                "actor": "user",
                "@timestamp": 1700000000000,
                "_document_id": "conflict_test",
            },
        ]

        await _upsert_audit_log_events(mock_session, "acme-corp", events)

        # Only 2 execute calls (dedup check + insert), no dedup insert
        assert mock_session.execute.call_count == 2
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_multiple_events_mixed_dedup(self) -> None:
        """Batch with mix of new and duplicate events processes correctly."""
        from app.workers.github_sync_worker import _upsert_audit_log_events

        mock_session = AsyncMock()

        # First event: not a duplicate, second event: duplicate
        mock_dedup_exists = MagicMock()
        mock_dedup_exists.fetchone.return_value = (1,)

        mock_dedup_new = MagicMock()
        mock_dedup_new.fetchone.return_value = None

        mock_insert_result = MagicMock()
        mock_insert_result.fetchone.return_value = (99,)

        mock_session.execute.side_effect = [
            mock_dedup_new,  # event 1 dedup check (new)
            mock_insert_result,  # event 1 insert
            MagicMock(),  # event 1 dedup insert
            mock_dedup_exists,  # event 2 dedup check (exists)
        ]

        events = [
            {
                "action": "repo.create",
                "actor": "user1",
                "@timestamp": 1700000000000,
                "_document_id": "new_event",
            },
            {
                "action": "repo.delete",
                "actor": "user2",
                "@timestamp": 1700000001000,
                "_document_id": "old_event",
            },
        ]

        await _upsert_audit_log_events(mock_session, "acme-corp", events)

        # 4 execute calls total
        assert mock_session.execute.call_count == 4

    @pytest.mark.asyncio
    async def test_secrets_stripped_from_workflow_events(self) -> None:
        """workflows.prepared_workflow_job events have secrets_passed scrubbed."""
        from app.workers.github_sync_worker import _upsert_audit_log_events

        mock_session = AsyncMock()

        mock_dedup_result = MagicMock()
        mock_dedup_result.fetchone.return_value = None

        mock_insert_result = MagicMock()
        mock_insert_result.fetchone.return_value = (1,)

        mock_session.execute.side_effect = [
            mock_dedup_result,
            mock_insert_result,
            MagicMock(),
        ]

        events = [
            {
                "action": "workflows.prepared_workflow_job",
                "actor": "ci-bot",
                "@timestamp": 1700000000000,
                "_document_id": "wf_test",
                "secrets_passed": ["SECRET_1", "SECRET_2", "SECRET_3"],
            },
        ]

        await _upsert_audit_log_events(mock_session, "acme-corp", events)

        insert_call = mock_session.execute.call_args_list[1]
        insert_params = insert_call[0][1] if len(insert_call[0]) > 1 else insert_call[1]
        data_json = json.loads(insert_params["data"])
        assert "secrets_passed" not in data_json
        assert data_json["secrets_passed_count"] == 3

    @pytest.mark.asyncio
    async def test_null_enterprise_slug_in_source_path(self) -> None:
        """When enterprise_slug is None, source_file_path uses 'unknown'."""
        from app.workers.github_sync_worker import _upsert_audit_log_events

        mock_session = AsyncMock()

        mock_dedup_result = MagicMock()
        mock_dedup_result.fetchone.return_value = None

        mock_insert_result = MagicMock()
        mock_insert_result.fetchone.return_value = (1,)

        mock_session.execute.side_effect = [
            mock_dedup_result,
            mock_insert_result,
            MagicMock(),
        ]

        events = [
            {
                "action": "repo.create",
                "actor": "user",
                "@timestamp": 1700000000000,
                "_document_id": "null_slug_test",
            },
        ]

        await _upsert_audit_log_events(mock_session, None, events)

        insert_call = mock_session.execute.call_args_list[1]
        insert_params = insert_call[0][1] if len(insert_call[0]) > 1 else insert_call[1]
        assert insert_params["source_file_path"] == "enterprise/unknown/audit-log"

    @pytest.mark.asyncio
    async def test_geoip_enrichment_failure_doesnt_block(self) -> None:
        """GeoIP lookup failure doesn't prevent event insertion."""
        from app.workers.github_sync_worker import _upsert_audit_log_events

        mock_session = AsyncMock()

        mock_dedup_result = MagicMock()
        mock_dedup_result.fetchone.return_value = None

        mock_insert_result = MagicMock()
        mock_insert_result.fetchone.return_value = (1,)

        mock_session.execute.side_effect = [
            mock_dedup_result,
            mock_insert_result,
            MagicMock(),
        ]

        events = [
            {
                "action": "repo.create",
                "actor": "user",
                "@timestamp": 1700000000000,
                "@ip": "invalid-ip-that-causes-lookup-failure",
                "_document_id": "geoip_fail_test",
            },
        ]

        with patch(
            "app.services.geoip_service.get_geoip_location",
            side_effect=Exception("GeoIP DB not found"),
        ):
            await _upsert_audit_log_events(mock_session, "acme-corp", events)

        # Should still insert despite GeoIP failure
        assert mock_session.execute.call_count == 3
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_missing_timestamp_gracefully(self) -> None:
        """Events without any timestamp field use current time."""
        from app.workers.github_sync_worker import _upsert_audit_log_events

        mock_session = AsyncMock()

        mock_dedup_result = MagicMock()
        mock_dedup_result.fetchone.return_value = None

        mock_insert_result = MagicMock()
        mock_insert_result.fetchone.return_value = (1,)

        mock_session.execute.side_effect = [
            mock_dedup_result,
            mock_insert_result,
            MagicMock(),
        ]

        events = [
            {
                "action": "repo.create",
                "actor": "user",
                "_document_id": "no_ts_test",
                # No @timestamp or created_at
            },
        ]

        await _upsert_audit_log_events(mock_session, "acme-corp", events)

        insert_call = mock_session.execute.call_args_list[1]
        insert_params = insert_call[0][1] if len(insert_call[0]) > 1 else insert_call[1]
        created_at = insert_params["created_at"]
        # Should be a recent datetime
        assert isinstance(created_at, datetime)
        assert created_at.tzinfo is not None
