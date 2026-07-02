"""Response caching for dashboard endpoints using Valkey.

Provides a scope-aware caching decorator that keys on the resolved
RBAC org list + endpoint parameters.  This avoids cross-tenant data
leakage while giving sub-second repeated reads.
"""

from __future__ import annotations

import functools
import hashlib
import json
from collections.abc import Callable
from typing import Any

import redis.asyncio as aioredis
import structlog

logger = structlog.get_logger(__name__)

# Default TTL for cached dashboard responses (seconds)
DEFAULT_TTL = 300  # 5 minutes


def _build_cache_key(
    prefix: str,
    scoped_orgs: list[str],
    params: dict[str, Any],
) -> str:
    """Build a Valkey cache key from endpoint prefix + RBAC-scoped orgs + params.

    The org list is sorted and hashed so the key is stable regardless of
    list ordering, and sensitive org names aren't stored as plain text.
    """
    org_hash = hashlib.sha256(",".join(sorted(scoped_orgs)).encode()).hexdigest()[:16]

    param_parts = []
    for k in sorted(params):
        param_parts.append(f"{k}={params[k]}")
    param_str = "&".join(param_parts)

    return f"cache:{prefix}:{org_hash}:{param_str}"


async def cache_get(
    valkey: aioredis.Redis,
    key: str,
) -> dict[str, Any] | None:
    """Fetch a cached response, returning None on miss or error."""
    try:
        raw = await valkey.get(key)
        if raw is not None:
            return json.loads(raw)
    except Exception:
        logger.warning("cache_get_error", key=key, exc_info=True)
    return None


async def cache_set(
    valkey: aioredis.Redis,
    key: str,
    data: dict[str, Any],
    ttl: int = DEFAULT_TTL,
) -> None:
    """Store a response in Valkey with TTL."""
    try:
        await valkey.setex(key, ttl, json.dumps(data, default=str))
    except Exception:
        logger.warning("cache_set_error", key=key, exc_info=True)


def cached_endpoint(
    prefix: str,
    ttl: int = DEFAULT_TTL,
    param_keys: list[str] | None = None,
) -> Callable:
    """Decorator for caching router endpoint results in Valkey.

    Usage::

        @cached_endpoint("dev-activity.developers", param_keys=["lookback_days"])
        async def list_developers(
            scoped_orgs, lookback_days, *, valkey, db, **kw
        ):
            ...

    The decorated function must accept ``scoped_orgs: list[str]`` as its
    first positional arg and ``valkey`` and ``db`` as keyword args.
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(
            scoped_orgs: list[str],
            *args: Any,
            valkey: aioredis.Redis | None = None,
            **kwargs: Any,
        ) -> dict[str, Any]:
            # Build cache key from scoped orgs + selected params
            params: dict[str, Any] = {}
            if param_keys:
                for k in param_keys:
                    if k in kwargs:
                        params[k] = kwargs[k]

            # Try cache if Valkey is available
            if valkey is not None:
                key = _build_cache_key(prefix, scoped_orgs, params)
                cached = await cache_get(valkey, key)
                if cached is not None:
                    logger.debug("cache_hit", prefix=prefix)
                    return cached

            # Cache miss — execute the real function
            result = await func(scoped_orgs, *args, **kwargs)

            # Store in cache
            if valkey is not None:
                await cache_set(valkey, key, result, ttl)

            return result

        return wrapper

    return decorator
