"""Plugin system for custom event enrichment."""

from app.plugins.base import EnrichmentPlugin
from app.plugins.loader import PluginManager

__all__ = ["EnrichmentPlugin", "PluginManager"]
