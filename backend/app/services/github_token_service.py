"""GitHub App authentication service.

Manages RS256 JWT generation and installation access token exchange.
Tokens are cached in Valkey with TTL = (expires_at − 5 minutes) to ensure
they are always valid for at least 5 minutes from the time of retrieval.

Security invariants:
  - The private key is loaded from the filesystem at construction time.
    The path is sourced from settings.github_app.GITHUB_APP_PRIVATE_KEY_PATH.
  - The private key is NEVER written to the database, logs, or API responses.
  - Installation access tokens are NEVER written to the database.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime

import httpx
import jwt  # PyJWT ≥ 2.x
import structlog
from redis.asyncio import Redis

logger = structlog.get_logger(__name__)

_GITHUB_API_BASE = "https://api.github.com"  # never interpolated from user input


@dataclass(frozen=True)
class InstallationToken:
    token: str
    expires_at: datetime  # UTC-aware


class GitHubAppTokenManager:
    """Generates GitHub App JWTs and exchanges them for installation access tokens.

    Parameters
    ----------
    app_id:
        The GitHub App's numeric App ID (from GitHub App settings page).
    private_key_pem:
        PEM-encoded RSA private key contents (already loaded from disk by
        the caller — this class never touches the filesystem at call time).
    valkey_client:
        An async redis.asyncio.Redis client used for token caching.
    """

    #: Cache key pattern — interpolated with installation_id (int only)
    _CACHE_KEY = "github:app:token:{installation_id}"
    #: Buffer in seconds subtracted from token TTL to force early refresh
    _TTL_BUFFER_SECS = 300  # 5 minutes

    def __init__(
        self,
        app_id: int,
        private_key_pem: str,
        valkey_client: Redis,
    ) -> None:
        self._app_id = app_id
        self._private_key_pem = private_key_pem
        self._valkey = valkey_client

    # ── Public API ────────────────────────────────────────────────────────────

    async def get_installation_token(self, installation_id: int) -> str:
        """Return a valid installation access token for *installation_id*.

        Algorithm:
          1. Check Valkey cache key ``github:app:token:{installation_id}``.
          2. Cache HIT → decode JSON, return ``token`` field.
          3. Cache MISS → generate RS256 JWT, POST to GitHub API to exchange for
             an installation token, store in Valkey with TTL, return token.

        The Valkey TTL is set to ``expires_at − now − _TTL_BUFFER_SECS`` so the
        cached token is evicted before it expires.

        Parameters
        ----------
        installation_id:
            Numeric GitHub App installation ID for the target org/enterprise.

        Returns
        -------
        str
            An opaque GitHub API access token valid for ≥ 5 minutes.

        Raises
        ------
        GitHubAuthError
            If GitHub rejects the JWT or returns a non-2xx status.
        """
        cache_key = self._CACHE_KEY.format(installation_id=installation_id)

        cached = await self._valkey.get(cache_key)
        if cached:
            # Decode and return without touching GitHub API
            data: dict[str, str] = json.loads(cached)
            logger.debug("github_token.cache_hit", installation_id=installation_id)
            return data["token"]

        logger.info("github_token.cache_miss", installation_id=installation_id)
        app_jwt = self._generate_jwt()
        installation_token = await self._exchange_jwt_for_token(app_jwt, installation_id)

        ttl = int((installation_token.expires_at.timestamp() - time.time()) - self._TTL_BUFFER_SECS)
        if ttl > 0:
            await self._valkey.set(
                cache_key,
                json.dumps(
                    {
                        "token": installation_token.token,
                        "expires_at": installation_token.expires_at.isoformat(),
                    }
                ),
                ex=ttl,
            )

        return installation_token.token

    # ── Private methods ───────────────────────────────────────────────────────

    def _generate_jwt(self) -> str:
        """Generate a short-lived RS256 JWT for GitHub App authentication.

        Claims:
          - ``iss`` (issuer): the App ID as a string
          - ``iat`` (issued at): ``now − 60s`` to account for clock skew
          - ``exp`` (expiry): ``now + 600s`` (10 minutes; GitHub max is 10 min)

        The JWT is signed with the RS256 algorithm using the app's RSA private
        key.  It is valid for use as a ``Bearer`` token in calls to
        ``GET /app/installations/{installation_id}/access_tokens``.

        Returns
        -------
        str
            A compact, Base64URL-encoded JWT string.
        """
        now = int(time.time())
        payload = {
            "iat": now - 60,  # back-date 60s for clock skew tolerance
            "exp": now + 600,  # 10 minutes (GitHub maximum)
            "iss": str(self._app_id),
        }
        return jwt.encode(payload, self._private_key_pem, algorithm="RS256")

    async def _exchange_jwt_for_token(
        self,
        app_jwt: str,
        installation_id: int,
    ) -> InstallationToken:
        """Exchange a GitHub App JWT for an installation access token.

        POSTs to ``https://api.github.com/app/installations/{id}/access_tokens``.
        The URL is constructed from the hard-coded base constant — never from
        user-supplied data — to prevent SSRF.

        Parameters
        ----------
        app_jwt:
            Short-lived RS256 JWT generated by ``_generate_jwt()``.
        installation_id:
            Numeric installation ID whose token is being requested.

        Returns
        -------
        InstallationToken
            Dataclass with ``token`` (str) and ``expires_at`` (UTC datetime).

        Raises
        ------
        GitHubAuthError
            On non-2xx GitHub API response.
        """
        # URL constructed from a hard-coded constant — SSRF safe
        url = f"{_GITHUB_API_BASE}/app/installations/{int(installation_id)}/access_tokens"
        headers = {
            "Authorization": f"Bearer {app_jwt}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        # follow_redirects=False prevents SSRF via redirect chain
        async with httpx.AsyncClient(follow_redirects=False) as client:
            response = await client.post(url, headers=headers)

        if response.status_code != 201:
            logger.error(
                "github_token.exchange_failed",
                status=response.status_code,
                installation_id=installation_id,
            )
            raise GitHubAuthError(
                f"GitHub returned {response.status_code} for installation {installation_id}"
            )

        data = response.json()
        expires_at = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
        return InstallationToken(token=data["token"], expires_at=expires_at)


class GitHubAuthError(RuntimeError):
    """Raised when GitHub App authentication or token exchange fails."""
