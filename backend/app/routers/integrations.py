"""Integrations router: ticketing configs, notification configs, IdP enrichment, and SIEM export."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_db, require_role, verify_csrf
from app.models.integration import NotificationConfig, SiemExportConfig, TicketingConfig
from app.schemas.integration import (
    BatchExportRequest,
    IdpEnrichmentResponse,
    NotificationConfigCreate,
    NotificationConfigResponse,
    SiemExportConfigCreate,
    SiemExportConfigResponse,
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


# ─── SIEM export configurations ──────────────────────────────────────────────


@router.get("/siem", response_model=list[SiemExportConfigResponse])
async def list_siem_configs(
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> list[SiemExportConfigResponse]:
    """List all SIEM/SOAR export configurations."""
    result = await db.execute(select(SiemExportConfig).order_by(SiemExportConfig.id))
    configs = result.scalars().all()
    return [SiemExportConfigResponse.model_validate(c) for c in configs]


@router.post(
    "/siem",
    response_model=SiemExportConfigResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_csrf)],
)
async def create_siem_config(
    payload: SiemExportConfigCreate,
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> SiemExportConfigResponse:
    """Register a new SIEM/SOAR export destination (syslog, Splunk HEC, or webhook)."""
    config = SiemExportConfig(
        export_type=payload.export_type,
        display_name=payload.display_name,
        syslog_host=payload.syslog_host,
        syslog_port=payload.syslog_port,
        syslog_protocol=payload.syslog_protocol,
        syslog_format=payload.syslog_format,
        splunk_hec_url=payload.splunk_hec_url,
        splunk_hec_token_env_var=payload.splunk_hec_token_env_var,
        splunk_sourcetype=payload.splunk_sourcetype,
        splunk_index=payload.splunk_index,
        webhook_url=payload.webhook_url,
        webhook_secret_env_var=payload.webhook_secret_env_var,
        webhook_headers=payload.webhook_headers,
        enabled=payload.enabled,
        export_events=payload.export_events,
        export_detections=payload.export_detections,
        created_by=current_user.github_login,
    )
    db.add(config)
    await db.flush()
    return SiemExportConfigResponse.model_validate(config)


@router.delete("/siem/{config_id}", dependencies=[Depends(verify_csrf)])
async def delete_siem_config(
    config_id: int,
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Delete a SIEM export configuration."""
    result = await db.execute(select(SiemExportConfig).where(SiemExportConfig.id == config_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Config not found")
    await db.delete(config)
    await db.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/siem/{config_id}/test",
    dependencies=[Depends(verify_csrf)],
)
async def test_siem_config(
    config_id: int,
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Send a test event to a SIEM export destination to verify connectivity."""
    result = await db.execute(select(SiemExportConfig).where(SiemExportConfig.id == config_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Config not found")

    from app.services.siem_export_service import send_soar_webhook, send_splunk_hec, send_syslog

    success = False
    if config.export_type == "syslog":
        test_msg = (
            "CEF:0|OctoWatch|OctoWatch|1.0|test|Test Connection|1"
            "|msg=OctoWatch SIEM export test event"
        )
        success = await send_syslog(config, test_msg)

    elif config.export_type == "splunk_hec":
        test_payload = {
            "time": None,
            "event": {"test": True, "message": "OctoWatch SIEM export test event"},
        }
        success = await send_splunk_hec(config, test_payload, sourcetype="octowatch:test")

    elif config.export_type == "webhook":
        # Create a minimal stub detection for testing
        from types import SimpleNamespace

        mock_detection = SimpleNamespace(
            id=0,
            title="Test Detection",
            description="OctoWatch SIEM export test event",
            severity="info",
            confidence="high",
            confidence_score=0.0,
            status="test",
            actor="octowatch-test",
            org=None,
            repo=None,
            source_ip=None,
            triggered_at=None,
            event_ids=[],
            context_data={},
            rule_id=0,
        )
        success = await send_soar_webhook(config, mock_detection)

    return JSONResponse(
        content={"success": success, "config_id": config_id},
        status_code=status.HTTP_200_OK if success else status.HTTP_502_BAD_GATEWAY,
    )


@router.post(
    "/siem/batch-export",
    dependencies=[Depends(verify_csrf)],
)
async def trigger_batch_export(
    payload: BatchExportRequest,
    current_user: AuthenticatedUser = Depends(require_role(["sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Trigger a batch export of detections in a date range to a SIEM destination."""
    from app.services.siem_export_service import batch_export

    result = await batch_export(
        db=db,
        start_date=payload.start_date,
        end_date=payload.end_date,
        config_id=payload.config_id,
    )
    return JSONResponse(content=result)


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
