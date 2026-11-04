"""Celery worker: poll the Copilot Chat sessions REST API for new sessions.

Scope: #387 (Phase 1 ingestion), #507. This worker is intentionally a REST
poller rather than a subclass of ``AbstractIngestWorker`` (see ``base.py``):
that base class is built around blob/file-based sources (S3, Azure Blob) that
hand the worker whole raw event payloads to dedup via a bloom filter and
``event_dedup`` table. The Copilot session API is paginated REST with its own
natural dedup key (``session_id``), so this module reuses only the
``IngestionCursor`` *tracking* pattern from that base (cursor row per source,
``FOR UPDATE SKIP LOCKED``, error/backoff bookkeeping) and implements its own
fetch/normalize/insert pipeline.

Each active ``IngestionCursor`` with ``source_type='copilot_session_api'``
represents one enterprise to poll (``source_name`` holds the enterprise
slug). For each cursor the worker:

1. Calls ``GET /enterprises/{enterprise}/copilot/chat/sessions?since={cursor}``
   (paginated via the standard GitHub ``Link: rel="next"`` header) to list
   sessions created since the last poll.
2. Calls ``GET /enterprises/{enterprise}/copilot/chat/sessions/{id}/turns``
   per session to fetch that session's prompt/response turns (and any
   embedded tool calls).
3. Normalizes both into ``copilot_sessions`` / ``copilot_session_turns`` /
   ``copilot_session_tool_calls`` rows, dedupes sessions on ``session_id``,
   and bulk-inserts.
4. Advances the cursor to the latest ``created_at`` seen across
   successfully-processed sessions (stored as an ISO-8601 string in the
   existing ``last_file`` text column — a generic "last position" field
   reused here for a timestamp cursor rather than a blob name).

Judgment call / known gap: the ``ingestion_cursors`` table's ``source_type``
CHECK constraint (added in ``0001_initial_schema.py``) only allows
``('s3', 'azure_blob', 'minio')``. Issue #507 explicitly directs this worker
to reuse the existing cursor table with ``source_type='copilot_session_api'``
without creating a new table, and migrations are outside this issue's file
allowlist, so no migration is included here. A cursor row with this
source_type cannot be persisted until a follow-up migration widens that
CHECK constraint — tracked as a follow-up in the PR description.

The exact response shape of the (not-yet-public) Copilot Chat sessions API is
assumed based on the ``CopilotSession`` / ``CopilotSessionTurn`` /
``CopilotSessionToolCall`` ORM models from #505; see ``_normalize_session``,
``_normalize_turn``, and ``_normalize_tool_call`` for the exact field
mapping, called out as a judgment call in the PR description.

Partial-failure handling: if fetching turns for a given session fails, that
session's metadata row is still inserted (it was already fetched
successfully) and the failure is logged; the worker continues on to the next
session rather than aborting the whole poll cycle. If fetching the sessions
list page itself fails, the whole cursor's poll for this cycle is aborted and
retried on the next scheduled run (the cursor position is not advanced past
the last previously-successful session).
"""

from __future__ import annotations

import asyncio
import secrets
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog
from celery import Task

from app.celery_app import celery_app

logger = structlog.get_logger(__name__)

_GITHUB_API_BASE = "https://api.github.com"
_API_VERSION = "2026-03-10"
_SOURCE_TYPE = "copilot_session_api"

# Maximum sessions to process per poll cycle (across all pages), to bound
# memory and keep each Celery task run within the soft time limit.
_MAX_SESSIONS_PER_POLL = 500

# Maximum pages to follow when paginating a single list endpoint.
_MAX_PAGES = 50

# Batch size for bulk inserts.
_BATCH_SIZE = 200


@celery_app.task(
    name="app.workers.ingestion.copilot_session_worker.poll_copilot_sessions",
    bind=True,
    max_retries=3,
)
def poll_copilot_sessions(self: Task) -> dict[str, object]:
    """Celery beat task: iterate active Copilot session API cursors and ingest new sessions."""
    try:
        result = asyncio.run(_poll_all_copilot_sessions())
        return {"status": "ok", **result}
    except Exception as exc:
        logger.error("poll_copilot_sessions.failed", error=str(exc))
        backoff = min(30 * (2**self.request.retries), 600)
        jitter = secrets.randbelow(max(int(backoff * 0.1), 1))
        raise self.retry(exc=exc, countdown=backoff + jitter) from exc


