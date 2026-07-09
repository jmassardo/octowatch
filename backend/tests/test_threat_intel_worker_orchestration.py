"""Tests for threat_intel_worker orchestration."""

from __future__ import annotations

from typing import Any

from app.workers.threat_intel_worker import _build_auth_headers


class TestBuildAuthHeaders:
    """Test authentication header generation from parser_config."""

    def test_bearer_token(self):
        config: dict[str, Any] = {"auth_token": "secret123"}
        headers = _build_auth_headers(config)
        assert headers == {"Authorization": "Bearer secret123"}

    def test_custom_header(self):
        config: dict[str, Any] = {"auth_header": "X-Api-Key", "auth_value": "key456"}
        headers = _build_auth_headers(config)
        assert headers == {"X-Api-Key": "key456"}

    def test_no_auth(self):
        assert _build_auth_headers(None) == {}
        assert _build_auth_headers({}) == {}

    def test_custom_header_missing_value(self):
        """Header name without value should produce empty headers."""
        config: dict[str, Any] = {"auth_header": "X-Api-Key"}
        headers = _build_auth_headers(config)
        assert headers == {}

    def test_bearer_takes_precedence(self):
        """If both auth_token and auth_header exist, bearer wins."""
        config: dict[str, Any] = {
            "auth_token": "bearer_token",
            "auth_header": "X-Api-Key",
            "auth_value": "key_value",
        }
        headers = _build_auth_headers(config)
        assert headers == {"Authorization": "Bearer bearer_token"}

    def test_unrelated_config_ignored(self):
        """Non-auth config keys should not produce headers."""
        config: dict[str, Any] = {"indicator_type": "ip", "format": "csv"}
        headers = _build_auth_headers(config)
        assert headers == {}
