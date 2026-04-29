"""Azure Key Vault secret provider with in-memory caching and background refresh.

Uses DefaultAzureCredential for authentication (supports Workload Identity,
Managed Identity, and local dev credentials like az cli).

Caching strategy:
- In-memory cache with configurable TTL (default: 5 minutes)
- Background refresh pre-fetches secrets within 60 seconds of expiry
- Graceful degradation: serves stale cache if Key Vault is temporarily unavailable
- Raises ServiceUnavailableError only when KV is down AND no cached value exists

Alerting:
- Logs warning after each failed attempt
- Logs critical alert after 5 consecutive failures or 5 minutes of unavailability
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import structlog

from app.services.secret_provider import (
    SecretMetadata,
    SecretProvider,
    SecretProviderError,
    ServiceUnavailableError,
)

logger = structlog.get_logger(__name__)

# Default cache TTL in seconds (5 minutes)
DEFAULT_CACHE_TTL_SECONDS = 300

# Refresh secrets this many seconds before TTL expiry
REFRESH_BEFORE_EXPIRY_SECONDS = 60

# Alert thresholds
MAX_CONSECUTIVE_FAILURES = 5
MAX_UNAVAILABILITY_SECONDS = 300  # 5 minutes


@dataclass
class CacheEntry:
    """A cached secret value with expiry metadata."""

    value: str | None
    fetched_at: float
    expires_at: float


@dataclass
class HealthState:
    """Tracks Key Vault availability for alerting."""

    consecutive_failures: int = 0
    first_failure_at: float | None = None
    alert_fired: bool = False

    def record_success(self) -> None:
        """Reset health state on successful operation."""
        if self.consecutive_failures > 0:
            logger.info(
                "keyvault_provider.recovered",
                after_failures=self.consecutive_failures,
            )
        self.consecutive_failures = 0
        self.first_failure_at = None
        self.alert_fired = False

    def record_failure(self) -> None:
        """Record a failure and fire alerts if thresholds are exceeded."""
        self.consecutive_failures += 1
        now = time.monotonic()
        if self.first_failure_at is None:
            self.first_failure_at = now

        unavailable_seconds = now - self.first_failure_at

        if not self.alert_fired and (
            self.consecutive_failures >= MAX_CONSECUTIVE_FAILURES
            or unavailable_seconds >= MAX_UNAVAILABILITY_SECONDS
        ):
            logger.critical(
                "keyvault_provider.prolonged_unavailability",
                consecutive_failures=self.consecutive_failures,
                unavailable_seconds=round(unavailable_seconds, 1),
                detail="Azure Key Vault has been unavailable beyond alert threshold",
            )
            self.alert_fired = True


class AzureKeyVaultProvider(SecretProvider):
    """Azure Key Vault-backed secret provider with caching and resilience.

    Args:
        vault_uri: The Key Vault URI (e.g., https://kv-octowatch-prod.vault.azure.net/).
        cache_ttl_seconds: Cache TTL in seconds. Defaults to 300 (5 minutes).
    """

    def __init__(
        self,
        vault_uri: str,
        cache_ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS,
    ) -> None:
        self._vault_uri = vault_uri
        self._cache_ttl = cache_ttl_seconds
        self._cache: dict[str, CacheEntry] = {}
        self._health = HealthState()
        self._refresh_task: asyncio.Task[None] | None = None
        self._closed = False
        self._client = self._create_client()

        # Start background refresh task
        self._refresh_task = asyncio.create_task(self._background_refresh())

    def _create_client(self) -> object:
        """Create the Azure Key Vault SecretClient with DefaultAzureCredential.

        Returns:
            An initialized SecretClient instance.
        """
        from azure.identity.aio import DefaultAzureCredential
        from azure.keyvault.secrets.aio import SecretClient

        credential = DefaultAzureCredential()
        return SecretClient(vault_url=self._vault_uri, credential=credential)

    @property
    def _secret_client(self) -> object:
        """Access the underlying SecretClient (typed as object for mypy compatibility)."""
        return self._client

    def _is_cache_valid(self, entry: CacheEntry) -> bool:
        """Check if a cache entry is still within its TTL."""
        return time.monotonic() < entry.expires_at

    def _should_refresh(self, entry: CacheEntry) -> bool:
        """Check if a cache entry should be proactively refreshed."""
        return time.monotonic() > (entry.expires_at - REFRESH_BEFORE_EXPIRY_SECONDS)

    async def get_secret(self, name: str) -> str | None:
        """Retrieve a secret from Key Vault with caching and graceful degradation.

        Args:
            name: The secret identifier.

        Returns:
            The secret value, or None if the secret does not exist.

        Raises:
            ServiceUnavailableError: If Key Vault is unavailable and no cached
                value exists for this secret.
        """
        # Check cache first
        cached = self._cache.get(name)
        if cached and self._is_cache_valid(cached):
            return cached.value

        # Try to fetch from Key Vault
        try:
            value = await self._fetch_from_keyvault(name)
            self._health.record_success()
            self._update_cache(name, value)
            return value
        except Exception as exc:
            self._health.record_failure()
            logger.warning(
                "keyvault_provider.fetch_failed",
                name=name,
                error=str(exc),
                consecutive_failures=self._health.consecutive_failures,
            )

            # Graceful degradation: serve stale cache if available
            if cached is not None:
                logger.warning(
                    "keyvault_provider.serving_stale_cache",
                    name=name,
                    stale_seconds=round(time.monotonic() - cached.expires_at, 1),
                )
                return cached.value

            # No cache available — hard failure
            raise ServiceUnavailableError(
                f"Key Vault unavailable and no cached value for secret '{name}'"
            ) from exc

    async def set_secret(self, name: str, value: str, **kwargs: str) -> None:
        """Store or update a secret in Key Vault.

        Args:
            name: The secret identifier.
            value: The secret value to store.
            **kwargs: Optional parameters (e.g., content_type).

        Raises:
            SecretProviderError: If the operation fails.
        """
        try:
            from azure.keyvault.secrets.aio import SecretClient

            client: SecretClient = self._client  # type: ignore[assignment]
            content_type = kwargs.get("content_type", "text/plain")
            await client.set_secret(name, value, content_type=content_type)
            self._health.record_success()
            self._update_cache(name, value)
            logger.info("keyvault_provider.secret_set", name=name)
        except Exception as exc:
            self._health.record_failure()
            logger.error("keyvault_provider.set_failed", name=name, error=str(exc))
            raise SecretProviderError(f"Failed to set secret '{name}'") from exc

    async def delete_secret(self, name: str) -> None:
        """Delete a secret from Key Vault (soft delete).

        Args:
            name: The secret identifier.

        Raises:
            SecretProviderError: If the operation fails.
        """
        try:
            from azure.keyvault.secrets.aio import SecretClient

            client: SecretClient = self._client  # type: ignore[assignment]
            await client.begin_delete_secret(name)
            self._health.record_success()
            self._cache.pop(name, None)
            logger.info("keyvault_provider.secret_deleted", name=name)
        except Exception as exc:
            self._health.record_failure()
            logger.error("keyvault_provider.delete_failed", name=name, error=str(exc))
            raise SecretProviderError(f"Failed to delete secret '{name}'") from exc

    async def list_secrets(self) -> list[SecretMetadata]:
        """List all secret metadata from Key Vault.

        Returns:
            List of SecretMetadata objects (never contains values).
        """
        try:
            from azure.keyvault.secrets.aio import SecretClient

            client: SecretClient = self._client  # type: ignore[assignment]
            secrets: list[SecretMetadata] = []
            async for props in client.list_properties_of_secrets():
                secrets.append(
                    SecretMetadata(
                        name=props.name or "",
                        created_at=props.created_on,
                        updated_at=props.updated_on,
                        content_type=props.content_type,
                        enabled=props.enabled if props.enabled is not None else True,
                    )
                )
            self._health.record_success()
            return secrets
        except Exception as exc:
            self._health.record_failure()
            logger.error("keyvault_provider.list_failed", error=str(exc))
            raise SecretProviderError("Failed to list secrets") from exc

    async def invalidate_cache(self, name: str) -> None:
        """Remove a specific secret from the cache, forcing next read from Key Vault.

        Args:
            name: The secret identifier to invalidate.
        """
        self._cache.pop(name, None)
        logger.debug("keyvault_provider.cache_invalidated", name=name)

    async def close(self) -> None:
        """Release resources: cancel background refresh and close the client."""
        if self._closed:
            return
        self._closed = True

        if self._refresh_task and not self._refresh_task.done():
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass

        try:
            from azure.keyvault.secrets.aio import SecretClient

            client: SecretClient = self._client  # type: ignore[assignment]
            await client.close()
        except Exception as exc:
            logger.warning("keyvault_provider.close_error", error=str(exc))

        logger.info("keyvault_provider.closed")

    async def _fetch_from_keyvault(self, name: str) -> str | None:
        """Fetch a single secret from Key Vault.

        Args:
            name: The secret identifier.

        Returns:
            The secret value, or None if the secret does not exist.
        """
        from azure.core.exceptions import ResourceNotFoundError
        from azure.keyvault.secrets.aio import SecretClient

        client: SecretClient = self._client  # type: ignore[assignment]
        try:
            secret = await client.get_secret(name)
            return secret.value
        except ResourceNotFoundError:
            return None

    def _update_cache(self, name: str, value: str | None) -> None:
        """Update the in-memory cache for a secret.

        Args:
            name: The secret identifier.
            value: The secret value (or None if not found).
        """
        now = time.monotonic()
        self._cache[name] = CacheEntry(
            value=value,
            fetched_at=now,
            expires_at=now + self._cache_ttl,
        )

    async def _background_refresh(self) -> None:
        """Background task that proactively refreshes cached secrets before expiry.

        Runs every 30 seconds and checks all cached entries. If an entry is
        within REFRESH_BEFORE_EXPIRY_SECONDS of expiring, it is re-fetched.
        """
        while not self._closed:
            try:
                await asyncio.sleep(30)
                if self._closed:
                    break

                for name, entry in list(self._cache.items()):
                    if self._closed:
                        break
                    if self._should_refresh(entry):
                        try:
                            value = await self._fetch_from_keyvault(name)
                            self._health.record_success()
                            self._update_cache(name, value)
                            logger.debug("keyvault_provider.background_refresh", name=name)
                        except Exception as exc:
                            self._health.record_failure()
                            logger.warning(
                                "keyvault_provider.background_refresh_failed",
                                name=name,
                                error=str(exc),
                            )
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("keyvault_provider.refresh_loop_error", error=str(exc))
                await asyncio.sleep(5)
