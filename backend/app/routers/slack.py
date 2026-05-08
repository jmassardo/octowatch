"""Slack integration router."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.deps import AuthenticatedUser, get_db, require_permission, verify_csrf
from app.schemas.integration import SlackConfigResponse, SlackConfigUpdate, SlackTestResponse
from app.services import slack_service
from app.services.settings_service import get_setting

router = APIRouter(prefix="/integrations/slack", tags=["slack"])


@router.post("/events")
async def slack_events(request: Request) -> JSONResponse:
    body = await request.body()
    payload = json.loads(body.decode("utf-8") or "{}")

    if payload.get("type") == "url_verification":
        return JSONResponse({"challenge": payload.get("challenge", "")})

    signing_secret = await _get_signing_secret(request)
    if not slack_service.verify_slack_signature(
        body=body,
        timestamp=request.headers.get("X-Slack-Request-Timestamp"),
        signature=request.headers.get("X-Slack-Signature"),
        signing_secret=signing_secret,
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Slack signature")

    return JSONResponse({"ok": True})


@router.post("/commands")
async def slack_commands(request: Request) -> JSONResponse:
    body = await request.body()
    signing_secret = await _get_signing_secret(request)
    if not slack_service.verify_slack_signature(
        body=body,
        timestamp=request.headers.get("X-Slack-Request-Timestamp"),
        signature=request.headers.get("X-Slack-Signature"),
        signing_secret=signing_secret,
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Slack signature")

    form = await request.form()
    response = await slack_service.handle_slack_command(
        str(form.get("command") or ""),
        str(form.get("text") or ""),
        str(form.get("user_id") or "unknown"),
    )
    return JSONResponse(response)


@router.post("/interactions")
async def slack_interactions(request: Request) -> JSONResponse:
    body = await request.body()
    signing_secret = await _get_signing_secret(request)
    if not slack_service.verify_slack_signature(
        body=body,
        timestamp=request.headers.get("X-Slack-Request-Timestamp"),
        signature=request.headers.get("X-Slack-Signature"),
        signing_secret=signing_secret,
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Slack signature")

    form = await request.form()
    raw_payload = form.get("payload")
    if raw_payload is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing payload")

    payload = json.loads(str(raw_payload))
    response = await slack_service.handle_slack_interaction(payload)
    return JSONResponse(response)


@router.get("/config", response_model=SlackConfigResponse)
async def get_slack_config(
    current_user: AuthenticatedUser = Depends(require_permission("admin_settings", "admin")),
    db: AsyncSession = Depends(get_db),
) -> SlackConfigResponse:
    return SlackConfigResponse.model_validate(await slack_service.get_slack_config(db))


@router.put(
    "/config",
    response_model=SlackConfigResponse,
    dependencies=[Depends(verify_csrf)],
)
async def update_slack_config(
    payload: SlackConfigUpdate,
    current_user: AuthenticatedUser = Depends(require_permission("admin_settings", "admin")),
    db: AsyncSession = Depends(get_db),
) -> SlackConfigResponse:
    config = await slack_service.update_slack_config(
        db,
        bot_token=payload.bot_token.strip() if payload.bot_token else None,
        signing_secret=payload.signing_secret.strip() if payload.signing_secret else None,
        default_channel=payload.default_channel,
        channel_mappings=payload.channel_mappings,
        notification_settings=payload.notification_settings,
        changed_by=current_user.github_login,
    )
    return SlackConfigResponse.model_validate(config)


@router.post(
    "/test",
    response_model=SlackTestResponse,
    dependencies=[Depends(verify_csrf)],
)
async def test_slack_connection(
    current_user: AuthenticatedUser = Depends(require_permission("admin_settings", "admin")),
    db: AsyncSession = Depends(get_db),
) -> SlackTestResponse:
    config = await slack_service.get_slack_config(db)
    bot_token = await get_setting(db, "slack_bot_token")
    channel = config["default_channel"]
    if not bot_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Slack bot token is not configured")
    if not channel:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Default Slack channel is not configured")

    await slack_service.send_slack_message(
        channel,
        "OctoWatch Slack integration test",
        [
            {"type": "header", "text": {"type": "plain_text", "text": "Slack connection test"}},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "OctoWatch successfully connected to Slack and can send notifications.",
                },
            },
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"Triggered by {current_user.github_login}"}
                ],
            },
        ],
        bot_token=bot_token,
    )
    return SlackTestResponse(ok=True, channel=channel, message="Test message sent successfully")


async def _get_signing_secret(request: Request) -> str | None:
    async with AsyncSessionLocal() as db:
        return await get_setting(db, "slack_signing_secret")
