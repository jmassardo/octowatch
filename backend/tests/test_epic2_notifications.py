"""Tests for Epic 2 notification features: routing rules, digest mode, PagerDuty & Teams.

Covers:
- Alert routing rules engine with severity/category/org filtering (#38)
- Catch-all fallback routing
- PagerDuty Events API v2 integration (#58)
- Microsoft Teams Adaptive Card webhook integration (#58)
- Digest mode with template rendering and SMTP delivery (#54)
- Pre-existing field mismatch fixes (credential_env_var, target)
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.notification_service import (
    _PD_SEVERITY_MAP,
    _build_teams_adaptive_card,
    _matches_config,
    _render_slack_blocks,
    _send_email_notification,
    _send_pagerduty_notification,
    _send_slack_notification,
    _send_teams_notification,
    build_and_send_digest,
    resolve_pagerduty_incident,
    send_detection_notifications,
)

# ── Test helpers ─────────────────────────────────────────────────────────────


def _make_detection(**overrides: object) -> MagicMock:
    """Create a mock Detection object with sensible defaults."""
    d = MagicMock()
    d.id = overrides.get("id", 1)
    d.rule_id = overrides.get("rule_id", 100)
    d.rule_version = overrides.get("rule_version", 1)
    d.severity = overrides.get("severity", "high")
    d.confidence = overrides.get("confidence", "high")
    d.confidence_score = overrides.get("confidence_score", 0.9)
    d.title = overrides.get("title", "Test Detection")
    d.description = overrides.get("description", "Test description")
    d.actor = overrides.get("actor", "octocat")
    d.org = overrides.get("org", "my-org")
    d.repo = overrides.get("repo", "my-org/repo")
    d.triggered_at = overrides.get("triggered_at", datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC))
    d.status = overrides.get("status", "open")
    return d


def _make_config(**overrides: object) -> MagicMock:
    """Create a mock NotificationConfig object with sensible defaults."""
    c = MagicMock()
    c.id = overrides.get("id", 1)
    c.channel_type = overrides.get("channel_type", "slack")
    c.display_name = overrides.get("display_name", "Test Config")
    c.target = overrides.get("target", "#security-alerts")
    c.credential_env_var = overrides.get("credential_env_var", "SLACK_BOT_TOKEN")
    c.notify_severities = overrides.get("notify_severities", ["critical", "high", "medium"])
    c.cooldown_seconds = overrides.get("cooldown_seconds", 3600)
    c.enabled = overrides.get("enabled", True)
    c.created_by = overrides.get("created_by", "admin")
    c.rule_categories = overrides.get("rule_categories", None)
    c.org_filter = overrides.get("org_filter", None)
    c.is_catch_all = overrides.get("is_catch_all", False)
    c.digest_enabled = overrides.get("digest_enabled", False)
    c.digest_cron = overrides.get("digest_cron", None)
    return c


def _mock_session_execute(*results: MagicMock) -> AsyncMock:
    """Create an AsyncMock for session.execute that returns results in order."""
    return AsyncMock(side_effect=list(results))


def _mock_scalars_result(items: list[MagicMock]) -> MagicMock:
    """Wrap a list of items into the shape returned by session.execute().scalars().all()."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = items
    return mock_result


