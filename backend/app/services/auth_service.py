"""Authentication service: GitHub OAuth, SAML 2.0, JWT, and session management."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt as pyjwt
import redis.asyncio as aioredis
import structlog
from fastapi import HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

logger = structlog.get_logger(__name__)

GITHUB_OAUTH_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_OAUTH_ACCESS_URL = "https://github.com/login/oauth/access_token"
GITHUB_API_BASE = "https://api.github.com"


def create_jwt(
    github_login: str,
    github_id: int,
    jti: str,
) -> str:
    """Create a signed HS256 JWT for the given user."""
    now = datetime.now(UTC)
    payload = {
        "sub": github_login,
        "github_id": github_id,
        "jti": jti,
        "exp": now + timedelta(seconds=settings.JWT_TTL_SECONDS),
        "iat": now,
    }
    return pyjwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


async def store_session(
    valkey: aioredis.Redis,
    jti: str,
    github_login: str,
    github_id: int,
    roles: list[str],
    scoped_orgs: list[str],
    scoped_repos: list[str],
    scope_type: str,
) -> str:
    """Store session metadata in Valkey and return the session expiry timestamp."""
    expires_at = datetime.now(UTC) + timedelta(seconds=settings.JWT_TTL_SECONDS)
    session_data = {
        "github_login": github_login,
        "github_id": github_id,
        "roles": roles,
        "scoped_orgs": scoped_orgs,
        "scoped_repos": scoped_repos,
        "scope_type": scope_type,
        "session_expires_at": expires_at.isoformat(),
    }
    await valkey.setex(
        f"session:{jti}",
        settings.JWT_TTL_SECONDS,
        json.dumps(session_data),
    )
    return expires_at.isoformat()


async def revoke_session(valkey: aioredis.Redis, jti: str) -> None:
    """Delete a session key from Valkey (immediate revocation)."""
    await valkey.delete(f"session:{jti}")


def set_auth_cookies(
    response: Response,
    token: str,
    csrf_token: str,
) -> None:
    """Set HTTP-only JWT cookie and non-HTTP-only CSRF cookie."""
    secure = settings.ENVIRONMENT == "production" or settings.AUTH.APP_BASE_URL.startswith(
        "https://"
    )
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=secure,
        samesite="strict",
        max_age=settings.JWT_TTL_SECONDS,
        path="/",
    )
    # CSRF cookie is NOT http-only (JS must read it for Double-Submit pattern)
    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        httponly=False,
        secure=secure,
        samesite="strict",
        max_age=settings.JWT_TTL_SECONDS,
        path="/",
    )


def clear_auth_cookies(response: Response) -> None:
    """Remove auth cookies on logout."""
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("csrf_token", path="/")


# ─── GitHub OAuth ─────────────────────────────────────────────────────────────


def build_github_authorize_url(state: str) -> str:
    """Build GitHub OAuth authorization URL."""
    params = {
        "client_id": settings.AUTH.GITHUB_CLIENT_ID,
        "state": state,
        "scope": "read:org read:user",
        "redirect_uri": f"{settings.AUTH.APP_BASE_URL}/api/v1/auth/github/callback",
    }
    return f"{GITHUB_OAUTH_AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_github_code(code: str) -> dict[str, Any]:
    """Exchange OAuth authorization code for an access token."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                GITHUB_OAUTH_ACCESS_URL,
                data={
                    "client_id": settings.AUTH.GITHUB_CLIENT_ID,
                    "client_secret": settings.AUTH.GITHUB_CLIENT_SECRET,
                    "code": code,
                    # Must match the redirect_uri used in the authorization request
                    "redirect_uri": f"{settings.AUTH.APP_BASE_URL}/api/v1/auth/github/callback",
                },
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error("github_token_exchange_failed", status=exc.response.status_code)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="GitHub token exchange failed. Ensure your OAuth App callback URL is set to "
                f"{settings.AUTH.APP_BASE_URL}/api/v1/auth/github/callback",
            ) from exc
    data = resp.json()
    if "error" in data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"GitHub OAuth error: {data.get('error_description', data['error'])}",
        )
    return data  # type: ignore[return-value]


async def fetch_github_user(access_token: str) -> dict[str, Any]:
    """Fetch GitHub user profile."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{GITHUB_API_BASE}/user",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
    resp.raise_for_status()
    return resp.json()  # type: ignore[return-value]


async def fetch_github_orgs_and_teams(access_token: str) -> list[dict[str, Any]]:
    """Fetch all teams the user belongs to (requires read:org scope)."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{GITHUB_API_BASE}/user/teams",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            params={"per_page": 100},
        )
    if resp.status_code == 403:
        logger.warning("github.teams_forbidden", detail="read:org scope may be missing")
        return []
    resp.raise_for_status()
    return resp.json()  # type: ignore[return-value]


# ─── SAML 2.0 ────────────────────────────────────────────────────────────────


def get_saml_auth(request: Request) -> Any:  # type: ignore[return]
    """Build a python3-saml OneLogin_Saml2_Auth for the current request."""
    try:
        from onelogin.saml2.auth import OneLogin_Saml2_Auth  # type: ignore[import-untyped]
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SAML is not configured",
        ) from exc

    if not settings.AUTH.SAML_IDP_METADATA_URL:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SAML not configured (SAML_IDP_METADATA_URL not set)",
        )

    saml_settings = {
        "strict": True,
        "debug": settings.LOG_LEVEL == "DEBUG",
        "security": {
            "authnRequestsSigned": False,
            "wantAssertionsSigned": True,
            "wantMessagesSigned": True,
            "signatureAlgorithm": "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256",
        },
        "sp": {
            "entityId": f"{settings.AUTH.APP_BASE_URL}/api/v1/auth/saml/metadata",
            "assertionConsumerService": {
                "url": f"{settings.AUTH.APP_BASE_URL}/api/v1/auth/saml/acs",
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
            },
            "x509cert": settings.AUTH.SAML_SP_CERT or "",
            "privateKey": settings.AUTH.SAML_SP_KEY or "",
        },
        "idp": {
            "entityId": settings.AUTH.SAML_IDP_METADATA_URL,
            "singleSignOnService": {
                "url": settings.AUTH.SAML_IDP_METADATA_URL,
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
            },
            "x509cert": "",  # loaded from metadata at init
        },
    }

    # Build request dict that python3-saml expects
    request_data = {
        "https": "on" if request.url.scheme == "https" else "off",
        "http_host": request.headers.get("host", ""),
        "script_name": request.url.path,
        "get_data": dict(request.query_params),
        "post_data": {},  # populated by caller if POST
    }

    return OneLogin_Saml2_Auth(request_data, saml_settings)


async def is_auth_method_enabled(db: AsyncSession, method_name: str) -> bool:
    """Check whether the given auth method is enabled in the database.

    Returns ``True`` (enabled) if the table doesn't exist yet or the query
    fails — this ensures existing auth flows keep working before the migration
    has been applied.
    """
    try:
        from app.models.auth_method import AuthMethodConfig

        result = await db.execute(
            select(AuthMethodConfig.enabled).where(AuthMethodConfig.method_name == method_name)
        )
        row = result.scalar_one_or_none()
        return row if row is not None else True
    except Exception:
        return True
