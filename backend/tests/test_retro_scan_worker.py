"""Tests for retro_scan_worker."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.workers.retro_scan_worker import (
    BATCH_SIZE,
    DEFAULT_LOOKBACK_DAYS,
    _collect_action_filters,
    _detection_exists,
    _retro_scan,
    _write_retro_detection,
)


@pytest.fixture
def mock_session():
    """Create a mock AsyncSession."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    return session


def _make_mock_rule(
    rule_id: int = 1,
    campaign_id: int = 42,
    action_filters: list[str] | None = None,
    engine: str = "threat_intel_actor",
):
    """Create a mock RuleDefinition."""
    rule = MagicMock()
    rule.id = rule_id
    rule.version = 1
    rule.name = "Test Rule"
    rule.description = "Test rule description"
    rule.default_severity = "critical"
    rule.category = "supply_chain"
    rule.slug = f"feed-test-rule-{rule_id}"
    rule.logic_type = "pattern"
    rule.logic_config = {
        "action_filters": action_filters or ["*"],
        "confidence": 0.85,
        "x_config": {
            "engine": engine,
            "campaign_id": campaign_id,
            "indicator_type": "github_username",
            "check_field": "actor",
        },
    }
    return rule


def _make_mock_event(event_id: int = 100, action: str = "org.add_member"):
    """Create a mock AuditEvent."""
    event = MagicMock()
    event.id = event_id
    event.action = action
    event.actor = "evil-user"
    event.org = "target-org"
    event.repo = "target-org/repo"
    event.source_ip = "1.2.3.4"
    event.created_at = datetime.now(UTC) - timedelta(days=2)
    event.data = {}
    return event


class TestCollectActionFilters:
    def test_collects_unique_filters(self):
        r1 = _make_mock_rule(action_filters=["git.push", "org.add_member"])
        r2 = _make_mock_rule(action_filters=["git.push", "packages.*"])
        result = _collect_action_filters([r1, r2])
        assert sorted(result) == ["git.push", "org.add_member", "packages.*"]

    def test_wildcard_preserved(self):
        r1 = _make_mock_rule(action_filters=["*"])
        result = _collect_action_filters([r1])
        assert result == ["*"]

    def test_empty_rules(self):
        assert _collect_action_filters([]) == []


class TestDetectionExists:
    @pytest.mark.asyncio
    async def test_returns_true_when_exists(self, mock_session):
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (1,)
        mock_session.execute.return_value = mock_result

        result = await _detection_exists(mock_session, rule_id=1, event_id=100)
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_not_exists(self, mock_session):
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        mock_session.execute.return_value = mock_result

        result = await _detection_exists(mock_session, rule_id=1, event_id=100)
        assert result is False


class TestWriteRetroDetection:
    @pytest.mark.asyncio
    async def test_writes_detection_with_retroactive_flag(self, mock_session):
        """Detection should have retroactive=True in context_data."""
        rule = _make_mock_rule()
        event = _make_mock_event()

        # Make session.add set a fake ID on the detection
        def _set_id(det):
            det.id = 501

        mock_session.add = MagicMock(side_effect=_set_id)
        mock_session.flush = AsyncMock()

        with (
            patch(
                "app.services.detection_service.check_suppression",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "app.services.detection_service.resolve_severity",
                new_callable=AsyncMock,
                return_value="critical",
            ),
            patch(
                "app.services.detection_service.compute_confidence_score",
                return_value=(0.85, "high"),
            ),
        ):
            det_id = await _write_retro_detection(
                mock_session,
                rule=rule,
                event=event,
                scan_started_at="2026-07-09T12:00:00Z",
            )

        assert det_id == 501
        # Verify the detection was added to session
        added = mock_session.add.call_args[0][0]
        assert added.context_data["retroactive"] is True
        assert added.context_data["scan_initiated_at"] == "2026-07-09T12:00:00Z"
        assert "[Retro]" in added.title

    @pytest.mark.asyncio
    async def test_skips_when_suppressed(self, mock_session):
        """Suppressed events should return None."""
        rule = _make_mock_rule()
        event = _make_mock_event()
        suppression = MagicMock()

        with patch(
            "app.services.detection_service.check_suppression",
            new_callable=AsyncMock,
            return_value=suppression,
        ):
            det_id = await _write_retro_detection(
                mock_session,
                rule=rule,
                event=event,
                scan_started_at="2026-07-09T12:00:00Z",
            )

        assert det_id is None
        assert mock_session.add.call_count == 0


