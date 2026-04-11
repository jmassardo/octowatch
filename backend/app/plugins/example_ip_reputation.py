"""Example enrichment plugin: IP reputation lookup.

This plugin demonstrates the ``EnrichmentPlugin`` interface.  It checks the
event's ``source_ip`` against a hard-coded list of "known-bad" IPs and adds
a reputation tag to the enrichment output.

In production you would replace the static list with a call to a threat-
intelligence API (e.g. AbuseIPDB, VirusTotal, GreyNoise).
"""

from __future__ import annotations

from typing import Any

from app.plugins.base import EnrichmentPlugin

# Example known-bad IPs (in production, load from external feed)
_KNOWN_BAD_IPS: frozenset[str] = frozenset(
    {
        "198.51.100.1",
        "203.0.113.42",
        "192.0.2.99",
    }
)


class IPReputationPlugin(EnrichmentPlugin):
    """Tag events from known-bad IP addresses."""

    @property
    def name(self) -> str:
        return "ip_reputation"

    @property
    def version(self) -> str:
        return "0.1.0"

    def on_load(self) -> None:
        """Load IP reputation data (static list in this example)."""
        self._bad_ips = _KNOWN_BAD_IPS

    async def enrich(self, event: dict[str, Any]) -> dict[str, Any] | None:
        """Check source_ip against known-bad list."""
        source_ip = event.get("source_ip")
        if not source_ip:
            return None

        ip_str = str(source_ip)
        if ip_str in self._bad_ips:
            return {
                "reputation": "malicious",
                "source": "static_list",
                "ip": ip_str,
            }

        return None
