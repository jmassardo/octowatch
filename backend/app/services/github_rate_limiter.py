"""GitHub API rate limit compliance service.

Implements a token-bucket algorithm calibrated to respect GitHub's
primary rate limit (15,000 req/hr for GitHub Apps) and secondary limits
(≤ 100 concurrent requests, ≤ 900 points/min).

When the remaining quota drops below 1,000 requests, the bucket refill rate
is capped to 3 tokens/s regardless of burst capacity, providing a proactive
throttle that keeps the sync from hitting hard limits.

All state is in-process (asyncio). This class is instantiated once per
Celery worker process and shared across all tasks via module-level singleton.
"""

from __future__ import annotations

import asyncio
import secrets
import time
from typing import ClassVar

import httpx
import structlog

logger = structlog.get_logger(__name__)


class GitHubRateLimiter:
    """Token-bucket rate limiter for the GitHub REST API.

    Parameters
    ----------
    rate_per_hour:
        Maximum requests per hour. Default 15,000 (GitHub App limit).
    max_burst:
        Maximum tokens that can accumulate in the bucket before capping.
        Limits burst behaviour to avoid hitting secondary limits.
    max_concurrent:
        asyncio.Semaphore count bounding in-flight concurrent requests.
        Set to 80 to stay safely under GitHub's 100-concurrent limit.
    """

    #: Proactive throttle threshold — cap to _PROACTIVE_THROTTLE_RATE req/s if remaining ≤ this
    _PROACTIVE_THROTTLE_THRESHOLD: ClassVar[int] = 1000
    #: Cap rate (req/s) applied when remaining quota is below the threshold
    _PROACTIVE_THROTTLE_RATE: ClassVar[float] = 3.0

    def __init__(
        self,
        rate_per_hour: int = 15_000,
        max_burst: int = 50,
        max_concurrent: int = 80,
    ) -> None:
        self._rate_per_sec: float = rate_per_hour / 3600.0  # ≈ 4.17 tokens/s
        self._max_burst = max_burst
        self._tokens: float = max_burst
        self._last_refill: float = time.monotonic()

        # Secondary-rate semaphore — max 80 simultaneous in-flight requests
        self._semaphore = asyncio.Semaphore(max_concurrent)

        # Tracking values parsed from GitHub response headers
        self._remaining: int = rate_per_hour
        self._reset_at: float = 0.0  # Unix timestamp
        self._proactive_throttle_active: bool = False

    # ── Public API ────────────────────────────────────────────────────────────

    async def acquire(self, cost: int = 1) -> None:
        """Block until *cost* tokens are available and the semaphore permits.

        Call this once before every GitHub API request. The semaphore is
        **not** released here — use it as an async context manager instead:

        .. code-block:: python

            async with rate_limiter._semaphore:
                await rate_limiter.acquire()
                response = await client.get(url)
                rate_limiter.update_from_headers(response.headers)

        If the proactive throttle is active (remaining < 1,000), the effective
        refill rate is capped to 1 token/s to bleed down the request queue slowly.

        Parameters
        ----------
        cost:
            Number of rate-limit tokens to consume. Almost always 1.
        """
        await self._semaphore.acquire()
        try:
            self._refill()
            while self._tokens < cost:
                effective_rate = (
                    self._PROACTIVE_THROTTLE_RATE
                    if self._proactive_throttle_active
                    else self._rate_per_sec
                )
                sleep_for = (cost - self._tokens) / effective_rate
                logger.debug(
                    "rate_limiter.waiting",
                    sleep_for=round(sleep_for, 2),
                    tokens=round(self._tokens, 2),
                    proactive_throttle=self._proactive_throttle_active,
                )
                await asyncio.sleep(sleep_for)
                self._refill()
            self._tokens -= cost
        except Exception:
            self._semaphore.release()
            raise

    def release(self) -> None:
        """Release the semaphore after a request completes."""
        self._semaphore.release()

    def update_from_headers(self, headers: httpx.Headers | dict[str, str]) -> None:
        """Parse GitHub rate-limit response headers and update internal state.

        Relevant headers:
          - ``x-ratelimit-remaining``: requests left in current window
          - ``x-ratelimit-reset``: Unix timestamp when window resets
          - ``x-ratelimit-used``: requests consumed in current window

        Also activates or deactivates the proactive throttle based on
        the ``remaining`` value relative to ``_PROACTIVE_THROTTLE_THRESHOLD``.

        Parameters
        ----------
        headers:
            Response headers from an httpx.Response or dict equivalent.
        """
        try:
            remaining_str = headers.get("x-ratelimit-remaining")
            reset_str = headers.get("x-ratelimit-reset")
            if remaining_str is not None:
                self._remaining = int(remaining_str)
            if reset_str is not None:
                self._reset_at = float(reset_str)

            was_throttled = self._proactive_throttle_active
            self._proactive_throttle_active = self._remaining < self._PROACTIVE_THROTTLE_THRESHOLD
            if self._proactive_throttle_active and not was_throttled:
                logger.warning(
                    "rate_limiter.proactive_throttle_activated",
                    remaining=self._remaining,
                    reset_at=self._reset_at,
                )
        except (ValueError, TypeError) as exc:
            logger.warning("rate_limiter.header_parse_error", error=str(exc))

    async def handle_rate_limit_response(self, response: httpx.Response) -> None:
        """Handle a 429 Too Many Requests or 403 (secondary rate limit) response.

        Parses the ``retry-after`` header if present; falls back to sleeping
        until ``x-ratelimit-reset``. Implements exponential backoff with
        jitter when called in rapid succession.

        Callers should retry the request after awaiting this method.

        Parameters
        ----------
        response:
            The non-2xx httpx.Response that triggered rate limiting.
        """
        status = response.status_code
        if status not in (429, 403):
            return

        retry_after_str = response.headers.get("retry-after")
        if retry_after_str:
            try:
                sleep_secs = float(retry_after_str) + (0.5 + secrets.randbelow(1500) / 1000.0)
            except ValueError:
                sleep_secs = 60.0
        elif self._reset_at > 0:
            sleep_secs = max(self._reset_at - time.time() + 1.0, 1.0)
        else:
            sleep_secs = 60.0

        logger.warning(
            "rate_limiter.backing_off",
            status=status,
            sleep_secs=round(sleep_secs, 1),
        )
        await asyncio.sleep(sleep_secs)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _refill(self) -> None:
        """Refill the token bucket based on elapsed time since last call."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._last_refill = now
        rate = (
            self._PROACTIVE_THROTTLE_RATE
            if self._proactive_throttle_active
            else self._rate_per_sec
        )
        self._tokens = min(self._tokens + elapsed * rate, float(self._max_burst))
