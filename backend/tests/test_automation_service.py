"""Tests for the automation dispatch service."""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.automation_service import (
    _check_rate_limit,
    _rate_windows,
    _record_delivery,
    build_alert_payload,
    deliver_repository_dispatch,
    deliver_webhook,
    dispatch_automation,
    get_matching_targets,
    retry_failed_deliveries,
    sign_payload,
)

# ─── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clear_rate_windows():
    """Clear rate limit state between tests."""
    _rate_windows.clear()
    yield
    _rate_windows.clear()


@pytest.fixture
def sample_detection() -> dict[str, Any]:
    """Return a sample detection dict."""
    return {
        "id": 42,
        "rule_id": 7,
        "triggered_at": "2024-03-15T10:30:00+00:00",
        "severity": "high",
        "confidence": "high",
        "confidence_score": 0.92,
        "status": "open",
        "actor": "evil-user",
        "org": "acme-corp",
        "repo": "acme-corp/secrets",
    }


@pytest.fixture
def sample_rule() -> dict[str, Any]:
    """Return a sample rule dict."""
    return {
        "id": 7,
        "name": "Impossible Travel",
        "slug": "impossible-travel",
        "category": "access_anomaly",
        "logic_type": "behavioral",
    }


@pytest.fixture
def sample_events() -> list[dict[str, Any]]:
    """Return sample contributing events."""
    return [
        {
            "action": "repo.access",
            "created_at": "2024-03-15T10:00:00+00:00",
            "source_ip": "1.2.3.4",
            "repo": "acme-corp/secrets",
        },
        {
            "action": "repo.access",
            "created_at": "2024-03-15T10:05:00+00:00",
            "source_ip": "5.6.7.8",
            "repo": "acme-corp/secrets",
        },
    ]


@pytest.fixture
def webhook_target() -> dict[str, Any]:
    """Return a sample webhook target."""
    return {
        "id": 1,
        "name": "Slack Webhook",
        "target_type": "webhook",
        "webhook_url": "https://hooks.example.com/webhook",
        "webhook_secret": "supersecret123",
        "webhook_headers": {"X-Custom": "value"},
        "dispatch_repo": None,
        "dispatch_event_type": None,
        "dispatch_token_env_var": None,
        "rule_ids": [7, 8],
        "rule_categories": None,
        "severity_filter": None,
        "org_filter": None,
        "is_catch_all": False,
        "rate_limit_per_minute": 60,
        "max_retries": 3,
    }


@pytest.fixture
def dispatch_target() -> dict[str, Any]:
    """Return a sample repository_dispatch target."""
    return {
        "id": 2,
        "name": "Response Workflow",
        "target_type": "repository_dispatch",
        "webhook_url": None,
        "webhook_secret": None,
        "webhook_headers": None,
        "dispatch_repo": "acme-corp/response-automation",
        "dispatch_event_type": "octowatch.high_severity",
        "dispatch_token_env_var": "GH_RESPONSE_TOKEN",
        "rule_ids": None,
        "rule_categories": None,
        "severity_filter": ["high", "critical"],
        "org_filter": None,
        "is_catch_all": False,
        "rate_limit_per_minute": 10,
        "max_retries": 5,
    }


# ─── build_alert_payload tests ────────────────────────────────────────────────


