"""Abstract base class for enrichment plugins.

All custom enrichment plugins must inherit from ``EnrichmentPlugin`` and
implement the required abstract properties and methods.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class EnrichmentPlugin(ABC):
    """Base class that every enrichment plugin must implement.

    Lifecycle
    ---------
    1. The :class:`PluginManager` discovers and instantiates plugins on startup.
    2. ``on_load()`` is called once after instantiation.
    3. ``enrich()`` is called for every ingested event.
    4. ``on_unload()`` is called during graceful shutdown.

    Thread-safety
    -------------
    ``enrich()`` may be invoked concurrently – implementations must be safe for
    concurrent use (no shared mutable state without proper locking).
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique human-readable name of this plugin."""
        ...

    @property
    @abstractmethod
    def version(self) -> str:
        """Semantic version string (e.g. ``'1.0.0'``)."""
        ...

    @abstractmethod
    async def enrich(self, event: dict[str, Any]) -> dict[str, Any] | None:
        """Return enrichment data for *event*, or ``None`` to skip.

        Parameters
        ----------
        event:
            Normalised event dict with keys such as ``action``, ``actor``,
            ``org``, ``repo``, ``source_ip``, ``data``, etc.

        Returns
        -------
        dict | None
            A dict of enrichment key/value pairs that will be merged into the
            event's ``custom_enrichments`` JSONB column.  Return ``None`` (or
            an empty dict) to indicate this plugin has nothing to add.
        """
        ...

    def on_load(self) -> None:
        """Called once after the plugin is instantiated.

        Override to perform one-time initialisation (open connections, warm
        caches, etc.).
        """
        return  # optional hook – subclasses may override

    def on_unload(self) -> None:
        """Called during graceful shutdown.

        Override to release resources (close connections, flush buffers, etc.).
        """
        return  # optional hook – subclasses may override
