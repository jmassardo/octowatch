"""Unit tests for new threat intel detection engines (#336)."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.detection_service import (
    _check_threat_intel_action_ref,
    _check_threat_intel_actor,
    _check_threat_intel_commit_author,
    _check_threat_intel_scope,
)


def _make_event(
    *,
    actor: str | None = None,
    data: dict | None = None,
    source_ip: str | None = None,
) -> MagicMock:
    """Create a mock AuditEvent with specified attributes."""
    event = MagicMock()
    event.actor = actor
    event.data = data or {}
    event.source_ip = source_ip
    return event


def _make_indicator(
    *,
    value: str,
    indicator_type: str = "github_username",
    active: bool = True,
    campaign_id: int | None = None,
    expires_at: datetime | None = None,
) -> MagicMock:
    """Create a mock ThreatIntelIndicator."""
    indicator = MagicMock()
    indicator.value = value
    indicator.indicator_type = indicator_type
    indicator.active = active
    indicator.campaign_id = campaign_id
    indicator.expires_at = expires_at
    return indicator


@pytest.fixture
def mock_session():
    """Create a mock AsyncSession that returns configurable query results."""
    session = AsyncMock()
    return session


def _setup_session_with_indicator(session: AsyncMock, indicator=None):
    """Configure mock session to return a specific indicator from execute()."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = indicator
    mock_result.scalars.return_value.all.return_value = [indicator] if indicator else []
    session.execute = AsyncMock(return_value=mock_result)


# =============================================================================
# _check_threat_intel_actor
# =============================================================================


class TestThreatIntelActor:
    """Tests for the threat_intel_actor engine."""

    @pytest.mark.asyncio
    async def test_returns_false_when_no_actor(self, mock_session):
        event = _make_event(actor=None)
        x_config = {"engine": "threat_intel_actor"}
        result = await _check_threat_intel_actor(event, x_config, mock_session)
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_true_when_actor_matches_indicator(self, mock_session):
        event = _make_event(actor="evil-user")
        indicator = _make_indicator(value="evil-user")
        _setup_session_with_indicator(mock_session, indicator)
        x_config = {"engine": "threat_intel_actor"}
        result = await _check_threat_intel_actor(event, x_config, mock_session)
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_actor_not_in_indicators(self, mock_session):
        event = _make_event(actor="good-user")
        _setup_session_with_indicator(mock_session, None)
        x_config = {"engine": "threat_intel_actor"}
        result = await _check_threat_intel_actor(event, x_config, mock_session)
        assert result is False

    @pytest.mark.asyncio
    async def test_respects_campaign_id_filter(self, mock_session):
        event = _make_event(actor="target-user")
        _setup_session_with_indicator(mock_session, None)
        x_config = {"engine": "threat_intel_actor", "campaign_id": 42}
        result = await _check_threat_intel_actor(event, x_config, mock_session)
        assert result is False
        # Verify the query was called (campaign filter applied)
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_custom_indicator_type(self, mock_session):
        event = _make_event(actor="bad-bot")
        indicator = _make_indicator(value="bad-bot", indicator_type="bot_account")
        _setup_session_with_indicator(mock_session, indicator)
        x_config = {"engine": "threat_intel_actor", "indicator_type": "bot_account"}
        result = await _check_threat_intel_actor(event, x_config, mock_session)
        assert result is True

    @pytest.mark.asyncio
    async def test_graceful_failure_on_exception(self, mock_session):
        event = _make_event(actor="user")
        mock_session.execute = AsyncMock(side_effect=RuntimeError("DB error"))
        x_config = {"engine": "threat_intel_actor"}
        result = await _check_threat_intel_actor(event, x_config, mock_session)
        assert result is False


# =============================================================================
# _check_threat_intel_commit_author
# =============================================================================


