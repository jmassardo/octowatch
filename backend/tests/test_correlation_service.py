"""Unit tests for the correlation service and correlation engine."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.correlation_service import (
    CorrelationEngine,
    CorrelationMatch,
    CorrelationResult,
    InvestigationChain,
    _highest_severity,
)

# ── Severity helpers ──────────────────────────────────────────────────────────


class TestHighestSeverity:
    def test_critical_beats_high(self) -> None:
        assert _highest_severity("critical", "high") == "critical"

    def test_high_beats_medium(self) -> None:
        assert _highest_severity("high", "medium") == "high"

    def test_medium_beats_low(self) -> None:
        assert _highest_severity("medium", "low") == "medium"

    def test_same_severity_returns_first(self) -> None:
        assert _highest_severity("high", "high") == "high"

    def test_low_vs_critical(self) -> None:
        assert _highest_severity("low", "critical") == "critical"

    def test_info_is_lowest(self) -> None:
        assert _highest_severity("info", "low") == "low"

    def test_unknown_severity_treated_as_zero(self) -> None:
        assert _highest_severity("unknown", "low") == "low"


# ── CorrelationResult data class ──────────────────────────────────────────────


class TestCorrelationResult:
    def test_default_values(self) -> None:
        result = CorrelationResult(detection_id=1)
        assert result.detection_id == 1
        assert result.chain_id is None
        assert result.matches == []
        assert result.created_new_chain is False

    def test_with_matches(self) -> None:
        matches = [
            CorrelationMatch(detection_id=2, correlation_type="actor_target", confidence=0.9),
            CorrelationMatch(detection_id=3, correlation_type="actor_category", confidence=0.8),
        ]
        result = CorrelationResult(
            detection_id=1,
            chain_id="chain-123",
            matches=matches,
            created_new_chain=True,
        )
        assert result.chain_id == "chain-123"
        assert len(result.matches) == 2
        assert result.created_new_chain is True


# ── CorrelationMatch data class ───────────────────────────────────────────────


class TestCorrelationMatch:
    def test_creation(self) -> None:
        match = CorrelationMatch(
            detection_id=5,
            correlation_type="target_severity",
            confidence=0.7,
        )
        assert match.detection_id == 5
        assert match.correlation_type == "target_severity"
        assert match.confidence == 0.7


# ── InvestigationChain data class ─────────────────────────────────────────────


class TestInvestigationChain:
    def test_creation(self) -> None:
        now = datetime.now(UTC)
        chain = InvestigationChain(
            chain_id="chain-abc",
            title="Test Chain",
            status="open",
            severity="high",
            assignee="alice",
            notes=None,
            created_at=now,
            updated_at=now,
            resolved_at=None,
        )
        assert chain.chain_id == "chain-abc"
        assert chain.title == "Test Chain"
        assert chain.members == []
        assert chain.assignee == "alice"


# ── CorrelationEngine unit tests ──────────────────────────────────────────────


class TestCorrelationEngine:
    """Test the correlation engine with mocked database sessions."""

    def setup_method(self) -> None:
        self.engine = CorrelationEngine()

    @pytest.mark.asyncio
    async def test_correlate_detection_not_found(self) -> None:
        """When detection doesn't exist, return empty result."""
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result_mock)

        result = await self.engine.correlate_detection(999, session)
        assert result.detection_id == 999
        assert result.chain_id is None
        assert result.matches == []

    @pytest.mark.asyncio
    async def test_correlate_detection_already_in_chain(self) -> None:
        """When detection already belongs to a chain, return early."""
        session = AsyncMock()
        detection = MagicMock()
        detection.id = 1
        detection.chain_id = "existing-chain"
        detection.rule_id = 10
        detection.actor = "alice"
        detection.repo = "org/repo"
        detection.org = "org"
        detection.severity = "high"
        detection.triggered_at = datetime.now(UTC)

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = detection
        session.execute = AsyncMock(return_value=result_mock)

        result = await self.engine.correlate_detection(1, session)
        assert result.detection_id == 1
        assert result.chain_id == "existing-chain"
        assert result.matches == []

    @pytest.mark.asyncio
    async def test_get_investigation_chain_not_found(self) -> None:
        """When chain doesn't exist, return None."""
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result_mock)

        result = await self.engine.get_investigation_chain("nonexistent", session)
        assert result is None

    @pytest.mark.asyncio
    async def test_merge_chains_single_chain(self) -> None:
        """Merging a single chain returns that chain ID."""
        session = AsyncMock()
        result = await self.engine.merge_chains(["chain-1"], session)
        assert result == "chain-1"

    @pytest.mark.asyncio
    async def test_merge_chains_empty_list(self) -> None:
        """Merging an empty list returns None."""
        session = AsyncMock()
        result = await self.engine.merge_chains([], session)
        assert result is None


# ── Strategy method tests ─────────────────────────────────────────────────────


class TestCorrelationStrategies:
    """Test individual correlation strategy methods."""

    def setup_method(self) -> None:
        self.engine = CorrelationEngine()

    @pytest.mark.asyncio
    async def test_actor_target_no_target(self) -> None:
        """No matches when detection has no repo or org."""
        detection = MagicMock()
        detection.actor = "alice"
        detection.repo = None
        detection.org = None
        detection.id = 1
        detection.triggered_at = datetime.now(UTC)

        session = AsyncMock()
        matches = await self.engine._find_actor_target_matches(detection, session)
        assert matches == []

    @pytest.mark.asyncio
    async def test_target_severity_no_target(self) -> None:
        """No matches when detection has no repo or org."""
        detection = MagicMock()
        detection.repo = None
        detection.org = None
        detection.severity = "high"
        detection.id = 1
        detection.triggered_at = datetime.now(UTC)

        session = AsyncMock()
        matches = await self.engine._find_target_severity_matches(detection, session)
        assert matches == []

    @pytest.mark.asyncio
    async def test_chain_rule_no_identifiers(self) -> None:
        """No matches when detection has no identifying fields."""
        detection = MagicMock()
        detection.actor = None
        detection.repo = None
        detection.org = None
        detection.id = 1

        session = AsyncMock()
        matches = await self.engine._find_chain_rule_matches(detection, session)
        assert matches == []

    @pytest.mark.asyncio
    async def test_get_detection_severity(self) -> None:
        """Can fetch a single detection's severity."""
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = "critical"
        session.execute = AsyncMock(return_value=result_mock)

        severity = await self.engine._get_detection_severity(1, session)
        assert severity == "critical"

    @pytest.mark.asyncio
    async def test_get_detection_severity_not_found(self) -> None:
        """Returns None when detection not found."""
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result_mock)

        severity = await self.engine._get_detection_severity(999, session)
        assert severity is None
