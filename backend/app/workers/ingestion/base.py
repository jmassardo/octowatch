"""Base ingest worker: shared dedup logic + bulk insert."""

from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from celery import Task

from app.celery_app import celery_app
from app.services.activity_category import derive_activity_category

logger = structlog.get_logger(__name__)

# ── Bloom filter configuration ──────────────────────────────────────────────────
# Two rotating bloom filters ("active" and "previous") to prevent saturation.
# Active filter collects new hashes; previous filter is checked for dedup.
# Every ROTATION_INTERVAL, active becomes previous and a fresh filter starts.
# This bounds the maximum fill rate and prevents false-positive storms.
_BLOOM_KEY_ACTIVE = "ingest:dedup:bloom:active"
_BLOOM_KEY_PREVIOUS = "ingest:dedup:bloom:previous"
_BLOOM_ROTATION_KEY = "ingest:dedup:bloom:rotated_at"
_BLOOM_N_BITS = 4_194_304  # 4M bits = 512KB — supports ~300K events at <1% FP
_BLOOM_N_HASHES = 5
_BLOOM_TTL = 86400  # 24 hours — each filter expires independently
_BLOOM_ROTATION_INTERVAL = 43200  # 12 hours — rotate to prevent saturation

# Default retention window for event_dedup pruning (7 days)
_DEDUP_RETENTION_DAYS = 7


@celery_app.task(
    name="app.workers.ingestion.base.prune_event_dedup",
    bind=True,
    max_retries=3,
)
def prune_event_dedup(self: Task) -> dict[str, object]:
    """Celery beat task: delete event_dedup rows older than the retention window."""
    try:
        deleted = asyncio.run(_prune_dedup())
        return {"status": "ok", "deleted": deleted}
    except Exception as exc:
        logger.error("prune_event_dedup.failed", error=str(exc))
        backoff = min(30 * (2**self.request.retries), 600)
        jitter = secrets.randbelow(max(int(backoff * 0.1), 1))
        raise self.retry(exc=exc, countdown=backoff + jitter) from exc


async def _prune_dedup() -> int:
    """Delete event_dedup rows older than the configured retention window."""
    from sqlalchemy import text

    from app.database import AsyncSessionLocal

    cutoff = datetime.now(UTC) - timedelta(days=_DEDUP_RETENTION_DAYS)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("DELETE FROM event_dedup WHERE created_at < :cutoff"),
            {"cutoff": cutoff},
        )
        await session.commit()
        deleted = int(getattr(result, "rowcount", 0) or 0)
        if deleted:
            logger.info("prune_event_dedup.complete", deleted=deleted, cutoff=cutoff.isoformat())
        return deleted


