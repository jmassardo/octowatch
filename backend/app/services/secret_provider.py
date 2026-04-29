"""Secret provider abstraction layer.

Defines the SecretProvider interface and factory function for selecting
the appropriate provider based on environment configuration.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

import structlog
from fastapi import Request

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class SecretMetadata:
    """Metadata about a stored secret (never contains the secret value)."""

    name: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
    content_type: str | None = None
    enabled: bool = True


class SecretProviderError(Exception):
    """Base exception for secret provider errors."""


class ServiceUnavailableError(SecretProviderError):
    """Raised when the secret backend is unavailable and no cached value exists."""


class SecretProvider(ABC):
    """Abstract interface for secret storage backends.

    Implementations must handle caching, error recovery, and cleanup.
    Secrets MUST NEVER be written to disk, database, or logs.
    """

    @abstractmethod
    async def get_secret(self, name: str) -> str | None:
        """Retrieve a secret value by name.

        Args:
            name: The secret identifier.

        Returns:
            The secret value, or None if not found.

        Raises:
            ServiceUnavailableError: If the backend is unavailable and no
                cached value exists.
        """

    @abstractmethod
    async def set_secret(self, name: str, value: str, **kwargs: str) -> None:
        """Store or update a secret.

        Args:
            name: The secret identifier.
            value: The secret value to store.
            **kwargs: Provider-specific options (e.g., content_type, tags).

        Raises:
            SecretProviderError: If the operation fails.
        """

    @abstractmethod
    async def delete_secret(self, name: str) -> None:
        """Delete a secret by name.

        Args:
            name: The secret identifier.

        Raises:
            SecretProviderError: If the operation fails.
        """

    @abstractmethod
    async def list_secrets(self) -> list[SecretMetadata]:
        """List all secret metadata (never values).

        Returns:
            List of SecretMetadata objects.
        """

    @abstractmethod
    async def invalidate_cache(self, name: str) -> None:
        """Invalidate the cached value for a specific secret.

        Args:
            name: The secret identifier to invalidate.
        """

    @abstractmethod
    async def close(self) -> None:
        """Release resources held by the provider.

        Called during application shutdown.
        """


def create_secret_provider() -> SecretProvider:
    """Create the appropriate SecretProvider based on environment configuration.

    Selection logic:
        - SECRET_PROVIDER=azure_keyvault → AzureKeyVaultProvider
        - SECRET_PROVIDER=env → EnvVarProvider
        - Not set → defaults based on ENVIRONMENT:
            - production → azure_keyvault
            - otherwise → env

    Returns:
        An initialized SecretProvider instance.
    """
    provider_type = os.environ.get("SECRET_PROVIDER", "").strip().lower()

    if not provider_type:
        environment = os.environ.get("ENVIRONMENT", "development").strip().lower()
        provider_type = "azure_keyvault" if environment == "production" else "env"

    if provider_type == "azure_keyvault":
        from app.services.keyvault_provider import AzureKeyVaultProvider

        vault_uri = os.environ.get("AZURE_KEYVAULT_URI", "")
        if not vault_uri:
            logger.error(
                "secret_provider.missing_vault_uri",
                detail="AZURE_KEYVAULT_URI must be set when using azure_keyvault provider",
            )
            raise SecretProviderError(
                "AZURE_KEYVAULT_URI environment variable is required for azure_keyvault provider"
            )
        logger.info("secret_provider.creating", provider="azure_keyvault", vault_uri=vault_uri)
        return AzureKeyVaultProvider(vault_uri=vault_uri)

    # Default: env provider
    logger.info("secret_provider.creating", provider="env")
    from app.services.env_provider import EnvVarProvider

    return EnvVarProvider()


def get_secret_provider(request: Request) -> SecretProvider:
    """FastAPI dependency: retrieve the SecretProvider from app state.

    Usage:
        @router.get("/example")
        async def example(
            provider: SecretProvider = Depends(get_secret_provider),
        ):
            secret = await provider.get_secret("my-secret")
    """
    return request.app.state.secret_provider  # type: ignore[no-any-return]
