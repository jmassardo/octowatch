"""Tests for the 0056 seed-default-threat-intel-feeds migration."""

from __future__ import annotations

import importlib.util
import types
from pathlib import Path

_MIGRATION_PATH = (
    Path(__file__).parent.parent
    / "alembic"
    / "versions"
    / "0056_seed_default_threat_intel_feeds.py"
)


def _load_migration() -> types.ModuleType:
    """Import the migration module whose name starts with a digit."""
    spec = importlib.util.spec_from_file_location("migration_0056", str(_MIGRATION_PATH))
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestMigrationFileStructure:
    """Validate the Alembic migration file is well-formed."""

    def test_migration_file_exists(self) -> None:
        assert _MIGRATION_PATH.exists(), f"Migration not found at {_MIGRATION_PATH}"

    def test_revision_chain(self) -> None:
        content = _MIGRATION_PATH.read_text()
        assert 'revision = "0056"' in content
        assert 'down_revision = "0055"' in content

    def test_upgrade_adds_is_default_column(self) -> None:
        content = _MIGRATION_PATH.read_text()
        assert "is_default" in content
        assert "add_column" in content

    def test_upgrade_creates_unique_constraint_on_url(self) -> None:
        content = _MIGRATION_PATH.read_text()
        assert "uq_threat_intel_feeds_url" in content
        assert "create_unique_constraint" in content

    def test_upgrade_inserts_five_feeds(self) -> None:
        content = _MIGRATION_PATH.read_text()
        assert "urlhaus.abuse.ch" in content
        assert "feodotracker.abuse.ch" in content
        assert "otx.alienvault.com" in content
        assert "cisa.gov" in content
        assert "phishtank.com" in content

    def test_upgrade_is_idempotent(self) -> None:
        content = _MIGRATION_PATH.read_text()
        assert "ON CONFLICT" in content

    def test_downgrade_removes_feeds_and_column(self) -> None:
        content = _MIGRATION_PATH.read_text()
        assert "DELETE FROM threat_intel_feeds" in content
        assert "drop_column" in content
        assert "drop_constraint" in content

    def test_feeds_are_marked_as_default(self) -> None:
        content = _MIGRATION_PATH.read_text()
        assert "is_default = TRUE" in content or "is_default, created_by" in content


class TestDefaultFeedData:
    """Validate the seed data constants are correct."""

    def test_feed_count(self) -> None:
        mod = _load_migration()
        assert len(mod._DEFAULT_FEEDS) == 5

    def test_feed_tuple_structure(self) -> None:
        mod = _load_migration()
        for feed in mod._DEFAULT_FEEDS:
            name, url, feed_type, refresh_minutes, description = feed
            assert isinstance(name, str) and len(name) > 0
            assert url.startswith("https://")
            assert feed_type in ("domain", "ip")
            assert isinstance(refresh_minutes, int) and refresh_minutes > 0
            assert isinstance(description, str) and len(description) > 0

    def test_feed_urls_are_unique(self) -> None:
        mod = _load_migration()
        urls = [url for _, url, *_ in mod._DEFAULT_FEEDS]
        assert len(urls) == len(set(urls)), "Feed URLs must be unique"

    def test_feed_names_are_unique(self) -> None:
        mod = _load_migration()
        names = [name for name, *_ in mod._DEFAULT_FEEDS]
        assert len(names) == len(set(names)), "Feed names must be unique"

    def test_all_feeds_enabled_by_default(self) -> None:
        """The INSERT statement sets enabled = TRUE for all default feeds."""
        content = _MIGRATION_PATH.read_text()
        assert "TRUE, TRUE, 'system'" in content


class TestThreatIntelFeedModel:
    """Verify the ORM model has the is_default column."""

    def test_model_has_is_default_field(self) -> None:
        from app.models.threat_intel import ThreatIntelFeed

        assert hasattr(ThreatIntelFeed, "is_default")

    def test_is_default_column_type(self) -> None:
        from app.models.threat_intel import ThreatIntelFeed

        col = ThreatIntelFeed.__table__.columns["is_default"]
        assert not col.nullable
        assert str(col.server_default.arg) == "FALSE"


class TestFeedResponseSchema:
    """Verify the Pydantic schema exposes is_default."""

    def test_schema_has_is_default(self) -> None:
        from app.schemas.threat_intel import FeedResponse

        assert "is_default" in FeedResponse.model_fields

    def test_schema_is_default_defaults_to_false(self) -> None:
        from app.schemas.threat_intel import FeedResponse

        field = FeedResponse.model_fields["is_default"]
        assert field.default is False