class TestBuildAlertPayload:
    """Tests for build_alert_payload."""

    def test_builds_correct_structure(self, sample_detection, sample_rule, sample_events):
        """Payload contains all expected top-level keys and sub-fields."""
        payload = build_alert_payload(sample_detection, sample_rule, sample_events)

        assert "alert" in payload
        assert "rule" in payload
        assert "actor" in payload
        assert "events" in payload
        assert "meta" in payload

        # Alert fields
        assert payload["alert"]["id"] == 42
        assert payload["alert"]["severity"] == "high"
        assert payload["alert"]["confidence_score"] == 0.92
        assert payload["alert"]["status"] == "open"

        # Rule fields
        assert payload["rule"]["id"] == 7
        assert payload["rule"]["name"] == "Impossible Travel"
        assert payload["rule"]["slug"] == "impossible-travel"
        assert payload["rule"]["category"] == "access_anomaly"

        # Actor fields
        assert payload["actor"]["login"] == "evil-user"
        assert payload["actor"]["org"] == "acme-corp"
        assert payload["actor"]["repo"] == "acme-corp/secrets"

        # Events
        assert len(payload["events"]) == 2
        assert payload["events"][0]["action"] == "repo.access"
        assert payload["events"][0]["source_ip"] == "1.2.3.4"

        # Meta
        assert payload["meta"]["source"] == "octowatch"
        assert payload["meta"]["version"] == "0.1.0"
        assert "delivered_at" in payload["meta"]

    def test_caps_events_at_20(self, sample_detection, sample_rule):
        """Events list is capped at 20 even if more are provided."""
        events = [
            {
                "action": f"action_{i}",
                "created_at": "2024-01-01",
                "source_ip": "1.1.1.1",
                "repo": "r",
            }
            for i in range(50)
        ]
        payload = build_alert_payload(sample_detection, sample_rule, events)
        assert len(payload["events"]) == 20

    def test_handles_no_events(self, sample_detection, sample_rule):
        """Works correctly with no events provided."""
        payload = build_alert_payload(sample_detection, sample_rule, None)
        assert payload["events"] == []

    def test_handles_empty_events(self, sample_detection, sample_rule):
        """Works correctly with empty events list."""
        payload = build_alert_payload(sample_detection, sample_rule, [])
        assert payload["events"] == []


# ─── sign_payload tests ───────────────────────────────────────────────────────


class TestSignPayload:
    """Tests for sign_payload."""

    def test_produces_sha256_prefixed_signature(self):
        """Signature starts with 'sha256=' prefix."""
        sig = sign_payload('{"test": true}', "secret")
        assert sig.startswith("sha256=")

    def test_signature_is_valid_hex(self):
        """Signature after prefix is valid hex and 64 chars (SHA-256)."""
        sig = sign_payload('{"test": true}', "secret")
        hex_part = sig.removeprefix("sha256=")
        assert len(hex_part) == 64
        int(hex_part, 16)  # Should not raise

    def test_signature_is_verifiable(self):
        """Signature can be verified by computing HMAC independently."""
        payload = '{"alert": {"id": 1}}'
        secret = "my-webhook-secret"

        sig = sign_payload(payload, secret)

        # Verify independently
        expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        assert sig == f"sha256={expected}"

    def test_different_secrets_produce_different_signatures(self):
        """Different secrets produce different signatures for same payload."""
        payload = '{"data": "same"}'
        sig1 = sign_payload(payload, "secret-a")
        sig2 = sign_payload(payload, "secret-b")
        assert sig1 != sig2

    def test_different_payloads_produce_different_signatures(self):
        """Different payloads produce different signatures for same secret."""
        secret = "shared-secret"
        sig1 = sign_payload('{"a": 1}', secret)
        sig2 = sign_payload('{"b": 2}', secret)
        assert sig1 != sig2


# ─── _check_rate_limit tests ─────────────────────────────────────────────────


class TestCheckRateLimit:
    """Tests for _check_rate_limit."""

    def test_allows_under_limit(self):
        """Returns True when under the rate limit."""
        assert _check_rate_limit(1, max_per_minute=5) is True
        assert _check_rate_limit(1, max_per_minute=5) is True
        assert _check_rate_limit(1, max_per_minute=5) is True

    def test_blocks_over_limit(self):
        """Returns False when at or over the rate limit."""
        for _ in range(3):
            _check_rate_limit(1, max_per_minute=3)
        # 4th call should be blocked
        assert _check_rate_limit(1, max_per_minute=3) is False

    def test_separate_targets_have_independent_limits(self):
        """Different target_ids have independent rate windows."""
        for _ in range(5):
            _check_rate_limit(1, max_per_minute=5)
        # Target 1 is exhausted
        assert _check_rate_limit(1, max_per_minute=5) is False
        # Target 2 still has capacity
        assert _check_rate_limit(2, max_per_minute=5) is True

    def test_old_entries_expire(self):
        """Entries older than 60 seconds are removed."""
        # Manually add old timestamps
        _rate_windows[99] = [time.time() - 120, time.time() - 90]
        # Should still allow (old entries purged)
        assert _check_rate_limit(99, max_per_minute=1) is True


