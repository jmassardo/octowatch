"""Celery worker for daily Copilot metrics persistence.

Fetches metrics from the GitHub Copilot NDJSON API and persists them
to the copilot_daily_metrics table.  Also snapshots seat data for
historical analysis.  Phase 3 fetches per-user usage data for UBB billing.

Runs daily at 06:00 UTC via Celery beat.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from typing import Any

import structlog
from celery import Task

from app.celery_app import celery_app
from app.database import AsyncSessionLocal

logger = structlog.get_logger(__name__)


def _run_async(coro: Any) -> Any:
    """Run an async coroutine in a new event loop (for Celery sync workers)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(
    name="app.workers.copilot_metrics_worker.sync_copilot_metrics",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
)
def sync_copilot_metrics(self: Task) -> dict[str, Any]:
    """Fetch and persist daily Copilot metrics and seat snapshots.

    Three-phase operation:
    1. Fetch metrics from the NDJSON API and upsert into copilot_daily_metrics
    2. Fetch seat data from billing/seats API and snapshot into copilot_seat_snapshots
    3. Fetch per-user usage data from the usage API and upsert into copilot_usage_reports
    """
    return _run_async(_sync_copilot_metrics_async(self))


async def _sync_copilot_metrics_async(task: Task) -> dict[str, Any]:
    """Async implementation of the Copilot metrics sync task."""
    from app.services import copilot_metrics_service

    metrics_count = 0
    seats_count = 0
    usage_count = 0

    async with AsyncSessionLocal() as db:
        try:
            # Phase 1: Fetch and persist daily metrics
            raw = await copilot_metrics_service._fetch_metrics_raw(db)
            if isinstance(raw, dict) and "error" in raw:
                logger.warning(
                    "copilot_sync.metrics_fetch_error",
                    error=raw.get("error"),
                    message=raw.get("message"),
                )
            elif isinstance(raw, list):
                metrics_count = await _persist_daily_metrics(db, raw)
                logger.info("copilot_sync.metrics_persisted", count=metrics_count)

            # Phase 2: Fetch and snapshot seat data
            seats = await copilot_metrics_service._fetch_copilot_seats(db)
            if isinstance(seats, dict) and "error" in seats:
                logger.warning(
                    "copilot_sync.seats_fetch_error",
                    error=seats.get("error"),
                    message=seats.get("message"),
                )
            elif isinstance(seats, list):
                seats_count = await _persist_seat_snapshots(db, seats)
                logger.info("copilot_sync.seats_persisted", count=seats_count)

            # Phase 3: Fetch and persist per-user usage data (UBB)
            usage_data = await _fetch_copilot_usage(db)
            if isinstance(usage_data, dict) and "error" in usage_data:
                logger.warning(
                    "copilot_sync.usage_fetch_error",
                    error=usage_data.get("error"),
                    message=usage_data.get("message"),
                )
            elif isinstance(usage_data, list):
                usage_count = await _persist_usage_reports(db, usage_data)
                logger.info("copilot_sync.usage_persisted", count=usage_count)

            await db.commit()

        except Exception as exc:
            logger.error("copilot_sync.failed", error=str(exc), exc_info=True)
            await db.rollback()
            raise task.retry(exc=exc) from exc

    return {
        "status": "completed",
        "metrics_persisted": metrics_count,
        "seats_persisted": seats_count,
        "usage_persisted": usage_count,
        "timestamp": datetime.now(UTC).isoformat(),
    }


