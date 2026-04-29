"""Unit tests for the SecretProvider abstraction layer.

Tests cover:
- EnvVarProvider: reads/writes/deletes env vars, name mapping
- Factory function: provider selection logic based on env vars
- AzureKeyVaultProvider: mocked cache behavior, graceful degradation, alerting
"""

from __future__ import annotations

import os
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.env_provider import EnvVarProvider
from app.services.secret_provider import (
    SecretProviderError,
    ServiceUnavailableError,
    create_secret_provider,
)

# ──────────────────────────────────────────────────────────────────────────────
# EnvVarProvider Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestEnvVarProvider:
    """Tests for the environment variable-based secret provider."""

    @pytest.fixture
    def provider(self):
        return EnvVarProvider()

    async def test_get_secret_existing(self, provider, monkeypatch):
        """Reading an existing env var returns its value."""
        monkeypatch.setenv("MY_SECRET", "supersecret")
        result = await provider.get_secret("my-secret")
        assert result == "supersecret"

    async def test_get_secret_missing(self, provider, monkeypatch):
        """Reading a non-existent env var returns None."""
        monkeypatch.delenv("NONEXISTENT_SECRET", raising=False)
        result = await provider.get_secret("nonexistent-secret")
        assert result is None

    async def test_get_secret_empty_value(self, provider, monkeypatch):
        """An empty string env var is treated as 'not set' (returns None)."""
        monkeypatch.setenv("EMPTY_VAR", "")
        result = await provider.get_secret("empty-var")
        assert result is None

    async def test_name_to_env_var_mapping(self, provider):
        """Secret names are mapped to uppercase with dashes → underscores."""
        assert provider._to_env_var("hec-token") == "HEC_TOKEN"
        assert provider._to_env_var("github-webhook-secret") == "GITHUB_WEBHOOK_SECRET"
        assert provider._to_env_var("simple") == "SIMPLE"
        assert provider._to_env_var("multi-dash-name") == "MULTI_DASH_NAME"

    async def test_set_secret(self, provider, monkeypatch):
        """Setting a secret sets the env var in the process."""
        monkeypatch.delenv("NEW_SECRET", raising=False)
        await provider.set_secret("new-secret", "myvalue")
        assert os.environ.get("NEW_SECRET") == "myvalue"

    async def test_delete_secret(self, provider, monkeypatch):
        """Deleting a secret removes the env var."""
        monkeypatch.setenv("TO_DELETE", "val")
        await provider.delete_secret("to-delete")
        assert "TO_DELETE" not in os.environ

    async def test_delete_secret_nonexistent(self, provider, monkeypatch):
        """Deleting a non-existent env var does not raise."""
        monkeypatch.delenv("GHOST", raising=False)
        await provider.delete_secret("ghost")  # Should not raise

    async def test_list_secrets_returns_empty(self, provider):
        """list_secrets always returns empty for env provider."""
        result = await provider.list_secrets()
        assert result == []

    async def test_invalidate_cache_noop(self, provider):
        """invalidate_cache is a no-op for env provider."""
        await provider.invalidate_cache("any-name")  # Should not raise

    async def test_close_noop(self, provider):
        """close is a no-op for env provider."""
        await provider.close()  # Should not raise


