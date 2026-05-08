"""User profile and preferences router.

Endpoints for viewing the current user's profile, managing personal
preferences, and listing/revoking active sessions.
"""

from __future__ import annotations

import json
from typing import Any, cast

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from redis.asyncio import Redis

from app.deps import AuthenticatedUser, get_current_user, get_valkey, verify_csrf
from app.schemas.user_preferences import (
    LoginHistoryEntry,
    SessionInfo,
    SessionListResponse,
    SessionRevokeResponse,
    UserPreferences,
    UserProfileResponse,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/user", tags=["user"])

# Valkey key helpers
_PREFS_KEY = "user_prefs:{login}"
_LOGIN_HISTORY_KEY = "user_login_history:{login}"
_SESSION_INDEX_KEY = "user_sessions:{login}"


def _prefs_key(login: str) -> str:
    return _PREFS_KEY.format(login=login)


def _login_history_key(login: str) -> str:
    return _LOGIN_HISTORY_KEY.format(login=login)


def _session_index_key(login: str) -> str:
    return _SESSION_INDEX_KEY.format(login=login)


# ─── Valkey helpers ───────────────────────────────────────────────────────────
# redis-py async command methods have union return types
# (Awaitable[T] | T) that mypy strict cannot narrow through await.
# These thin wrappers accept the client as Any to keep call-sites typed.


async def _lrange(client: Any, key: str, start: int, end: int) -> list[str]:
    """Typed wrapper around Redis LRANGE."""
    result = await client.lrange(key, start, end)
    return cast(list[str], result)


async def _smembers(client: Any, key: str) -> set[str]:
    """Typed wrapper around Redis SMEMBERS."""
    result = await client.smembers(key)
    return cast(set[str], result)


async def _sismember(client: Any, key: str, value: str) -> bool:
    """Typed wrapper around Redis SISMEMBER."""
    result = await client.sismember(key, value)
    return cast(bool, result)


async def _srem(client: Any, key: str, *values: str) -> int:
    """Typed wrapper around Redis SREM."""
    result = await client.srem(key, *values)
    return cast(int, result)


@router.get("/profile", response_model=UserProfileResponse)
async def get_user_profile(
    current_user: AuthenticatedUser = Depends(get_current_user),
    valkey: Redis = Depends(get_valkey),
) -> UserProfileResponse:
    """Return the current user's full profile including login history."""
    login = current_user.github_login

    # Fetch login history from Valkey (last 5 entries)
    raw_history = await _lrange(valkey, _login_history_key(login), 0, 4)
    login_history: list[LoginHistoryEntry] = []
    for entry_raw in raw_history:
        try:
            entry_data = json.loads(entry_raw)
            login_history.append(LoginHistoryEntry(**entry_data))
        except (json.JSONDecodeError, TypeError):
            continue

    return UserProfileResponse(
        github_login=current_user.github_login,
        github_id=current_user.github_id,
        display_name=current_user.display_name or current_user.github_login,
        email=current_user.email,
        avatar_url=current_user.avatar_url,
        roles=current_user.roles,
        scoped_orgs=current_user.scoped_orgs,
        scoped_repos=current_user.scoped_repos,
        scope_type=current_user.scope_type,
        login_history=login_history,
        session_expires_at=current_user.session_expires_at,
    )


@router.get("/preferences", response_model=UserPreferences)
async def get_user_preferences(
    current_user: AuthenticatedUser = Depends(get_current_user),
    valkey: Redis = Depends(get_valkey),
) -> UserPreferences:
    """Return the current user's saved preferences."""
    raw = await valkey.get(_prefs_key(current_user.github_login))
    if raw:
        try:
            data = json.loads(raw)
            return UserPreferences(**data)
        except (json.JSONDecodeError, TypeError):
            logger.warning(
                "user_preferences.parse_error",
                user=current_user.github_login,
            )
    return UserPreferences()


@router.put(
    "/preferences",
    response_model=UserPreferences,
    dependencies=[Depends(verify_csrf)],
)
async def update_user_preferences(
    prefs: UserPreferences,
    current_user: AuthenticatedUser = Depends(get_current_user),
    valkey: Redis = Depends(get_valkey),
) -> UserPreferences:
    """Update the current user's preferences."""
    key = _prefs_key(current_user.github_login)
    await valkey.set(key, prefs.model_dump_json())
    logger.info(
        "user_preferences.updated",
        user=current_user.github_login,
    )
    return prefs


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(
    current_user: AuthenticatedUser = Depends(get_current_user),
    valkey: Redis = Depends(get_valkey),
) -> SessionListResponse:
    """List the current user's active sessions."""
    login = current_user.github_login
    current_jti = current_user.jti

    # Get all session JTIs for this user
    session_jtis = await _smembers(valkey, _session_index_key(login))

    sessions: list[SessionInfo] = []
    for jti in session_jtis:
        session_key = f"session:{jti}"
        raw = await valkey.get(session_key)
        if not raw:
            # Session expired; clean up the index
            await _srem(valkey, _session_index_key(login), jti)
            continue

        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue

        sessions.append(
            SessionInfo(
                session_id=str(jti),
                ip_address=data.get("ip_address"),
                user_agent=data.get("user_agent"),
                created_at=data.get("created_at"),
                expires_at=data.get("session_expires_at"),
                is_current=(str(jti) == current_jti),
            )
        )

    # Sort: current session first, then by created_at descending
    sessions.sort(key=lambda s: (not s.is_current, s.created_at or ""), reverse=False)
    return SessionListResponse(sessions=sessions)


@router.delete(
    "/sessions/{session_id}",
    response_model=SessionRevokeResponse,
    dependencies=[Depends(verify_csrf)],
)
async def revoke_session(
    session_id: str,
    request: Request,
    current_user: AuthenticatedUser = Depends(get_current_user),
    valkey: Redis = Depends(get_valkey),
) -> SessionRevokeResponse:
    """Revoke a specific session. Cannot revoke your own current session."""
    if session_id == current_user.jti:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot revoke your current session. Use logout instead.",
        )

    # Verify session belongs to this user
    login = current_user.github_login
    is_member = await _sismember(valkey, _session_index_key(login), session_id)
    if not is_member:
        # Also check if the session key exists (for users without session index)
        session_key = f"session:{session_id}"
        raw = await valkey.get(session_key)
        if not raw:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found",
            )
        try:
            data = json.loads(raw)
            if data.get("github_login") != login:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Session not found",
                )
        except (json.JSONDecodeError, TypeError):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found",
            ) from None

    # Delete session from Valkey
    session_key = f"session:{session_id}"
    await valkey.delete(session_key)
    await _srem(valkey, _session_index_key(login), session_id)

    logger.info(
        "user_session.revoked",
        user=login,
        revoked_session=session_id,
    )
    return SessionRevokeResponse(status="revoked")