async def _persist_daily_metrics(
    db: Any,
    days: list[dict[str, Any]],
) -> int:
    """Upsert daily metric rows from raw API data.

    Extracts per-language, per-editor, per-model breakdowns and stores
    each combination as a row in ``copilot_daily_metrics``.
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.models.copilot_metrics import CopilotDailyMetric

    rows: list[dict[str, Any]] = []
    enterprise_slug = ""

    try:
        from app.config import settings as app_settings

        enterprise_slug = app_settings.github_app.GITHUB_ENTERPRISE_SLUG or "default"
    except Exception:
        enterprise_slug = "default"

    for day_obj in days:
        date_str = day_obj.get("date", "")
        if not date_str:
            continue

        # Summary row
        rows.append(
            {
                "date": date_str,
                "org_slug": enterprise_slug,
                "metric_type": "summary",
                "language": None,
                "editor": None,
                "model": None,
                "active_users": day_obj.get("total_active_users", 0),
                "engaged_users": day_obj.get("total_engaged_users", 0),
                "total_suggestions": 0,
                "total_acceptances": 0,
                "total_lines_suggested": 0,
                "total_lines_accepted": 0,
                "acceptance_rate": None,
            }
        )

        # Completions breakdown
        completions = day_obj.get("copilot_ide_code_completions") or {}
        for editor_obj in completions.get("editors", []):
            editor_name = editor_obj.get("name", "Unknown")
            for model_obj in editor_obj.get("models", []):
                model_name = model_obj.get("name", "Unknown")
                for lang_obj in model_obj.get("languages", []):
                    lang_name = lang_obj.get("name", "Unknown")
                    sugg = lang_obj.get("total_code_suggestions", 0)
                    acc = lang_obj.get("total_code_acceptances", 0)
                    rate = round(acc / sugg * 100, 2) if sugg > 0 else None

                    rows.append(
                        {
                            "date": date_str,
                            "org_slug": enterprise_slug,
                            "metric_type": "completions",
                            "language": lang_name,
                            "editor": editor_name,
                            "model": model_name,
                            "active_users": 0,
                            "engaged_users": model_obj.get("total_engaged_users", 0),
                            "total_suggestions": sugg,
                            "total_acceptances": acc,
                            "total_lines_suggested": lang_obj.get("total_code_lines_suggested", 0),
                            "total_lines_accepted": lang_obj.get("total_code_lines_accepted", 0),
                            "acceptance_rate": rate,
                        }
                    )

        # Chat / PR / Dotcom rows
        for feature_key, metric_type in (
            ("copilot_ide_chat", "chat"),
            ("copilot_dotcom_chat", "dotcom_chat"),
            ("copilot_dotcom_pull_requests", "pr"),
        ):
            feature = day_obj.get(feature_key) or {}
            engaged = feature.get("total_engaged_users", 0)
            if engaged > 0:
                rows.append(
                    {
                        "date": date_str,
                        "org_slug": enterprise_slug,
                        "metric_type": metric_type,
                        "language": None,
                        "editor": None,
                        "model": None,
                        "active_users": 0,
                        "engaged_users": engaged,
                        "total_suggestions": 0,
                        "total_acceptances": 0,
                        "total_lines_suggested": 0,
                        "total_lines_accepted": 0,
                        "acceptance_rate": None,
                    }
                )

    if not rows:
        return 0

    # Batch upsert (PostgreSQL ON CONFLICT)
    try:
        stmt = pg_insert(CopilotDailyMetric).values(rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_copilot_daily_metrics_composite",
            set_={
                "active_users": stmt.excluded.active_users,
                "engaged_users": stmt.excluded.engaged_users,
                "total_suggestions": stmt.excluded.total_suggestions,
                "total_acceptances": stmt.excluded.total_acceptances,
                "total_lines_suggested": stmt.excluded.total_lines_suggested,
                "total_lines_accepted": stmt.excluded.total_lines_accepted,
                "acceptance_rate": stmt.excluded.acceptance_rate,
                "synced_at": datetime.now(UTC),
            },
        )
        await db.execute(stmt)
    except Exception:
        logger.error("copilot_sync.daily_metrics_upsert_failed", exc_info=True)

    return len(rows)


async def _persist_seat_snapshots(
    db: Any,
    seats: list[dict[str, Any]],
) -> int:
    """Snapshot current seat assignments into copilot_seat_snapshots."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.models.copilot_metrics import CopilotSeatSnapshot

    today = datetime.now(UTC).date()
    rows: list[dict[str, Any]] = []

    for seat in seats:
        assignee = seat.get("assignee") or {}
        login = assignee.get("login")
        if not login:
            continue

        org_slug = seat.get("_org_slug", "")
        last_activity = seat.get("last_activity_at")
        last_editor = seat.get("last_activity_editor")
        plan_type = seat.get("plan_type", "business")
        pending_cancel = seat.get("pending_cancellation_date")

        rows.append(
            {
                "snapshot_date": today,
                "org_slug": org_slug,
                "github_login": login,
                "plan_type": plan_type,
                "last_activity_at": last_activity,
                "last_activity_editor": last_editor,
                "pending_cancellation_date": pending_cancel,
            }
        )

    if not rows:
        return 0

    try:
        stmt = pg_insert(CopilotSeatSnapshot).values(rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_copilot_seat_snapshots_composite",
            set_={
                "plan_type": stmt.excluded.plan_type,
                "last_activity_at": stmt.excluded.last_activity_at,
                "last_activity_editor": stmt.excluded.last_activity_editor,
                "pending_cancellation_date": stmt.excluded.pending_cancellation_date,
            },
        )
        await db.execute(stmt)
    except Exception:
        logger.error("copilot_sync.seat_snapshots_upsert_failed", exc_info=True)

    return len(rows)