async def _poll_all_copilot_sessions() -> dict[str, Any]:
    """Poll every active Copilot session API ingestion cursor."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.config import settings

    tmp_engine = create_async_engine(
        settings.DATABASE_URL,
        poolclass=NullPool,
        echo=settings.LOG_LEVEL == "DEBUG",
    )
    tmp_session_factory = async_sessionmaker(
        bind=tmp_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )

    try:
        async with tmp_session_factory() as db:
            rows = await db.execute(
                text(
                    "SELECT id, source_name, last_file "
                    "FROM ingestion_cursors "
                    "WHERE source_type = :source_type AND status = 'active' "
                    "FOR UPDATE SKIP LOCKED"
                ),
                {"source_type": _SOURCE_TYPE},
            )
            cursors = rows.fetchall()

        total_sessions = 0
        total_turns = 0
        total_tool_calls = 0

        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            for cursor in cursors:
                cursor_id, enterprise_slug, since = cursor
                try:
                    token = await _get_enterprise_token(tmp_session_factory, enterprise_slug)
                    if token is None:
                        logger.warning(
                            "poll_copilot_sessions.no_token",
                            cursor_id=cursor_id,
                            enterprise=enterprise_slug,
                        )
                        continue

                    sessions, turns, tool_calls = await _poll_single_copilot_cursor(
                        cursor_id=cursor_id,
                        enterprise=enterprise_slug,
                        since=since,
                        token=token,
                        client=client,
                        session_factory=tmp_session_factory,
                    )
                    total_sessions += sessions
                    total_turns += turns
                    total_tool_calls += tool_calls
                except Exception:
                    logger.exception(
                        "poll_copilot_sessions.source_failed",
                        cursor_id=cursor_id,
                        enterprise=enterprise_slug,
                    )
                    async with tmp_session_factory() as db:
                        await db.execute(
                            text(
                                "UPDATE ingestion_cursors "
                                "SET error_count = error_count + 1, "
                                "    error_message = :msg, "
                                "    updated_at = NOW() "
                                "WHERE id = :id"
                            ),
                            {"id": cursor_id, "msg": "Poll failed — see worker logs"},
                        )
                        await db.commit()

        logger.info(
            "poll_copilot_sessions.complete",
            sources=len(cursors),
            sessions=total_sessions,
            turns=total_turns,
            tool_calls=total_tool_calls,
        )
        return {
            "sources": len(cursors),
            "sessions": total_sessions,
            "turns": total_turns,
            "tool_calls": total_tool_calls,
        }
    finally:
        await tmp_engine.dispose()


async def _get_enterprise_token(session_factory: Any, enterprise_slug: str) -> str | None:
    """Obtain a GitHub App installation token for the enterprise-level installation.

    Returns ``None`` (rather than raising) when credentials or the
    installation config are missing, so the caller can skip this cursor and
    continue with others.
    """
    import redis.asyncio as aioredis
    from sqlalchemy import select

    from app.config import settings
    from app.models.github_sync import GitHubAppConfig
    from app.services.github_token_service import GitHubAppTokenManager, GitHubAuthError

    app_id = settings.github_app.GITHUB_APP_ID
    private_key = settings.github_app.resolve_private_key()
    if not app_id or not private_key:
        return None

    async with session_factory() as db:
        result = await db.execute(
            select(GitHubAppConfig).where(
                GitHubAppConfig.enterprise_slug == enterprise_slug,
                GitHubAppConfig.enabled.is_(True),
            )
        )
        config = result.scalars().first()

    if config is None:
        return None

    valkey = aioredis.Redis.from_url(settings.VALKEY_URL, decode_responses=True, max_connections=5)
    try:
        token_manager = GitHubAppTokenManager(
            app_id=int(app_id),
            private_key_pem=private_key,
            valkey_client=valkey,
        )
        return await token_manager.get_installation_token(config.installation_id)
    except GitHubAuthError:
        logger.warning("poll_copilot_sessions.token_failed", enterprise=enterprise_slug)
        return None
    finally:
        await valkey.aclose()


async def _poll_single_copilot_cursor(
    *,
    cursor_id: int,
    enterprise: str,
    since: str | None,
    token: str,
    client: httpx.AsyncClient,
    session_factory: Any,
) -> tuple[int, int, int]:
    """Poll one enterprise's Copilot session API and ingest new sessions.

    Returns ``(sessions_inserted, turns_inserted, tool_calls_inserted)``.
    """
    from sqlalchemy import text

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": _API_VERSION,
    }

    list_url = f"{_GITHUB_API_BASE}/enterprises/{enterprise}/copilot/chat/sessions"
    params: dict[str, Any] = {"per_page": 100}
    if since:
        params["since"] = since

    raw_sessions = await _fetch_paginated(client, list_url, headers, params)
    raw_sessions = raw_sessions[:_MAX_SESSIONS_PER_POLL]

    if not raw_sessions:
        return 0, 0, 0

    deduped = _dedupe_sessions(raw_sessions)

    sessions_to_insert: list[dict[str, Any]] = []
    turns_to_insert: list[dict[str, Any]] = []
    tool_calls_to_insert: list[dict[str, Any]] = []
    latest_created_at: str | None = since

    for raw_session in deduped:
        normalized_session = _normalize_session(raw_session, enterprise)
        session_id = normalized_session["session_id"]

        try:
            turns_url = (
                f"{_GITHUB_API_BASE}/enterprises/{enterprise}"
                f"/copilot/chat/sessions/{session_id}/turns"
            )
            raw_turns = await _fetch_paginated(client, turns_url, headers, {"per_page": 100})
            for raw_turn in raw_turns:
                normalized_turn = _normalize_turn(raw_turn, session_id, normalized_session["org"])
                turns_to_insert.append(normalized_turn)
                for raw_tool_call in raw_turn.get("tool_calls") or []:
                    tool_calls_to_insert.append(
                        _normalize_tool_call(
                            raw_tool_call,
                            session_id=session_id,
                            turn_index=normalized_turn["turn_index"],
                            org=normalized_session["org"],
                        )
                    )
        except Exception:
            # Partial failure: keep the session row (already fetched OK),
            # skip its turns/tool calls, and continue with the next session.
            logger.warning(
                "poll_copilot_sessions.turns_fetch_failed",
                enterprise=enterprise,
                session_id=session_id,
                exc_info=True,
            )

        sessions_to_insert.append(normalized_session)
        created_at_iso = normalized_session["created_at_iso"]
        if created_at_iso and (latest_created_at is None or created_at_iso > latest_created_at):
            latest_created_at = created_at_iso

    inserted_sessions = await _bulk_insert_sessions(session_factory, sessions_to_insert)
    inserted_turns = await _bulk_insert_turns(session_factory, turns_to_insert)
    inserted_tool_calls = await _bulk_insert_tool_calls(session_factory, tool_calls_to_insert)

    if latest_created_at and latest_created_at != since:
        async with session_factory() as db:
            await db.execute(
                text(
                    "UPDATE ingestion_cursors "
                    "SET last_file = :last_file, "
                    "    last_event_count = last_event_count + :events, "
                    "    last_processed_at = :ts, "
                    "    error_count = 0, "
                    "    error_message = NULL, "
                    "    updated_at = NOW() "
                    "WHERE id = :id"
                ),
                {
                    "id": cursor_id,
                    "last_file": latest_created_at,
                    "events": inserted_sessions,
                    "ts": datetime.now(UTC),
                },
            )
            await db.commit()

    return inserted_sessions, inserted_turns, inserted_tool_calls


async def _fetch_paginated(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    params: dict[str, Any],
) -> list[dict[str, Any]]:
    """GET *url* and follow ``Link: rel="next"`` pagination up to ``_MAX_PAGES``.

    Each page is expected to be a bare JSON array, matching GitHub's standard
    list-endpoint convention (e.g. ``GET /orgs/{org}/issues``).
    """
    results: list[dict[str, Any]] = []
    next_url: str | None = url
    next_params: dict[str, Any] | None = params

    for _page in range(_MAX_PAGES):
        if not next_url:
            break
        resp = await client.get(next_url, headers=headers, params=next_params)
        resp.raise_for_status()
        page_data = resp.json()
        if isinstance(page_data, dict):
            # Tolerate a wrapped shape (e.g. {"sessions": [...]}) in case the
            # eventual public API nests the array under a key.
            page_items = page_data.get("sessions") or page_data.get("turns") or []
        else:
            page_items = page_data
        results.extend(page_items)

        next_url = _next_link(resp.headers)
        next_params = None  # `next_url` already carries page params

    return results


def _next_link(headers: httpx.Headers) -> str | None:
    """Parse the ``rel="next"`` URL out of a GitHub ``Link`` response header."""
    link_header = headers.get("link")
    if not link_header:
        return None
    for part in link_header.split(","):
        segments = part.split(";")
        if len(segments) < 2:
            continue
        url_part = segments[0].strip()
        rel_part = segments[1].strip()
        if rel_part == 'rel="next"' and url_part.startswith("<") and url_part.endswith(">"):
            return str(url_part[1:-1])
    return None


def _dedupe_sessions(raw_sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Dedupe raw session payloads on ``id``, keeping the first occurrence."""
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for raw_session in raw_sessions:
        session_id = str(raw_session.get("id") or raw_session.get("session_id") or "")
        if not session_id or session_id in seen:
            continue
        seen.add(session_id)
        deduped.append(raw_session)
    return deduped