# ──────────────────────────────────────────────────────────────────────────────
# Factory Function Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestCreateSecretProvider:
    """Tests for the create_secret_provider factory function."""

    def test_explicit_env_provider(self, monkeypatch):
        """SECRET_PROVIDER=env creates an EnvVarProvider."""
        monkeypatch.setenv("SECRET_PROVIDER", "env")
        provider = create_secret_provider()
        assert isinstance(provider, EnvVarProvider)

    def test_default_development_uses_env(self, monkeypatch):
        """Without SECRET_PROVIDER set, development uses env provider."""
        monkeypatch.delenv("SECRET_PROVIDER", raising=False)
        monkeypatch.setenv("ENVIRONMENT", "development")
        provider = create_secret_provider()
        assert isinstance(provider, EnvVarProvider)

    def test_default_staging_uses_env(self, monkeypatch):
        """Without SECRET_PROVIDER set, staging uses env provider."""
        monkeypatch.delenv("SECRET_PROVIDER", raising=False)
        monkeypatch.setenv("ENVIRONMENT", "staging")
        provider = create_secret_provider()
        assert isinstance(provider, EnvVarProvider)

    def test_explicit_azure_keyvault_without_uri_raises(self, monkeypatch):
        """SECRET_PROVIDER=azure_keyvault without AZURE_KEYVAULT_URI raises."""
        monkeypatch.setenv("SECRET_PROVIDER", "azure_keyvault")
        monkeypatch.delenv("AZURE_KEYVAULT_URI", raising=False)
        with pytest.raises(SecretProviderError, match="AZURE_KEYVAULT_URI"):
            create_secret_provider()

    def test_default_production_without_uri_raises(self, monkeypatch):
        """Production environment without AZURE_KEYVAULT_URI raises."""
        monkeypatch.delenv("SECRET_PROVIDER", raising=False)
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("AZURE_KEYVAULT_URI", raising=False)
        with pytest.raises(SecretProviderError, match="AZURE_KEYVAULT_URI"):
            create_secret_provider()

    def test_explicit_azure_keyvault_with_uri(self, monkeypatch):
        """SECRET_PROVIDER=azure_keyvault with AZURE_KEYVAULT_URI creates provider."""
        monkeypatch.setenv("SECRET_PROVIDER", "azure_keyvault")
        monkeypatch.setenv("AZURE_KEYVAULT_URI", "https://kv-test.vault.azure.net/")
        with (
            patch(
                "app.services.keyvault_provider.AzureKeyVaultProvider._create_client"
            ) as mock_client,
            patch("asyncio.create_task") as mock_task,
        ):
            mock_client.return_value = MagicMock()
            mock_task.return_value = MagicMock()
            provider = create_secret_provider()
            from app.services.keyvault_provider import AzureKeyVaultProvider

            assert isinstance(provider, AzureKeyVaultProvider)

    def test_no_env_vars_defaults_to_env_provider(self, monkeypatch):
        """With no SECRET_PROVIDER or ENVIRONMENT set, defaults to env provider."""
        monkeypatch.delenv("SECRET_PROVIDER", raising=False)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        provider = create_secret_provider()
        assert isinstance(provider, EnvVarProvider)


# ──────────────────────────────────────────────────────────────────────────────
# AzureKeyVaultProvider Tests (Mocked)
# ──────────────────────────────────────────────────────────────────────────────