async def _fetch_copilot_usage(db: Any) -> list[dict[str, Any]] | dict[str, str]:
    """Fetch per-user usage data from org-level Copilot users-28-day NDJSON reports.

    Iterates over all Organization GitHub App installations, calls
    ``GET /orgs/{org}/copilot/metrics/reports/users-28-day/latest`` for each,
    downloads the NDJSON files, and returns aggregated per-user records.
    """
    from app.services.copilot_metrics_service import _get_org_tokens, _parse_ndjson

    org_tokens_result = await _get_org_tokens(db)
    if isinstance(org_tokens_result, dict):
        return org_tokens_result

    import httpx

    all_usage: list[dict[str, Any]] = []

    async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as client:
        for org_login, token in org_tokens_result:
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "X-GitHub-Api-Version": "2022-11-28",
            }

            report_url = (
                f"https://api.github.com/orgs/{org_login}"
                f"/copilot/metrics/reports/users-28-day/latest"
            )

            try:
                resp = await client.get(report_url, headers=headers)
                if resp.status_code in (403, 404):
                    logger.debug(
                        "copilot_sync.org_usage_report_unavailable",
                        org=org_login,
                        status=resp.status_code,
                    )
                    continue
                if resp.status_code != 200:
                    logger.warning(
                        "copilot_sync.org_usage_report_error",
                        org=org_login,
                        status=resp.status_code,
                    )
                    continue

                report_data = resp.json()
                download_links = report_data.get("download_links", [])

                # Download each NDJSON file immediately (signed URLs are short-lived)
                for link in download_links:
                    try:
                        ndjson_resp = await client.get(link)
                        if ndjson_resp.status_code == 200:
                            records = _parse_ndjson(ndjson_resp.text)
                            for record in records:
                                record["_org_slug"] = org_login
                                record["_source"] = "org"
                                # Normalize user field to 'login' if not present
                                if "login" not in record:
                                    if "github_login" in record:
                                        record["login"] = record["github_login"]
                                    elif "user" in record:
                                        record["login"] = record["user"]
                                    elif "assignee" in record and isinstance(
                                        record["assignee"], dict
                                    ):
                                        record["login"] = record["assignee"].get("login", "")
                            all_usage.extend(records)
                        else:
                            logger.warning(
                                "copilot_sync.usage_ndjson_download_error",
                                org=org_login,
                                status=ndjson_resp.status_code,
                            )
                    except Exception:
                        logger.warning(
                            "copilot_sync.usage_ndjson_download_failed",
                            org=org_login,
                            exc_info=True,
                        )

            except Exception:
                logger.warning(
                    "copilot_sync.org_usage_report_fetch_failed",
                    org=org_login,
                    exc_info=True,
                )
                continue

    return all_usage


async def _persist_usage_reports(
    db: Any,
    usage_records: list[dict[str, Any]],
) -> int:
    """Upsert per-user usage data into copilot_usage_reports."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.models.copilot_usage import CopilotUsageReport

    today = date.today()
    rows: list[dict[str, Any]] = []

    try:
        from app.config import settings as app_settings

        default_org = app_settings.github_app.GITHUB_ENTERPRISE_SLUG or "default"
    except Exception:
        default_org = "default"

    for record in usage_records:
        login = record.get("login") or record.get("github_login") or record.get("user", "")
        if not login:
            # Try nested assignee format
            assignee = record.get("assignee") or {}
            login = assignee.get("login", "")
        if not login:
            continue

        report_date_str = record.get("date") or record.get("day")
        if report_date_str:
            try:
                from datetime import date as date_type

                parts = report_date_str.split("-")
                report_date = date_type(int(parts[0]), int(parts[1]), int(parts[2]))
            except (ValueError, IndexError):
                report_date = today
        else:
            report_date = today

        org_slug = record.get("_org_slug") or record.get("org", default_org)

        # Extract credit breakdown
        breakdown = record.get("breakdown") or {}
        total_credits = float(record.get("total_credits_consumed", 0) or breakdown.get("total", 0))
        completions_credits = float(
            record.get("completions_credits", 0) or breakdown.get("completions", 0)
        )
        chat_credits = float(record.get("chat_credits", 0) or breakdown.get("chat", 0))
        pr_credits = float(record.get("pr_credits", 0) or breakdown.get("pull_requests", 0))
        other_credits = float(record.get("other_credits", 0) or breakdown.get("other", 0))

        # If total is 0 but breakdown has values, sum them
        if total_credits == 0 and (completions_credits or chat_credits or pr_credits):
            total_credits = completions_credits + chat_credits + pr_credits + other_credits

        # Budget data if present
        budget_amount = record.get("budget_amount")
        budget_consumed = record.get("budget_consumed")
        is_blocked = bool(record.get("is_blocked", False))

        rows.append(
            {
                "report_date": report_date,
                "org_slug": org_slug,
                "github_login": login,
                "total_credits_consumed": total_credits,
                "completions_credits": completions_credits,
                "chat_credits": chat_credits,
                "pr_credits": pr_credits,
                "other_credits": other_credits,
                "budget_amount": float(budget_amount) if budget_amount is not None else None,
                "budget_consumed": float(budget_consumed) if budget_consumed is not None else None,
                "is_blocked": is_blocked,
                "synced_at": datetime.now(UTC),
            }
        )

    if not rows:
        return 0

    try:
        stmt = pg_insert(CopilotUsageReport).values(rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_copilot_usage_composite",
            set_={
                "total_credits_consumed": stmt.excluded.total_credits_consumed,
                "completions_credits": stmt.excluded.completions_credits,
                "chat_credits": stmt.excluded.chat_credits,
                "pr_credits": stmt.excluded.pr_credits,
                "other_credits": stmt.excluded.other_credits,
                "budget_amount": stmt.excluded.budget_amount,
                "budget_consumed": stmt.excluded.budget_consumed,
                "is_blocked": stmt.excluded.is_blocked,
                "synced_at": stmt.excluded.synced_at,
            },
        )
        await db.execute(stmt)
    except Exception:
        logger.error("copilot_sync.usage_reports_upsert_failed", exc_info=True)

    return len(rows)
