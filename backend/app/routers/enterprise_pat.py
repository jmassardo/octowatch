"""Enterprise Classic PAT router — manage the GitHub classic PAT used for audit log sync.

All endpoints require ``sys_admin`` role. The token is stored encrypted in
the ``app_settings`` table under key ``enterprise_pat``.  The actual token
value is **never** returned to the frontend — only a masked representation.
"""

from __future__ import annotations

import re

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_db, require_permission, verify_csrf
from app.services.audit_service import log_action
from app.services.config_overlay import load_settings_overlay
from app.services.settings_service import delete_setting, get_setting, set_setting
from app.utils.client_ip import get_client_ip

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/admin/enterprise-pat", tags=["enterprise-pat"])

# ── Constants ─────────────────────────────────────────────────────────────────

SETTING_KEY = "enterprise_pat"
SETTING_CATEGORY = "github"
SETTING_SENSITIVITY = "critical"
SETTING_DESCRIPTION = "GitHub Enterprise classic PAT for audit log API access"

# Matches ghp_xxxx (classic) or github_pat_xxxx (fine-grained)
_PAT_RE = re.compile(r"^(ghp_[A-Za-z0-9_]{1,255}|github_pat_[A-Za-z0-9_]{1,255})$")


# ── Schemas ───────────────────────────────────────────────────────────────────


class EnterprisePATPayload(BaseModel):
    """Request body for saving a classic PAT."""

    token: str = Field(
        ...,
        min_length=4,
        max_length=300,
        description="GitHub classic PAT (ghp_… or github_pat_…)",
    )


class EnterprisePATStatus(BaseModel):
    """Response for GET — indicates whether a PAT is configured."""

    configured: bool
    masked: str | None = None


class EnterprisePATSaveResult(BaseModel):
    """Response after successfully saving a PAT."""

    status: str = "ok"
    masked: str


class EnterprisePATTestResult(BaseModel):
    """Response from testing the stored PAT against the audit log API."""

    status: str
    message: str | None = None
    scopes: str | None = None
    login: str | None = None


class EnterprisePATDeleteResult(BaseModel):
    """Response after deleting the stored PAT."""

    status: str = "ok"
    message: str = "Enterprise PAT removed"


# ── Helpers ───────────────────────────────────────────────────────────────────


def mask_token(token: str) -> str:
    """Return a masked representation of a PAT.

    Shows the first 4 and last 4 characters with ``****…`` in the middle.
    Tokens 8 characters or shorter are fully masked.
    """
    if len(token) <= 8:
        return "****"
    return token[:4] + "****..." + token[-4:]


async def _validate_token_with_github(token: str) -> dict[str, str]:
    """Call ``GET /user`` with the token to verify it is valid.

    Returns a dict with ``login`` and ``scopes`` on success.
    Raises :class:`HTTPException` on failure.
    """
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )

    if resp.status_code == 401:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Token is invalid or expired. GitHub returned 401.",
        )
    if resp.status_code == 403:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Token was rejected by GitHub (403 Forbidden).",
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"GitHub API returned unexpected status {resp.status_code}.",
        )

    scopes = resp.headers.get("x-oauth-scopes", "")
    data = resp.json()
    login = data.get("login", "unknown")
    return {"login": login, "scopes": scopes}


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("", response_model=EnterprisePATStatus)
async def get_enterprise_pat_status(
    current_user: AuthenticatedUser = Depends(require_permission("admin_settings", "admin")),
    db: AsyncSession = Depends(get_db),
) -> EnterprisePATStatus:
    """Check whether an enterprise PAT is configured. Never returns the raw token."""
    value = await get_setting(db, SETTING_KEY)
    if value is None:
        return EnterprisePATStatus(configured=False, masked=None)
    return EnterprisePATStatus(configured=True, masked=mask_token(value))


