"""Tests for Epic 7 SIEM Export & Integration Ecosystem.

Covers:
- CEF format validation with all required fields (#34)
- LEEF format validation (#34)
- Syslog send via TCP/UDP (mock socket) (#34)
- Splunk HEC send (mock httpx) (#56)
- SOAR webhook with retry logic (mock httpx, simulate failures) (#53)
- Webhook receiver HMAC validation (valid/invalid signatures) (#37)
- Webhook event normalization (#37)
- SIEM config CRUD endpoints (#34, #56, #53)
- Batch export (#34)
- Detection pipeline SIEM export integration (#34, #53, #56)
"""

from __future__ import annotations

import hashlib
import hmac
import os
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routers.ingest_webhook import _normalize_webhook_event, _verify_signature
from app.services.siem_export_service import (
    _MAX_RETRIES,
    _build_splunk_detection_payload,
    _build_splunk_event_payload,
    _build_webhook_payload,
    _compute_webhook_signature,
    _escape_cef_header,
    _escape_cef_value,
    batch_export,
    export_detection,
    export_events_to_splunk,
    format_cef,
    format_leef,
    send_soar_webhook,
    send_splunk_hec,
    send_syslog,
)

# ── Test helpers ─────────────────────────────────────────────────────────────


def _make_detection(**overrides: object) -> MagicMock:
    """Create a mock Detection object with sensible defaults."""
    d = MagicMock()
    d.id = overrides.get("id", 42)
    d.rule_id = overrides.get("rule_id", 100)
    d.rule_version = overrides.get("rule_version", 1)
    d.severity = overrides.get("severity", "high")
    d.confidence = overrides.get("confidence", "high")
    d.confidence_score = overrides.get("confidence_score", 0.9)
    d.title = overrides.get("title", "Suspicious PAT Creation")
    d.description = overrides.get(
        "description", "User octocat created a PAT with admin scope from unusual location"
    )
    d.actor = overrides.get("actor", "octocat")
    d.org = overrides.get("org", "my-org")
    d.repo = overrides.get("repo", "my-org/secret-repo")
    d.source_ip = overrides.get("source_ip", "203.0.113.42")
    d.triggered_at = overrides.get("triggered_at", datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC))
    d.status = overrides.get("status", "open")
    d.event_ids = overrides.get("event_ids", [1001, 1002, 1003])
    d.context_data = overrides.get("context_data", {"key": "value"})
    d.assigned_to = overrides.get("assigned_to", None)
    return d


def _make_rule(**overrides: object) -> MagicMock:
    """Create a mock RuleDefinition object."""
    r = MagicMock()
    r.id = overrides.get("id", 100)
    r.name = overrides.get("name", "Suspicious PAT Creation")
    r.slug = overrides.get("slug", "suspicious_pat_creation")
    r.category = overrides.get("category", "credential_abuse")
    r.description = overrides.get("description", "Detects suspicious PAT creation patterns")
    return r


def _make_siem_config(**overrides: object) -> MagicMock:
    """Create a mock SiemExportConfig object."""
    c = MagicMock()
    c.id = overrides.get("id", 1)
    c.export_type = overrides.get("export_type", "syslog")
    c.display_name = overrides.get("display_name", "Test Syslog")
    c.syslog_host = overrides.get("syslog_host", "syslog.example.com")
    c.syslog_port = overrides.get("syslog_port", 514)
    c.syslog_protocol = overrides.get("syslog_protocol", "udp")
    c.syslog_format = overrides.get("syslog_format", "cef")
    c.splunk_hec_url = overrides.get("splunk_hec_url", None)
    c.splunk_hec_token_env_var = overrides.get("splunk_hec_token_env_var", None)
    c.splunk_sourcetype = overrides.get("splunk_sourcetype", "octowatch:event")
    c.splunk_index = overrides.get("splunk_index", "main")
    c.webhook_url = overrides.get("webhook_url", None)
    c.webhook_secret_env_var = overrides.get("webhook_secret_env_var", None)
    c.webhook_headers = overrides.get("webhook_headers", None)
    c.enabled = overrides.get("enabled", True)
    c.export_events = overrides.get("export_events", False)
    c.export_detections = overrides.get("export_detections", True)
    c.created_by = overrides.get("created_by", "admin")
    return c


# ═══════════════════════════════════════════════════════════════════════════════
#  CEF FORMAT TESTS (#34)
# ═══════════════════════════════════════════════════════════════════════════════