class TestThreatIntelCommitAuthor:
    """Tests for the threat_intel_commit_author engine."""

    @pytest.mark.asyncio
    async def test_returns_false_when_no_email_fields(self, mock_session):
        event = _make_event(data={"something_else": "value"})
        x_config = {"engine": "threat_intel_commit_author"}
        result = await _check_threat_intel_commit_author(event, x_config, mock_session)
        assert result is False

    @pytest.mark.asyncio
    async def test_matches_author_email(self, mock_session):
        event = _make_event(data={"author_email": "attacker@evil.com"})
        indicator = _make_indicator(value="attacker@evil.com", indicator_type="commit_author_email")
        _setup_session_with_indicator(mock_session, indicator)
        x_config = {"engine": "threat_intel_commit_author"}
        result = await _check_threat_intel_commit_author(event, x_config, mock_session)
        assert result is True

    @pytest.mark.asyncio
    async def test_matches_committer_email(self, mock_session):
        event = _make_event(data={"committer_email": "bad@evil.org"})
        indicator = _make_indicator(value="bad@evil.org", indicator_type="commit_author_email")
        _setup_session_with_indicator(mock_session, indicator)
        x_config = {"engine": "threat_intel_commit_author"}
        result = await _check_threat_intel_commit_author(event, x_config, mock_session)
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_email_not_in_indicators(self, mock_session):
        event = _make_event(data={"author_email": "good@legit.com"})
        _setup_session_with_indicator(mock_session, None)
        x_config = {"engine": "threat_intel_commit_author"}
        result = await _check_threat_intel_commit_author(event, x_config, mock_session)
        assert result is False

    @pytest.mark.asyncio
    async def test_checks_both_author_and_committer(self, mock_session):
        event = _make_event(
            data={
                "author_email": "legit@good.com",
                "committer_email": "evil@bad.com",
            }
        )
        indicator = _make_indicator(value="evil@bad.com", indicator_type="commit_author_email")
        _setup_session_with_indicator(mock_session, indicator)
        x_config = {"engine": "threat_intel_commit_author"}
        result = await _check_threat_intel_commit_author(event, x_config, mock_session)
        assert result is True

    @pytest.mark.asyncio
    async def test_graceful_failure_on_exception(self, mock_session):
        event = _make_event(data={"author_email": "x@y.com"})
        mock_session.execute = AsyncMock(side_effect=RuntimeError("DB error"))
        x_config = {"engine": "threat_intel_commit_author"}
        result = await _check_threat_intel_commit_author(event, x_config, mock_session)
        assert result is False


# =============================================================================
# _check_threat_intel_scope
# =============================================================================


class TestThreatIntelScope:
    """Tests for the threat_intel_scope engine."""

    @pytest.mark.asyncio
    async def test_returns_false_when_no_package_name(self, mock_session):
        event = _make_event(data={})
        x_config = {"engine": "threat_intel_scope"}
        result = await _check_threat_intel_scope(event, x_config, mock_session)
        assert result is False

    @pytest.mark.asyncio
    async def test_matches_scope_prefix(self, mock_session):
        event = _make_event(data={"package_name": "@evil-scope/some-pkg"})
        indicator = _make_indicator(value="@evil-scope", indicator_type="npm_scope")
        _setup_session_with_indicator(mock_session, indicator)
        x_config = {"engine": "threat_intel_scope"}
        result = await _check_threat_intel_scope(event, x_config, mock_session)
        assert result is True

    @pytest.mark.asyncio
    async def test_exact_scope_match(self, mock_session):
        event = _make_event(data={"package_name": "@evil-scope"})
        indicator = _make_indicator(value="@evil-scope", indicator_type="npm_scope")
        _setup_session_with_indicator(mock_session, indicator)
        x_config = {"engine": "threat_intel_scope"}
        result = await _check_threat_intel_scope(event, x_config, mock_session)
        assert result is True

    @pytest.mark.asyncio
    async def test_no_match_for_similar_but_different_scope(self, mock_session):
        # "@evil-scope-extended/pkg" should NOT match indicator "@evil-scope"
        event = _make_event(data={"package_name": "@evil-scope-extended/pkg"})
        indicator = _make_indicator(value="@evil-scope", indicator_type="npm_scope")
        _setup_session_with_indicator(mock_session, indicator)
        x_config = {"engine": "threat_intel_scope"}
        result = await _check_threat_intel_scope(event, x_config, mock_session)
        assert result is False

    @pytest.mark.asyncio
    async def test_uses_name_field_fallback(self, mock_session):
        event = _make_event(data={"name": "@bad/thing"})
        indicator = _make_indicator(value="@bad", indicator_type="npm_scope")
        _setup_session_with_indicator(mock_session, indicator)
        x_config = {"engine": "threat_intel_scope"}
        result = await _check_threat_intel_scope(event, x_config, mock_session)
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_no_indicators_match(self, mock_session):
        event = _make_event(data={"package_name": "@legit-scope/pkg"})
        _setup_session_with_indicator(mock_session, None)
        x_config = {"engine": "threat_intel_scope"}
        result = await _check_threat_intel_scope(event, x_config, mock_session)
        assert result is False

    @pytest.mark.asyncio
    async def test_graceful_failure_on_exception(self, mock_session):
        event = _make_event(data={"package_name": "@x/y"})
        mock_session.execute = AsyncMock(side_effect=RuntimeError("DB error"))
        x_config = {"engine": "threat_intel_scope"}
        result = await _check_threat_intel_scope(event, x_config, mock_session)
        assert result is False


