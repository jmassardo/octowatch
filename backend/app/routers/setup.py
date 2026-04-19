"""Setup wizard router — first-run configuration endpoints.

These endpoints are ONLY available when setup has not been completed.
After setup is complete, all endpoints (except ``/setup/status``) return 403.
"""

from __future__ import annotations

import json
import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.deps import AuthenticatedUser, get_db, get_valkey, require_role
from app.models.user import RbacRole, UserRoleAssignment
from app.rate_limit import limiter
from app.schemas.setup import (
    GitHubAppSetup,
    GitHubOAuthSetup,
    InitialAdminsSetup,
    SetupLoginRequest,
    SetupStatusResponse,
    TLSSetup,
)
from app.services.config_overlay import load_settings_overlay
from app.services.settings_service import (
    complete_setup,
    is_setup_complete,
    set_setting,
    verify_setup_token,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/setup", tags=["setup"])


async def _require_setup_incomplete(db: AsyncSession) -> None:
    """Raise 403 if setup is already complete."""
    if await is_setup_complete(db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Setup has already been completed",
        )


async def _count_admin_assignments(db: AsyncSession) -> int:
    """Return the number of active sys_admin role assignments created by the setup wizard."""
    result = await db.execute(
        select(func.count())
        .select_from(UserRoleAssignment)
        .join(RbacRole, UserRoleAssignment.role_id == RbacRole.id)
        .where(
            RbacRole.name == "sys_admin",
            UserRoleAssignment.granted_by == "setup_wizard",
            UserRoleAssignment.active.is_(True),
        )
    )
    return result.scalar_one()


@router.get("/status", response_model=SetupStatusResponse)
async def setup_status(db: AsyncSession = Depends(get_db)) -> SetupStatusResponse:
    """Check if setup is needed. No authentication required."""
    complete = await is_setup_complete(db)
    return SetupStatusResponse(
        setup_required=not complete,
        setup_hint="Check container logs for the setup credential" if not complete else "",
    )


@router.post("/login", response_model=dict[str, Any])
@limiter.limit("5/minute")
async def setup_login(
    payload: SetupLoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    valkey: Redis = Depends(get_valkey),
) -> dict[str, str]:
    """Authenticate with setup token. Returns JWT session cookie.

    This endpoint creates a temporary ``sys_admin`` session that is valid
    only until the setup is completed.
    """
    await _require_setup_incomplete(db)

    if not await verify_setup_token(db, payload.token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid setup token",
        )

    # Create a temporary session for the setup wizard
    import jwt as pyjwt

    jti = str(uuid.uuid4())
    now = datetime.now(UTC)
    exp = int(now.timestamp()) + settings.JWT_TTL_SECONDS
    jwt_payload = {
        "sub": "setup_admin",
        "github_id": 0,
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": exp,
    }
    token = pyjwt.encode(jwt_payload, settings.SECRET_KEY, algorithm="HS256")

    # Store session in Valkey
    session_data = {
        "github_login": "setup_admin",
        "github_id": 0,
        "roles": ["sys_admin"],
        "scoped_orgs": [],
        "scoped_repos": [],
        "scope_type": "global",
        "session_expires_at": datetime.fromtimestamp(exp, tz=UTC).isoformat(),
        "display_name": "Setup Administrator",
    }
    await valkey.setex(
        f"session:{jti}",
        settings.JWT_TTL_SECONDS,
        json.dumps(session_data),
    )

    # Set cookies
    csrf_token = secrets.token_urlsafe(32)
    response.set_cookie(
        "access_token",
        token,
        httponly=True,
        samesite="lax",
        secure=True,
        max_age=settings.JWT_TTL_SECONDS,
    )
    response.set_cookie(
        "csrf_token",
        csrf_token,
        httponly=False,
        samesite="lax",
        secure=True,
        max_age=settings.JWT_TTL_SECONDS,
    )
    return {"status": "ok", "message": "Setup session created"}


@router.get("/current", response_model=dict[str, Any])
async def setup_current_config(
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """Get current configuration state for the wizard."""
    await _require_setup_incomplete(db)

    return {
        "github_oauth_configured": bool(
            settings.AUTH.GITHUB_CLIENT_ID and settings.AUTH.GITHUB_CLIENT_ID != "CHANGE_ME"
        ),
        "github_app_configured": bool(settings.GITHUB_APP.GITHUB_APP_ID),
        "saml_configured": bool(settings.AUTH.SAML_IDP_METADATA_URL),
        "initial_admins_configured": bool(await _count_admin_assignments(db)),
    }


@router.post("/github-oauth", response_model=dict[str, Any])
async def setup_github_oauth(
    payload: GitHubOAuthSetup,
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Step 1: Configure GitHub OAuth credentials."""
    await _require_setup_incomplete(db)

    await set_setting(
        db,
        "github_client_id",
        payload.client_id,
        category="github_oauth",
        sensitivity="sensitive",
        description="GitHub OAuth App client ID",
        changed_by=current_user.github_login,
    )
    await set_setting(
        db,
        "github_client_secret",
        payload.client_secret,
        category="github_oauth",
        sensitivity="critical",
        description="GitHub OAuth App client secret",
        changed_by=current_user.github_login,
    )
    return {"status": "ok", "message": "GitHub OAuth configured"}


@router.post("/github-app", response_model=dict[str, Any])
async def setup_github_app(
    payload: GitHubAppSetup,
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Step 2: Configure GitHub App credentials."""
    await _require_setup_incomplete(db)

    await set_setting(
        db,
        "github_app_id",
        payload.app_id,
        category="github_app",
        sensitivity="config",
        description="GitHub App numeric ID",
        changed_by=current_user.github_login,
    )
    await set_setting(
        db,
        "github_app_private_key",
        payload.private_key_pem,
        category="github_app",
        sensitivity="critical",
        description="GitHub App PEM-encoded private key",
        changed_by=current_user.github_login,
    )
    await set_setting(
        db,
        "github_enterprise_slug",
        payload.enterprise_slug,
        category="github_app",
        sensitivity="config",
        description="GitHub Enterprise account slug",
        changed_by=current_user.github_login,
    )
    await set_setting(
        db,
        "github_sync_enabled",
        str(payload.sync_enabled).lower(),
        category="github_app",
        sensitivity="config",
        description="Enable/disable GitHub Enterprise sync",
        changed_by=current_user.github_login,
    )
    await set_setting(
        db,
        "github_sync_interval_days",
        str(payload.sync_interval_days),
        category="github_app",
        sensitivity="config",
        description="Sync interval in days",
        changed_by=current_user.github_login,
    )
    if payload.sync_orgs:
        await set_setting(
            db,
            "github_sync_orgs",
            payload.sync_orgs,
            category="github_app",
            sensitivity="config",
            description="Comma-separated org logins for sync",
            changed_by=current_user.github_login,
        )
    return {"status": "ok", "message": "GitHub App configured"}


@router.post("/tls", response_model=dict[str, Any])
async def setup_tls(
    payload: TLSSetup,
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Step 3: Configure TLS certificates."""
    await _require_setup_incomplete(db)

    if payload.generate_self_signed:
        # Generate a self-signed certificate
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes as crypto_hashes
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = x509.Name(
            [
                x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "OctoWatch"),
            ]
        )
        import datetime as dt

        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(dt.datetime.now(dt.UTC))
            .not_valid_after(dt.datetime.now(dt.UTC) + dt.timedelta(days=365))
            .sign(key, crypto_hashes.SHA256())
        )
        cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()
        key_pem = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        ).decode()
    elif payload.cert_pem and payload.key_pem:
        cert_pem = payload.cert_pem
        key_pem = payload.key_pem
    else:
        return {"status": "skipped", "message": "No TLS configuration provided"}

    await set_setting(
        db,
        "tls_cert_pem",
        cert_pem,
        category="tls",
        sensitivity="config",
        description="TLS certificate (PEM)",
        changed_by=current_user.github_login,
    )
    await set_setting(
        db,
        "tls_key_pem",
        key_pem,
        category="tls",
        sensitivity="critical",
        description="TLS private key (PEM)",
        changed_by=current_user.github_login,
    )
    return {"status": "ok", "message": "TLS configured"}


@router.post("/initial-admins", response_model=dict[str, Any])
async def setup_initial_admins(
    payload: InitialAdminsSetup,
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Step 4: Designate initial system administrators by GitHub login.

    Creates DB-backed ``sys_admin`` role assignments for each specified login.
    This replaces the old ``INITIAL_ADMIN_LOGINS`` environment variable so that
    admin access is managed through the database rather than a permanent runtime
    backdoor.
    """
    await _require_setup_incomplete(db)

    # Look up the sys_admin role ID
    result = await db.execute(select(RbacRole).where(RbacRole.name == "sys_admin"))
    sys_admin_role = result.scalar_one_or_none()
    if not sys_admin_role:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="sys_admin role not found in database",
        )

    # Create UserRoleAssignment for each login
    for login in payload.admin_logins:
        assignment = UserRoleAssignment(
            github_login=login.strip().lower(),
            role_id=sys_admin_role.id,
            scope_type="global",
            scope_value=None,
            granted_by="setup_wizard",
            active=True,
        )
        db.add(assignment)

    await db.commit()
    return {
        "status": "ok",
        "message": f"Granted sys_admin to {len(payload.admin_logins)} users",
    }


@router.post("/complete", response_model=dict[str, Any])
@limiter.limit("3/minute")
async def setup_complete_endpoint(
    request: Request,
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str | int]:
    """Mark setup as complete. Applies settings overlay and invalidates setup token."""
    await _require_setup_incomplete(db)

    # Apply the settings overlay now
    count = await load_settings_overlay(db)
    await complete_setup(db, completed_by=current_user.github_login)

    return {
        "status": "ok",
        "message": "Setup completed successfully",
        "settings_applied": count,
    }