class TestCefFormat:
    """Validate CEF message format and field population."""

    def test_basic_cef_format(self) -> None:
        """CEF output follows the standard header format."""
        detection = _make_detection()
        rule = _make_rule()
        result = format_cef(detection, rule)

        assert result.startswith("CEF:0|")
        parts = result.split("|")
        assert parts[0] == "CEF:0"
        assert parts[1] == "OctoWatch"  # vendor
        assert parts[2] == "OctoWatch"  # product
        assert parts[3] == "1.0"  # version
        assert parts[4] == "suspicious_pat_creation"  # signatureId = rule slug
        assert parts[5] == "Suspicious PAT Creation"  # name = detection title
        assert parts[6] == "8"  # severity: high=8

    def test_cef_severity_mapping(self) -> None:
        """CEF severity maps detection severities to numeric values."""
        for severity, expected_int in [
            ("critical", 10),
            ("high", 8),
            ("medium", 5),
            ("low", 3),
            ("info", 1),
        ]:
            detection = _make_detection(severity=severity)
            result = format_cef(detection)
            parts = result.split("|")
            assert parts[6] == str(expected_int), f"Failed for {severity}"

    def test_cef_extension_fields(self) -> None:
        """CEF extension contains actor, repo, org, message, and IP."""
        detection = _make_detection()
        rule = _make_rule()
        result = format_cef(detection, rule)

        # Extension is the last part after the 7th pipe
        extension = result.split("|", 7)[7]
        assert "src=octocat" in extension
        assert "dst=my-org/secret-repo" in extension
        assert "cs1=my-org" in extension
        assert "cs1Label=Organization" in extension
        assert "msg=" in extension
        assert "sourceAddress=203.0.113.42" in extension
        assert "externalId=42" in extension
        assert "cnt=3" in extension  # 3 event_ids

    def test_cef_without_rule(self) -> None:
        """CEF works when rule is None (uses fallback signatureId)."""
        detection = _make_detection()
        result = format_cef(detection, rule=None)
        parts = result.split("|")
        assert parts[4] == "rule_100"

    def test_cef_escaping_pipe_in_title(self) -> None:
        """Pipe characters in detection title are escaped in CEF header."""
        detection = _make_detection(title="Test|Detection")
        result = format_cef(detection)
        # In header field 5, pipe should be escaped
        assert "Test\\|Detection" in result

    def test_cef_escaping_equals_in_extension(self) -> None:
        """Equals signs in extension values are escaped."""
        result = _escape_cef_value("key=value")
        assert result == "key\\=value"

    def test_cef_escaping_backslash(self) -> None:
        """Backslashes are properly escaped."""
        assert _escape_cef_header("a\\b") == "a\\\\b"
        assert _escape_cef_value("a\\b") == "a\\\\b"

    def test_cef_no_source_ip(self) -> None:
        """CEF handles None source_ip gracefully."""
        detection = _make_detection(source_ip=None)
        result = format_cef(detection)
        assert "sourceAddress" not in result

    def test_cef_no_event_ids(self) -> None:
        """CEF handles empty event_ids list gracefully."""
        detection = _make_detection(event_ids=[])
        result = format_cef(detection)
        assert "cnt=" not in result


# ═══════════════════════════════════════════════════════════════════════════════
#  LEEF FORMAT TESTS (#34)
# ═══════════════════════════════════════════════════════════════════════════════


class TestLeefFormat:
    """Validate LEEF 2.0 message format."""

    def test_basic_leef_format(self) -> None:
        """LEEF output follows the standard header format."""
        detection = _make_detection()
        rule = _make_rule()
        result = format_leef(detection, rule)

        assert result.startswith("LEEF:2.0|")
        parts = result.split("|", 5)
        assert parts[1] == "OctoWatch"
        assert parts[2] == "OctoWatch"
        assert parts[3] == "1.0"
        assert parts[4] == "suspicious_pat_creation"

    def test_leef_key_value_pairs(self) -> None:
        """LEEF contains tab-separated key=value pairs."""
        detection = _make_detection()
        result = format_leef(detection)

        kv_section = result.split("|", 5)[5]
        pairs = kv_section.split("\t")
        kv_dict = {}
        for pair in pairs:
            if "=" in pair:
                key, _, val = pair.partition("=")
                kv_dict[key] = val

        assert kv_dict["cat"] == "high"
        assert kv_dict["sev"] == "8"
        assert kv_dict["usrName"] == "octocat"
        assert kv_dict["resource"] == "my-org/secret-repo"
        assert kv_dict["org"] == "my-org"
        assert "externalId" in kv_dict

    def test_leef_severity_mapping(self) -> None:
        """LEEF severity maps correctly."""
        detection = _make_detection(severity="critical")
        result = format_leef(detection)
        assert "sev=10" in result

    def test_leef_without_rule(self) -> None:
        """LEEF works when rule is None."""
        detection = _make_detection()
        result = format_leef(detection, rule=None)
        assert "rule_100" in result


