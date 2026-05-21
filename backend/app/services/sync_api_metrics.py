"""API call metrics tracking for GitHub sync runs.

Provides a lightweight counter that tracks the number of API calls made
during a sync run, broken down by entity type and whether the response
was a cache hit (304) or a full fetch.  Results are logged at the end
of each entity sync and aggregated into the run's sync log for
observability.

Usage
-----
Instantiate :class:`SyncAPICallCounter` at the start of a sync entity task.
Pass it through to ``_github_get`` calls.  At completion, call
:meth:`summary` to get a dict suitable for structured logging.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger(__name__)


@dataclass(slots=True)
class EntityMetrics:
    """Metrics for a single entity type within a sync run."""

    api_calls: int = 0
    cache_hits: int = 0
    pages_fetched: int = 0
    items_received: int = 0


@dataclass
class SyncAPICallCounter:
    """Thread-safe counter for tracking API calls during a sync run.

    Attributes
    ----------
    run_id:
        The UUID string of the parent sync run (for logging context).
    entity_type:
        The entity type being synced (e.g., "repositories", "teams").
    """

    run_id: str
    entity_type: str
    _metrics: EntityMetrics = field(default_factory=EntityMetrics)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def record_api_call(self, *, cache_hit: bool = False) -> None:
        """Record a single API call.

        Parameters
        ----------
        cache_hit:
            True if the response was a 304 (served from cache).
        """
        with self._lock:
            self._metrics.api_calls += 1
            if cache_hit:
                self._metrics.cache_hits += 1

    def record_page(self, items_count: int) -> None:
        """Record a successfully fetched page with *items_count* items."""
        with self._lock:
            self._metrics.pages_fetched += 1
            self._metrics.items_received += items_count

    @property
    def total_calls(self) -> int:
        """Return the total number of API calls made so far."""
        return self._metrics.api_calls

    @property
    def cache_hits(self) -> int:
        """Return the total number of cache hits (304 responses)."""
        return self._metrics.cache_hits

    def summary(self) -> dict[str, object]:
        """Return a summary dict suitable for structured logging."""
        with self._lock:
            savings_pct = (
                round(self._metrics.cache_hits / self._metrics.api_calls * 100, 1)
                if self._metrics.api_calls > 0
                else 0.0
            )
            return {
                "run_id": self.run_id,
                "entity_type": self.entity_type,
                "total_api_calls": self._metrics.api_calls,
                "cache_hits_304": self._metrics.cache_hits,
                "actual_fetches": self._metrics.api_calls - self._metrics.cache_hits,
                "pages_fetched": self._metrics.pages_fetched,
                "items_received": self._metrics.items_received,
                "cache_hit_rate_pct": savings_pct,
            }

    def log_summary(self) -> None:
        """Emit a structured log with the sync metrics summary."""
        logger.info(
            "github_sync.api_metrics",
            **self.summary(),
        )