class TestAzureKeyVaultProvider:
    """Tests for the Azure Key Vault provider with mocked SecretClient.

    All Azure SDK calls are mocked at the _fetch_from_keyvault level since the
    azure-keyvault-secrets package may not be installed in the test environment.
    """

    @pytest.fixture
    def mock_provider(self):
        """Create an AzureKeyVaultProvider with mocked Azure client."""
        with (
            patch(
                "app.services.keyvault_provider.AzureKeyVaultProvider._create_client"
            ) as mock_create,
            patch("asyncio.create_task") as mock_task,
        ):
            mock_client = AsyncMock()
            mock_create.return_value = mock_client
            mock_task.return_value = MagicMock()

            from app.services.keyvault_provider import AzureKeyVaultProvider

            provider = AzureKeyVaultProvider(
                vault_uri="https://kv-test.vault.azure.net/",
                cache_ttl_seconds=300,
            )
            provider._client = mock_client
            yield provider, mock_client

    async def test_get_secret_cache_miss_fetches_from_kv(self, mock_provider):
        """On cache miss, fetches from Key Vault and caches the result."""
        provider, _mock_client = mock_provider

        with patch.object(
            provider, "_fetch_from_keyvault", new_callable=AsyncMock, return_value="my-secret-value"
        ) as mock_fetch:
            result = await provider.get_secret("test-secret")
            assert result == "my-secret-value"
            mock_fetch.assert_called_once_with("test-secret")
            # Verify it was cached
            assert "test-secret" in provider._cache
            assert provider._cache["test-secret"].value == "my-secret-value"

    async def test_get_secret_cache_hit(self, mock_provider):
        """Cached values are returned without calling Key Vault."""
        provider, _mock_client = mock_provider

        from app.services.keyvault_provider import CacheEntry

        provider._cache["cached-secret"] = CacheEntry(
            value="cached-value",
            fetched_at=time.monotonic(),
            expires_at=time.monotonic() + 300,
        )

        with patch.object(provider, "_fetch_from_keyvault", new_callable=AsyncMock) as mock_fetch:
            result = await provider.get_secret("cached-secret")
            assert result == "cached-value"
            mock_fetch.assert_not_called()

    async def test_get_secret_cache_expired(self, mock_provider):
        """Expired cache entries trigger a fresh fetch from Key Vault."""
        provider, _mock_client = mock_provider

        from app.services.keyvault_provider import CacheEntry

        provider._cache["expired-secret"] = CacheEntry(
            value="stale-value",
            fetched_at=time.monotonic() - 600,
            expires_at=time.monotonic() - 1,
        )

        with patch.object(
            provider, "_fetch_from_keyvault", new_callable=AsyncMock, return_value="fresh-value"
        ):
            result = await provider.get_secret("expired-secret")
            assert result == "fresh-value"

    async def test_graceful_degradation_serves_stale_cache(self, mock_provider):
        """When KV is unavailable but cache exists, serves stale cache."""
        provider, _mock_client = mock_provider

        from app.services.keyvault_provider import CacheEntry

        provider._cache["degraded-secret"] = CacheEntry(
            value="stale-but-usable",
            fetched_at=time.monotonic() - 600,
            expires_at=time.monotonic() - 1,
        )

        with patch.object(
            provider,
            "_fetch_from_keyvault",
            new_callable=AsyncMock,
            side_effect=Exception("Connection refused"),
        ):
            result = await provider.get_secret("degraded-secret")
            assert result == "stale-but-usable"

    async def test_hard_failure_no_cache(self, mock_provider):
        """When KV is unavailable and no cache exists, raises ServiceUnavailableError."""
        provider, _mock_client = mock_provider

        with patch.object(
            provider,
            "_fetch_from_keyvault",
            new_callable=AsyncMock,
            side_effect=Exception("Connection refused"),
        ):
            with pytest.raises(ServiceUnavailableError, match="no cached value"):
                await provider.get_secret("unknown-secret")

    async def test_get_secret_not_found(self, mock_provider):
        """When KV returns None (not found), returns None and caches it."""
        provider, _mock_client = mock_provider

        with patch.object(
            provider, "_fetch_from_keyvault", new_callable=AsyncMock, return_value=None
        ):
            result = await provider.get_secret("nonexistent")
            assert result is None
            # None values are also cached
            assert "nonexistent" in provider._cache

    async def test_set_secret(self, mock_provider):
        """set_secret calls the KV client and updates cache."""
        provider, mock_client = mock_provider
        mock_client.set_secret = AsyncMock(return_value=MagicMock())

        # Patch the import that happens inside set_secret
        with patch.dict("sys.modules", {"azure.keyvault.secrets.aio": MagicMock()}):
            await provider.set_secret("new-secret", "new-value")
            mock_client.set_secret.assert_called_once_with(
                "new-secret", "new-value", content_type="text/plain"
            )
            assert "new-secret" in provider._cache
            assert provider._cache["new-secret"].value == "new-value"

    async def test_delete_secret(self, mock_provider):
        """delete_secret calls begin_delete_secret and removes from cache."""
        provider, mock_client = mock_provider

        from app.services.keyvault_provider import CacheEntry

        provider._cache["to-delete"] = CacheEntry(
            value="val", fetched_at=time.monotonic(), expires_at=time.monotonic() + 300
        )

        mock_client.begin_delete_secret = AsyncMock(return_value=MagicMock())

        with patch.dict("sys.modules", {"azure.keyvault.secrets.aio": MagicMock()}):
            await provider.delete_secret("to-delete")
            mock_client.begin_delete_secret.assert_called_once_with("to-delete")
            assert "to-delete" not in provider._cache

    async def test_invalidate_cache(self, mock_provider):
        """invalidate_cache removes the entry from cache."""
        provider, _mock_client = mock_provider

        from app.services.keyvault_provider import CacheEntry

        provider._cache["cached"] = CacheEntry(
            value="val", fetched_at=time.monotonic(), expires_at=time.monotonic() + 300
        )

        await provider.invalidate_cache("cached")
        assert "cached" not in provider._cache

    async def test_close_sets_closed_flag(self, mock_provider):
        """close() sets the closed flag and closes the client."""
        provider, mock_client = mock_provider
        mock_client.close = AsyncMock()
        provider._refresh_task = None  # No background task

        with patch.dict("sys.modules", {"azure.keyvault.secrets.aio": MagicMock()}):
            await provider.close()
            assert provider._closed is True

    async def test_close_is_idempotent(self, mock_provider):
        """Calling close() twice does not raise."""
        provider, mock_client = mock_provider
        mock_client.close = AsyncMock()
        provider._refresh_task = None

        with patch.dict("sys.modules", {"azure.keyvault.secrets.aio": MagicMock()}):
            await provider.close()
            await provider.close()  # Second call should be no-op
            assert provider._closed is True

    async def test_health_state_records_failures(self, mock_provider):
        """Health state tracks consecutive failures."""
        provider, _mock_client = mock_provider

        with patch.object(
            provider,
            "_fetch_from_keyvault",
            new_callable=AsyncMock,
            side_effect=Exception("fail"),
        ):
            with pytest.raises(ServiceUnavailableError):
                await provider.get_secret("test")
            assert provider._health.consecutive_failures == 1

            with pytest.raises(ServiceUnavailableError):
                await provider.get_secret("test")
            assert provider._health.consecutive_failures == 2

    async def test_health_state_resets_on_success(self, mock_provider):
        """Health state resets after a successful operation."""
        provider, _mock_client = mock_provider

        # First fail
        with patch.object(
            provider,
            "_fetch_from_keyvault",
            new_callable=AsyncMock,
            side_effect=Exception("fail"),
        ):
            with pytest.raises(ServiceUnavailableError):
                await provider.get_secret("test")

        # Then succeed
        with patch.object(
            provider, "_fetch_from_keyvault", new_callable=AsyncMock, return_value="recovered"
        ):
            result = await provider.get_secret("test")
            assert result == "recovered"
            assert provider._health.consecutive_failures == 0

    async def test_cache_ttl_respected(self, mock_provider):
        """Cache entries respect the configured TTL."""
        provider, _mock_client = mock_provider

        with patch.object(
            provider, "_fetch_from_keyvault", new_callable=AsyncMock, return_value="value1"
        ):
            await provider.get_secret("ttl-test")
            entry = provider._cache["ttl-test"]
            assert entry.expires_at > time.monotonic()
            assert entry.expires_at <= time.monotonic() + 300


# ──────────────────────────────────────────────────────────────────────────────
# HealthState Unit Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestHealthState:
    """Tests for the HealthState alerting logic."""

    def test_initial_state(self):
        from app.services.keyvault_provider import HealthState

        state = HealthState()
        assert state.consecutive_failures == 0
        assert state.first_failure_at is None
        assert state.alert_fired is False

    def test_record_failure_increments(self):
        from app.services.keyvault_provider import HealthState

        state = HealthState()
        state.record_failure()
        assert state.consecutive_failures == 1
        assert state.first_failure_at is not None

    def test_record_success_resets(self):
        from app.services.keyvault_provider import HealthState

        state = HealthState()
        state.record_failure()
        state.record_failure()
        state.record_success()
        assert state.consecutive_failures == 0
        assert state.first_failure_at is None
        assert state.alert_fired is False

    def test_alert_fires_after_threshold(self):
        from app.services.keyvault_provider import HealthState

        state = HealthState()
        for _ in range(5):
            state.record_failure()
        assert state.alert_fired is True

    def test_alert_fires_only_once(self):
        from app.services.keyvault_provider import HealthState

        state = HealthState()
        for _ in range(10):
            state.record_failure()
        # alert_fired should still be True (not reset)
        assert state.alert_fired is True
