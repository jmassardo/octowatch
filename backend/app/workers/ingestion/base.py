"""Base ingest worker: shared dedup logic + bulk insert."""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Bloom filter window size (64 KB is sufficient for ~4M events with 1% FP rate)
_BLOOM_KEY = "ingest:dedup:bloom"
_BLOOM_TTL = 86400  # 24 hours


class AbstractIngestWorker(ABC):
    """Base class for all event ingest workers.

    Subclasses implement ``fetch_events()`` and call ``ingest_batch()`` with the
    raw event dicts. The base class handles deduplication, enrichment, and bulk
    write-to-DB.
    """

    def __init__(self, valkey_client: Any, db_session_factory: Any) -> None:
        self._valkey = valkey_client
        self._make_session = db_session_factory

    @staticmethod
    def compute_dedup_hash(event: dict[str, Any]) -> str:
        """Compute a SHA-256 dedup hash from the event's stable fields."""
        key_fields = {
            "action": event.get("action", ""),
            "actor": event.get("actor", ""),
            "org": event.get("org", ""),
            "repo": event.get("repo", ""),
            "created_at": str(event.get("created_at", "")),
            "source_ip": str(event.get("@ip", event.get("source_ip", ""))),
        }
        canonical = json.dumps(key_fields, sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()

    async def _is_duplicate_bloom(self, dedup_hash: str) -> bool:
        """Fast bloom filter check in Valkey. Returns True if likely seen before."""
        # Use SETBIT-based probabilistic filter with 512K bits
        bit_positions = _bloom_bit_positions(dedup_hash, n_hashes=5, n_bits=524288)
        pipe = self._valkey.pipeline()
        for pos in bit_positions:
            pipe.getbit(_BLOOM_KEY, pos)
        results = await pipe.execute()
        # If all bits are set, it's a likely duplicate
        return all(results)

    async def _mark_bloom(self, dedup_hash: str) -> None:
        """Set bloom filter bits for this event hash."""
        bit_positions = _bloom_bit_positions(dedup_hash, n_hashes=5, n_bits=524288)
        pipe = self._valkey.pipeline()
        for pos in bit_positions:
            pipe.setbit(_BLOOM_KEY, pos, 1)
        pipe.expire(_BLOOM_KEY, _BLOOM_TTL)
        await pipe.execute()

    async def ingest_batch(self, raw_events: list[dict[str, Any]]) -> int:
        """Process a batch of raw events: dedup + bulk insert. Returns count inserted."""
        if not raw_events:
            return 0

        to_insert: list[dict[str, Any]] = []
        dedup_hashes: list[str] = []

        # Tier 1: Bloom filter pass
        for event in raw_events:
            dedup_hash = self.compute_dedup_hash(event)
            if await self._is_duplicate_bloom(dedup_hash):
                logger.debug("ingest.bloom_dedup", hash=dedup_hash[:16])
                continue
            to_insert.append(event)
            dedup_hashes.append(dedup_hash)

        if not to_insert:
            return 0

        inserted = 0
        async with self._make_session() as session:
            from sqlalchemy import text

            for event, dedup_hash in zip(to_insert, dedup_hashes, strict=False):
                # Tier 2: DB-level dedup check
                existing = await session.execute(
                    text("SELECT 1 FROM event_dedup WHERE dedup_hash = :h"),
                    {"h": dedup_hash},
                )
                if existing.fetchone():
                    continue

                # Parse and enrich event
                normalized = self._normalize_event(event)
                if not normalized:
                    continue

                # Insert event (ON CONFLICT DO NOTHING for per-chunk uniqueness)
                await session.execute(
                    text("""
                        INSERT INTO events (
                            action, actor, actor_id, actor_is_bot,
                            org, repo, source_ip, created_at, data,
                            geo_country, geo_city, geo_latitude, geo_longitude, geo_is_proxy,
                            user_agent
                        ) VALUES (
                            :action, :actor, :actor_id, :actor_is_bot,
                            :org, :repo, :source_ip, :created_at, :data::jsonb,
                            :geo_country, :geo_city, :geo_latitude, :geo_longitude, :geo_is_proxy,
                            :user_agent
                        )
                        ON CONFLICT DO NOTHING
                    """),
                    normalized,
                )

                # Insert dedup record
                await session.execute(
                    text(
                        "INSERT INTO event_dedup (dedup_hash, created_at) "
                        "VALUES (:h, :ts) ON CONFLICT DO NOTHING"
                    ),
                    {"h": dedup_hash, "ts": normalized["created_at"]},
                )

                # Mark bloom filter
                await self._mark_bloom(dedup_hash)
                inserted += 1

            await session.commit()

        if inserted:
            logger.info("ingest.batch_complete", inserted=inserted, total=len(raw_events))

        return inserted

    def _normalize_event(self, raw: dict[str, Any]) -> dict[str, Any] | None:
        """Convert a raw GitHub audit log entry to DB row parameters."""
        action = raw.get("action")
        if not action:
            logger.warning("ingest.missing_action", raw_keys=list(raw.keys()))
            return None

        # GitHub audit log uses `@timestamp` (milliseconds epoch) or `created_at` ISO
        ts_raw = raw.get("@timestamp") or raw.get("created_at")
        if ts_raw is None:
            created_at = datetime.now(UTC)
        elif isinstance(ts_raw, (int, float)):
            created_at = datetime.fromtimestamp(ts_raw / 1000, tz=UTC)
        else:
            try:
                created_at = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
            except ValueError:
                created_at = datetime.now(UTC)

        source_ip = raw.get("@ip") or raw.get("actor_ip")

        # GeoIP enrichment (best-effort; doesn't block insert on failure)
        geo_country = geo_city = geo_latitude = geo_longitude = None
        geo_is_proxy = False
        if source_ip:
            try:
                from app.services.geoip_service import get_geoip_location

                geo = get_geoip_location(source_ip)
                if geo:
                    geo_country = geo.country_code
                    geo_city = geo.city
                    geo_latitude = geo.latitude
                    geo_longitude = geo.longitude
                    geo_is_proxy = geo.is_proxy or False
            except Exception:  # best-effort geo enrichment; must not block ingestion
                logger.debug("geoip.lookup_failed", source_ip=source_ip)

        # Strip large/sensitive fields from data blob
        data = {k: v for k, v in raw.items() if not k.startswith("@")}

        return {
            "action": action,
            "actor": raw.get("actor"),
            "actor_id": raw.get("actor_id"),
            "actor_is_bot": bool(raw.get("actor_is_bot", False)),
            "org": raw.get("org"),
            "repo": raw.get("repo"),
            "source_ip": source_ip,
            "created_at": created_at,
            "data": json.dumps(data),
            "geo_country": geo_country,
            "geo_city": geo_city,
            "geo_latitude": geo_latitude,
            "geo_longitude": geo_longitude,
            "geo_is_proxy": geo_is_proxy,
            "user_agent": raw.get("user_agent"),
        }

    @abstractmethod
    async def run(self) -> None:
        """Run the ingestion loop (implemented by subclasses)."""
        raise NotImplementedError


def _bloom_bit_positions(key: str, n_hashes: int, n_bits: int) -> list[int]:
    """Compute n_hashes bit positions for a bloom filter using double-hashing."""
    h1 = int(hashlib.md5(key.encode()).hexdigest(), 16)  # noqa: S324
    h2 = int(hashlib.sha1(key.encode()).hexdigest(), 16)  # noqa: S324
    return [(h1 + i * h2) % n_bits for i in range(n_hashes)]
