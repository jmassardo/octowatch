"""Plugin discovery, loading, and lifecycle management.

The :class:`PluginManager` scans a configured directory for Python modules
that contain concrete subclasses of :class:`EnrichmentPlugin`, instantiates
them, and orchestrates the ``enrich()`` calls during event ingestion.

Plugin exceptions are **fully isolated** – a failing plugin never blocks core
event processing.
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
from pathlib import Path
from typing import Any

import structlog

from app.plugins.base import EnrichmentPlugin

logger = structlog.get_logger(__name__)


class PluginManager:
    """Discover, load, and run enrichment plugins."""

    def __init__(self, plugin_dir: str | None = None) -> None:
        self._plugin_dir = plugin_dir
        self.plugins: list[EnrichmentPlugin] = []
        self._loaded = False

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover(self) -> None:
        """Scan *plugin_dir* for Python modules implementing :class:`EnrichmentPlugin`.

        Only ``.py`` files (excluding ``__init__.py`` and private modules
        starting with ``_``) are inspected.  Each concrete subclass of
        ``EnrichmentPlugin`` found in a module is instantiated and its
        ``on_load`` hook is called.
        """
        if self._loaded:
            return

        if self._plugin_dir is None:
            # Default to the ``plugins/`` package directory itself
            self._plugin_dir = str(Path(__file__).parent)

        plugin_path = Path(self._plugin_dir)
        if not plugin_path.is_dir():
            logger.warning("plugin_manager.dir_not_found", path=str(plugin_path))
            self._loaded = True
            return

        for py_file in sorted(plugin_path.glob("*.py")):
            if py_file.name.startswith("_"):
                continue

            module_name = f"app.plugins.{py_file.stem}"
            try:
                spec = importlib.util.spec_from_file_location(module_name, py_file)
                if spec is None or spec.loader is None:
                    continue
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
            except Exception:
                logger.exception("plugin_manager.load_module_failed", module=module_name)
                continue

            for _attr_name, obj in inspect.getmembers(module, inspect.isclass):
                if (
                    issubclass(obj, EnrichmentPlugin)
                    and obj is not EnrichmentPlugin
                    and not inspect.isabstract(obj)
                ):
                    try:
                        instance = obj()
                        instance.on_load()
                        self.plugins.append(instance)
                        logger.info(
                            "plugin_manager.loaded",
                            plugin=instance.name,
                            version=instance.version,
                        )
                    except Exception:
                        logger.exception(
                            "plugin_manager.instantiate_failed",
                            cls=obj.__name__,
                        )

        self._loaded = True
        logger.info("plugin_manager.discovery_complete", count=len(self.plugins))

    # ------------------------------------------------------------------
    # Enrichment
    # ------------------------------------------------------------------

    async def run_enrichments(self, event: dict[str, Any]) -> dict[str, Any]:
        """Run all loaded plugins against *event*.

        Returns a merged dict of enrichment data from all plugins.  Each
        plugin's output is stored under a key equal to its ``name``.  Plugin
        exceptions are caught and logged – they never propagate.
        """
        merged: dict[str, Any] = {}

        for plugin in self.plugins:
            try:
                result = await plugin.enrich(event)
                if result:
                    merged[plugin.name] = result
            except Exception:
                logger.exception(
                    "plugin_manager.enrich_failed",
                    plugin=plugin.name,
                    action=event.get("action"),
                )
                # Isolated: do NOT re-raise

        return merged

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def unload_all(self) -> None:
        """Call ``on_unload`` for every loaded plugin and clear the list."""
        for plugin in self.plugins:
            try:
                plugin.on_unload()
            except Exception:
                logger.exception("plugin_manager.unload_failed", plugin=plugin.name)
        self.plugins.clear()
        self._loaded = False
