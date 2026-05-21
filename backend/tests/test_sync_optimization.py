"""Tests for GitHub sync optimization: ETag cache, If-Modified-Since, API metrics."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.github_etag_cache import (
    ETAG_CACHE_TTL_SECONDS,
    SLOW_CHANGE_ENTITY_TYPES,
    SLOW_CHANGE_TTL_SECONDS,
    GitHubETagCache,
)
from app.services.sync_api_metrics import SyncAPICallCounter

# ─── GitHubETagCache tests ────────────────────────────────────────────────────


class TestGitHubETagCacheTTL:
    """Test TTL logic for slowly-changing vs normal entity types."""

    def test_default_ttl_for_normal_entities(self) -> None:
        cache = GitHubETagCache(valkey_client=None)
        assert cache.ttl_for_entity("repositories") == ETAG_CACHE_TTL_SECONDS
        assert cache.ttl_for_entity("branch_protections") == ETAG_CACHE_TTL_SECONDS
        assert cache.ttl_for_entity("secret_scanning_alerts") == ETAG_CACHE_TTL_SECONDS

    def test_slow_change_ttl_for_eligible_entities(self) -> None:
        cache = GitHubETagCache(valkey_client=None)
        for entity in SLOW_CHANGE_ENTITY_TYPES:
            assert cache.ttl_for_entity(entity) == SLOW_CHANGE_TTL_SECONDS

    def test_none_entity_type_uses_default_ttl(self) -> None:
        cache = GitHubETagCache(valkey_client=None)
        assert cache.ttl_for_entity(None) == ETAG_CACHE_TTL_SECONDS


class TestGitHubETagCacheGetEtag:
    """Test get_etag method."""

    @pytest.mark.asyncio
    async def test_returns_none_when_no_client(self) -> None:
        cache = GitHubETagCache(valkey_client=None)
        result = await cache.get_etag("https://api.github.com/test")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_cached_etag(self) -> None:
        mock_valkey = AsyncMock()
        mock_valkey.get = AsyncMock(return_value='W/"abc123"')
        cache = GitHubETagCache(valkey_client=mock_valkey)
        result = await cache.get_etag("https://api.github.com/test")
        assert result == 'W/"abc123"'
        mock_valkey.get.assert_called_once_with("etag:https://api.github.com/test")

    @pytest.mark.asyncio
    async def test_returns_none_on_error(self) -> None:
        mock_valkey = AsyncMock()
        mock_valkey.get = AsyncMock(side_effect=Exception("connection lost"))
        cache = GitHubETagCache(valkey_client=mock_valkey)
        result = await cache.get_etag("https://api.github.com/test")
        assert result is None


class TestGitHubETagCacheLastModified:
    """Test Last-Modified caching."""

    @pytest.mark.asyncio
    async def test_get_last_modified_returns_none_when_no_client(self) -> None:
        cache = GitHubETagCache(valkey_client=None)
        result = await cache.get_last_modified("https://api.github.com/test")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_last_modified_returns_cached_value(self) -> None:
        mock_valkey = AsyncMock()
        mock_valkey.get = AsyncMock(return_value="Tue, 01 Jan 2025 00:00:00 GMT")
        cache = GitHubETagCache(valkey_client=mock_valkey)
        result = await cache.get_last_modified("https://api.github.com/test")
        assert result == "Tue, 01 Jan 2025 00:00:00 GMT"
        mock_valkey.get.assert_called_once_with("last_modified:https://api.github.com/test")

    @pytest.mark.asyncio
    async def test_store_last_modified(self) -> None:
        mock_pipe = AsyncMock()
        mock_pipe.set = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=[True, True])

        mock_valkey = AsyncMock()
        mock_valkey.pipeline = MagicMock(return_value=mock_pipe)
        # Make pipeline a context manager
        mock_pipe.__aenter__ = AsyncMock(return_value=mock_pipe)
        mock_pipe.__aexit__ = AsyncMock(return_value=False)

        cache = GitHubETagCache(valkey_client=mock_valkey)
        body = [{"id": 1, "name": "test"}]
        await cache.store_last_modified(
            "https://api.github.com/test",
            "Tue, 01 Jan 2025 00:00:00 GMT",
            body,
            entity_type="repositories",
        )
        # Verify pipeline was used (set calls were made)
        assert mock_pipe.set.call_count == 2

    @pytest.mark.asyncio
    async def test_store_last_modified_noop_when_no_client(self) -> None:
        cache = GitHubETagCache(valkey_client=None)
        # Should not raise
        await cache.store_last_modified(
            "https://api.github.com/test",
            "Tue, 01 Jan 2025 00:00:00 GMT",
            [{"data": "test"}],
        )


class TestGitHubETagCacheStore:
    """Test store method with entity_type-aware TTL."""

    @pytest.mark.asyncio
    async def test_store_uses_slow_ttl_for_eligible_entities(self) -> None:
        mock_pipe = AsyncMock()
        mock_pipe.set = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=[True, True])

        mock_valkey = AsyncMock()
        mock_valkey.pipeline = MagicMock(return_value=mock_pipe)
        mock_pipe.__aenter__ = AsyncMock(return_value=mock_pipe)
        mock_pipe.__aexit__ = AsyncMock(return_value=False)

        cache = GitHubETagCache(valkey_client=mock_valkey)
        await cache.store(
            "https://api.github.com/orgs/test/teams",
            'W/"etag1"',
            [{"slug": "team-a"}],
            entity_type="teams",
        )
        # Verify slow TTL was used
        calls = mock_pipe.set.call_args_list
        for call in calls:
            assert (
                call.kwargs.get("ex") == SLOW_CHANGE_TTL_SECONDS
                or call[1].get("ex") == SLOW_CHANGE_TTL_SECONDS
            )

    @pytest.mark.asyncio
    async def test_store_uses_default_ttl_for_normal_entities(self) -> None:
        mock_pipe = AsyncMock()
        mock_pipe.set = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=[True, True])

        mock_valkey = AsyncMock()
        mock_valkey.pipeline = MagicMock(return_value=mock_pipe)
        mock_pipe.__aenter__ = AsyncMock(return_value=mock_pipe)
        mock_pipe.__aexit__ = AsyncMock(return_value=False)

        cache = GitHubETagCache(valkey_client=mock_valkey)
        await cache.store(
            "https://api.github.com/orgs/test/repos",
            'W/"etag2"',
            [{"name": "repo-a"}],
            entity_type="repositories",
        )
        calls = mock_pipe.set.call_args_list
        for call in calls:
            assert (
                call.kwargs.get("ex") == ETAG_CACHE_TTL_SECONDS
                or call[1].get("ex") == ETAG_CACHE_TTL_SECONDS
            )


class TestGitHubETagCacheHandle304:
    """Test 304 handling."""

    @pytest.mark.asyncio
    async def test_handle_304_returns_cached_body(self) -> None:
        body = [{"id": 1}]
        mock_pipe = AsyncMock()
        mock_pipe.expire = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=[True, True, True])

        mock_valkey = AsyncMock()
        mock_valkey.get = AsyncMock(return_value=json.dumps(body))
        mock_valkey.pipeline = MagicMock(return_value=mock_pipe)
        mock_pipe.__aenter__ = AsyncMock(return_value=mock_pipe)
        mock_pipe.__aexit__ = AsyncMock(return_value=False)

        cache = GitHubETagCache(valkey_client=mock_valkey)
        result = await cache.handle_304("https://api.github.com/test", 'W/"abc"')
        assert result is not None
        assert result.body == body
        assert result.etag == 'W/"abc"'

    @pytest.mark.asyncio
    async def test_handle_304_returns_none_when_body_missing(self) -> None:
        mock_valkey = AsyncMock()
        mock_valkey.get = AsyncMock(return_value=None)
        cache = GitHubETagCache(valkey_client=mock_valkey)
        result = await cache.handle_304("https://api.github.com/test", 'W/"abc"')
        assert result is None


# ─── SyncAPICallCounter tests ─────────────────────────────────────────────────


class TestSyncAPICallCounter:
    """Test API call counting and metrics."""

    def test_initial_state(self) -> None:
        counter = SyncAPICallCounter(run_id="test-run-id", entity_type="repositories")
        assert counter.total_calls == 0
        assert counter.cache_hits == 0

    def test_record_api_call(self) -> None:
        counter = SyncAPICallCounter(run_id="test-run-id", entity_type="repositories")
        counter.record_api_call(cache_hit=False)
        counter.record_api_call(cache_hit=False)
        counter.record_api_call(cache_hit=True)
        assert counter.total_calls == 3
        assert counter.cache_hits == 1

    def test_record_page(self) -> None:
        counter = SyncAPICallCounter(run_id="test-run-id", entity_type="teams")
        counter.record_page(50)
        counter.record_page(30)
        summary = counter.summary()
        assert summary["pages_fetched"] == 2
        assert summary["items_received"] == 80

    def test_summary_format(self) -> None:
        counter = SyncAPICallCounter(run_id="run-123", entity_type="org_members")
        counter.record_api_call(cache_hit=False)
        counter.record_api_call(cache_hit=False)
        counter.record_api_call(cache_hit=True)
        counter.record_page(100)
        counter.record_page(50)

        summary = counter.summary()
        assert summary["run_id"] == "run-123"
        assert summary["entity_type"] == "org_members"
        assert summary["total_api_calls"] == 3
        assert summary["cache_hits_304"] == 1
        assert summary["actual_fetches"] == 2
        assert summary["pages_fetched"] == 2
        assert summary["items_received"] == 150
        assert summary["cache_hit_rate_pct"] == pytest.approx(33.3, abs=0.1)

    def test_summary_zero_calls(self) -> None:
        counter = SyncAPICallCounter(run_id="run-456", entity_type="teams")
        summary = counter.summary()
        assert summary["total_api_calls"] == 0
        assert summary["cache_hit_rate_pct"] == 0.0

    def test_log_summary_does_not_raise(self) -> None:
        counter = SyncAPICallCounter(run_id="run-789", entity_type="repositories")
        counter.record_api_call(cache_hit=False)
        # Should not raise
        counter.log_summary()


# ─── Integration: _github_get with If-Modified-Since ──────────────────────────


class TestGithubGetConditionalHeaders:
    """Test that _github_get integrates conditional headers correctly."""

    @pytest.mark.asyncio
    async def test_github_get_sends_if_modified_since_when_no_etag(self) -> None:
        """When no ETag is cached but Last-Modified is, use If-Modified-Since."""
        from unittest.mock import patch as _patch

        import httpx

        from app.services.github_etag_cache import GitHubETagCache
        from app.services.sync_api_metrics import SyncAPICallCounter

        # Mock the ETag cache to return no ETag but a Last-Modified value
        mock_valkey = AsyncMock()
        mock_valkey.get = AsyncMock(
            side_effect=lambda key: (
                None
                if key.startswith("etag:")
                else ("Tue, 01 Jul 2025 00:00:00 GMT" if key.startswith("last_modified:") else None)
            )
        )
        mock_pipe = AsyncMock()
        mock_pipe.set = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=[True, True])
        mock_valkey.pipeline = MagicMock(return_value=mock_pipe)
        mock_pipe.__aenter__ = AsyncMock(return_value=mock_pipe)
        mock_pipe.__aexit__ = AsyncMock(return_value=False)

        etag_cache = GitHubETagCache(valkey_client=mock_valkey)
        api_counter = SyncAPICallCounter(run_id="test", entity_type="org_members")

        # Mock the rate limiter
        mock_rate_limiter = MagicMock()
        mock_rate_limiter.acquire = AsyncMock()
        mock_rate_limiter.release = MagicMock()
        mock_rate_limiter.update_from_headers = MagicMock()

        # Mock httpx to capture the request headers
        captured_headers: dict[str, str] = {}

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.headers = {"last-modified": "Wed, 02 Jul 2025 00:00:00 GMT"}
        mock_response.json = MagicMock(return_value=[{"login": "user1"}])
        mock_response.request = MagicMock()

        async def mock_get(*args: object, **kwargs: object) -> MagicMock:
            headers_arg = kwargs.get("headers", {})
            if isinstance(headers_arg, dict):
                captured_headers.update(headers_arg)
            return mock_response

        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        from app.workers.github_sync_worker import _github_get

        with _patch("app.workers.github_sync_worker.httpx.AsyncClient", return_value=mock_client):
            await _github_get(
                "https://api.github.com/orgs/test/members",
                {"Authorization": "token test123", "Accept": "application/vnd.github+json"},
                {"per_page": 100, "page": 1},
                mock_rate_limiter,
                etag_cache=etag_cache,
                api_counter=api_counter,
                entity_type="org_members",
            )

        assert "If-Modified-Since" in captured_headers
        assert captured_headers["If-Modified-Since"] == "Tue, 01 Jul 2025 00:00:00 GMT"
        assert api_counter.total_calls == 1
        assert api_counter.cache_hits == 0
