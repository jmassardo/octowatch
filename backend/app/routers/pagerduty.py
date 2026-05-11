"""PagerDuty integration router."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_db, require_permission, verify_csrf
from app.schemas.integration import (
    PagerDutyConfigResponse,
    PagerDutyConfigUpdate,
    PagerDutyTestResponse,
)
from app.services import pagerduty_service

router = APIRouter(prefix="/integrations/pagerduty", tags=["pagerduty"])


@router.get("/config", response_model=PagerDutyConfigResponse)
async def get_pagerduty_config(
    current_user: AuthenticatedUser = Depends(require_permission("admin_settings", "admin")),
    db: AsyncSession = Depends(get_db),
) -> PagerDutyConfigResponse:
    return PagerDutyConfigResponse.model_validate(await pagerduty_service.get_pagerduty_config(db))


@router.put(
    "/config",
    response_model=PagerDutyConfigResponse,
    dependencies=[Depends(verify_csrf)],
)
async def update_pagerduty_config(
    payload: PagerDutyConfigUpdate,
    current_user: AuthenticatedUser = Depends(require_permission("admin_settings", "admin")),
    db: AsyncSession = Depends(get_db),
) -> PagerDutyConfigResponse:
    config = await pagerduty_service.update_pagerduty_config(
        db,
        routing_key=payload.routing_key.strip() if payload.routing_key else None,
        severity_mapping=payload.severity_mapping,
        notification_settings=payload.notification_settings,
        auto_resolve=payload.auto_resolve,
        changed_by=current_user.github_login,
    )
    return PagerDutyConfigResponse.model_validate(config)


@router.post(
    "/test",
    response_model=PagerDutyTestResponse,
    dependencies=[Depends(verify_csrf)],
)
async def test_pagerduty_connection(
    current_user: AuthenticatedUser = Depends(require_permission("admin_settings", "admin")),
    db: AsyncSession = Depends(get_db),
) -> PagerDutyTestResponse:
    config = await pagerduty_service.get_runtime_notification_config(db, "detections")
    routing_key = str(config.get("routing_key") or "").strip()
    if not routing_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PagerDuty routing key is not configured",
        )

    await pagerduty_service.send_change_event(
        "OctoWatch PagerDuty integration test",
        source="octowatch",
        routing_key=routing_key,
        custom_details={"triggered_by": current_user.github_login},
    )
    return PagerDutyTestResponse(ok=True, message="Test event sent successfully")
