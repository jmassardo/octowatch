"""Microsoft Teams integration router."""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_db, require_permission, verify_csrf
from app.schemas.integration import (
    TeamsConfigResponse,
    TeamsConfigUpdate,
    TeamsTestRequest,
    TeamsTestResponse,
)
from app.services import teams_service

router = APIRouter(prefix="/integrations/teams", tags=["teams"])


@router.get("/config", response_model=TeamsConfigResponse)
async def get_teams_config(
    current_user: AuthenticatedUser = Depends(require_permission("admin_settings", "admin")),
    db: AsyncSession = Depends(get_db),
) -> TeamsConfigResponse:
    return TeamsConfigResponse.model_validate(await teams_service.get_teams_config(db))


@router.put(
    "/config",
    response_model=TeamsConfigResponse,
    dependencies=[Depends(verify_csrf)],
)
async def update_teams_config(
    payload: TeamsConfigUpdate,
    current_user: AuthenticatedUser = Depends(require_permission("admin_settings", "admin")),
    db: AsyncSession = Depends(get_db),
) -> TeamsConfigResponse:
    config = await teams_service.update_teams_config(
        db,
        channel_webhooks=payload.channel_webhooks,
        source_mappings=payload.source_mappings,
        notification_settings=payload.notification_settings,
        clear_channels=payload.clear_channels,
        changed_by=current_user.github_login,
    )
    return TeamsConfigResponse.model_validate(config)


@router.post(
    "/test",
    response_model=TeamsTestResponse,
    dependencies=[Depends(verify_csrf)],
)
async def test_teams_connection(
    payload: TeamsTestRequest | None = Body(default=None),
    current_user: AuthenticatedUser = Depends(require_permission("admin_settings", "admin")),
    db: AsyncSession = Depends(get_db),
) -> TeamsTestResponse:
    config = await teams_service.get_runtime_notification_config(db, "detections")
    channel_webhooks = config["channel_webhooks"]
    preferred_channel = (payload.channel if payload else None) or "default"
    channel = (
        preferred_channel
        if channel_webhooks.get(preferred_channel)
        else next(
            (name for name, url in channel_webhooks.items() if url),
            None,
        )
    )
    if channel is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No Teams webhook is configured",
        )

    card = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": [
                        {
                            "type": "TextBlock",
                            "size": "Large",
                            "weight": "Bolder",
                            "text": "Teams connection test",
                        },
                        {
                            "type": "TextBlock",
                            "text": (
                                "OctoWatch successfully connected to Microsoft Teams "
                                "and can send notifications."
                            ),
                            "wrap": True,
                        },
                        {
                            "type": "TextBlock",
                            "text": f"Triggered by {current_user.github_login}",
                            "isSubtle": True,
                        },
                    ],
                },
            }
        ],
    }
    await teams_service.send_adaptive_card(channel_webhooks[channel], card)
    return TeamsTestResponse(ok=True, channel=channel, message="Test message sent successfully")