def _mock_scalar_one_result(value: object) -> MagicMock:
    """Wrap a scalar value into the shape returned by session.execute().scalar_one_or_none()."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = value
    return mock_result


# ── Routing rules (#38) ─────────────────────────────────────────────────────


class TestMatchesConfig:
    """Test _matches_config routing filter logic."""

    def test_severity_match(self) -> None:
        config = _make_config(notify_severities=["critical", "high"])
        detection = _make_detection(severity="high")
        assert _matches_config(config, detection, rule_category="access") is True

    def test_severity_mismatch(self) -> None:
        config = _make_config(notify_severities=["critical"])
        detection = _make_detection(severity="low")
        assert _matches_config(config, detection, rule_category="access") is False

    def test_empty_severities_rejects_all(self) -> None:
        config = _make_config(notify_severities=[])
        detection = _make_detection(severity="high")
        assert _matches_config(config, detection, rule_category="access") is False

    def test_category_match(self) -> None:
        config = _make_config(rule_categories=["access", "admin"])
        detection = _make_detection(severity="high")
        assert _matches_config(config, detection, rule_category="access") is True

    def test_category_mismatch(self) -> None:
        config = _make_config(rule_categories=["admin"])
        detection = _make_detection(severity="high")
        assert _matches_config(config, detection, rule_category="access") is False

    def test_category_none_accepts_all(self) -> None:
        config = _make_config(rule_categories=None)
        detection = _make_detection(severity="high")
        assert _matches_config(config, detection, rule_category="access") is True

    def test_category_empty_list_accepts_all(self) -> None:
        config = _make_config(rule_categories=[])
        detection = _make_detection(severity="high")
        assert _matches_config(config, detection, rule_category="access") is True

    def test_org_match(self) -> None:
        config = _make_config(org_filter=["my-org", "other-org"])
        detection = _make_detection(severity="high", org="my-org")
        assert _matches_config(config, detection, rule_category=None) is True

    def test_org_mismatch(self) -> None:
        config = _make_config(org_filter=["other-org"])
        detection = _make_detection(severity="high", org="my-org")
        assert _matches_config(config, detection, rule_category=None) is False

    def test_org_none_accepts_all(self) -> None:
        config = _make_config(org_filter=None)
        detection = _make_detection(severity="high", org="my-org")
        assert _matches_config(config, detection, rule_category=None) is True

    def test_org_empty_list_accepts_all(self) -> None:
        config = _make_config(org_filter=[])
        detection = _make_detection(severity="high", org="my-org")
        assert _matches_config(config, detection, rule_category=None) is True

    def test_detection_org_none_with_org_filter(self) -> None:
        """Detection with no org should not match an org filter."""
        config = _make_config(org_filter=["my-org"])
        detection = _make_detection(severity="high", org=None)
        assert _matches_config(config, detection, rule_category=None) is False

    def test_all_filters_match(self) -> None:
        config = _make_config(
            notify_severities=["high"],
            rule_categories=["access"],
            org_filter=["my-org"],
        )
        detection = _make_detection(severity="high", org="my-org")
        assert _matches_config(config, detection, rule_category="access") is True

    def test_all_filters_severity_mismatch(self) -> None:
        config = _make_config(
            notify_severities=["critical"],
            rule_categories=["access"],
            org_filter=["my-org"],
        )
        detection = _make_detection(severity="high", org="my-org")
        assert _matches_config(config, detection, rule_category="access") is False

    def test_all_filters_category_mismatch(self) -> None:
        config = _make_config(
            notify_severities=["high"],
            rule_categories=["admin"],
            org_filter=["my-org"],
        )
        detection = _make_detection(severity="high", org="my-org")
        assert _matches_config(config, detection, rule_category="access") is False


# ── Catch-all routing ────────────────────────────────────────────────────────


class TestCatchAllRouting:
    """Test catch-all fallback routing behaviour."""

    @pytest.mark.anyio
    async def test_catch_all_used_when_no_specific_match(self) -> None:
        """Catch-all config should receive alert when no specific config matches."""
        detection = _make_detection(severity="low", org="unknown-org")

        specific_config = _make_config(
            id=1,
            notify_severities=["critical"],
            is_catch_all=False,
            channel_type="slack",
        )
        catch_all_config = _make_config(
            id=2,
            notify_severities=["low", "medium", "high", "critical"],
            is_catch_all=True,
            channel_type="email",
            target="alerts@example.com",
        )

        configs_result = _mock_scalars_result([specific_config, catch_all_config])
        rule_result = _mock_scalar_one_result("access")
        mock_session = AsyncMock()
        mock_session.execute = _mock_session_execute(configs_result, rule_result)

        mock_valkey = AsyncMock()
        mock_valkey.set = AsyncMock(return_value=True)  # not a duplicate

        with (
            patch(
                "app.services.notification_service._send_email_notification",
                new_callable=AsyncMock,
            ) as mock_email,
            patch(
                "app.services.notification_service._send_slack_notification",
                new_callable=AsyncMock,
            ) as mock_slack,
        ):
            await send_detection_notifications(mock_session, mock_valkey, detection)
            mock_email.assert_awaited_once_with(catch_all_config, detection)
            mock_slack.assert_not_awaited()

    @pytest.mark.anyio
    async def test_catch_all_not_used_when_specific_matches(self) -> None:
        """Catch-all should NOT be used when a specific config matches."""
        detection = _make_detection(severity="high")

        specific_config = _make_config(
            id=1,
            notify_severities=["high"],
            is_catch_all=False,
            channel_type="slack",
        )
        catch_all_config = _make_config(
            id=2,
            notify_severities=["high"],
            is_catch_all=True,
            channel_type="email",
            target="alerts@example.com",
        )

        configs_result = _mock_scalars_result([specific_config, catch_all_config])
        rule_result = _mock_scalar_one_result("access")
        mock_session = AsyncMock()
        mock_session.execute = _mock_session_execute(configs_result, rule_result)

        mock_valkey = AsyncMock()
        mock_valkey.set = AsyncMock(return_value=True)

        with (
            patch(
                "app.services.notification_service._send_slack_notification",
                new_callable=AsyncMock,
            ) as mock_slack,
            patch(
                "app.services.notification_service._send_email_notification",
                new_callable=AsyncMock,
            ) as mock_email,
        ):
            await send_detection_notifications(mock_session, mock_valkey, detection)
            mock_slack.assert_awaited_once()
            mock_email.assert_not_awaited()

    @pytest.mark.anyio
    async def test_catch_all_respects_severity(self) -> None:
        """Catch-all should still reject detections whose severity is not listed."""
        detection = _make_detection(severity="info")

        catch_all_config = _make_config(
            id=1,
            notify_severities=["critical", "high"],
            is_catch_all=True,
            channel_type="email",
            target="alerts@example.com",
        )

        configs_result = _mock_scalars_result([catch_all_config])
        rule_result = _mock_scalar_one_result("access")
        mock_session = AsyncMock()
        mock_session.execute = _mock_session_execute(configs_result, rule_result)

        mock_valkey = AsyncMock()
        mock_valkey.set = AsyncMock(return_value=True)

        with patch(
            "app.services.notification_service._send_email_notification",
            new_callable=AsyncMock,
        ) as mock_email:
            await send_detection_notifications(mock_session, mock_valkey, detection)
            mock_email.assert_not_awaited()

    @pytest.mark.anyio
    async def test_multiple_specific_configs_match(self) -> None:
        """Multiple specific configs can match the same detection."""
        detection = _make_detection(severity="critical")

        slack_config = _make_config(
            id=1,
            notify_severities=["critical"],
            is_catch_all=False,
            channel_type="slack",
        )
        pd_config = _make_config(
            id=2,
            notify_severities=["critical"],
            is_catch_all=False,
            channel_type="pagerduty",
            credential_env_var="PD_KEY",
        )

        configs_result = _mock_scalars_result([slack_config, pd_config])
        rule_result = _mock_scalar_one_result("access")
        mock_session = AsyncMock()
        mock_session.execute = _mock_session_execute(configs_result, rule_result)

        mock_valkey = AsyncMock()
        mock_valkey.set = AsyncMock(return_value=True)

        with (
            patch(
                "app.services.notification_service._send_slack_notification",
                new_callable=AsyncMock,
            ) as mock_slack,
            patch(
                "app.services.notification_service._send_pagerduty_notification",
                new_callable=AsyncMock,
            ) as mock_pd,
        ):
            await send_detection_notifications(mock_session, mock_valkey, detection)
            mock_slack.assert_awaited_once()
            mock_pd.assert_awaited_once()


# ── Routing with send_detection_notifications ────────────────────────────────


class TestSendDetectionNotifications:
    """Integration tests for the main dispatch function."""

    @pytest.mark.anyio
    async def test_skips_when_no_rule_id(self) -> None:
        detection = _make_detection(rule_id=None)
        mock_session = AsyncMock()
        mock_valkey = AsyncMock()

        await send_detection_notifications(mock_session, mock_valkey, detection)
        mock_session.execute.assert_not_awaited()

    @pytest.mark.anyio
    async def test_skips_when_no_configs(self) -> None:
        detection = _make_detection()
        configs_result = _mock_scalars_result([])
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=configs_result)
        mock_valkey = AsyncMock()

        await send_detection_notifications(mock_session, mock_valkey, detection)
        mock_valkey.set.assert_not_awaited()

    @pytest.mark.anyio
    async def test_skips_when_deduped(self) -> None:
        detection = _make_detection()
        config = _make_config()
        configs_result = _mock_scalars_result([config])
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=configs_result)

        mock_valkey = AsyncMock()
        mock_valkey.set = AsyncMock(return_value=None)  # duplicate

        with patch(
            "app.services.notification_service._send_slack_notification",
            new_callable=AsyncMock,
        ) as mock_slack:
            await send_detection_notifications(mock_session, mock_valkey, detection)
            mock_slack.assert_not_awaited()

    @pytest.mark.anyio
    async def test_routes_to_teams_channel(self) -> None:
        detection = _make_detection(severity="medium")
        teams_config = _make_config(
            channel_type="teams",
            notify_severities=["medium", "high", "critical"],
            target="https://webhook.example.com/teams",
        )

        configs_result = _mock_scalars_result([teams_config])
        rule_result = _mock_scalar_one_result("access")
        mock_session = AsyncMock()
        mock_session.execute = _mock_session_execute(configs_result, rule_result)

        mock_valkey = AsyncMock()
        mock_valkey.set = AsyncMock(return_value=True)

        with patch(
            "app.services.notification_service._send_teams_notification",
            new_callable=AsyncMock,
        ) as mock_teams:
            await send_detection_notifications(mock_session, mock_valkey, detection)
            mock_teams.assert_awaited_once_with(teams_config, detection)

    @pytest.mark.anyio
    async def test_handles_send_failure_gracefully(self) -> None:
        """A failing channel should not prevent other channels from sending."""
        detection = _make_detection(severity="critical")
        slack_config = _make_config(
            id=1,
            channel_type="slack",
            notify_severities=["critical"],
        )
        email_config = _make_config(
            id=2,
            channel_type="email",
            notify_severities=["critical"],
            target="admin@example.com",
        )

        configs_result = _mock_scalars_result([slack_config, email_config])
        rule_result = _mock_scalar_one_result("access")
        mock_session = AsyncMock()
        mock_session.execute = _mock_session_execute(configs_result, rule_result)

        mock_valkey = AsyncMock()
        mock_valkey.set = AsyncMock(return_value=True)

        with (
            patch(
                "app.services.notification_service._send_slack_notification",
                new_callable=AsyncMock,
                side_effect=RuntimeError("Slack API down"),
            ),
            patch(
                "app.services.notification_service._send_email_notification",
                new_callable=AsyncMock,
            ) as mock_email,
        ):
            # Should not raise despite Slack failure
            await send_detection_notifications(mock_session, mock_valkey, detection)
            # Email should still be called
            mock_email.assert_awaited_once()


# ── PagerDuty integration (#58) ─────────────────────────────────────────────


class TestPagerDutyIntegration:
    """Test PagerDuty Events API v2 integration."""

    def test_severity_mapping(self) -> None:
        assert _PD_SEVERITY_MAP["critical"] == "critical"
        assert _PD_SEVERITY_MAP["high"] == "error"
        assert _PD_SEVERITY_MAP["medium"] == "warning"
        assert _PD_SEVERITY_MAP["low"] == "info"
        assert _PD_SEVERITY_MAP["info"] == "info"

    @pytest.mark.anyio
    async def test_sends_trigger_event(self) -> None:
        config = _make_config(
            channel_type="pagerduty",
            credential_env_var="PD_ROUTING_KEY",
        )
        detection = _make_detection(severity="critical", id=42)
        mock_valkey = AsyncMock()

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.dict(os.environ, {"PD_ROUTING_KEY": "test-routing-key"}),
            patch(
                "app.services.notification_service.httpx.AsyncClient",
                return_value=mock_client,
            ),
        ):
            await _send_pagerduty_notification(config, detection, mock_valkey)

            mock_client.post.assert_awaited_once()
            args, kwargs = mock_client.post.call_args
            assert args[0] == "https://events.pagerduty.com/v2/enqueue"

            payload = kwargs["json"]
            assert payload["routing_key"] == "test-routing-key"
            assert payload["event_action"] == "trigger"
            assert payload["dedup_key"] == "octowatch-detection-42"
            assert payload["payload"]["severity"] == "critical"
            assert payload["payload"]["custom_details"]["detection_id"] == 42
            assert payload["payload"]["custom_details"]["actor"] == "octocat"

    @pytest.mark.anyio
    async def test_stores_dedup_key_in_valkey(self) -> None:
        config = _make_config(
            channel_type="pagerduty",
            credential_env_var="PD_ROUTING_KEY",
        )
        detection = _make_detection(id=99)
        mock_valkey = AsyncMock()

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.dict(os.environ, {"PD_ROUTING_KEY": "rk-123"}),
            patch(
                "app.services.notification_service.httpx.AsyncClient",
                return_value=mock_client,
            ),
        ):
            await _send_pagerduty_notification(config, detection, mock_valkey)

            mock_valkey.set.assert_awaited_once_with(
                "pagerduty:dedup:99",
                "rk-123",
                ex=86400 * 30,
            )

    @pytest.mark.anyio
    async def test_skips_when_no_routing_key(self) -> None:
        config = _make_config(
            channel_type="pagerduty",
            credential_env_var="PD_ROUTING_KEY",
        )
        detection = _make_detection()
        mock_valkey = AsyncMock()

        with patch.dict(os.environ, {}, clear=False):
            # Ensure the env var is NOT set
            os.environ.pop("PD_ROUTING_KEY", None)
            await _send_pagerduty_notification(config, detection, mock_valkey)
            # No valkey interaction expected
            mock_valkey.set.assert_not_awaited()

    @pytest.mark.anyio
    async def test_resolve_sends_resolve_event(self) -> None:
        mock_valkey = AsyncMock()
        mock_valkey.get = AsyncMock(return_value="test-routing-key")
        mock_valkey.delete = AsyncMock()

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "app.services.notification_service.httpx.AsyncClient",
            return_value=mock_client,
        ):
            result = await resolve_pagerduty_incident(mock_valkey, detection_id=42)

        assert result is True
        mock_client.post.assert_awaited_once()
        _, kwargs = mock_client.post.call_args
        payload = kwargs["json"]
        assert payload["event_action"] == "resolve"
        assert payload["dedup_key"] == "octowatch-detection-42"
        assert payload["routing_key"] == "test-routing-key"

        mock_valkey.delete.assert_awaited_once_with("pagerduty:dedup:42")

    @pytest.mark.anyio
    async def test_resolve_returns_false_when_no_key(self) -> None:
        mock_valkey = AsyncMock()
        mock_valkey.get = AsyncMock(return_value=None)

        result = await resolve_pagerduty_incident(mock_valkey, detection_id=999)
        assert result is False


# ── Teams integration (#58) ──────────────────────────────────────────────────


class TestTeamsIntegration:
    """Test Microsoft Teams Adaptive Card integration."""

    def test_adaptive_card_structure(self) -> None:
        detection = _make_detection(severity="high", title="Suspicious Login")
        card = _build_teams_adaptive_card(detection)

        assert card["type"] == "message"
        assert len(card["attachments"]) == 1

        content = card["attachments"][0]["content"]
        assert content["type"] == "AdaptiveCard"
        assert content["version"] == "1.4"

        # Verify body contains expected blocks
        body = content["body"]
        assert body[0]["type"] == "TextBlock"
        assert "Suspicious Login" in body[0]["text"]

        # ColumnSet should have severity, confidence, actor, org
        column_set = body[1]
        assert column_set["type"] == "ColumnSet"
        assert len(column_set["columns"]) == 4

        # FactSet should have detection ID and triggered time
        fact_set = body[3]
        assert fact_set["type"] == "FactSet"
        assert fact_set["facts"][0]["value"] == "1"

    def test_adaptive_card_severity_colors(self) -> None:
        for severity, expected_color in [
            ("critical", "attention"),
            ("high", "attention"),
            ("medium", "warning"),
            ("low", "accent"),
            ("info", "default"),
        ]:
            detection = _make_detection(severity=severity)
            card = _build_teams_adaptive_card(detection)
            columns = card["attachments"][0]["content"]["body"][1]["columns"]
            severity_text_block = columns[0]["items"][1]
            assert severity_text_block["color"] == expected_color

    @pytest.mark.anyio
    async def test_sends_webhook_request(self) -> None:
        config = _make_config(
            channel_type="teams",
            target="https://webhook.example.com/incoming",
        )
        detection = _make_detection()

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "app.services.notification_service.httpx.AsyncClient",
            return_value=mock_client,
        ):
            await _send_teams_notification(config, detection)

        mock_client.post.assert_awaited_once()
        args, kwargs = mock_client.post.call_args
        assert args[0] == "https://webhook.example.com/incoming"
        assert "attachments" in kwargs["json"]

    @pytest.mark.anyio
    async def test_skips_when_no_webhook_url(self) -> None:
        config = _make_config(channel_type="teams", target="")
        detection = _make_detection()

        with patch(
            "app.services.notification_service.httpx.AsyncClient",
        ) as mock_client_cls:
            await _send_teams_notification(config, detection)
            mock_client_cls.assert_not_called()


# ── Digest mode (#54) ───────────────────────────────────────────────────────


class TestDigestMode:
    """Test digest email generation and delivery."""

    @pytest.mark.anyio
    async def test_skips_when_no_detections(self) -> None:
        config = _make_config(digest_enabled=True, target="admin@example.com")

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_valkey = AsyncMock()
        mock_valkey.get = AsyncMock(return_value=None)

        result = await build_and_send_digest(mock_session, mock_valkey, config)
        assert result["status"] == "skipped"
        assert result["reason"] == "no_detections"
        assert result["count"] == 0

    @pytest.mark.anyio
    async def test_sends_when_detections_exist(self) -> None:
        config = _make_config(digest_enabled=True, target="admin@example.com", id=5)

        detections = [
            _make_detection(id=1, severity="critical", title="Critical Alert"),
            _make_detection(id=2, severity="high", title="High Alert"),
            _make_detection(id=3, severity="critical", title="Another Critical"),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = detections
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_valkey = AsyncMock()
        mock_valkey.get = AsyncMock(return_value=None)
        mock_valkey.set = AsyncMock()

        mock_template = MagicMock()
        mock_template.render.return_value = "rendered content"

        with (
            patch("app.services.notification_service._jinja_env") as mock_env,
            patch(
                "app.services.notification_service.aiosmtplib.send",
                new_callable=AsyncMock,
            ) as mock_smtp,
            patch("app.services.notification_service.settings") as mock_settings,
        ):
            mock_env.get_template.return_value = mock_template
            mock_settings.INTEGRATIONS.SMTP_HOST = "smtp.example.com"
            mock_settings.INTEGRATIONS.SMTP_PORT = 587
            mock_settings.INTEGRATIONS.SMTP_USERNAME = None
            mock_settings.INTEGRATIONS.SMTP_PASSWORD = None
            mock_settings.INTEGRATIONS.SMTP_FROM_ADDRESS = "noreply@example.com"
            mock_settings.INTEGRATIONS.SMTP_USE_TLS = True

            result = await build_and_send_digest(mock_session, mock_valkey, config)

        assert result["status"] == "sent"
        assert result["count"] == 3
        mock_smtp.assert_awaited_once()
        # Last sent timestamp should be updated
        mock_valkey.set.assert_awaited_once()
        set_args = mock_valkey.set.call_args
        assert set_args[0][0] == "digest:last_sent:5"

    @pytest.mark.anyio
    async def test_uses_last_sent_timestamp(self) -> None:
        """Digest should use the stored last-sent timestamp as the period start."""
        config = _make_config(digest_enabled=True, target="admin@example.com", id=7)

        stored_ts = (datetime.now(UTC) - timedelta(hours=6)).isoformat()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_valkey = AsyncMock()
        mock_valkey.get = AsyncMock(return_value=stored_ts)

        result = await build_and_send_digest(mock_session, mock_valkey, config)
        assert result["status"] == "skipped"
        # Verify Valkey was queried for last sent timestamp
        mock_valkey.get.assert_awaited_once_with("digest:last_sent:7")

    @pytest.mark.anyio
    async def test_groups_detections_by_severity(self) -> None:
        """Detections should be grouped by severity in priority order."""
        config = _make_config(digest_enabled=True, target="admin@example.com", id=10)

        detections = [
            _make_detection(id=1, severity="low"),
            _make_detection(id=2, severity="critical"),
            _make_detection(id=3, severity="high"),
            _make_detection(id=4, severity="critical"),
            _make_detection(id=5, severity="medium"),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = detections
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_valkey = AsyncMock()
        mock_valkey.get = AsyncMock(return_value=None)
        mock_valkey.set = AsyncMock()

        mock_template = MagicMock()
        mock_template.render.return_value = "rendered"

        with (
            patch("app.services.notification_service._jinja_env") as mock_env,
            patch(
                "app.services.notification_service.aiosmtplib.send",
                new_callable=AsyncMock,
            ),
            patch("app.services.notification_service.settings") as mock_settings,
        ):
            mock_env.get_template.return_value = mock_template
            mock_settings.INTEGRATIONS.SMTP_HOST = "smtp.example.com"
            mock_settings.INTEGRATIONS.SMTP_PORT = 587
            mock_settings.INTEGRATIONS.SMTP_USERNAME = None
            mock_settings.INTEGRATIONS.SMTP_PASSWORD = None
            mock_settings.INTEGRATIONS.SMTP_FROM_ADDRESS = "noreply@example.com"
            mock_settings.INTEGRATIONS.SMTP_USE_TLS = True

            result = await build_and_send_digest(mock_session, mock_valkey, config)

        assert result["count"] == 5

        # Verify template was called with grouped detections in severity order
        render_kwargs = mock_template.render.call_args.kwargs
        grouped = render_kwargs["grouped_detections"]
        severity_keys = list(grouped.keys())
        assert severity_keys == ["critical", "high", "medium", "low"]
        assert render_kwargs["severity_counts"]["critical"] == 2
        assert render_kwargs["severity_counts"]["high"] == 1

    @pytest.mark.anyio
    async def test_skips_when_no_recipients(self) -> None:
        config = _make_config(digest_enabled=True, target="", id=11)

        detections = [_make_detection()]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = detections
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_valkey = AsyncMock()
        mock_valkey.get = AsyncMock(return_value=None)

        mock_template = MagicMock()
        mock_template.render.return_value = "rendered"

        with patch("app.services.notification_service._jinja_env") as mock_env:
            mock_env.get_template.return_value = mock_template
            result = await build_and_send_digest(mock_session, mock_valkey, config)

        assert result["status"] == "skipped"
        assert result["reason"] == "no_recipients"


# ── Field mismatch fixes ────────────────────────────────────────────────────


class TestFieldMismatchFixes:
    """Verify pre-existing field mismatches are corrected."""

    @pytest.mark.anyio
    async def test_slack_uses_credential_env_var(self) -> None:
        """Slack should read token from env var, not from config.credentials."""
        config = _make_config(
            channel_type="slack",
            credential_env_var="MY_SLACK_TOKEN",
            target="#alerts",
        )
        detection = _make_detection()

        mock_client = AsyncMock()
        mock_client.chat_postMessage = AsyncMock()

        with (
            patch.dict(os.environ, {"MY_SLACK_TOKEN": "xoxb-test-token"}),
            patch(
                "app.services.notification_service.AsyncWebClient",
                return_value=mock_client,
            ) as mock_client_cls,
        ):
            await _send_slack_notification(config, detection)

        # Verify the client was created with the env var token
        mock_client_cls.assert_called_once_with(token="xoxb-test-token")

    @pytest.mark.anyio
    async def test_slack_uses_target_not_destination(self) -> None:
        """Slack should post to config.target, not config.destination."""
        config = _make_config(
            channel_type="slack",
            credential_env_var="SLACK_TOKEN",
            target="#my-channel",
        )
        detection = _make_detection()

        mock_client = AsyncMock()
        mock_client.chat_postMessage = AsyncMock()

        with (
            patch.dict(os.environ, {"SLACK_TOKEN": "xoxb-token"}),
            patch(
                "app.services.notification_service.AsyncWebClient",
                return_value=mock_client,
            ),
        ):
            await _send_slack_notification(config, detection)

        mock_client.chat_postMessage.assert_awaited_once()
        call_kwargs = mock_client.chat_postMessage.call_args.kwargs
        assert call_kwargs["channel"] == "#my-channel"

    @pytest.mark.anyio
    async def test_slack_skips_when_no_token_env_var(self) -> None:
        """Slack should skip gracefully when credential env var is not set."""
        config = _make_config(
            channel_type="slack",
            credential_env_var="NONEXISTENT_VAR",
            target="#alerts",
        )
        detection = _make_detection()

        os.environ.pop("NONEXISTENT_VAR", None)

        with patch(
            "app.services.notification_service.AsyncWebClient",
        ) as mock_client_cls:
            await _send_slack_notification(config, detection)
            mock_client_cls.assert_not_called()

    @pytest.mark.anyio
    async def test_email_uses_target_not_destination(self) -> None:
        """Email should read recipients from config.target."""
        config = _make_config(
            channel_type="email",
            target="alice@example.com,bob@example.com",
        )
        detection = _make_detection()

        with (
            patch(
                "app.services.notification_service.aiosmtplib.send",
                new_callable=AsyncMock,
            ) as mock_send,
            patch("app.services.notification_service.settings") as mock_settings,
        ):
            mock_settings.INTEGRATIONS.SMTP_HOST = "localhost"
            mock_settings.INTEGRATIONS.SMTP_PORT = 587
            mock_settings.INTEGRATIONS.SMTP_USERNAME = None
            mock_settings.INTEGRATIONS.SMTP_PASSWORD = None
            mock_settings.INTEGRATIONS.SMTP_FROM_ADDRESS = "noreply@example.com"
            mock_settings.INTEGRATIONS.SMTP_USE_TLS = False

            await _send_email_notification(config, detection)

        mock_send.assert_awaited_once()
        # Verify the MIMEMultipart message was built with correct recipients
        sent_msg = mock_send.call_args[0][0]
        assert "alice@example.com" in sent_msg["To"]
        assert "bob@example.com" in sent_msg["To"]


# ── Slack block rendering ───────────────────────────────────────────────────


class TestSlackBlocks:
    """Test Slack Block Kit message rendering."""

    def test_render_slack_blocks_structure(self) -> None:
        detection = _make_detection(severity="critical", title="Token Leaked")
        blocks = _render_slack_blocks(detection)

        assert len(blocks) == 4
        assert blocks[0]["type"] == "header"
        assert "Token Leaked" in blocks[0]["text"]["text"]
        assert ":rotating_light:" in blocks[0]["text"]["text"]

    def test_severity_emoji_mapping(self) -> None:
        for severity, emoji in [
            ("critical", ":rotating_light:"),
            ("high", ":red_circle:"),
            ("medium", ":large_yellow_circle:"),
            ("low", ":large_blue_circle:"),
            ("info", ":information_source:"),
        ]:
            detection = _make_detection(severity=severity)
            blocks = _render_slack_blocks(detection)
            assert emoji in blocks[0]["text"]["text"]


# ── Digest worker task ──────────────────────────────────────────────────────


class TestDigestWorkerTask:
    """Test the digest Celery task wrapper."""

    @pytest.mark.anyio
    async def test_send_digests_skips_when_no_configs(self) -> None:
        """Digest task returns zeros when no enabled digest configs exist."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_valkey = AsyncMock()
        mock_valkey.aclose = AsyncMock()

        mock_factory = AsyncMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "app.workers.notification_worker.AsyncSessionLocal",
                return_value=mock_factory,
            ),
            patch("redis.asyncio.from_url", return_value=mock_valkey),
        ):
            from app.workers.notification_worker import _send_digests

            result = await _send_digests()

        assert result["configs_processed"] == 0
        assert result["digests_sent"] == 0
