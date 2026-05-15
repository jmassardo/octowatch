"""Secure client IP extraction with trusted-proxy awareness.

The naive approach of blindly reading X-Forwarded-For is dangerous:
an attacker can prepend arbitrary IPs to bypass IP-based allowlists
or poison audit logs.  This module only trusts the XFF chain when
the *direct* peer (``request.client.host``) is a known trusted proxy.
It then walks the XFF chain **right-to-left** and returns the first
IP that is *not* in the trusted proxy set — the real client IP.

When the direct peer is *not* trusted, ``request.client.host`` is
returned verbatim and XFF is ignored entirely.
"""

from __future__ import annotations

import ipaddress
import logging
from functools import lru_cache

from starlette.requests import Request

from app.config import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _trusted_networks() -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    """Parse ``settings.TRUSTED_PROXIES`` into a cached tuple of network objects.

    Invalid entries are logged and skipped so a single typo does not
    break the entire allowlist.
    """
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for entry in settings.TRUSTED_PROXIES:
        try:
            networks.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            logger.warning("trusted_proxies.invalid_entry: [REDACTED]")
    return tuple(networks)


def _is_trusted(ip_str: str) -> bool:
    """Return ``True`` if *ip_str* falls within any configured trusted proxy range."""
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return any(addr in net for net in _trusted_networks())


def get_client_ip(request: Request) -> str | None:
    """Extract the real client IP from *request*.

    Algorithm
    ---------
    1. If ``request.client`` is ``None`` → return ``None``.
    2. If the direct peer IP is **not** in ``TRUSTED_PROXIES``
       → return ``request.client.host`` (XFF is untrusted).
    3. Otherwise, parse the ``X-Forwarded-For`` header and walk
       the address chain **right-to-left**, returning the first
       IP that is *not* in ``TRUSTED_PROXIES``.
    4. If all IPs in the chain are trusted (unlikely) → return
       the leftmost entry.
    5. Malformed individual IPs in the chain are silently skipped.
    """
    if request.client is None:
        return None

    direct_ip: str = request.client.host

    # No trusted proxies configured or direct peer is not trusted
    # → XFF is untrusted, return the TCP-level peer address.
    if not settings.TRUSTED_PROXIES or not _is_trusted(direct_ip):
        return direct_ip

    # Direct peer is trusted — parse XFF.
    xff = request.headers.get("x-forwarded-for")
    if not xff:
        return direct_ip

    # XFF format: "client, proxy1, proxy2" — walk right-to-left.
    parts = [part.strip() for part in xff.split(",") if part.strip()]
    if not parts:
        return direct_ip

    for ip_str in reversed(parts):
        # Validate the IP string before checking trust status.
        try:
            ipaddress.ip_address(ip_str)
        except ValueError:
            # Skip malformed entries rather than trusting them.
            continue

        if not _is_trusted(ip_str):
            return ip_str

    # Every entry in the chain is a trusted proxy.  Return the
    # leftmost entry as the best-effort client IP.
    return parts[0]
