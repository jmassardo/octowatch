"""Environment variable-based secret provider for local development.

Reads secrets from environment variables using a simple name mapping:
secret name → uppercase, dashes replaced with underscores.

Example: "hec-token" → "HEC_TOKEN"
"""

from __future__ import annotations

import os

import structlog

from app.services.secret_provider import SecretMetadata, SecretProvider

logger = structlog.get_logger(__name__)


class EnvVarProvider(SecretProvider):
    """Secret provider that reads from environment variables.

    Intended for local development where Azure authentication is not available.
    Secrets are read directly from the process environment with no caching.
    """

    def _to_env_var(self, name: str) -> str:
        """Convert a secret name to its environment variable equivalent.

        Args:
            name: Secret name (e.g., "hec-token", "github-webhook-secret").

        Returns:
            Environment variable name (e.g., "HEC_TOKEN", "GITHUB_WEBHOOK_SECRET").
        """
        return name.upper().replace("-", "_")

    async def get_secret(self, name: str) -> str | None:
        """Retrieve a secret from environment variables.

        Args:
            name: The secret identifier.

        Returns:
            The environment variable value, or None if not set.
        """
        env_var = self._to_env_var(name)
        value = os.environ.get(env_var)
        if value is not None:
            logger.debug("env_provider.get_secret", name=name, env_var=env_var, found=True)
        else:
            logger.debug("env_provider.get_secret", name=name, env_var=env_var, found=False)
        return value if value else None

    async def set_secret(self, name: str, value: str, **kwargs: str) -> None:
        """Set an environment variable (in-process only).

        Note: This only affects the current process environment.
        Changes are lost when the process exits.

        Args:
            name: The secret identifier.
            value: The secret value to store.
            **kwargs: Ignored for env provider.
        """
        env_var = self._to_env_var(name)
        os.environ[env_var] = value
        logger.info("env_provider.set_secret", name=name, env_var=env_var)

    async def delete_secret(self, name: str) -> None:
        """Remove an environment variable from the current process.

        Args:
            name: The secret identifier.
        """
        env_var = self._to_env_var(name)
        os.environ.pop(env_var, None)
        logger.info("env_provider.delete_secret", name=name, env_var=env_var)

    async def list_secrets(self) -> list[SecretMetadata]:
        """List secrets is not meaningfully supported for env vars.

        Returns an empty list since we cannot enumerate which env vars
        are "secrets" vs regular configuration.

        Returns:
            Empty list.
        """
        return []

    async def invalidate_cache(self, name: str) -> None:
        """No-op for env provider (no caching layer).

        Args:
            name: The secret identifier (ignored).
        """

    async def close(self) -> None:
        """No-op for env provider (no resources to release)."""
