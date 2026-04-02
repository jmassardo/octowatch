"""GitHub IP allowlist service.

Maintains a cached set of GitHub's published IP CIDR ranges (from the
``/meta`` endpoint) so that webhook and audit-stream ingestion endpoints
can be restricted to traffic originating from GitHub infrastructure.

The allowlist is persisted in Valkey with a 24-hour TTL and refreshed
every 6 hours by a Celery beat task.  On FastAPI startup the service
loads from cache first; if the cache is empty it fetches fresh data.
"""

from __future__ import annotations

import ipaddress
import json

import httpx
import redis.asyncio as aioredis
import structlog

logger = structlog.get_logger(__name__)

GITHUB_META_URL = "https://api.github.com/meta"
VALKEY_KEY = "github:ip_allowlist"
VALKEY_TTL = 86400  # 24 hours


class GitHubIPAllowlist:
    """Maintains a cached set of GitHub's published IP CIDR ranges."""

    _networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    _loaded: bool = False

    @classmethod
    async def refresh(cls, valkey: aioredis.Redis) -> int:
        """Fetch GitHub /meta, cache CIDRs in Valkey, update in-memory list.

        Returns the number of CIDR ranges cached.
        """
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(GITHUB_META_URL)
            resp.raise_for_status()
            meta = resp.json()

        # Collect CIDRs from hooks + actions keys
        cidrs: list[str] = []
        for key in ("hooks", "actions"):
            cidrs.extend(meta.get(key, []))

        # Deduplicate and sort for deterministic caching
        cidrs = sorted(set(cidrs))

        # Cache in Valkey as JSON array
        await valkey.set(VALKEY_KEY, json.dumps(cidrs), ex=VALKEY_TTL)

        # Update in-memory network objects
        cls._networks = [ipaddress.ip_network(c, strict=False) for c in cidrs]
        cls._loaded = True

        logger.info("github_ip_allowlist.refreshed", count=len(cidrs))
        return len(cidrs)

    @classmethod
    async def load_from_cache(cls, valkey: aioredis.Redis) -> bool:
        """Load CIDRs from Valkey cache.

        Returns ``True`` if loaded successfully, ``False`` if the cache is
        empty.
        """
        raw = await valkey.get(VALKEY_KEY)
        if not raw:
            return False
        cidrs: list[str] = json.loads(raw)
        cls._networks = [ipaddress.ip_network(c, strict=False) for c in cidrs]
        cls._loaded = True
        logger.info("github_ip_allowlist.loaded_from_cache", count=len(cidrs))
        return True

    @classmethod
    def is_allowed(cls, ip: str) -> bool:
        """Check if an IP address falls within GitHub's published ranges."""
        if not cls._loaded:
            # Fail-open if allowlist hasn't been loaded yet
            logger.warning("github_ip_allowlist.not_loaded, allowing request")
            return True
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False
        return any(addr in network for network in cls._networks)

    @classmethod
    def is_loaded(cls) -> bool:
        """Return whether the allowlist has been loaded."""
        return cls._loaded

    @classmethod
    def network_count(cls) -> int:
        """Return the number of CIDR networks currently loaded."""
        return len(cls._networks)

    @classmethod
    def reset(cls) -> None:
        """Reset internal state (used in tests)."""
        cls._networks = []
        cls._loaded = False
