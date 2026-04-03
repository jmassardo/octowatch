"""Tests for the centralized client IP extraction utility.

Covers:
- No trusted proxies configured → always returns request.client.host
- Request from trusted proxy → extracts correct IP from XFF
- Spoofed XFF from untrusted client → ignores XFF, returns direct IP
- Multiple proxies in chain → returns rightmost untrusted
- CIDR-based trust matching
- Malformed IPs handled gracefully
- Missing client / empty header edge cases
- IPv6 support
- Cache invalidation across tests
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from starlette.requests import Request

from app.utils.client_ip import _is_trusted, _trusted_networks, get_client_ip


def _make_request(
    client_host: str | None = "203.0.113.50",
    xff: str | None = None,
) -> Request:
    """Build a minimal Starlette Request mock for testing."""
    scope: dict = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
    }
    if xff is not None:
        scope["headers"].append((b"x-forwarded-for", xff.encode()))
    request = Request(scope)
    if client_host is not None:
        request._client = MagicMock()  # type: ignore[attr-defined]
        request._client.host = client_host  # type: ignore[attr-defined]
        # Patch the property
        object.__setattr__(request, "_client", request._client)  # type: ignore[attr-defined]
    else:
        object.__setattr__(request, "_client", None)  # type: ignore[attr-defined]
    return request


def _make_request_with_client(client_host: str | None, xff: str | None) -> MagicMock:
    """Build a MagicMock Request with proper client and headers."""
    req = MagicMock(spec=Request)
    if client_host is not None:
        req.client = MagicMock()
        req.client.host = client_host
    else:
        req.client = None

    headers: dict[str, str] = {}
    if xff is not None:
        headers["x-forwarded-for"] = xff
    req.headers = headers
    return req


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    """Clear the LRU cache between every test so TRUSTED_PROXIES changes take effect."""
    _trusted_networks.cache_clear()
    yield  # type: ignore[misc]
    _trusted_networks.cache_clear()


# ─── No Trusted Proxies ─────────────────────────────────────────────────────


class TestNoTrustedProxies:
    """When TRUSTED_PROXIES is empty, XFF is never consulted."""

    @patch("app.utils.client_ip.settings")
    def test_returns_direct_ip_without_xff(self, mock_settings: MagicMock) -> None:
        mock_settings.TRUSTED_PROXIES = []
        req = _make_request_with_client("203.0.113.50", xff=None)
        assert get_client_ip(req) == "203.0.113.50"

    @patch("app.utils.client_ip.settings")
    def test_ignores_xff_when_no_trusted_proxies(self, mock_settings: MagicMock) -> None:
        mock_settings.TRUSTED_PROXIES = []
        req = _make_request_with_client("203.0.113.50", xff="10.1.2.3, 192.168.1.1")
        assert get_client_ip(req) == "203.0.113.50"

    @patch("app.utils.client_ip.settings")
    def test_returns_none_when_no_client(self, mock_settings: MagicMock) -> None:
        mock_settings.TRUSTED_PROXIES = []
        req = _make_request_with_client(None, xff="10.1.2.3")
        assert get_client_ip(req) is None


# ─── Trusted Proxy — Basic ───────────────────────────────────────────────────


class TestTrustedProxyBasic:
    """When direct peer is a trusted proxy, the XFF chain is parsed."""

    @patch("app.utils.client_ip.settings")
    def test_extracts_client_from_xff(self, mock_settings: MagicMock) -> None:
        mock_settings.TRUSTED_PROXIES = ["10.0.0.0/8"]
        req = _make_request_with_client("10.0.0.1", xff="203.0.113.50")
        assert get_client_ip(req) == "203.0.113.50"

    @patch("app.utils.client_ip.settings")
    def test_returns_direct_ip_when_xff_empty(self, mock_settings: MagicMock) -> None:
        mock_settings.TRUSTED_PROXIES = ["10.0.0.0/8"]
        req = _make_request_with_client("10.0.0.1", xff="")
        assert get_client_ip(req) == "10.0.0.1"

    @patch("app.utils.client_ip.settings")
    def test_returns_direct_ip_when_no_xff_header(self, mock_settings: MagicMock) -> None:
        mock_settings.TRUSTED_PROXIES = ["10.0.0.0/8"]
        req = _make_request_with_client("10.0.0.1", xff=None)
        assert get_client_ip(req) == "10.0.0.1"


# ─── Spoofed XFF from Untrusted Client ──────────────────────────────────────


class TestSpoofedXFF:
    """When direct peer is NOT trusted, XFF is ignored entirely."""

    @patch("app.utils.client_ip.settings")
    def test_ignores_xff_from_untrusted_client(self, mock_settings: MagicMock) -> None:
        mock_settings.TRUSTED_PROXIES = ["10.0.0.0/8"]
        # Attacker at 203.0.113.50 spoofing XFF to pretend to be 192.30.252.1
        req = _make_request_with_client("203.0.113.50", xff="192.30.252.1")
        assert get_client_ip(req) == "203.0.113.50"

    @patch("app.utils.client_ip.settings")
    def test_ignores_xff_from_unknown_proxy(self, mock_settings: MagicMock) -> None:
        mock_settings.TRUSTED_PROXIES = ["10.0.0.0/8"]
        req = _make_request_with_client("172.31.0.1", xff="10.1.2.3, 8.8.8.8")
        assert get_client_ip(req) == "172.31.0.1"


# ─── Multiple Proxies in Chain ───────────────────────────────────────────────


class TestMultipleProxies:
    """Walk the XFF chain right-to-left, returning the rightmost untrusted IP."""

    @patch("app.utils.client_ip.settings")
    def test_rightmost_untrusted_ip(self, mock_settings: MagicMock) -> None:
        # XFF: "spoofed, real_client, proxy1"
        # Direct peer: proxy2 (trusted)
        mock_settings.TRUSTED_PROXIES = ["10.0.0.0/8"]
        req = _make_request_with_client(
            "10.0.0.2",
            xff="1.2.3.4, 203.0.113.50, 10.0.0.1",
        )
        # Walking right-to-left: 10.0.0.1 is trusted → skip; 203.0.113.50 is not → return
        assert get_client_ip(req) == "203.0.113.50"

    @patch("app.utils.client_ip.settings")
    def test_single_entry_xff(self, mock_settings: MagicMock) -> None:
        mock_settings.TRUSTED_PROXIES = ["10.0.0.0/8"]
        req = _make_request_with_client("10.0.0.1", xff="198.51.100.42")
        assert get_client_ip(req) == "198.51.100.42"

    @patch("app.utils.client_ip.settings")
    def test_all_proxies_trusted_returns_leftmost(self, mock_settings: MagicMock) -> None:
        mock_settings.TRUSTED_PROXIES = ["10.0.0.0/8"]
        req = _make_request_with_client("10.0.0.3", xff="10.0.0.1, 10.0.0.2")
        # All entries are trusted → return leftmost as best-effort
        assert get_client_ip(req) == "10.0.0.1"

    @patch("app.utils.client_ip.settings")
    def test_multiple_cidrs(self, mock_settings: MagicMock) -> None:
        mock_settings.TRUSTED_PROXIES = ["10.0.0.0/8", "172.16.0.0/12"]
        req = _make_request_with_client(
            "10.0.0.1",
            xff="203.0.113.10, 172.16.0.5, 10.0.0.2",
        )
        # 10.0.0.2 trusted → skip, 172.16.0.5 trusted → skip, 203.0.113.10 not → return
        assert get_client_ip(req) == "203.0.113.10"


# ─── CIDR Matching ───────────────────────────────────────────────────────────


class TestCIDRMatching:
    """Verify IP-to-CIDR matching works for various network sizes."""

    @patch("app.utils.client_ip.settings")
    def test_exact_ip_as_trusted(self, mock_settings: MagicMock) -> None:
        mock_settings.TRUSTED_PROXIES = ["10.0.0.1/32"]
        req = _make_request_with_client("10.0.0.1", xff="8.8.8.8")
        assert get_client_ip(req) == "8.8.8.8"

    @patch("app.utils.client_ip.settings")
    def test_ip_outside_cidr_not_trusted(self, mock_settings: MagicMock) -> None:
        mock_settings.TRUSTED_PROXIES = ["10.0.0.0/24"]
        req = _make_request_with_client("10.0.1.1", xff="8.8.8.8")
        # 10.0.1.1 is NOT in 10.0.0.0/24 → XFF ignored
        assert get_client_ip(req) == "10.0.1.1"

    @patch("app.utils.client_ip.settings")
    def test_single_ip_without_cidr(self, mock_settings: MagicMock) -> None:
        # "10.0.0.1" without prefix → treated as /32
        mock_settings.TRUSTED_PROXIES = ["10.0.0.1"]
        req = _make_request_with_client("10.0.0.1", xff="8.8.8.8")
        assert get_client_ip(req) == "8.8.8.8"


# ─── Malformed IPs ──────────────────────────────────────────────────────────


class TestMalformedIPs:
    """Malformed entries in XFF or trusted proxies are handled gracefully."""

    @patch("app.utils.client_ip.settings")
    def test_malformed_xff_entries_skipped(self, mock_settings: MagicMock) -> None:
        mock_settings.TRUSTED_PROXIES = ["10.0.0.0/8"]
        req = _make_request_with_client(
            "10.0.0.1",
            xff="203.0.113.50, not-an-ip, also-bad",
        )
        # Walking right-to-left: "also-bad" skipped, "not-an-ip" skipped, 203.0.113.50 returned
        assert get_client_ip(req) == "203.0.113.50"

    @patch("app.utils.client_ip.settings")
    def test_all_xff_entries_malformed_returns_leftmost(self, mock_settings: MagicMock) -> None:
        mock_settings.TRUSTED_PROXIES = ["10.0.0.0/8"]
        req = _make_request_with_client("10.0.0.1", xff="garbage, trash")
        # All entries malformed → return leftmost (best-effort)
        assert get_client_ip(req) == "garbage"

    @patch("app.utils.client_ip.settings")
    def test_invalid_trusted_proxy_entry_ignored(self, mock_settings: MagicMock) -> None:
        mock_settings.TRUSTED_PROXIES = ["not-a-cidr", "10.0.0.0/8"]
        req = _make_request_with_client("10.0.0.1", xff="203.0.113.50")
        # Invalid entry is skipped, 10.0.0.0/8 still works
        assert get_client_ip(req) == "203.0.113.50"

    @patch("app.utils.client_ip.settings")
    def test_xff_with_whitespace(self, mock_settings: MagicMock) -> None:
        mock_settings.TRUSTED_PROXIES = ["10.0.0.0/8"]
        req = _make_request_with_client("10.0.0.1", xff="  203.0.113.50 ,  10.0.0.2  ")
        assert get_client_ip(req) == "203.0.113.50"


# ─── IPv6 Support ────────────────────────────────────────────────────────────


class TestIPv6:
    """IPv6 addresses work correctly in both client and XFF."""

    @patch("app.utils.client_ip.settings")
    def test_ipv6_direct_client(self, mock_settings: MagicMock) -> None:
        mock_settings.TRUSTED_PROXIES = []
        req = _make_request_with_client("::1", xff=None)
        assert get_client_ip(req) == "::1"

    @patch("app.utils.client_ip.settings")
    def test_ipv6_trusted_proxy(self, mock_settings: MagicMock) -> None:
        mock_settings.TRUSTED_PROXIES = ["fd00::/8"]
        req = _make_request_with_client("fd00::1", xff="2001:db8::1")
        assert get_client_ip(req) == "2001:db8::1"

    @patch("app.utils.client_ip.settings")
    def test_mixed_v4_v6_xff_chain(self, mock_settings: MagicMock) -> None:
        mock_settings.TRUSTED_PROXIES = ["10.0.0.0/8", "fd00::/8"]
        req = _make_request_with_client(
            "10.0.0.1",
            xff="2001:db8::1, fd00::2, 10.0.0.3",
        )
        # 10.0.0.3 trusted → skip, fd00::2 trusted → skip, 2001:db8::1 → return
        assert get_client_ip(req) == "2001:db8::1"


# ─── _is_trusted helper ─────────────────────────────────────────────────────


class TestIsTrusted:
    """Unit tests for the _is_trusted helper function."""

    @patch("app.utils.client_ip.settings")
    def test_trusted_ip(self, mock_settings: MagicMock) -> None:
        mock_settings.TRUSTED_PROXIES = ["10.0.0.0/8"]
        assert _is_trusted("10.1.2.3") is True

    @patch("app.utils.client_ip.settings")
    def test_untrusted_ip(self, mock_settings: MagicMock) -> None:
        mock_settings.TRUSTED_PROXIES = ["10.0.0.0/8"]
        assert _is_trusted("192.168.1.1") is False

    @patch("app.utils.client_ip.settings")
    def test_malformed_ip_not_trusted(self, mock_settings: MagicMock) -> None:
        mock_settings.TRUSTED_PROXIES = ["10.0.0.0/8"]
        assert _is_trusted("not-an-ip") is False

    @patch("app.utils.client_ip.settings")
    def test_empty_trusted_list(self, mock_settings: MagicMock) -> None:
        mock_settings.TRUSTED_PROXIES = []
        assert _is_trusted("10.0.0.1") is False
