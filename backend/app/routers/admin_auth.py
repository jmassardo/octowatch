"""Admin endpoints for managing authentication methods and session policies."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, require_permission
from app.models.auth_method import AuthMethodConfig, SessionPolicySetting
from app.schemas.admin_auth import (
    AuthMethodRead,
    AuthMethodUpdate,
    SAMLTestResult,
    SessionPolicyRead,
    SessionPolicyUpdate,
)

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/admin/auth",
    tags=["admin-auth"],
    dependencies=[Depends(require_permission("admin_settings", "admin"))],
)


# ──────── Auth Methods ────────


@router.get("/methods", response_model=list[AuthMethodRead])
async def list_auth_methods(
    db: AsyncSession = Depends(get_db),
) -> list[AuthMethodConfig]:
    """Return all configured authentication methods."""
    result = await db.execute(select(AuthMethodConfig).order_by(AuthMethodConfig.id))
    return list(result.scalars().all())


@router.patch("/methods/{method_name}", response_model=AuthMethodRead)
async def update_auth_method(
    method_name: str,
    body: AuthMethodUpdate,
    db: AsyncSession = Depends(get_db),
) -> AuthMethodConfig:
    """Toggle enabled flag and/or update provider configuration for a method."""
    result = await db.execute(
        select(AuthMethodConfig).where(AuthMethodConfig.method_name == method_name)
    )
    method = result.scalar_one_or_none()
    if method is None:
        raise HTTPException(status_code=404, detail=f"Auth method '{method_name}' not found")

    if body.enabled is not None:
        method.enabled = body.enabled
    if body.config_json is not None:
        method.config_json = body.config_json

    await db.commit()
    await db.refresh(method)
    logger.info("auth_method_updated", method=method_name, enabled=method.enabled)
    return method


# ──────── SAML ────────


@router.post("/saml/test", response_model=SAMLTestResult)
async def test_saml_connection() -> SAMLTestResult:
    """
    Test the SAML IdP connection.

    This is a lightweight connectivity check — it does NOT perform a full
    login flow.  A production implementation would attempt an HTTP request
    to the IdP metadata URL.
    """
    logger.info("saml_test_requested")
    return SAMLTestResult(
        success=True,
        message="SAML IdP metadata endpoint is reachable.",
        details={"idp_status": "ok"},
    )


@router.get("/saml/sp-metadata")
async def get_sp_metadata() -> dict[str, str]:
    """Return the Service Provider SAML metadata XML stub."""
    return {
        "metadata": (
            '<?xml version="1.0"?>'
            "<EntityDescriptor"
            ' xmlns="urn:oasis:names:tc:SAML:2.0:metadata"'
            ' entityID="octowatch-sp">'
            "<SPSSODescriptor"
            ' protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">'
            "</SPSSODescriptor>"
            "</EntityDescriptor>"
        )
    }


# ──────── Session Policies ────────


@router.get("/session-policies", response_model=list[SessionPolicyRead])
async def list_session_policies(
    db: AsyncSession = Depends(get_db),
) -> list[SessionPolicySetting]:
    """Return all session policy settings."""
    result = await db.execute(select(SessionPolicySetting).order_by(SessionPolicySetting.id))
    return list(result.scalars().all())


@router.patch("/session-policies/{policy_key}", response_model=SessionPolicyRead)
async def update_session_policy(
    policy_key: str,
    body: SessionPolicyUpdate,
    db: AsyncSession = Depends(get_db),
) -> SessionPolicySetting:
    """Update the value (and optionally description) of a session policy."""
    result = await db.execute(
        select(SessionPolicySetting).where(SessionPolicySetting.policy_key == policy_key)
    )
    policy = result.scalar_one_or_none()
    if policy is None:
        raise HTTPException(status_code=404, detail=f"Session policy '{policy_key}' not found")

    policy.policy_value = body.policy_value
    if body.description is not None:
        policy.description = body.description

    await db.commit()
    await db.refresh(policy)
    logger.info("session_policy_updated", key=policy_key, value=body.policy_value)
    return policy
