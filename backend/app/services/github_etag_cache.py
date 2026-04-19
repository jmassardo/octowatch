"""ETag-based conditional request cache for GitHub API calls.

Stores ETag values and response bodies in Valkey so that subsequent requests
to the same URL can send ``If-None-Match`` and short-circuit on ``304 Not
Modified``. This reduces rate-limit consumption — GitHub does not count 304
responses against the primary rate limit.

Usage
-----
Pass a :class:`GitHubETagCache` instance into the request layer.  The cache
is a pure performance optimisation: if Valkey is unavailable or a key is
missing, the caller falls through to a normal (unconditional) request.

Cache keys::

    etag:{url}       → ETag header value (string)
    etag_body:{url}  → JSON-serialised response body (string)

Both keys share the same TTL (default 24 h).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

#: Default TTL for cached ETags and response bodies (seconds).
ETAG_CACHE_TTL_SECONDS: int = 86_400  # 24 hours


def _etag_key(url: str) -> str:
    """Return the Valkey key for the ETag value."""
    return f"etag:{url}"


def _body_key(url: str) -> str:
    """Return the Valkey key for the cached response body."""
    return f"etag_body:{url}"


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

    async def get_etag(self, url: str) -> str | None:
        """Return the cached ETag for *url*, or ``None`` on miss / error."""
        if self._valkey is None:
            return None
        try:
            return await self._valkey.get(_etag_key(url))
        except Exception as exc:
            logger.debug("etag_cache.get_etag_error", url=url, error=str(exc))
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

    async def store(self, url: str, etag: str, body: Any) -> None:
        """Persist the ETag and response body for *url*.

        Both keys are set with the configured TTL.  Errors are swallowed
        (cache is best-effort).
        """
        if self._valkey is None:
            return
        try:
            serialised = json.dumps(body)
            async with self._valkey.pipeline(transaction=False) as pipe:
                pipe.set(_etag_key(url), etag, ex=self._ttl)
                pipe.set(_body_key(url), serialised, ex=self._ttl)
                await pipe.execute()
        except Exception as exc:
            logger.debug("etag_cache.store_error", url=url, error=str(exc))

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
                    await pipe.execute()
        except Exception:  # noqa: S110 — best-effort TTL refresh
            pass
        logger.debug("etag_cache.hit", url=url)
        return CachedResponse(body=body, etag=etag)