# ─── get_matching_targets tests ───────────────────────────────────────────────


class TestGetMatchingTargets:
    """Tests for get_matching_targets."""

    def _make_row(self, target_dict: dict[str, Any]) -> MagicMock:
        """Create a mock row with _mapping attribute."""
        row = MagicMock()
        row._mapping = target_dict
        return row

    @pytest.mark.asyncio
    async def test_catch_all_matches_everything(self, sample_detection, sample_rule):
        """A target with is_catch_all=True matches any detection."""
        target = {
            "id": 1,
            "name": "catch-all",
            "target_type": "webhook",
            "webhook_url": "https://example.com",
            "webhook_secret": "",
            "webhook_headers": None,
            "dispatch_repo": None,
            "dispatch_event_type": None,
            "dispatch_token_env_var": None,
            "rule_ids": None,
            "rule_categories": None,
            "severity_filter": None,
            "org_filter": None,
            "is_catch_all": True,
            "rate_limit_per_minute": 60,
            "max_retries": 3,
        }
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [self._make_row(target)]
        db = AsyncMock()
        db.execute.return_value = mock_result

        matches = await get_matching_targets(db, sample_detection, sample_rule)
        assert len(matches) == 1
        assert matches[0]["id"] == 1

    @pytest.mark.asyncio
    async def test_rule_id_match(self, sample_detection, sample_rule):
        """Target matches when rule_ids contains the detection's rule id."""
        target = {
            "id": 2,
            "name": "rule-match",
            "target_type": "webhook",
            "webhook_url": "https://example.com",
            "webhook_secret": "",
            "webhook_headers": None,
            "dispatch_repo": None,
            "dispatch_event_type": None,
            "dispatch_token_env_var": None,
            "rule_ids": [7, 10, 15],
            "rule_categories": None,
            "severity_filter": None,
            "org_filter": None,
            "is_catch_all": False,
            "rate_limit_per_minute": 60,
            "max_retries": 3,
        }
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [self._make_row(target)]
        db = AsyncMock()
        db.execute.return_value = mock_result

        matches = await get_matching_targets(db, sample_detection, sample_rule)
        assert len(matches) == 1

    @pytest.mark.asyncio
    async def test_category_match(self, sample_detection, sample_rule):
        """Target matches when rule_categories contains the rule's category."""
        target = {
            "id": 3,
            "name": "cat-match",
            "target_type": "webhook",
            "webhook_url": "https://example.com",
            "webhook_secret": "",
            "webhook_headers": None,
            "dispatch_repo": None,
            "dispatch_event_type": None,
            "dispatch_token_env_var": None,
            "rule_ids": None,
            "rule_categories": ["access_anomaly", "admin"],
            "severity_filter": None,
            "org_filter": None,
            "is_catch_all": False,
            "rate_limit_per_minute": 60,
            "max_retries": 3,
        }
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [self._make_row(target)]
        db = AsyncMock()
        db.execute.return_value = mock_result

        matches = await get_matching_targets(db, sample_detection, sample_rule)
        assert len(matches) == 1

    @pytest.mark.asyncio
    async def test_severity_match(self, sample_detection, sample_rule):
        """Target matches when severity_filter contains detection severity."""
        target = {
            "id": 4,
            "name": "sev-match",
            "target_type": "webhook",
            "webhook_url": "https://example.com",
            "webhook_secret": "",
            "webhook_headers": None,
            "dispatch_repo": None,
            "dispatch_event_type": None,
            "dispatch_token_env_var": None,
            "rule_ids": None,
            "rule_categories": None,
            "severity_filter": ["high", "critical"],
            "org_filter": None,
            "is_catch_all": False,
            "rate_limit_per_minute": 60,
            "max_retries": 3,
        }
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [self._make_row(target)]
        db = AsyncMock()
        db.execute.return_value = mock_result

        matches = await get_matching_targets(db, sample_detection, sample_rule)
        assert len(matches) == 1

    @pytest.mark.asyncio
    async def test_org_filter_excludes_non_matching(self, sample_detection, sample_rule):
        """Target with org_filter that doesn't match is excluded."""
        target = {
            "id": 5,
            "name": "org-filter",
            "target_type": "webhook",
            "webhook_url": "https://example.com",
            "webhook_secret": "",
            "webhook_headers": None,
            "dispatch_repo": None,
            "dispatch_event_type": None,
            "dispatch_token_env_var": None,
            "rule_ids": None,
            "rule_categories": None,
            "severity_filter": ["high"],
            "org_filter": ["other-org"],
            "is_catch_all": False,
            "rate_limit_per_minute": 60,
            "max_retries": 3,
        }
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [self._make_row(target)]
        db = AsyncMock()
        db.execute.return_value = mock_result

        matches = await get_matching_targets(db, sample_detection, sample_rule)
        assert len(matches) == 0

    @pytest.mark.asyncio
    async def test_org_filter_includes_matching(self, sample_detection, sample_rule):
        """Target with org_filter that matches is included."""
        target = {
            "id": 6,
            "name": "org-ok",
            "target_type": "webhook",
            "webhook_url": "https://example.com",
            "webhook_secret": "",
            "webhook_headers": None,
            "dispatch_repo": None,
            "dispatch_event_type": None,
            "dispatch_token_env_var": None,
            "rule_ids": None,
            "rule_categories": None,
            "severity_filter": ["high"],
            "org_filter": ["acme-corp"],
            "is_catch_all": False,
            "rate_limit_per_minute": 60,
            "max_retries": 3,
        }
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [self._make_row(target)]
        db = AsyncMock()
        db.execute.return_value = mock_result

        matches = await get_matching_targets(db, sample_detection, sample_rule)
        assert len(matches) == 1

    @pytest.mark.asyncio
    async def test_no_match_when_no_criteria_met(self, sample_detection, sample_rule):
        """Target with non-matching filters is excluded."""
        target = {
            "id": 7,
            "name": "no-match",
            "target_type": "webhook",
            "webhook_url": "https://example.com",
            "webhook_secret": "",
            "webhook_headers": None,
            "dispatch_repo": None,
            "dispatch_event_type": None,
            "dispatch_token_env_var": None,
            "rule_ids": [99, 100],
            "rule_categories": ["other_cat"],
            "severity_filter": ["low"],
            "org_filter": None,
            "is_catch_all": False,
            "rate_limit_per_minute": 60,
            "max_retries": 3,
        }
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [self._make_row(target)]
        db = AsyncMock()
        db.execute.return_value = mock_result

        matches = await get_matching_targets(db, sample_detection, sample_rule)
        assert len(matches) == 0