# =============================================================================
# _check_threat_intel_action_ref
# =============================================================================


class TestThreatIntelActionRef:
    """Tests for the threat_intel_action_ref engine."""

    @pytest.mark.asyncio
    async def test_returns_false_when_no_action_refs(self, mock_session):
        event = _make_event(data={"some_field": "value"})
        x_config = {"engine": "threat_intel_action_ref"}
        result = await _check_threat_intel_action_ref(event, x_config, mock_session)
        assert result is False

    @pytest.mark.asyncio
    async def test_matches_action_ref_field(self, mock_session):
        event = _make_event(data={"action_ref": "evil-org/malicious-action@v1"})
        indicator = _make_indicator(value="evil-org/malicious-action", indicator_type="action_ref")
        _setup_session_with_indicator(mock_session, indicator)
        x_config = {"engine": "threat_intel_action_ref"}
        result = await _check_threat_intel_action_ref(event, x_config, mock_session)
        assert result is True

    @pytest.mark.asyncio
    async def test_matches_uses_field(self, mock_session):
        event = _make_event(data={"uses": "bad-owner/bad-action@main"})
        indicator = _make_indicator(value="bad-owner/bad-action", indicator_type="action_ref")
        _setup_session_with_indicator(mock_session, indicator)
        x_config = {"engine": "threat_intel_action_ref"}
        result = await _check_threat_intel_action_ref(event, x_config, mock_session)
        assert result is True

    @pytest.mark.asyncio
    async def test_matches_exact_versioned_ref(self, mock_session):
        event = _make_event(data={"action_ref": "evil-org/malicious-action@abc123"})
        indicator = _make_indicator(
            value="evil-org/malicious-action@abc123", indicator_type="action_ref"
        )
        _setup_session_with_indicator(mock_session, indicator)
        x_config = {"engine": "threat_intel_action_ref"}
        result = await _check_threat_intel_action_ref(event, x_config, mock_session)
        assert result is True

    @pytest.mark.asyncio
    async def test_checks_nested_actions_list(self, mock_session):
        event = _make_event(
            data={
                "actions": [
                    {"uses": "good/action@v1"},
                    {"uses": "evil/action@v2"},
                ]
            }
        )
        indicator = _make_indicator(value="evil/action", indicator_type="action_ref")
        _setup_session_with_indicator(mock_session, indicator)
        x_config = {"engine": "threat_intel_action_ref"}
        result = await _check_threat_intel_action_ref(event, x_config, mock_session)
        assert result is True

    @pytest.mark.asyncio
    async def test_ignores_non_ref_strings(self, mock_session):
        # "action" field without "/" is not a ref
        event = _make_event(data={"action": "push"})
        x_config = {"engine": "threat_intel_action_ref"}
        result = await _check_threat_intel_action_ref(event, x_config, mock_session)
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_ref_not_in_indicators(self, mock_session):
        event = _make_event(data={"action_ref": "legit-org/safe-action@v3"})
        _setup_session_with_indicator(mock_session, None)
        x_config = {"engine": "threat_intel_action_ref"}
        result = await _check_threat_intel_action_ref(event, x_config, mock_session)
        assert result is False

    @pytest.mark.asyncio
    async def test_graceful_failure_on_exception(self, mock_session):
        event = _make_event(data={"action_ref": "x/y@v1"})
        mock_session.execute = AsyncMock(side_effect=RuntimeError("DB error"))
        x_config = {"engine": "threat_intel_action_ref"}
        result = await _check_threat_intel_action_ref(event, x_config, mock_session)
        assert result is False
