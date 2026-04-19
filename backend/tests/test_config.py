"""Unit tests for config.py: Settings validation, SSRF checks, and env parsing."""

from __future__ import annotations

import pytest
from pydantic import ValidationError


class TestValkeySettings:
    def test_valid_redis_url(self):
        from app.config import ValkeySettings

        s = ValkeySettings(VALKEY_URL="redis://localhost:6379/0")
        assert s.VALKEY_URL == "redis://localhost:6379/0"

    def test_invalid_scheme_rejected(self):
        from app.config import ValkeySettings

        with pytest.raises(ValidationError):
            ValkeySettings(VALKEY_URL="http://localhost:6379")


class TestIntegrationSettings:
    def test_valid_okta_org_url(self):
        from app.config import IntegrationSettings

        s = IntegrationSettings(OKTA_ORG_URL="https://mycompany.okta.com")
        assert s.OKTA_ORG_URL is not None
        assert "okta.com" in s.OKTA_ORG_URL

    def test_invalid_okta_org_url_rejected(self):
        from app.config import IntegrationSettings

        with pytest.raises(ValidationError):
            IntegrationSettings(OKTA_ORG_URL="https://evil.example.com")
