"""Integrations router: ticketing configs, notification configs, and IdP enrichment."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_db, require_role, verify_csrf
from app.models.integration import NotificationConfig, TicketingConfig
from app.schemas.integration import (
    IdpEnrichmentResponse,
    NotificationConfigCreate,
    NotificationConfigResponse,
    TicketingConfigCreate,
    TicketingConfigResponse,
)
from app.services.idp_service import auto_enrich_actor, get_enrichment

router = APIRouter(prefix="/integrations", tags=["integrations"])


# ─── Ticketing configurations ─────────────────────────────────────────────────


@router.get("/ticketing", response_model=list[TicketingConfigResponse])
async def list_ticketing_configs(
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> list[TicketingConfigResponse]:
    """List all ticketing platform configurations."""
    result = await db.execute(select(TicketingConfig).order_by(TicketingConfig.id))
    configs = result.scalars().all()
    return [TicketingConfigResponse.model_validate(c) for c in configs]


@router.post(
    "/ticketing",
    response_model=TicketingConfigResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_csrf)],
)
async def create_ticketing_config(
    payload: TicketingConfigCreate,
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> TicketingConfigResponse:
    """Register a new ticketing platform configuration (Jira or GitHub Issues)."""
    config = TicketingConfig(
        provider=payload.provider,
        display_name=payload.display_name,
        target=payload.target,
        project_key=payload.project_key,
        default_issue_type=payload.default_issue_type,
        severity_priority_map=payload.severity_priority_map,
        auto_create=payload.auto_create,
        auto_create_severities=payload.auto_create_severities,
        credential_env_var=payload.credential_env_var,
        enabled=payload.enabled,
        created_by=current_user.github_login,
    )
    db.add(config)
    await db.flush()
    return TicketingConfigResponse.model_validate(config)


@router.delete("/ticketing/{config_id}", dependencies=[Depends(verify_csrf)])
async def delete_ticketing_config(
    config_id: int,
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Delete a ticketing configuration."""
    result = await db.execute(select(TicketingConfig).where(TicketingConfig.id == config_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Config not found")
    await db.delete(config)
    await db.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─── Notification configurations ──────────────────────────────────────────────


@router.get("/notifications", response_model=list[NotificationConfigResponse])
async def list_notification_configs(
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> list[NotificationConfigResponse]:
    """List all notification channel configurations."""
    result = await db.execute(select(NotificationConfig).order_by(NotificationConfig.id))
    configs = result.scalars().all()
    return [NotificationConfigResponse.model_validate(c) for c in configs]


@router.post(
    "/notifications",
    response_model=NotificationConfigResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_csrf)],
)
async def create_notification_config(
    payload: NotificationConfigCreate,
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> NotificationConfigResponse:
    """Register a notification channel (Slack or email)."""
    config = NotificationConfig(
        channel_type=payload.channel_type,
        display_name=payload.display_name,
        target=payload.target,
        credential_env_var=payload.credential_env_var,
        notify_severities=payload.notify_severities,
        cooldown_seconds=payload.cooldown_seconds,
        enabled=payload.enabled,
        created_by=current_user.github_login,
    )
    db.add(config)
    await db.flush()
    return NotificationConfigResponse.model_validate(config)


@router.delete("/notifications/{config_id}", dependencies=[Depends(verify_csrf)])
async def delete_notification_config(
    config_id: int,
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Delete a notification configuration."""
    result = await db.execute(select(NotificationConfig).where(NotificationConfig.id == config_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Config not found")
    await db.delete(config)
    await db.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─── IdP enrichment ───────────────────────────────────────────────────────────


@router.get("/idp/{github_login}", response_model=IdpEnrichmentResponse)
async def get_actor_enrichment(
    github_login: str,
    current_user: AuthenticatedUser = Depends(require_role(["analyst", "sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> IdpEnrichmentResponse:
    """Get cached IdP enrichment data for a GitHub actor."""
    enrichment = await get_enrichment(db, actor=github_login)
    if not enrichment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No enrichment found for '{github_login}'",
        )
    return IdpEnrichmentResponse.model_validate(enrichment)


@router.post(
    "/idp/{github_login}/refresh",
    response_model=IdpEnrichmentResponse,
    dependencies=[Depends(verify_csrf)],
)
async def refresh_actor_enrichment(
    github_login: str,
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> IdpEnrichmentResponse:
    """Force a fresh enrichment fetch from the configured IdP."""
    enrichment = await auto_enrich_actor(db, actor=github_login)
    if not enrichment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No IdP data found for '{github_login}'",
        )
    return IdpEnrichmentResponse.model_validate(enrichment)
