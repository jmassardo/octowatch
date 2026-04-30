"""Tests for centralised retention policy management (Issue #139).

Covers:
- RetentionPolicy model basic attributes
- Policy CRUD (list, update)
- Minimum days enforcement
- Cache invalidation on update
- Retention service reads from DB
- Admin retention router request/response schemas
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.retention_policy import RetentionPolicy
from app.routers.admin_retention import RetentionPolicyResponse, RetentionPolicyUpdate
from app.services import retention_service

# ── Helpers ──────────────────────────────────────────────────────────────────


def _mock_db() -> AsyncMock:
    """Return an AsyncMock that behaves like an AsyncSession."""
    from sqlalchemy.ext.asyncio import AsyncSession

    db = AsyncMock(spec=AsyncSession)
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock()
    return db


def _make_policy_row(
    data_type: str = "events",
    category: str = "core_data",
    retention_days: int = 365,
    minimum_days: int = 90,
    is_system: bool = True,
) -> MagicMock:
    """Create a mock RetentionPolicy row."""
    from datetime import UTC, datetime

    row = MagicMock(spec=RetentionPolicy)
    row.id = 1
    row.data_type = data_type
    row.category = category
    row.display_name = data_type.replace("_", " ").title()
    row.description = f"Policy for {data_type}"
    row.retention_days = retention_days
    row.minimum_days = minimum_days
    row.is_system = is_system
    row.updated_by = None
    row.updated_at = datetime(2024, 1, 15, tzinfo=UTC)
    row.created_at = datetime(2024, 1, 1, tzinfo=UTC)
    return row


# ── Tests: RetentionPolicy model ─────────────────────────────────────────────


class TestRetentionPolicyModel:
    """Basic model attribute tests."""

    def test_tablename(self) -> None:
        """Model should map to retention_policies table."""
        assert RetentionPolicy.__tablename__ == "retention_policies"

    def test_data_type_is_unique(self) -> None:
        """data_type column should have a unique constraint."""
        col = RetentionPolicy.__table__.columns["data_type"]
        assert col.unique is True

    def test_required_columns_exist(self) -> None:
        """All expected columns should be present on the model."""
        expected = {
            "id",
            "data_type",
            "category",
            "display_name",
            "description",
            "retention_days",
            "minimum_days",
            "is_system",
            "updated_by",
            "updated_at",
            "created_at",
        }
        actual = {c.name for c in RetentionPolicy.__table__.columns}
        assert expected.issubset(actual), f"Missing columns: {expected - actual}"


# ── Tests: Pydantic schemas ──────────────────────────────────────────────────


class TestRetentionSchemas:
    """Pydantic request/response schemas."""

    def test_update_schema_validates_min(self) -> None:
        """RetentionPolicyUpdate should accept valid days."""
        update = RetentionPolicyUpdate(retention_days=180)
        assert update.retention_days == 180

    def test_update_schema_rejects_zero(self) -> None:
        """RetentionPolicyUpdate should reject retention_days < 1."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            RetentionPolicyUpdate(retention_days=0)

    def test_update_schema_rejects_too_large(self) -> None:
        """RetentionPolicyUpdate should reject retention_days > 3650."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            RetentionPolicyUpdate(retention_days=5000)

    def test_response_schema_defaults(self) -> None:
        """RetentionPolicyResponse should have sensible defaults."""
        resp = RetentionPolicyResponse(
            data_type="events",
            category="core_data",
            display_name="Events",
            description="test",
            retention_days=365,
            minimum_days=90,
            is_system=True,
            table_name="events",
            time_column="created_at",
        )
        assert resp.row_count == 0
        assert resp.size_bytes == 0


# ── Tests: Service functions ─────────────────────────────────────────────────


class TestRetentionServiceFunctions:
    """Tests for retention_service module functions."""

    def test_fallback_policies_cover_all_known_types(self) -> None:
        """Fallback policies should cover the core data types."""
        policies = retention_service._build_fallback_policies()
        expected_types = {
            "events",
            "raw_payloads",
            "detections",
            "event_dedup",
            "audit_trail",
            "enterprise_sync_log",
            "system_health_events",
            "behavioral_baselines",
        }
        assert expected_types.issubset(set(policies.keys()))

    def test_fallback_policies_have_consistent_structure(self) -> None:
        """Each fallback policy should have all required keys."""
        policies = retention_service._build_fallback_policies()
        required_keys = {
            "data_type",
            "category",
            "display_name",
            "description",
            "retention_days",
            "minimum_days",
            "is_system",
            "table_name",
            "time_column",
        }
        for data_type, policy in policies.items():
            missing = required_keys - set(policy.keys())
            assert not missing, f"{data_type} missing keys: {missing}"

    def test_table_map_has_all_data_types(self) -> None:
        """_TABLE_MAP should include all migration-seeded data types."""
        expected = {
            "events",
            "raw_payloads",
            "detections",
            "event_dedup",
            "audit_trail",
            "enterprise_sync_log",
            "system_health_events",
            "behavioral_baselines",
            "copilot_metrics",
            "report_history",
            "notification_history",
        }
        assert expected == set(retention_service._TABLE_MAP.keys())

    def test_cache_invalidation_resets_state(self) -> None:
        """invalidate_cache should clear the cached policies."""
        retention_service._policy_cache = {"cached": {}}
        retention_service._policy_cache_ts = 99999.0

        retention_service.invalidate_cache()

        assert retention_service._policy_cache is None
        assert retention_service._policy_cache_ts == 0.0

    @pytest.mark.asyncio
    async def test_get_retention_policies_caches_result(self) -> None:
        """Successive calls within TTL should return cached data."""
        db = _mock_db()
        retention_service.invalidate_cache()

        rows = [_make_policy_row("events"), _make_policy_row("detections", retention_days=365)]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = rows
        db.execute = AsyncMock(return_value=mock_result)

        # First call → DB query
        policies1 = await retention_service.get_retention_policies(db)
        assert "events" in policies1

        # Second call → should use cache (db.execute not called again)
        db.execute.reset_mock()
        policies2 = await retention_service.get_retention_policies(db)
        assert policies2 == policies1
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_retention_policies_falls_back_on_error(self) -> None:
        """If DB query fails, fallback policies should be returned."""
        db = _mock_db()
        retention_service.invalidate_cache()
        db.execute = AsyncMock(side_effect=Exception("connection failed"))

        policies = await retention_service.get_retention_policies(db)
        fallbacks = retention_service._build_fallback_policies()
        assert len(policies) == len(fallbacks)

    @pytest.mark.asyncio
    async def test_get_policy_returns_days(self) -> None:
        """get_policy should return the retention_days for a known type."""
        db = _mock_db()
        retention_service.invalidate_cache()

        rows = [_make_policy_row("events", retention_days=180)]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = rows
        db.execute = AsyncMock(return_value=mock_result)

        days = await retention_service.get_policy(db, "events")
        assert days == 180

    @pytest.mark.asyncio
    async def test_get_policy_raises_for_unknown(self) -> None:
        """get_policy should raise ValueError for an unknown data type."""
        db = _mock_db()
        retention_service.invalidate_cache()
        db.execute = AsyncMock(side_effect=Exception("no table"))

        with pytest.raises(ValueError, match="Unknown retention data type"):
            await retention_service.get_policy(db, "totally_unknown")

    @pytest.mark.asyncio
    async def test_update_retention_policy_validates_minimum(self) -> None:
        """update_retention_policy should reject days below minimum_days."""
        db = _mock_db()
        mock_policy = _make_policy_row("events", retention_days=365, minimum_days=90)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_policy
        db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(ValueError, match="must be >= minimum_days"):
            await retention_service.update_retention_policy(db, "events", 30, user_login="admin")

    @pytest.mark.asyncio
    async def test_update_retention_policy_unknown_type(self) -> None:
        """update_retention_policy should raise for unknown data_type."""
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(ValueError, match="Unknown retention data type"):
            await retention_service.update_retention_policy(
                db, "nonexistent", 100, user_login="admin"
            )

    @pytest.mark.asyncio
    async def test_update_retention_policy_invalidates_cache(self) -> None:
        """After update, the cache should be invalidated."""
        db = _mock_db()
        retention_service._policy_cache = {"cached": {}}
        retention_service._policy_cache_ts = 99999.0

        mock_policy = _make_policy_row("events", retention_days=365, minimum_days=90)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_policy

        call_count = 0

        async def _mock_execute(stmt: Any, params: Any = None) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # select
                return mock_result
            # update / log_action
            return MagicMock()

        db.execute = AsyncMock(side_effect=_mock_execute)

        from unittest.mock import patch

        with patch(
            "app.services.retention_service.log_action",
            new_callable=AsyncMock,
        ):
            result = await retention_service.update_retention_policy(
                db, "events", 180, user_login="admin"
            )

        assert result["retention_days"] == 180
        assert result["old_days"] == 365
        assert retention_service._policy_cache is None

    @pytest.mark.asyncio
    async def test_enforce_retention_unknown_type(self) -> None:
        """enforce_retention should raise ValueError for unknown data_type."""
        db = _mock_db()
        retention_service.invalidate_cache()
        db.execute = AsyncMock(side_effect=Exception("no table"))

        with pytest.raises(ValueError, match="Unknown retention data type"):
            await retention_service.enforce_retention(db, "totally_unknown")

    def test_legacy_update_policy_alias_exists(self) -> None:
        """The legacy update_policy function should still be importable."""
        from app.services.retention_service import update_policy

        assert callable(update_policy)


# ── Tests: Default policy values alignment ───────────────────────────────────


class TestRetentionDefaults:
    """Verify that default values are consistent and correct."""

    def test_events_default_is_365(self) -> None:
        """Events default retention should be 365 days."""
        policies = retention_service._build_fallback_policies()
        assert policies["events"]["retention_days"] == 365

    def test_audit_trail_default_is_730(self) -> None:
        """Audit trail default retention should be 730 days."""
        policies = retention_service._build_fallback_policies()
        assert policies["audit_trail"]["retention_days"] == 730

    def test_minimum_days_are_positive(self) -> None:
        """All minimum_days should be at least 1."""
        policies = retention_service._build_fallback_policies()
        for data_type, policy in policies.items():
            assert policy["minimum_days"] >= 1, f"{data_type} minimum_days < 1"

    def test_retention_days_gte_minimum_days(self) -> None:
        """Default retention_days should always be >= minimum_days."""
        policies = retention_service._build_fallback_policies()
        for data_type, policy in policies.items():
            assert policy["retention_days"] >= policy["minimum_days"], (
                f"{data_type}: retention_days ({policy['retention_days']}) "
                f"< minimum_days ({policy['minimum_days']})"
            )
