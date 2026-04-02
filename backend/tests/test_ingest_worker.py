"""Unit tests for the ingest worker base class: dedup hash and bloom filter logic."""

from __future__ import annotations

from unittest.mock import AsyncMock

from app.workers.ingestion.base import AbstractIngestWorker, _bloom_bit_positions


class ConcreteWorker(AbstractIngestWorker):
    """Concrete test double for the abstract base worker."""

    async def run(self) -> None:
        pass


class TestDedupHash:
    def _worker(self):
        return ConcreteWorker(valkey_client=AsyncMock(), db_session_factory=AsyncMock())

    def test_same_event_produces_same_hash(self):
        w = self._worker()
        ev = {
            "action": "repos.create",
            "actor": "alice",
            "org": "my-org",
            "repo": "my-org/repo1",
            "created_at": "2024-01-01T00:00:00Z",
            "@ip": "1.2.3.4",
        }
        h1 = w.compute_dedup_hash(ev)
        h2 = w.compute_dedup_hash(ev)
        assert h1 == h2

    def test_different_events_produce_different_hashes(self):
        w = self._worker()
        ev1 = {
            "action": "repos.create",
            "actor": "alice",
            "org": "o",
            "repo": "r",
            "created_at": "t",
            "@ip": "1.1.1.1",
        }
        ev2 = {
            "action": "repos.delete",
            "actor": "alice",
            "org": "o",
            "repo": "r",
            "created_at": "t",
            "@ip": "1.1.1.1",
        }
        assert w.compute_dedup_hash(ev1) != w.compute_dedup_hash(ev2)

    def test_hash_is_64_hex_chars(self):
        w = self._worker()
        ev = {"action": "x", "actor": "y", "org": "z", "repo": "r", "created_at": "t", "@ip": "1"}
        h = w.compute_dedup_hash(ev)
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_hash_is_not_affected_by_extra_keys(self):
        """Adding non-stable keys does not change the dedup hash."""
        w = self._worker()
        ev_base = {
            "action": "repos.create",
            "actor": "alice",
            "org": "o",
            "repo": "r",
            "created_at": "t",
            "@ip": "1.1.1.1",
        }
        ev_extra = {**ev_base, "extra_field": "ignored"}
        assert w.compute_dedup_hash(ev_base) == w.compute_dedup_hash(ev_extra)


class TestNormalizeEvent:
    def _worker(self):
        return ConcreteWorker(valkey_client=AsyncMock(), db_session_factory=AsyncMock())

    def test_normalizes_timestamp_from_ms(self):
        w = self._worker()
        ev = {
            "action": "repos.create",
            "actor": "alice",
            "org": "my-org",
            "@timestamp": 1700000000000,  # milliseconds
        }
        result = w._normalize_event(ev, dedup_hash="test-hash")
        assert result is not None
        assert result["action"] == "repos.create"
        assert result["actor"] == "alice"

    def test_normalizes_iso_timestamp(self):
        w = self._worker()
        ev = {
            "action": "member.add",
            "actor": "bob",
            "created_at": "2024-03-15T10:00:00Z",
        }
        result = w._normalize_event(ev, dedup_hash="test-hash")
        assert result is not None
        assert result["actor"] == "bob"

    def test_missing_action_returns_none(self):
        w = self._worker()
        ev = {"actor": "alice", "org": "my-org", "@timestamp": 1700000000000}
        result = w._normalize_event(ev, dedup_hash="test-hash")
        assert result is None

    def test_source_ip_extracted_from_at_ip(self):
        w = self._worker()
        ev = {"action": "repos.create", "actor": "alice", "@ip": "192.168.0.1"}
        result = w._normalize_event(ev, dedup_hash="test-hash")
        assert result is not None
        assert result["source_ip"] == "192.168.0.1"

    def test_at_prefix_keys_excluded_from_data_blob(self):
        w = self._worker()
        ev = {
            "action": "repos.create",
            "actor": "alice",
            "@ip": "192.168.0.1",
            "@timestamp": 1700000000000,
            "visibility": "private",
        }
        result = w._normalize_event(ev, dedup_hash="test-hash")
        import json

        data = json.loads(result["data"])
        assert "@ip" not in data
        assert "@timestamp" not in data
        assert "visibility" in data


class TestBloomBitPositions:
    def test_returns_n_positions(self):
        positions = _bloom_bit_positions("test_key", n_hashes=5, n_bits=1024)
        assert len(positions) == 5

    def test_all_positions_within_range(self):
        n_bits = 8192
        positions = _bloom_bit_positions("hello_world", n_hashes=7, n_bits=n_bits)
        assert all(0 <= p < n_bits for p in positions)

    def test_deterministic_for_same_key(self):
        p1 = _bloom_bit_positions("key_abc", n_hashes=4, n_bits=4096)
        p2 = _bloom_bit_positions("key_abc", n_hashes=4, n_bits=4096)
        assert p1 == p2

    def test_different_keys_different_positions(self):
        p1 = _bloom_bit_positions("key_a", n_hashes=5, n_bits=4096)
        p2 = _bloom_bit_positions("key_b", n_hashes=5, n_bits=4096)
        assert p1 != p2