# ─── deliver_webhook tests ────────────────────────────────────────────────────


class TestDeliverWebhook:
    """Tests for deliver_webhook."""

    @pytest.mark.asyncio
    async def test_sends_correct_headers_and_signature(self, webhook_target):
        """Webhook delivery includes correct headers and HMAC signature."""
        payload = {"alert": {"id": 1}}

        with patch("app.services.automation_service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = "OK"
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            status, error = await deliver_webhook(webhook_target, payload)

        assert status == 200
        assert error is None

        # Verify the call
        _, kwargs = mock_client.post.call_args
        sent_headers = kwargs.get("headers", {})
        assert "X-OctoWatch-Signature-256" in sent_headers
        assert sent_headers["X-OctoWatch-Signature-256"].startswith("sha256=")
        assert sent_headers["Content-Type"] == "application/json"
        assert sent_headers["X-Custom"] == "value"

    @pytest.mark.asyncio
    async def test_no_signature_without_secret(self):
        """No signature header when webhook_secret is empty."""
        target = {
            "webhook_url": "https://hooks.example.com/test",
            "webhook_secret": "",
            "webhook_headers": None,
        }
        payload = {"alert": {"id": 1}}

        with patch("app.services.automation_service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = "OK"
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            status, error = await deliver_webhook(target, payload)

        assert status == 200
        _, kwargs = mock_client.post.call_args
        assert "X-OctoWatch-Signature-256" not in kwargs.get("headers", {})

    @pytest.mark.asyncio
    async def test_returns_error_on_4xx(self):
        """Returns error message when server responds with 4xx."""
        target = {
            "webhook_url": "https://hooks.example.com/test",
            "webhook_secret": "",
            "webhook_headers": None,
        }
        payload = {"alert": {"id": 1}}

        with patch("app.services.automation_service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 403
            mock_response.text = "Forbidden"
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            status, error = await deliver_webhook(target, payload)

        assert status == 403
        assert error == "Forbidden"

    @pytest.mark.asyncio
    async def test_handles_timeout(self):
        """Returns None status code and error on timeout."""
        target = {
            "webhook_url": "https://hooks.example.com/test",
            "webhook_secret": "",
            "webhook_headers": None,
        }
        payload = {"alert": {"id": 1}}

        with patch("app.services.automation_service.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = httpx.TimeoutException("timed out")
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            status, error = await deliver_webhook(target, payload)

        assert status is None
        assert error == "Connection timeout"


# ─── deliver_repository_dispatch tests ────────────────────────────────────────


class TestDeliverRepositoryDispatch:
    """Tests for deliver_repository_dispatch."""

    @pytest.mark.asyncio
    async def test_sends_correct_body_and_handles_204(self, dispatch_target):
        """Sends correct dispatch body and handles 204 success."""
        payload = {"alert": {"id": 42}}

        with (
            patch.dict("os.environ", {"GH_RESPONSE_TOKEN": "ghp_test123"}),
            patch("app.services.automation_service.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 204
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            status, error = await deliver_repository_dispatch(dispatch_target, payload)

        assert status == 204
        assert error is None

        # Verify URL and body
        call_args, kwargs = mock_client.post.call_args
        sent_json = kwargs.get("json", {})
        assert sent_json["event_type"] == "octowatch.high_severity"
        assert sent_json["client_payload"] == payload

    @pytest.mark.asyncio
    async def test_returns_error_when_token_not_set(self, dispatch_target):
        """Returns error when token env var is not set."""
        payload = {"alert": {"id": 42}}

        with patch.dict("os.environ", {}, clear=False):
            # Ensure the env var is not set
            import os

            os.environ.pop("GH_RESPONSE_TOKEN", None)

            status, error = await deliver_repository_dispatch(dispatch_target, payload)

        assert status is None
        assert "GH_RESPONSE_TOKEN" in (error or "")

    @pytest.mark.asyncio
    async def test_handles_non_204_response(self, dispatch_target):
        """Returns error message for non-204 responses."""
        payload = {"alert": {"id": 42}}

        with (
            patch.dict("os.environ", {"GH_RESPONSE_TOKEN": "ghp_test123"}),
            patch("app.services.automation_service.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_response.text = "Not Found"
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            status, error = await deliver_repository_dispatch(dispatch_target, payload)

        assert status == 404
        assert error == "Not Found"


# ─── dispatch_automation tests ────────────────────────────────────────────────


class TestDispatchAutomation:
    """Tests for dispatch_automation end-to-end."""

    def _mock_detection_row(self) -> MagicMock:
        """Create a mock row for detection query."""
        row = MagicMock()
        row._mapping = {
            "id": 42,
            "rule_id": 7,
            "triggered_at": "2024-03-15T10:30:00+00:00",
            "severity": "high",
            "confidence": "high",
            "confidence_score": 0.92,
            "status": "open",
            "actor": "evil-user",
            "data": {"org": "acme-corp", "repo": "acme-corp/secrets"},
            "event_ids": [1, 2, 3],
            "rule_name": "Impossible Travel",
            "rule_slug": "impossible-travel",
            "rule_category": "access_anomaly",
            "rule_logic_type": "behavioral",
        }
        return row

    @pytest.mark.asyncio
    async def test_detection_not_found(self):
        """Returns error when detection doesn't exist."""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        db.execute.return_value = mock_result

        result = await dispatch_automation(db, detection_id=999)
        assert result["dispatched"] == 0
        assert result["error"] == "detection not found"

    @pytest.mark.asyncio
    async def test_no_matching_targets(self):
        """Returns zero dispatched when no targets match."""
        db = AsyncMock()

        # First call: detection query
        det_result = MagicMock()
        det_result.fetchone.return_value = self._mock_detection_row()

        # Second call: events query (empty)
        ev_result = MagicMock()
        ev_result.fetchall.return_value = []

        # Third call: targets query (empty)
        targets_result = MagicMock()
        targets_result.fetchall.return_value = []

        db.execute.side_effect = [det_result, ev_result, targets_result]

        result = await dispatch_automation(db, detection_id=42)
        assert result["dispatched"] == 0
        assert result["targets_matched"] == 0

    @pytest.mark.asyncio
    async def test_dry_run_does_not_send(self):
        """Dry run records delivery but doesn't actually send."""
        db = AsyncMock()

        det_result = MagicMock()
        det_result.fetchone.return_value = self._mock_detection_row()

        ev_result = MagicMock()
        ev_result.fetchall.return_value = []

        target_row = MagicMock()
        target_row._mapping = {
            "id": 1,
            "name": "test",
            "target_type": "webhook",
            "webhook_url": "https://example.com",
            "webhook_secret": "",
            "webhook_headers": None,
            "dispatch_repo": None,
            "dispatch_event_type": None,
            "dispatch_token_env_var": None,
            "rule_ids": None,
            "rule_categories": None,
            "severity_filter": None,
            "org_filter": None,
            "is_catch_all": True,
            "rate_limit_per_minute": 60,
            "max_retries": 3,
        }
        targets_result = MagicMock()
        targets_result.fetchall.return_value = [target_row]

        db.execute.side_effect = [det_result, ev_result, targets_result, MagicMock()]

        with patch("app.services.automation_service.deliver_webhook") as mock_deliver:
            result = await dispatch_automation(db, detection_id=42, dry_run=True)

        assert result["dispatched"] == 1
        # deliver_webhook should NOT have been called
        mock_deliver.assert_not_called()

    @pytest.mark.asyncio
    async def test_successful_webhook_delivery(self):
        """Full dispatch with successful webhook delivery."""
        db = AsyncMock()

        det_result = MagicMock()
        det_result.fetchone.return_value = self._mock_detection_row()

        ev_result = MagicMock()
        ev_result.fetchall.return_value = []

        target_row = MagicMock()
        target_row._mapping = {
            "id": 1,
            "name": "test",
            "target_type": "webhook",
            "webhook_url": "https://example.com",
            "webhook_secret": "sec",
            "webhook_headers": None,
            "dispatch_repo": None,
            "dispatch_event_type": None,
            "dispatch_token_env_var": None,
            "rule_ids": [7],
            "rule_categories": None,
            "severity_filter": None,
            "org_filter": None,
            "is_catch_all": False,
            "rate_limit_per_minute": 60,
            "max_retries": 3,
        }
        targets_result = MagicMock()
        targets_result.fetchall.return_value = [target_row]

        # execute calls: detection, events, targets, record_delivery
        db.execute.side_effect = [det_result, ev_result, targets_result, MagicMock()]

        with patch(
            "app.services.automation_service.deliver_webhook",
            return_value=(200, None),
        ):
            result = await dispatch_automation(db, detection_id=42)

        assert result["dispatched"] == 1
        assert result["targets_matched"] == 1
        assert result["failed"] == 0


# ─── _record_delivery tests ──────────────────────────────────────────────────


class TestRecordDelivery:
    """Tests for _record_delivery."""

    @pytest.mark.asyncio
    async def test_inserts_correct_record(self):
        """Delivery record is inserted with correct parameters."""
        db = AsyncMock()

        await _record_delivery(
            db,
            target_id=1,
            detection_id=42,
            status="success",
            payload_hash="abc123",
            response_code=200,
        )

        db.execute.assert_called_once()
        call_args = db.execute.call_args
        params = call_args[0][1]
        assert params["target_id"] == 1
        assert params["detection_id"] == 42
        assert params["status"] == "success"
        assert params["response_code"] == 200
        assert params["payload_hash"] == "abc123"
        assert params["is_dry_run"] is False

    @pytest.mark.asyncio
    async def test_sets_next_retry_on_failure(self):
        """Failed delivery sets next_retry_at."""
        db = AsyncMock()

        await _record_delivery(
            db,
            target_id=1,
            detection_id=42,
            status="failed",
            payload_hash="abc123",
            error_message="timeout",
        )

        call_args = db.execute.call_args
        params = call_args[0][1]
        assert params["next_retry"] is not None
        assert params["error_message"] == "timeout"

    @pytest.mark.asyncio
    async def test_no_next_retry_on_success(self):
        """Successful delivery does not set next_retry_at."""
        db = AsyncMock()

        await _record_delivery(
            db,
            target_id=1,
            detection_id=42,
            status="success",
            payload_hash="abc123",
            response_code=200,
        )

        call_args = db.execute.call_args
        params = call_args[0][1]
        assert params["next_retry"] is None

    @pytest.mark.asyncio
    async def test_dry_run_flag(self):
        """Dry run flag is correctly passed."""
        db = AsyncMock()

        await _record_delivery(
            db,
            target_id=1,
            detection_id=42,
            status="dry_run",
            payload_hash="abc123",
            dry_run=True,
            response_code=200,
        )

        call_args = db.execute.call_args
        params = call_args[0][1]
        assert params["is_dry_run"] is True


# ─── retry_failed_deliveries tests ───────────────────────────────────────────


class TestRetryFailedDeliveries:
    """Tests for retry_failed_deliveries."""

    @pytest.mark.asyncio
    async def test_no_failed_deliveries(self):
        """Returns zero when no failed deliveries exist."""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        db.execute.return_value = mock_result

        result = await retry_failed_deliveries(db)
        assert result["retried"] == 0
        assert result["succeeded"] == 0

    @pytest.mark.asyncio
    async def test_successful_retry(self):
        """Successful retry updates delivery status to success."""
        db = AsyncMock()

        # First call: failed deliveries query
        delivery_row = MagicMock()
        delivery_row._mapping = {
            "id": 10,
            "target_id": 1,
            "detection_id": 42,
            "attempts": 1,
            "max_retries": 3,
            "target_type": "webhook",
            "webhook_url": "https://example.com",
            "webhook_secret": "",
            "webhook_headers": None,
            "dispatch_repo": None,
            "dispatch_event_type": None,
            "dispatch_token_env_var": None,
            "rate_limit_per_minute": 60,
        }
        deliveries_result = MagicMock()
        deliveries_result.fetchall.return_value = [delivery_row]

        # Second call: detection query for rebuilding payload
        det_row = MagicMock()
        det_row._mapping = {
            "id": 42,
            "rule_id": 7,
            "triggered_at": "2024-01-01",
            "severity": "high",
            "confidence": "high",
            "confidence_score": 0.9,
            "status": "open",
            "actor": "user",
            "data": {},
            "event_ids": [],
            "rule_name": "Test Rule",
            "rule_slug": "test-rule",
            "rule_category": "access",
            "rule_logic_type": "threshold",
        }
        det_result = MagicMock()
        det_result.fetchone.return_value = det_row

        # Third call: update delivery
        update_result = MagicMock()

        db.execute.side_effect = [deliveries_result, det_result, update_result]

        with patch(
            "app.services.automation_service.deliver_webhook",
            return_value=(200, None),
        ):
            result = await retry_failed_deliveries(db)

        assert result["retried"] == 1
        assert result["succeeded"] == 1
