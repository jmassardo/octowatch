"""FastAPI dependency injection functions.

These are the building blocks for auth, database access, and rate limiting
used as FastAPI Depends() parameters throughout all routers.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from typing import Annotated

import redis.asyncio as aioredis
import structlog
from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_session

logger = structlog.get_logger(__name__)

# ─── Database ─────────────────────────────────────────────────────────────────


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yield an async SQLAlchemy session."""
    async for session in get_session():
        yield session


# ─── Valkey ───────────────────────────────────────────────────────────────────

# Module-level connection pool (created once, shared across requests)
_valkey_pool: aioredis.ConnectionPool | None = None


def get_valkey_pool() -> aioredis.ConnectionPool:
    global _valkey_pool
    if _valkey_pool is None:
        _valkey_pool = aioredis.ConnectionPool.from_url(
            settings.VALKEY_URL,
            decode_responses=True,
            max_connections=50,
        )
    return _valkey_pool


async def get_valkey() -> AsyncGenerator[aioredis.Redis, None]:
    """FastAPI dependency: yield a Valkey async client from the shared pool."""
    client: aioredis.Redis = aioredis.Redis(connection_pool=get_valkey_pool())
    try:
        yield client
    finally:
        await client.aclose()


# ─── Current User ─────────────────────────────────────────────────────────────


class AuthenticatedUser:
    """Resolved user context attached to each authenticated request."""

    def __init__(
        self,
        *,
        github_login: str,
        github_id: int,
        roles: list[str],
        scoped_orgs: list[str],
        scoped_repos: list[str],
        scope_type: str,
        jti: str,
        session_expires_at: str,
        display_name: str | None = None,
        email: str | None = None,
        avatar_url: str | None = None,
    ) -> None:
        self.github_login = github_login
        self.github_id = github_id
        self.roles = roles
        self.scoped_orgs = scoped_orgs
        self.scoped_repos = scoped_repos
        self.scope_type = scope_type
        self.jti = jti
        self.session_expires_at = session_expires_at
        self.display_name = display_name or github_login
        self.email = email
        self.avatar_url = avatar_url

    def has_role(self, *role_names: str) -> bool:
        """Return True if user holds any of the specified roles (or sys_admin)."""
        if "sys_admin" in self.roles:
            return True
        return any(r in self.roles for r in role_names)

    def has_permission(self, permission: str) -> bool:
        """Check permission string, e.g. 'events:read'. sys_admin has all."""
        if "sys_admin" in self.roles:
            return True
        return permission in self.roles  # simplified; full check in rbac_service


async def get_current_user(
    request: Request,
    access_token: Annotated[str | None, Cookie()] = None,
    valkey: aioredis.Redis = Depends(get_valkey),
) -> AuthenticatedUser:
    """
    Extract and validate JWT from HTTP-only cookie, verify Valkey session key
    exists, and return the resolved user. Raises HTTP 401 on any failure.
    """
    import jwt as pyjwt

    token = access_token or request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = pyjwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=["HS256"],
            options={"verify_exp": True},
        )
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
        ) from None
    except pyjwt.InvalidTokenError as exc:
        logger.warning("jwt.invalid", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        ) from exc

    jti = payload.get("jti")
    if not jti:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token structure",
        )

    # Verify session still exists in Valkey (supports immediate revocation)
    session_key = f"session:{jti}"
    session_data_raw = await valkey.get(session_key)
    if not session_data_raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session revoked or expired",
        )

    import json

    session_data = json.loads(session_data_raw)

    github_login = session_data["github_login"]
    roles: list[str] = list(session_data.get("roles", []))

    # Bootstrap: always grant sys_admin at request time for logins in INITIAL_ADMIN_LOGINS.
    # This means existing sessions get the role without needing to re-login.
    if github_login.lower() in settings.initial_admin_logins:
        if "sys_admin" not in roles:
            roles.append("sys_admin")

    scope_type = "global" if "sys_admin" in roles else session_data.get("scope_type", "scoped")

    return AuthenticatedUser(
        github_login=github_login,
        github_id=session_data.get("github_id", 0),
        roles=roles,
        scoped_orgs=session_data.get("scoped_orgs", []),
        scoped_repos=session_data.get("scoped_repos", []),
        scope_type=scope_type,
        jti=jti,
        session_expires_at=session_data.get("session_expires_at", ""),
        display_name=session_data.get("display_name"),
        email=session_data.get("email"),
        avatar_url=session_data.get("avatar_url"),
    )


# ─── RBAC Role Enforcement ────────────────────────────────────────────────────


def require_role(roles: list[str]) -> Callable[..., AuthenticatedUser]:
    """
    FastAPI dependency factory. Creates a dependency that ensures the current
    user has at least one of the specified roles (sys_admin always passes).

    Usage:
        @router.get("/events")
        async def list_events(
            user: AuthenticatedUser = Depends(require_role(["analyst", "sys_admin"])),
        ):
            ...
    """

    async def _check_role(
        user: AuthenticatedUser = Depends(get_current_user),
    ) -> AuthenticatedUser:
        if not user.has_role(*roles):
            logger.warning(
                "rbac.forbidden",
                user=user.github_login,
                required_roles=roles,
                user_roles=user.roles,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role required: one of {roles}",
            )
        return user

    return _check_role


# ─── CSRF Protection ─────────────────────────────────────────────────────────


async def verify_csrf(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
) -> None:
    """
    Verify CSRF double-submit cookie pattern for state-changing requests.
    Skipped on GET/HEAD/OPTIONS.
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return

    csrf_header = request.headers.get("X-CSRF-Token")
    csrf_cookie = request.cookies.get("csrf_token")
    if not csrf_header or not csrf_cookie:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token required",
        )
    import hmac as _hmac

    if not _hmac.compare_digest(csrf_header, csrf_cookie):
        logger.warning("csrf.mismatch", user=user.github_login, path=request.url.path)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token mismatch",
        )


# ─── Internal helpers (used by middleware, not DI) ───────────────────────────


def _get_valkey_pool() -> aioredis.ConnectionPool:
    """Expose the module-level pool for use in app startup lifespan."""
    return get_valkey_pool()


def _extract_jwt_payload(request: Request) -> dict | None:
    """Extract JWT payload without raising — used by AuditTrailMiddleware.

    Returns None if no token or token is invalid.
    """
    import jwt as pyjwt

    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        return pyjwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=["HS256"],
            options={"verify_exp": False},  # Don't raise on expiry in middleware
        )
    except Exception:
        return None