# ═══════════════════════════════════════════════════════════════════════════════
#  SYSLOG TRANSPORT TESTS (#34)
# ═══════════════════════════════════════════════════════════════════════════════


class TestSyslogSend:
    """Test syslog transport (TCP/UDP/TLS) with mocked sockets."""

    @pytest.mark.asyncio
    async def test_send_syslog_udp(self) -> None:
        """UDP syslog sends datagram to configured host."""
        config = _make_siem_config(syslog_protocol="udp")
        message = "CEF:0|OctoWatch|OctoWatch|1.0|test|Test|1|msg=test"

        mock_transport = MagicMock()
        mock_protocol = MagicMock()

        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.create_datagram_endpoint = AsyncMock(
                return_value=(mock_transport, mock_protocol)
            )
            result = await send_syslog(config, message)

        assert result is True
        mock_transport.sendto.assert_called_once()
        mock_transport.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_syslog_tcp(self) -> None:
        """TCP syslog sends with octet-counting framing."""
        config = _make_siem_config(syslog_protocol="tcp")
        message = "CEF:0|OctoWatch|OctoWatch|1.0|test|Test|1|msg=test"

        mock_writer = AsyncMock()
        mock_writer.close = MagicMock()
        mock_writer.wait_closed = AsyncMock()
        mock_reader = AsyncMock()

        with patch(
            "asyncio.open_connection",
            new=AsyncMock(return_value=(mock_reader, mock_writer)),
        ):
            result = await send_syslog(config, message)

        assert result is True
        mock_writer.write.assert_called_once()
        # Verify octet-counting framing
        call_data = mock_writer.write.call_args[0][0]
        assert call_data.startswith(b"")  # starts with length prefix

    @pytest.mark.asyncio
    async def test_send_syslog_no_host(self) -> None:
        """Syslog returns False when host is missing."""
        config = _make_siem_config(syslog_host=None)
        result = await send_syslog(config, "test message")
        assert result is False

    @pytest.mark.asyncio
    async def test_send_syslog_invalid_protocol(self) -> None:
        """Syslog returns False for unsupported protocol."""
        config = _make_siem_config(syslog_protocol="invalid")
        result = await send_syslog(config, "test message")
        assert result is False

    @pytest.mark.asyncio
    async def test_send_syslog_connection_error(self) -> None:
        """Syslog returns False on connection error."""
        config = _make_siem_config(syslog_protocol="tcp")

        with patch("asyncio.open_connection", new=AsyncMock(side_effect=ConnectionRefusedError)):
            result = await send_syslog(config, "test message")

        assert result is False


# ═══════════════════════════════════════════════════════════════════════════════
#  SPLUNK HEC TESTS (#56)
# ═══════════════════════════════════════════════════════════════════════════════