class TestRetroScan:
    @pytest.mark.asyncio
    async def test_no_rules_returns_early(self):
        """If no rules exist for campaign, return immediately."""
        with patch("app.workers.retro_scan_worker.AsyncSessionLocal") as mock_session_cls:
            mock_session = AsyncMock()
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch(
                "app.workers.retro_scan_worker._load_campaign_rules",
                new_callable=AsyncMock,
                return_value=[],
            ):
                result = await _retro_scan(campaign_id=99, lookback_days=7)

        assert result["events_scanned"] == 0
        assert result["detections_created"] == 0

    @pytest.mark.asyncio
    async def test_processes_events_in_batches(self):
        """Should process events and skip duplicates."""
        rule = _make_mock_rule()
        event1 = _make_mock_event(event_id=1)
        event2 = _make_mock_event(event_id=2)

        with patch("app.workers.retro_scan_worker.AsyncSessionLocal") as mock_session_cls:
            mock_session = AsyncMock()
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            with (
                patch(
                    "app.workers.retro_scan_worker._load_campaign_rules",
                    new_callable=AsyncMock,
                    return_value=[rule],
                ),
                patch(
                    "app.workers.retro_scan_worker._fetch_event_batch",
                    new_callable=AsyncMock,
                    side_effect=[[event1, event2], []],
                ),
                patch(
                    "app.services.detection_service.event_matches_rule",
                    return_value=True,
                ),
                patch(
                    "app.services.detection_service._check_x_config_engine",
                    new_callable=AsyncMock,
                    return_value=True,
                ),
                patch(
                    "app.workers.retro_scan_worker._detection_exists",
                    new_callable=AsyncMock,
                    side_effect=[False, True],  # event1 new, event2 duplicate
                ),
                patch(
                    "app.workers.retro_scan_worker._write_retro_detection",
                    new_callable=AsyncMock,
                    return_value=501,
                ),
                patch(
                    "app.workers.retro_scan_worker._send_retro_scan_notification",
                    new_callable=AsyncMock,
                ),
            ):
                result = await _retro_scan(campaign_id=42, lookback_days=7)

        assert result["events_scanned"] == 2
        assert result["detections_created"] == 1
        assert result["duplicates_skipped"] == 1

    @pytest.mark.asyncio
    async def test_no_notification_when_no_matches(self):
        """Should not send notification if no detections created."""
        rule = _make_mock_rule()
        event = _make_mock_event()

        with patch("app.workers.retro_scan_worker.AsyncSessionLocal") as mock_session_cls:
            mock_session = AsyncMock()
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_notify = AsyncMock()
            with (
                patch(
                    "app.workers.retro_scan_worker._load_campaign_rules",
                    new_callable=AsyncMock,
                    return_value=[rule],
                ),
                patch(
                    "app.workers.retro_scan_worker._fetch_event_batch",
                    new_callable=AsyncMock,
                    side_effect=[[event], []],
                ),
                patch(
                    "app.services.detection_service.event_matches_rule",
                    return_value=False,
                ),
                patch(
                    "app.workers.retro_scan_worker._send_retro_scan_notification",
                    mock_notify,
                ),
            ):
                result = await _retro_scan(campaign_id=42, lookback_days=7)

        assert result["detections_created"] == 0
        mock_notify.assert_not_awaited()


class TestRetroScanConstants:
    def test_default_lookback(self):
        assert DEFAULT_LOOKBACK_DAYS == 7

    def test_batch_size(self):
        assert BATCH_SIZE == 1000