class AbstractIngestWorker(ABC):
    """Base class for all event ingest workers.

    Subclasses implement ``fetch_events()`` and call ``ingest_batch()`` with the
    raw event dicts. The base class handles deduplication, enrichment, and bulk
    write-to-DB.
    """

    # Subclasses set this to 's3' or 'hec'
    ingestion_source: str = "unknown"

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
        """Fast bloom filter check in Valkey. Returns True if likely seen before.

        Checks both the active and previous bloom filters.  An event is
        considered a duplicate only if ALL bit positions are set in EITHER
        filter (not across both).
        """
        bit_positions = _bloom_bit_positions(dedup_hash, _BLOOM_N_HASHES, _BLOOM_N_BITS)

        # Check active filter
        pipe = self._valkey.pipeline()
        for pos in bit_positions:
            pipe.getbit(_BLOOM_KEY_ACTIVE, pos)
        results_active = await pipe.execute()
        if all(results_active):
            return True

        # Check previous filter
        pipe = self._valkey.pipeline()
        for pos in bit_positions:
            pipe.getbit(_BLOOM_KEY_PREVIOUS, pos)
        results_prev = await pipe.execute()
        return all(results_prev)

    async def _mark_bloom(self, dedup_hash: str) -> None:
        """Set bloom filter bits in the active filter for this event hash."""
        await self._maybe_rotate_bloom()
        bit_positions = _bloom_bit_positions(dedup_hash, _BLOOM_N_HASHES, _BLOOM_N_BITS)
        pipe = self._valkey.pipeline()
        for pos in bit_positions:
            pipe.setbit(_BLOOM_KEY_ACTIVE, pos, 1)
        pipe.expire(_BLOOM_KEY_ACTIVE, _BLOOM_TTL)
        await pipe.execute()

    async def _maybe_rotate_bloom(self) -> None:
        """Rotate bloom filters if the rotation interval has elapsed.

        Uses a Valkey key to track last rotation time.  Only one worker
        wins the rotation (atomic SETNX-style) to avoid race conditions.
        """
        import time

        now = int(time.time())
        last_rotated = await self._valkey.get(_BLOOM_ROTATION_KEY)

        if last_rotated and (now - int(last_rotated)) < _BLOOM_ROTATION_INTERVAL:
            return

        # Attempt atomic rotation — only one worker should do this
        was_set = await self._valkey.set(
            _BLOOM_ROTATION_KEY, str(now), nx=True, ex=_BLOOM_ROTATION_INTERVAL
        )
        if not was_set:
            # Another worker already rotated or key existed — check if expired
            was_set = await self._valkey.set(
                _BLOOM_ROTATION_KEY, str(now), ex=_BLOOM_ROTATION_INTERVAL, xx=True
            )
            # Even if we didn't win, proceed — worst case is a double-rotation
            # which just means the previous filter gets replaced slightly early

        # Rotate: rename active → previous (atomically), then start fresh active
        try:
            await self._valkey.rename(_BLOOM_KEY_ACTIVE, _BLOOM_KEY_PREVIOUS)
            await self._valkey.expire(_BLOOM_KEY_PREVIOUS, _BLOOM_TTL)
            logger.info("bloom.rotated", new_active_key=_BLOOM_KEY_ACTIVE)
        except Exception:  # noqa: BLE001
            # Active key may not exist yet (first boot) — that's fine
            logger.debug("bloom.rotate_skipped", reason="active key missing")

    async def ingest_batch(
        self, raw_events: list[dict[str, Any]], source_file_path: str = "unknown"
    ) -> int:
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

        inserted_ids: list[int] = []
        async with self._make_session() as session:
            from sqlalchemy import text

            for event, dedup_hash in zip(to_insert, dedup_hashes, strict=False):
                # Tier 2: DB-level dedup check (document_id is the stable dedup key)
                existing = await session.execute(
                    text("SELECT 1 FROM event_dedup WHERE document_id = :doc_id"),
                    {"doc_id": dedup_hash},
                )
                if existing.fetchone():
                    continue

                # Parse and enrich event
                normalized = self._normalize_event(
                    event,
                    dedup_hash=dedup_hash,
                    source_file_path=source_file_path,
                )
                if not normalized:
                    continue

                # Insert event; return the generated id for the dedup record
                result = await session.execute(
                    text("""
                        INSERT INTO events (
                            document_id, action, actor, actor_id, actor_is_bot,
                            org, repo, source_ip, created_at, data,
                            geo_country_code, geo_city, geo_latitude, geo_longitude, geo_is_proxy,
                            user_agent, ingestion_source, source_file_path,
                            activity_category
                        ) VALUES (
                            :document_id, :action, :actor, :actor_id, :actor_is_bot,
                            :org, :repo, :source_ip, :created_at, CAST(:data AS jsonb),
                            :geo_country_code, :geo_city,
                            :geo_latitude, :geo_longitude, :geo_is_proxy,
                            :user_agent, :ingestion_source, :source_file_path,
                            :activity_category
                        )
                        RETURNING id
                    """),
                    normalized,
                )
                row = result.fetchone()
                if not row:
                    continue  # duplicate document_id race condition
                event_id = row[0]

                # Insert dedup record
                await session.execute(
                    text(
                        "INSERT INTO event_dedup (document_id, event_id, created_at) "
                        "VALUES (:doc_id, :event_id, :ts) ON CONFLICT DO NOTHING"
                    ),
                    {
                        "doc_id": normalized["document_id"],
                        "event_id": event_id,
                        "ts": normalized["created_at"],
                    },
                )

                # Mark bloom filter
                await self._mark_bloom(dedup_hash)
                inserted_ids.append(event_id)

                # WS-4: Upsert external_collaborators for lifecycle events
                await self._upsert_external_collaborator(session, normalized, event_id)

            await session.commit()

        if inserted_ids:
            logger.info(
                "ingest.batch_complete",
                inserted=len(inserted_ids),
                total=len(raw_events),
            )

            # Chain detection pipeline for newly inserted events
            try:
                from app.workers.detection_worker import run_detection_pipeline_task

                run_detection_pipeline_task.delay(inserted_ids)
                logger.info(
                    "ingest.detection_chained",
                    event_count=len(inserted_ids),
                )
            except Exception:
                logger.warning(
                    "ingest.detection_chain_failed",
                    event_ids=inserted_ids[:5],
                    exc_info=True,
                )

        return len(inserted_ids)

    # External collaborator lifecycle actions
    _COLLAB_ADD_ACTIONS = frozenset(
        {
            "org.add_outside_collaborator",
            "repo.add_member",
        }
    )
    _COLLAB_REMOVE_ACTIONS = frozenset(
        {
            "org.remove_outside_collaborator",
            "repo.remove_member",
        }
    )

    async def _upsert_external_collaborator(
        self,
        session: Any,
        normalized: dict[str, Any],
        event_id: int,
    ) -> None:
        """Upsert external_collaborators table for collaborator lifecycle events."""
        from sqlalchemy import text as sql_text

        action = normalized.get("action", "")
        org = normalized.get("org")
        if not org:
            return

        data = normalized.get("data")
        if isinstance(data, str):
            import json as _json

            try:
                data = _json.loads(data)
            except (ValueError, TypeError):
                data = {}
        data = data or {}

        if action in self._COLLAB_ADD_ACTIONS:
            role = data.get("role", data.get("permission", "outside_collaborator"))
            # Only track outside collaborators, not internal members
            member_type = data.get("member_type", "")
            if action == "repo.add_member" and member_type not in (
                "outside_collaborator",
                "guest_collaborator",
                "guest",
            ):
                return

            collaborator = data.get("user", data.get("collaborator", normalized.get("actor")))
            if not collaborator:
                return

            repo = normalized.get("repo") if action == "repo.add_member" else None

            await session.execute(
                sql_text("""
                    INSERT INTO external_collaborators
                        (org, repo, github_login, role, granted_at, granted_by,
                         is_active, source_event_id)
                    VALUES
                        (:org, :repo, :login, :role, :granted_at, :granted_by,
                         TRUE, :event_id)
                    ON CONFLICT (org, repo, github_login)
                    DO UPDATE SET
                        role = EXCLUDED.role,
                        granted_at = EXCLUDED.granted_at,
                        granted_by = EXCLUDED.granted_by,
                        is_active = TRUE,
                        removed_at = NULL,
                        removed_by = NULL,
                        source_event_id = EXCLUDED.source_event_id,
                        updated_at = NOW()
                """),
                {
                    "org": org,
                    "repo": repo,
                    "login": collaborator,
                    "role": role,
                    "granted_at": normalized.get("created_at"),
                    "granted_by": normalized.get("actor"),
                    "event_id": event_id,
                },
            )

        elif action in self._COLLAB_REMOVE_ACTIONS:
            collaborator = data.get("user", data.get("collaborator"))
            if not collaborator:
                return
            repo = normalized.get("repo") if action == "repo.remove_member" else None

            await session.execute(
                sql_text("""
                    UPDATE external_collaborators
                    SET is_active = FALSE,
                        removed_at = :removed_at,
                        removed_by = :removed_by,
                        source_event_id = :event_id,
                        updated_at = NOW()
                    WHERE org = :org
                      AND github_login = :login
                      AND is_active = TRUE
                """),
                {
                    "org": org,
                    "login": collaborator,
                    "removed_at": normalized.get("created_at"),
                    "removed_by": normalized.get("actor"),
                    "event_id": event_id,
                },
            )

        # Update last_event_at for any event from a known collaborator
        actor = normalized.get("actor")
        if actor and org:
            await session.execute(
                sql_text("""
                    UPDATE external_collaborators
                    SET last_event_at = :event_time, updated_at = NOW()
                    WHERE github_login = :actor
                      AND org = :org
                      AND is_active = TRUE
                      AND (last_event_at IS NULL OR last_event_at < :event_time)
                """),
                {
                    "actor": actor,
                    "org": org,
                    "event_time": normalized.get("created_at"),
                },
            )

    def _normalize_event(
        self,
        raw: dict[str, Any],
        *,
        dedup_hash: str,
        source_file_path: str = "unknown",
    ) -> dict[str, Any] | None:
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
        geo_country_code = geo_city = geo_latitude = geo_longitude = None
        geo_is_proxy = False
        if source_ip:
            try:
                from app.services.geoip_service import get_geoip_location

                geo = get_geoip_location(source_ip)
                if geo:
                    geo_country_code = geo.country_code
                    geo_city = geo.city
                    geo_latitude = geo.latitude
                    geo_longitude = geo.longitude
                    geo_is_proxy = geo.is_proxy or False
            except Exception:  # best-effort geo enrichment; must not block ingestion
                logger.debug("geoip.lookup_failed", source_ip=source_ip)

        # Strip large/sensitive fields from data blob
        data = {k: v for k, v in raw.items() if not k.startswith("@")}

        # ── Namespace-specific normalization ─────────────────────────────────
        # workflows.prepared_workflow_job: count secrets but never persist names
        if action == "workflows.prepared_workflow_job":
            secrets = data.get("secrets_passed", [])
            data["secrets_passed_count"] = len(secrets) if isinstance(secrets, list) else 0
            data.pop("secrets_passed", None)  # security: never persist secret names

        # Use GitHub's _document_id if present, otherwise the computed dedup hash
        document_id = raw.get("_document_id") or dedup_hash

        return {
            "document_id": document_id,
            "action": action,
            "actor": raw.get("actor"),
            "actor_id": raw.get("actor_id"),
            "actor_is_bot": bool(raw.get("actor_is_bot", False)),
            "org": raw.get("org"),
            "repo": raw.get("repo"),
            "source_ip": source_ip,
            "created_at": created_at,
            "data": json.dumps(data),
            "geo_country_code": geo_country_code,
            "geo_city": geo_city,
            "geo_latitude": geo_latitude,
            "geo_longitude": geo_longitude,
            "geo_is_proxy": geo_is_proxy,
            "user_agent": raw.get("user_agent"),
            "ingestion_source": self.ingestion_source,
            "source_file_path": source_file_path,
            "activity_category": derive_activity_category(action),
        }

    @abstractmethod
    async def run(self) -> None:
        """Run the ingestion loop (implemented by subclasses)."""
        raise NotImplementedError


def _bloom_bit_positions(
    key: str, n_hashes: int = _BLOOM_N_HASHES, n_bits: int = _BLOOM_N_BITS
) -> list[int]:
    """Compute n_hashes bit positions for a bloom filter using double-hashing."""
    h1 = int(hashlib.md5(key.encode()).hexdigest(), 16)  # noqa: S324
    h2 = int(hashlib.sha1(key.encode()).hexdigest(), 16)  # noqa: S324
    return [(h1 + i * h2) % n_bits for i in range(n_hashes)]