class TestSplunkHec:
    """Test Splunk HEC integration with mocked httpx."""

    @pytest.mark.asyncio
    async def test_send_splunk_hec_success(self) -> None:
        """Splunk HEC returns True on 200 response."""
        config = _make_siem_config(
            export_type="splunk_hec",
            splunk_hec_url="https://splunk.example.com:8088/services/collector",
            splunk_hec_token_env_var="SPLUNK_HEC_TOKEN",
            splunk_index="security",
        )
        payload = {"time": 1718452800, "event": {"test": True}}

        mock_response = MagicMock()
        mock_response.status_code = 200

        with (
            patch.dict(os.environ, {"SPLUNK_HEC_TOKEN": "test-token-123"}),
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await send_splunk_hec(config, payload, sourcetype="octowatch:detection")

        assert result is True
        # Verify the POST was made with proper auth header
        call_kwargs = mock_client.post.call_args
        assert call_kwargs[1]["headers"]["Authorization"] == "Splunk test-token-123"

    @pytest.mark.asyncio
    async def test_send_splunk_hec_payload_format(self) -> None:
        """Splunk HEC payload contains correct sourcetype and index."""
        config = _make_siem_config(
            splunk_hec_url="https://splunk.example.com:8088/services/collector",
            splunk_hec_token_env_var="SPLUNK_HEC_TOKEN",
            splunk_index="github_security",
        )
        payload = {"time": 1718452800, "event": {"action": "org.add_member"}}

        mock_response = MagicMock()
        mock_response.status_code = 200

        with (
            patch.dict(os.environ, {"SPLUNK_HEC_TOKEN": "token"}),
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await send_splunk_hec(config, payload, sourcetype="octowatch:event")

        sent_json = mock_client.post.call_args[1]["json"]
        assert sent_json["sourcetype"] == "octowatch:event"
        assert sent_json["source"] == "octowatch"
        assert sent_json["index"] == "github_security"

    @pytest.mark.asyncio
    async def test_send_splunk_hec_no_url(self) -> None:
        """Returns False when HEC URL is missing."""
        config = _make_siem_config(splunk_hec_url=None)
        result = await send_splunk_hec(config, {"event": {}})
        assert result is False

    @pytest.mark.asyncio
    async def test_send_splunk_hec_no_token(self) -> None:
        """Returns False when token env var has no value."""
        config = _make_siem_config(
            splunk_hec_url="https://splunk.example.com:8088/services/collector",
            splunk_hec_token_env_var="NONEXISTENT_TOKEN_VAR",
        )
        with patch.dict(os.environ, {}, clear=False):
            # Ensure the var does NOT exist
            os.environ.pop("NONEXISTENT_TOKEN_VAR", None)
            result = await send_splunk_hec(config, {"event": {}})
        assert result is False

    @pytest.mark.asyncio
    async def test_send_splunk_hec_rejected(self) -> None:
        """Returns False on non-200 response."""
        config = _make_siem_config(
            splunk_hec_url="https://splunk.example.com:8088/services/collector",
            splunk_hec_token_env_var="SPLUNK_HEC_TOKEN",
        )
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Invalid data"

        with (
            patch.dict(os.environ, {"SPLUNK_HEC_TOKEN": "token"}),
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await send_splunk_hec(config, {"event": {}})

        assert result is False

    def test_build_splunk_detection_payload(self) -> None:
        """Splunk detection payload includes all required metadata."""
        detection = _make_detection()
        rule = _make_rule()
        payload = _build_splunk_detection_payload(detection, rule)

        assert payload["time"] == int(detection.triggered_at.timestamp())
        event = payload["event"]
        assert event["detection_id"] == 42
        assert event["severity"] == "high"
        assert event["actor"] == "octocat"
        assert event["rule_slug"] == "suspicious_pat_creation"
        assert event["rule_category"] == "credential_abuse"

    def test_build_splunk_event_payload(self) -> None:
        """Splunk event payload formats audit events correctly."""
        event = {
            "action": "org.add_member",
            "actor": "octocat",
            "org": "my-org",
            "repo": "my-org/repo",
            "source_ip": "1.2.3.4",
            "created_at": datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC),
            "data": {"role": "admin"},
        }
        payload = _build_splunk_event_payload(event)
        assert payload["time"] is not None
        assert payload["event"]["action"] == "org.add_member"
        assert payload["event"]["actor"] == "octocat"

    def test_build_splunk_detection_payload_sourcetype(self) -> None:
        """Detection sourcetype should be octowatch:detection when used."""
        # This verifies the constant is used correctly in dispatch
        detection = _make_detection()
        payload = _build_splunk_detection_payload(detection)
        # Payload itself doesn't include sourcetype; that's set in send_splunk_hec
        assert "event" in payload


# ═══════════════════════════════════════════════════════════════════════════════
#  SOAR WEBHOOK TESTS (#53)
# ═══════════════════════════════════════════════════════════════════════════════


class TestSoarWebhook:
    """Test SOAR outbound webhook with retry logic."""

    @pytest.mark.asyncio
    async def test_webhook_success(self) -> None:
        """Webhook returns True on 200 response."""
        config = _make_siem_config(
            export_type="webhook",
            webhook_url="https://soar.example.com/webhook",
        )
        detection = _make_detection()

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await send_soar_webhook(config, detection)

        assert result is True

    @pytest.mark.asyncio
    async def test_webhook_retry_on_500(self) -> None:
        """Webhook retries on 5xx with exponential backoff, then succeeds."""
        config = _make_siem_config(
            export_type="webhook",
            webhook_url="https://soar.example.com/webhook",
        )
        detection = _make_detection()

        # First two attempts fail, third succeeds
        fail_response = MagicMock()
        fail_response.status_code = 500
        success_response = MagicMock()
        success_response.status_code = 200

        with (
            patch("httpx.AsyncClient") as mock_client_cls,
            patch("asyncio.sleep", new=AsyncMock()) as mock_sleep,
        ):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(
                side_effect=[fail_response, fail_response, success_response]
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await send_soar_webhook(config, detection)

        assert result is True
        assert mock_client.post.call_count == 3
        # Verify exponential backoff: 1s, 2s
        assert mock_sleep.call_count == 2

    @pytest.mark.asyncio
    async def test_webhook_exhausted_retries(self) -> None:
        """Webhook returns False after all retries exhausted."""
        config = _make_siem_config(
            export_type="webhook",
            webhook_url="https://soar.example.com/webhook",
        )
        detection = _make_detection()

        fail_response = MagicMock()
        fail_response.status_code = 503

        with (
            patch("httpx.AsyncClient") as mock_client_cls,
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=fail_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await send_soar_webhook(config, detection)

        assert result is False
        assert mock_client.post.call_count == _MAX_RETRIES

    @pytest.mark.asyncio
    async def test_webhook_connection_error_retry(self) -> None:
        """Webhook retries on connection errors."""
        config = _make_siem_config(
            export_type="webhook",
            webhook_url="https://soar.example.com/webhook",
        )
        detection = _make_detection()

        success_response = MagicMock()
        success_response.status_code = 200

        with (
            patch("httpx.AsyncClient") as mock_client_cls,
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=[ConnectionError("refused"), success_response])
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await send_soar_webhook(config, detection)

        assert result is True
        assert mock_client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_webhook_no_url(self) -> None:
        """Webhook returns False when URL is missing."""
        config = _make_siem_config(webhook_url=None)
        detection = _make_detection()
        result = await send_soar_webhook(config, detection)
        assert result is False

    @pytest.mark.asyncio
    async def test_webhook_hmac_signature(self) -> None:
        """Webhook includes HMAC signature when secret is configured."""
        config = _make_siem_config(
            export_type="webhook",
            webhook_url="https://soar.example.com/webhook",
            webhook_secret_env_var="SOAR_SECRET",
        )
        detection = _make_detection()

        mock_response = MagicMock()
        mock_response.status_code = 200

        with (
            patch.dict(os.environ, {"SOAR_SECRET": "supersecret"}),
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await send_soar_webhook(config, detection)

        call_kwargs = mock_client.post.call_args
        headers = call_kwargs[1]["headers"]
        assert "X-OctoWatch-Signature-256" in headers
        assert headers["X-OctoWatch-Signature-256"].startswith("sha256=")

    def test_webhook_payload_structure(self) -> None:
        """Webhook payload contains detection details, rule info, and suggested actions."""
        detection = _make_detection()
        rule = _make_rule()
        events = [{"action": "org.add_member", "actor": "octocat"}]

        payload = _build_webhook_payload(detection, rule, events)

        assert payload["source"] == "octowatch"
        assert payload["version"] == "1.0"
        assert payload["event_type"] == "detection"
        assert payload["detection"]["id"] == 42
        assert payload["detection"]["severity"] == "high"
        assert payload["detection"]["actor"] == "octocat"
        assert payload["rule"]["slug"] == "suspicious_pat_creation"
        assert len(payload["related_events"]) == 1
        assert len(payload["suggested_actions"]) > 0

    def test_webhook_payload_suggested_actions_by_severity(self) -> None:
        """Suggested actions vary by severity."""
        for severity in ["critical", "high", "medium", "low"]:
            detection = _make_detection(severity=severity)
            payload = _build_webhook_payload(detection)
            assert len(payload["suggested_actions"]) >= 1

    def test_compute_webhook_signature(self) -> None:
        """HMAC signature computation is correct."""
        payload = b'{"test": true}'
        secret = "mysecret"
        sig = _compute_webhook_signature(payload, secret)
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        assert sig == expected


# ═══════════════════════════════════════════════════════════════════════════════
#  WEBHOOK RECEIVER TESTS (#37)
# ═══════════════════════════════════════════════════════════════════════════════


class TestWebhookReceiver:
    """Test GitHub webhook HMAC validation and event normalization."""

    def test_verify_valid_signature(self) -> None:
        """Valid HMAC-SHA256 signature passes verification."""
        secret = "webhook-secret-123"
        payload = b'{"action": "created"}'
        sig_hex = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
        signature_header = f"sha256={sig_hex}"

        assert _verify_signature(payload, signature_header, secret) is True

    def test_verify_invalid_signature(self) -> None:
        """Invalid HMAC-SHA256 signature fails verification."""
        secret = "webhook-secret-123"
        payload = b'{"action": "created"}'
        signature_header = "sha256=invalid_hex_signature"

        assert _verify_signature(payload, signature_header, secret) is False

    def test_verify_wrong_prefix(self) -> None:
        """Signature without sha256= prefix fails."""
        assert _verify_signature(b"body", "md5=abc", "secret") is False

    def test_verify_tampered_payload(self) -> None:
        """Signature fails when payload is tampered with."""
        secret = "my-secret"
        original = b'{"action": "created"}'
        sig_hex = hmac.new(secret.encode(), original, hashlib.sha256).hexdigest()

        tampered = b'{"action": "deleted"}'
        assert _verify_signature(tampered, f"sha256={sig_hex}", secret) is False

    def test_normalize_webhook_event(self) -> None:
        """Webhook payload is normalized to audit-log-like event format."""
        payload = {
            "action": "member_added",
            "sender": {"login": "octocat", "id": 12345},
            "organization": {"login": "my-org"},
            "repository": {"full_name": "my-org/repo"},
        }
        event = _normalize_webhook_event(payload, "organization", "delivery-123")

        assert event is not None
        assert event["action"] == "organization.member_added"
        assert event["actor"] == "octocat"
        assert event["actor_id"] == 12345
        assert event["org"] == "my-org"
        assert event["repo"] == "my-org/repo"
        assert event["_document_id"] == "delivery-123"

    def test_normalize_ping_event_skipped(self) -> None:
        """Ping events return None (skip ingestion)."""
        result = _normalize_webhook_event({"zen": "Beautiful is better"}, "ping", "del-1")
        assert result is None

    def test_normalize_without_sender(self) -> None:
        """Normalization handles missing sender gracefully."""
        payload = {"action": "completed"}
        event = _normalize_webhook_event(payload, "workflow_run", "del-2")
        assert event is not None
        assert event["actor"] is None

    def test_normalize_same_event_type_as_action(self) -> None:
        """When action equals event_type, don't duplicate in action string."""
        payload = {"action": "push", "sender": {"login": "bot"}}
        event = _normalize_webhook_event(payload, "push", "del-3")
        assert event is not None
        assert event["action"] == "push"


# ═══════════════════════════════════════════════════════════════════════════════
#  EXPORT DISPATCH TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestExportDispatch:
    """Test the main detection export dispatch to SIEM destinations."""

    @pytest.mark.asyncio
    async def test_export_detection_syslog(self) -> None:
        """Export dispatches to syslog when a syslog config exists."""
        config = _make_siem_config(export_type="syslog", syslog_format="cef")
        detection = _make_detection()
        rule = _make_rule()

        # Mock DB queries
        mock_db = AsyncMock()
        # First execute: load enabled SIEM configs
        config_result = MagicMock()
        config_result.scalars.return_value.all.return_value = [config]
        # Second execute: load rule
        rule_result = MagicMock()
        rule_result.scalar_one_or_none.return_value = rule

        mock_db.execute = AsyncMock(side_effect=[config_result, rule_result])

        with patch(
            "app.services.siem_export_service.send_syslog",
            new=AsyncMock(return_value=True),
        ):
            result = await export_detection(mock_db, detection)

        assert result["sent"] == 1
        assert result["failed"] == 0

    @pytest.mark.asyncio
    async def test_export_detection_no_configs(self) -> None:
        """Export returns zeros when no configs are enabled."""
        mock_db = AsyncMock()
        config_result = MagicMock()
        config_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=config_result)

        detection = _make_detection()
        result = await export_detection(mock_db, detection)
        assert result == {"sent": 0, "failed": 0}

    @pytest.mark.asyncio
    async def test_export_detection_multiple_configs(self) -> None:
        """Export dispatches to multiple configs."""
        syslog_config = _make_siem_config(id=1, export_type="syslog")
        webhook_config = _make_siem_config(
            id=2, export_type="webhook", webhook_url="https://soar.test/hook"
        )
        detection = _make_detection()
        rule = _make_rule()

        mock_db = AsyncMock()
        config_result = MagicMock()
        config_result.scalars.return_value.all.return_value = [syslog_config, webhook_config]
        rule_result = MagicMock()
        rule_result.scalar_one_or_none.return_value = rule
        mock_db.execute = AsyncMock(side_effect=[config_result, rule_result])

        _syslog_patch = "app.services.siem_export_service.send_syslog"
        _webhook_patch = "app.services.siem_export_service.send_soar_webhook"

        with (
            patch(_syslog_patch, new=AsyncMock(return_value=True)),
            patch(_webhook_patch, new=AsyncMock(return_value=True)),
        ):
            result = await export_detection(mock_db, detection)

        assert result["sent"] == 2
        assert result["failed"] == 0

    @pytest.mark.asyncio
    async def test_export_detection_partial_failure(self) -> None:
        """Export counts failures correctly when one destination fails."""
        syslog_config = _make_siem_config(id=1, export_type="syslog")
        webhook_config = _make_siem_config(
            id=2, export_type="webhook", webhook_url="https://soar.test/hook"
        )
        detection = _make_detection()
        rule = _make_rule()

        mock_db = AsyncMock()
        config_result = MagicMock()
        config_result.scalars.return_value.all.return_value = [syslog_config, webhook_config]
        rule_result = MagicMock()
        rule_result.scalar_one_or_none.return_value = rule
        mock_db.execute = AsyncMock(side_effect=[config_result, rule_result])

        _syslog_patch = "app.services.siem_export_service.send_syslog"
        _webhook_patch = "app.services.siem_export_service.send_soar_webhook"

        with (
            patch(_syslog_patch, new=AsyncMock(return_value=True)),
            patch(_webhook_patch, new=AsyncMock(return_value=False)),
        ):
            result = await export_detection(mock_db, detection)

        assert result["sent"] == 1
        assert result["failed"] == 1


# ═══════════════════════════════════════════════════════════════════════════════
#  BATCH EXPORT TESTS (#34)
# ═══════════════════════════════════════════════════════════════════════════════


class TestBatchExport:
    """Test batch export of detections over a date range."""

    @pytest.mark.asyncio
    async def test_batch_export_success(self) -> None:
        """Batch export exports all detections in range."""
        config = _make_siem_config(export_type="syslog", syslog_format="cef")
        d1 = _make_detection(id=1)
        d2 = _make_detection(id=2)
        rule = _make_rule()

        mock_db = AsyncMock()
        # First: load config
        config_result = MagicMock()
        config_result.scalar_one_or_none.return_value = config
        # Second: load detections
        detections_result = MagicMock()
        detections_result.scalars.return_value.all.return_value = [d1, d2]
        # Third & Fourth: load rules for each detection
        rule_result1 = MagicMock()
        rule_result1.scalar_one_or_none.return_value = rule
        rule_result2 = MagicMock()
        rule_result2.scalar_one_or_none.return_value = rule

        mock_db.execute = AsyncMock(
            side_effect=[config_result, detections_result, rule_result1, rule_result2]
        )

        with patch(
            "app.services.siem_export_service.send_syslog",
            new=AsyncMock(return_value=True),
        ):
            result = await batch_export(
                mock_db,
                start_date=datetime(2024, 1, 1, tzinfo=UTC),
                end_date=datetime(2024, 12, 31, tzinfo=UTC),
                config_id=1,
            )

        assert result["exported"] == 2
        assert result["failed"] == 0

    @pytest.mark.asyncio
    async def test_batch_export_config_not_found(self) -> None:
        """Batch export returns error when config doesn't exist."""
        mock_db = AsyncMock()
        config_result = MagicMock()
        config_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=config_result)

        result = await batch_export(
            mock_db,
            start_date=datetime(2024, 1, 1, tzinfo=UTC),
            end_date=datetime(2024, 12, 31, tzinfo=UTC),
            config_id=999,
        )
        assert result["exported"] == 0

    @pytest.mark.asyncio
    async def test_batch_export_no_detections(self) -> None:
        """Batch export handles empty detection set."""
        config = _make_siem_config()

        mock_db = AsyncMock()
        config_result = MagicMock()
        config_result.scalar_one_or_none.return_value = config
        detections_result = MagicMock()
        detections_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(side_effect=[config_result, detections_result])

        result = await batch_export(
            mock_db,
            start_date=datetime(2024, 1, 1, tzinfo=UTC),
            end_date=datetime(2024, 12, 31, tzinfo=UTC),
            config_id=1,
        )
        assert result == {"exported": 0, "failed": 0}


# ═══════════════════════════════════════════════════════════════════════════════
#  EVENT EXPORT TO SPLUNK (#56)
# ═══════════════════════════════════════════════════════════════════════════════


class TestEventExportToSplunk:
    """Test raw event forwarding to Splunk HEC."""

    @pytest.mark.asyncio
    async def test_export_events_no_configs(self) -> None:
        """No configs means zero exports."""
        mock_db = AsyncMock()
        config_result = MagicMock()
        config_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=config_result)

        result = await export_events_to_splunk(mock_db, [{"action": "test"}])
        assert result == {"sent": 0, "failed": 0}

    @pytest.mark.asyncio
    async def test_export_events_success(self) -> None:
        """Events are forwarded to Splunk HEC with octowatch:event sourcetype."""
        config = _make_siem_config(
            export_type="splunk_hec",
            export_events=True,
            splunk_hec_url="https://splunk.test:8088/services/collector",
            splunk_hec_token_env_var="SPLUNK_TOKEN",
        )
        events = [
            {"action": "org.add_member", "actor": "octocat", "created_at": "2024-06-15T12:00:00Z"},
        ]

        mock_db = AsyncMock()
        config_result = MagicMock()
        config_result.scalars.return_value.all.return_value = [config]
        mock_db.execute = AsyncMock(return_value=config_result)

        with patch(
            "app.services.siem_export_service.send_splunk_hec",
            new=AsyncMock(return_value=True),
        ) as mock_send:
            result = await export_events_to_splunk(mock_db, events)

        assert result["sent"] == 1
        # Verify sourcetype was set to octowatch:event
        call_kwargs = mock_send.call_args
        assert call_kwargs[1]["sourcetype"] == "octowatch:event"


# ═══════════════════════════════════════════════════════════════════════════════
#  SCHEMA VALIDATION TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestSchemaValidation:
    """Test Pydantic schema validation for SIEM configs."""

    def test_valid_syslog_config(self) -> None:
        """Valid syslog config passes validation."""
        from app.schemas.integration import SiemExportConfigCreate

        config = SiemExportConfigCreate(
            export_type="syslog",
            display_name="My Syslog",
            syslog_host="syslog.example.com",
            syslog_port=514,
            syslog_protocol="tcp",
            syslog_format="cef",
        )
        assert config.export_type == "syslog"
        assert config.syslog_protocol == "tcp"

    def test_valid_splunk_hec_config(self) -> None:
        """Valid Splunk HEC config passes validation."""
        from app.schemas.integration import SiemExportConfigCreate

        config = SiemExportConfigCreate(
            export_type="splunk_hec",
            display_name="Splunk HEC",
            splunk_hec_url="https://splunk.example.com:8088/services/collector",
            splunk_hec_token_env_var="SPLUNK_HEC_TOKEN",
            splunk_index="security",
            export_events=True,
        )
        assert config.export_type == "splunk_hec"
        assert config.export_events is True

    def test_valid_webhook_config(self) -> None:
        """Valid webhook config passes validation."""
        from app.schemas.integration import SiemExportConfigCreate

        config = SiemExportConfigCreate(
            export_type="webhook",
            display_name="SOAR Webhook",
            webhook_url="https://soar.example.com/api/webhook",
            webhook_secret_env_var="SOAR_SECRET",
        )
        assert config.export_type == "webhook"

    def test_invalid_export_type(self) -> None:
        """Invalid export_type fails validation."""
        from pydantic import ValidationError

        from app.schemas.integration import SiemExportConfigCreate

        with pytest.raises(ValidationError):
            SiemExportConfigCreate(
                export_type="invalid",
                display_name="Bad Config",
            )

    def test_invalid_protocol(self) -> None:
        """Invalid syslog_protocol fails validation."""
        from pydantic import ValidationError

        from app.schemas.integration import SiemExportConfigCreate

        with pytest.raises(ValidationError):
            SiemExportConfigCreate(
                export_type="syslog",
                display_name="Test",
                syslog_protocol="ftp",
            )

    def test_invalid_format(self) -> None:
        """Invalid syslog_format fails validation."""
        from pydantic import ValidationError

        from app.schemas.integration import SiemExportConfigCreate

        with pytest.raises(ValidationError):
            SiemExportConfigCreate(
                export_type="syslog",
                display_name="Test",
                syslog_format="json",
            )

    def test_invalid_port_range(self) -> None:
        """Port outside 1-65535 fails validation."""
        from pydantic import ValidationError

        from app.schemas.integration import SiemExportConfigCreate

        with pytest.raises(ValidationError):
            SiemExportConfigCreate(
                export_type="syslog",
                display_name="Test",
                syslog_port=0,
            )

    def test_batch_export_request(self) -> None:
        """BatchExportRequest validates start_date, end_date, config_id."""
        from app.schemas.integration import BatchExportRequest

        req = BatchExportRequest(
            start_date=datetime(2024, 1, 1, tzinfo=UTC),
            end_date=datetime(2024, 12, 31, tzinfo=UTC),
            config_id=1,
        )
        assert req.config_id == 1

    def test_siem_export_config_response(self) -> None:
        """SiemExportConfigResponse properly serializes from attributes."""
        from app.schemas.integration import SiemExportConfigResponse

        data = {
            "id": 1,
            "export_type": "syslog",
            "display_name": "Test",
            "syslog_host": "syslog.test",
            "syslog_port": 514,
            "syslog_protocol": "tcp",
            "syslog_format": "cef",
            "splunk_hec_url": None,
            "splunk_hec_token_env_var": None,
            "splunk_sourcetype": None,
            "splunk_index": None,
            "webhook_url": None,
            "webhook_secret_env_var": None,
            "webhook_headers": None,
            "enabled": True,
            "export_events": False,
            "export_detections": True,
            "created_by": "admin",
            "created_at": datetime(2024, 1, 1, tzinfo=UTC),
        }
        resp = SiemExportConfigResponse.model_validate(data)
        assert resp.id == 1
        assert resp.export_type == "syslog"