@router.put(
    "",
    response_model=EnterprisePATSaveResult,
    dependencies=[Depends(verify_csrf)],
)
async def save_enterprise_pat(
    payload: EnterprisePATPayload,
    request: Request,
    current_user: AuthenticatedUser = Depends(require_permission("admin_settings", "admin")),
    db: AsyncSession = Depends(get_db),
) -> EnterprisePATSaveResult:
    """Validate and store a GitHub classic PAT for audit log sync.

    The token format is checked, then validated against the GitHub API
    (``GET /user``).  If valid it is stored encrypted in the settings table.
    """
    token = payload.token.strip()

    # Format check
    if not _PAT_RE.match(token):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Invalid token format. Expected a classic PAT starting with "
                "'ghp_' or a fine-grained PAT starting with 'github_pat_'."
            ),
        )

    # Validate against GitHub
    github_info = await _validate_token_with_github(token)

    # Persist encrypted
    await set_setting(
        db,
        SETTING_KEY,
        token,
        category=SETTING_CATEGORY,
        sensitivity=SETTING_SENSITIVITY,
        description=SETTING_DESCRIPTION,
        changed_by=current_user.github_login,
    )

    # Also write to Key Vault if provider available
    if hasattr(request.app.state, "secret_provider"):
        try:
            await request.app.state.secret_provider.set_secret("octowatch--pat--enterprise", token)
        except Exception as exc:
            logger.warning("enterprise_pat.kv_write_failed", error=str(exc))

    # Refresh overlay so sync picks up the token immediately
    await load_settings_overlay(db)

    # Audit log
    ip = get_client_ip(request)
    await log_action(
        db,
        user_login=current_user.github_login,
        user_github_id=current_user.github_id,
        ip_address=ip,
        user_agent=request.headers.get("user-agent"),
        action_type="enterprise_pat.saved",
        resource_type="setting",
        resource_id=SETTING_KEY,
    )

    logger.info(
        "enterprise_pat.saved",
        github_login=github_info["login"],
        scopes=github_info["scopes"],
        changed_by=current_user.github_login,
    )

    return EnterprisePATSaveResult(status="ok", masked=mask_token(token))


@router.delete(
    "",
    response_model=EnterprisePATDeleteResult,
    dependencies=[Depends(verify_csrf)],
)
async def remove_enterprise_pat(
    request: Request,
    current_user: AuthenticatedUser = Depends(require_permission("admin_settings", "admin")),
    db: AsyncSession = Depends(get_db),
) -> EnterprisePATDeleteResult:
    """Remove the stored enterprise PAT."""
    deleted = await delete_setting(db, SETTING_KEY, changed_by=current_user.github_login)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No enterprise PAT is currently configured.",
        )

    # Also delete from Key Vault if provider available
    if hasattr(request.app.state, "secret_provider"):
        try:
            await request.app.state.secret_provider.delete_secret("octowatch--pat--enterprise")
        except Exception as exc:
            logger.warning("enterprise_pat.kv_delete_failed", error=str(exc))

    await load_settings_overlay(db)

    ip = get_client_ip(request)
    await log_action(
        db,
        user_login=current_user.github_login,
        user_github_id=current_user.github_id,
        ip_address=ip,
        user_agent=request.headers.get("user-agent"),
        action_type="enterprise_pat.deleted",
        resource_type="setting",
        resource_id=SETTING_KEY,
    )

    logger.info("enterprise_pat.deleted", changed_by=current_user.github_login)

    return EnterprisePATDeleteResult()


@router.post(
    "/test",
    response_model=EnterprisePATTestResult,
    dependencies=[Depends(verify_csrf)],
)
async def test_enterprise_pat(
    request: Request,
    current_user: AuthenticatedUser = Depends(require_permission("admin_settings", "admin")),
    db: AsyncSession = Depends(get_db),
) -> EnterprisePATTestResult:
    """Test the stored PAT by calling ``GET /user`` on GitHub.

    Returns the authenticated login name and granted scopes, so the admin
    can verify the token has the required ``admin:enterprise`` scope.
    """
    token = await get_setting(db, SETTING_KEY)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No enterprise PAT is currently configured.",
        )

    try:
        info = await _validate_token_with_github(token)
    except HTTPException as exc:
        return EnterprisePATTestResult(
            status="error",
            message=exc.detail if isinstance(exc.detail, str) else str(exc.detail),
        )

    ip = get_client_ip(request)
    await log_action(
        db,
        user_login=current_user.github_login,
        user_github_id=current_user.github_id,
        ip_address=ip,
        user_agent=request.headers.get("user-agent"),
        action_type="enterprise_pat.tested",
        resource_type="setting",
        resource_id=SETTING_KEY,
    )

    return EnterprisePATTestResult(
        status="ok",
        login=info["login"],
        scopes=info["scopes"],
    )
