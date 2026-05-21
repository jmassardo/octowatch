"""ETag-based conditional request cache for GitHub API calls.

Stores ETag values and response bodies in Valkey so that subsequent requests
to the same URL can send ``If-None-Match`` and short-circuit on ``304 Not
Modified``. This reduces rate-limit consumption — GitHub does not count 304
responses against the primary rate limit.

Also supports ``Last-Modified`` / ``If-Modified-Since`` conditional headers
for endpoints that provide them.

Usage
-----
Pass a :class:`GitHubETagCache` instance into the request layer.  The cache
is a pure performance optimisation: if Valkey is unavailable or a key is
missing, the caller falls through to a normal (unconditional) request.

Cache keys::

    etag:{url}           → ETag header value (string)
    etag_body:{url}      → JSON-serialised response body (string)
    last_modified:{url}  → Last-Modified header value (string)

Both keys share the same TTL (default 24 h).  Slowly-changing entity types
(org metadata, team membership) use a longer TTL (7 days).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

#: Default TTL for cached ETags and response bodies (seconds).
ETAG_CACHE_TTL_SECONDS: int = 86_400  # 24 hours

#: Extended TTL for slowly-changing data (org settings, teams).
SLOW_CHANGE_TTL_SECONDS: int = 604_800  # 7 days

#: Entity types whose responses change infrequently and benefit from longer caching.
SLOW_CHANGE_ENTITY_TYPES: frozenset[str] = frozenset(
    {
        "orgs",
        "teams",
        "team_members",
        "installations",
        "org_members",
    }
)


def _etag_key(url: str) -> str:
    """Return the Valkey key for the ETag value."""
    return f"etag:{url}"


def _body_key(url: str) -> str:
    """Return the Valkey key for the cached response body."""
    return f"etag_body:{url}"


def _last_modified_key(url: str) -> str:
    """Return the Valkey key for the Last-Modified header value."""
    return f"last_modified:{url}"


@dataclass(frozen=True, slots=True)
class CachedResponse:
    """Lightweight container returned on a 304 cache hit."""

    body: Any
    etag: str


class GitHubETagCache:
    """Thin wrapper around a Valkey (redis-compatible) async client for ETag caching.

    Parameters
    ----------
    valkey_client:
        An ``redis.asyncio.Redis`` instance.  May be ``None`` — in that case
        every method is a no-op (cache disabled).
    ttl:
        Time-to-live in seconds for both ETag and body keys.
    """

    def __init__(
        self,
        valkey_client: Any | None,
        ttl: int = ETAG_CACHE_TTL_SECONDS,
    ) -> None:
        self._valkey = valkey_client
        self._ttl = ttl

    # ── Public API ────────────────────────────────────────────────────────

    def ttl_for_entity(self, entity_type: str | None) -> int:
        """Return the appropriate TTL based on entity type.

        Slowly-changing entity types get a longer TTL to reduce unnecessary
        API calls on subsequent syncs.
        """
        if entity_type and entity_type in SLOW_CHANGE_ENTITY_TYPES:
            return SLOW_CHANGE_TTL_SECONDS
        return self._ttl

    async def get_etag(self, url: str) -> str | None:
        """Return the cached ETag for *url*, or ``None`` on miss / error."""
        if self._valkey is None:
            return None
        try:
            result: str | None = await self._valkey.get(_etag_key(url))
            return result
        except Exception as exc:
            logger.debug("etag_cache.get_etag_error", url=url, error=str(exc))
            return None

    async def get_last_modified(self, url: str) -> str | None:
        """Return the cached Last-Modified value for *url*, or ``None``."""
        if self._valkey is None:
            return None
        try:
            result: str | None = await self._valkey.get(_last_modified_key(url))
            return result
        except Exception as exc:
            logger.debug("etag_cache.get_last_modified_error", url=url, error=str(exc))
            return None

    async def get_cached_body(self, url: str) -> Any | None:
        """Return the cached response body for *url*, or ``None``."""
        if self._valkey is None:
            return None
        try:
            raw = await self._valkey.get(_body_key(url))
            if raw is None:
                return None
            return json.loads(raw)
        except Exception as exc:
            logger.debug("etag_cache.get_body_error", url=url, error=str(exc))
            return None

    async def store(
        self, url: str, etag: str, body: Any, *, entity_type: str | None = None
    ) -> None:
        """Persist the ETag and response body for *url*.

        Both keys are set with the configured TTL (or the slow-change TTL
        for eligible entity types).  Errors are swallowed (cache is best-effort).
        """
        if self._valkey is None:
            return
        ttl = self.ttl_for_entity(entity_type)
        try:
            serialised = json.dumps(body)
            async with self._valkey.pipeline(transaction=False) as pipe:
                pipe.set(_etag_key(url), etag, ex=ttl)
                pipe.set(_body_key(url), serialised, ex=ttl)
                await pipe.execute()
        except Exception as exc:
            logger.debug("etag_cache.store_error", url=url, error=str(exc))

    async def store_last_modified(
        self, url: str, last_modified: str, body: Any, *, entity_type: str | None = None
    ) -> None:
        """Persist the Last-Modified header and response body for *url*.

        Used for endpoints that provide Last-Modified but not ETag.
        """
        if self._valkey is None:
            return
        ttl = self.ttl_for_entity(entity_type)
        try:
            serialised = json.dumps(body)
            async with self._valkey.pipeline(transaction=False) as pipe:
                pipe.set(_last_modified_key(url), last_modified, ex=ttl)
                pipe.set(_body_key(url), serialised, ex=ttl)
                await pipe.execute()
        except Exception as exc:
            logger.debug("etag_cache.store_last_modified_error", url=url, error=str(exc))

    async def handle_304(self, url: str, etag: str) -> CachedResponse | None:
        """Handle a 304 response: return cached body or ``None`` if unavailable.

        On success the TTL is refreshed so that actively-used entries stay warm.
        """
        body = await self.get_cached_body(url)
        if body is None:
            logger.debug("etag_cache.304_but_no_body", url=url)
            return None
        # Refresh TTL on hit
        try:
            if self._valkey is not None:
                async with self._valkey.pipeline(transaction=False) as pipe:
                    pipe.expire(_etag_key(url), self._ttl)
                    pipe.expire(_body_key(url), self._ttl)
                    pipe.expire(_last_modified_key(url), self._ttl)
                    await pipe.execute()
        except Exception:  # noqa: S110 — best-effort TTL refresh
            pass
        logger.debug("etag_cache.hit", url=url)
        return CachedResponse(body=body, etag=etag)