def _parse_gh_dt(value: Any) -> datetime | None:
    """Parse a GitHub ISO-8601 timestamp string into a timezone-aware datetime."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _normalize_session(raw: dict[str, Any], enterprise: str) -> dict[str, Any]:
    """Map a raw Copilot session API payload to a ``copilot_sessions`` row dict."""
    user = raw.get("user") or {}
    created_at = raw.get("created_at") or raw.get("started_at")
    return {
        "session_id": str(raw.get("id") or raw.get("session_id")),
        "created_at": _parse_gh_dt(created_at) or datetime.now(UTC),
        "enterprise": enterprise,
        "org": raw.get("organization") or raw.get("org"),
        "actor": user.get("login") or raw.get("actor") or "unknown",
        "actor_id": user.get("id") or raw.get("actor_id"),
        "editor": raw.get("editor"),
        "editor_version": raw.get("editor_version"),
        "copilot_version": raw.get("client_version") or raw.get("copilot_version"),
        "model": raw.get("model"),
        "language": raw.get("language"),
        "repository": raw.get("repository"),
        "turn_count": raw.get("turn_count"),
        "tool_call_count": raw.get("tool_call_count"),
        "total_tokens_in": raw.get("total_tokens_in"),
        "total_tokens_out": raw.get("total_tokens_out"),
        "duration_seconds": raw.get("duration_seconds"),
        "started_at": _parse_gh_dt(raw.get("started_at")),
        "ended_at": _parse_gh_dt(raw.get("ended_at")),
        "data": raw,
        "ingestion_source": _SOURCE_TYPE,
        # ISO string copy of created_at, used for cursor advancement — kept
        # separate from the parsed datetime above (which asyncpg needs as a
        # real datetime object, not a string).
        "created_at_iso": (created_at or datetime.now(UTC).isoformat()),
    }


def _normalize_turn(raw: dict[str, Any], session_id: str, org: str | None) -> dict[str, Any]:
    """Map a raw session turn payload to a ``copilot_session_turns`` row dict."""
    prompt = raw.get("prompt") or {}
    response = raw.get("response") or {}
    return {
        "session_id": session_id,
        "turn_index": raw.get("index") if raw.get("index") is not None else raw.get("turn_index"),
        "created_at": _parse_gh_dt(raw.get("created_at")),
        "prompt_text": prompt.get("text") if isinstance(prompt, dict) else prompt,
        "prompt_tokens": prompt.get("tokens") if isinstance(prompt, dict) else None,
        "response_text": response.get("text") if isinstance(response, dict) else response,
        "response_tokens": response.get("tokens") if isinstance(response, dict) else None,
        "model": raw.get("model"),
        "finish_reason": raw.get("finish_reason"),
        "latency_ms": raw.get("latency_ms"),
        "tool_calls": raw.get("tool_calls"),
        "references": raw.get("references"),
        "annotations": raw.get("annotations"),
        "org": org,
    }


def _normalize_tool_call(
    raw: dict[str, Any],
    *,
    session_id: str,
    turn_index: int | None,
    org: str | None,
) -> dict[str, Any]:
    """Map a raw tool-call payload (nested in a turn) to a row dict."""
    return {
        "session_id": session_id,
        "turn_index": turn_index,
        "tool_name": raw.get("name") or raw.get("tool_name"),
        "tool_input": raw.get("input") or raw.get("tool_input"),
        "tool_output_summary": raw.get("output_summary") or raw.get("tool_output_summary"),
        "duration_ms": raw.get("duration_ms"),
        "success": raw.get("success"),
        "created_at": _parse_gh_dt(raw.get("created_at")),
        "org": org,
    }


async def _bulk_insert_sessions(session_factory: Any, rows: list[dict[str, Any]]) -> int:
    """Bulk-insert normalized session rows, idempotent via ON CONFLICT DO NOTHING."""
    if not rows:
        return 0

    from sqlalchemy import text

    inserted = 0
    async with session_factory() as db:
        for i in range(0, len(rows), _BATCH_SIZE):
            batch = rows[i : i + _BATCH_SIZE]
            params = [
                {k: v for k, v in row.items() if k not in ("created_at_iso", "data")}
                | {"data": _to_json(row.get("data"))}
                for row in batch
            ]
            result = await db.execute(
                text("""
                    INSERT INTO copilot_sessions (
                        session_id, created_at, enterprise, org, actor, actor_id,
                        editor, editor_version, copilot_version, model, language,
                        repository, turn_count, tool_call_count, total_tokens_in,
                        total_tokens_out, duration_seconds, started_at, ended_at,
                        data, ingestion_source
                    ) VALUES (
                        :session_id, :created_at, :enterprise, :org, :actor, :actor_id,
                        :editor, :editor_version, :copilot_version, :model, :language,
                        :repository, :turn_count, :tool_call_count, :total_tokens_in,
                        :total_tokens_out, :duration_seconds, :started_at, :ended_at,
                        CAST(:data AS jsonb), :ingestion_source
                    )
                    ON CONFLICT (session_id, created_at) DO NOTHING
                """),
                params,
            )
            inserted += result.rowcount or 0
        await db.commit()
    return inserted


async def _bulk_insert_turns(session_factory: Any, rows: list[dict[str, Any]]) -> int:
    """Bulk-insert normalized turn rows.

    Deletes any pre-existing turns for the affected session_ids first so a
    retried poll (after a partial earlier failure) doesn't duplicate turns —
    there is no unique constraint on this table to rely on ON CONFLICT (see
    the 0073 migration docstring on why it can't have a DB-enforced FK/unique
    constraint back to ``copilot_sessions``).
    """
    if not rows:
        return 0

    from sqlalchemy import text

    session_ids = sorted({row["session_id"] for row in rows})
    inserted = 0
    async with session_factory() as db:
        await db.execute(
            text("DELETE FROM copilot_session_turns WHERE session_id = ANY(:session_ids)"),
            {"session_ids": session_ids},
        )
        for i in range(0, len(rows), _BATCH_SIZE):
            batch = rows[i : i + _BATCH_SIZE]
            params = [
                {
                    k: v
                    for k, v in row.items()
                    if k not in ("tool_calls", "references", "annotations")
                }
                | {
                    "tool_calls": _to_json(row.get("tool_calls")),
                    "references": _to_json(row.get("references")),
                    "annotations": _to_json(row.get("annotations")),
                }
                for row in batch
            ]
            result = await db.execute(
                text("""
                    INSERT INTO copilot_session_turns (
                        session_id, turn_index, created_at, prompt_text, prompt_tokens,
                        response_text, response_tokens, model, finish_reason, latency_ms,
                        tool_calls, "references", annotations, org
                    ) VALUES (
                        :session_id, :turn_index, :created_at, :prompt_text, :prompt_tokens,
                        :response_text, :response_tokens, :model, :finish_reason, :latency_ms,
                        CAST(:tool_calls AS jsonb), CAST(:references AS jsonb),
                        CAST(:annotations AS jsonb), :org
                    )
                """),
                params,
            )
            inserted += result.rowcount or 0
        await db.commit()
    return inserted


async def _bulk_insert_tool_calls(session_factory: Any, rows: list[dict[str, Any]]) -> int:
    """Bulk-insert normalized tool-call rows.

    See ``_bulk_insert_turns`` for the delete-first rationale.
    """
    if not rows:
        return 0

    from sqlalchemy import text

    session_ids = sorted({row["session_id"] for row in rows})
    inserted = 0
    async with session_factory() as db:
        await db.execute(
            text("DELETE FROM copilot_session_tool_calls WHERE session_id = ANY(:session_ids)"),
            {"session_ids": session_ids},
        )
        for i in range(0, len(rows), _BATCH_SIZE):
            batch = rows[i : i + _BATCH_SIZE]
            params = [
                {k: v for k, v in row.items() if k != "tool_input"}
                | {"tool_input": _to_json(row.get("tool_input"))}
                for row in batch
            ]
            result = await db.execute(
                text("""
                    INSERT INTO copilot_session_tool_calls (
                        session_id, turn_index, tool_name, tool_input, tool_output_summary,
                        duration_ms, success, created_at, org
                    ) VALUES (
                        :session_id, :turn_index, :tool_name, CAST(:tool_input AS jsonb),
                        :tool_output_summary, :duration_ms, :success, :created_at, :org
                    )
                """),
                params,
            )
            inserted += result.rowcount or 0
        await db.commit()
    return inserted


def _to_json(value: Any) -> str:
    """Serialize *value* to a JSON string, treating ``None`` as a JSON null."""
    import json

    return json.dumps(value)
