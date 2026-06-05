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
    """Upsert daily metric rows from raw NDJSON report data.

    The new org-level 28-day NDJSON reports have a single record per org
    containing a ``day_totals`` array.  Each entry has per-IDE, per-feature,
    and per-language breakdowns.
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.models.copilot_metrics import CopilotDailyMetric

    rows: list[dict[str, Any]] = []

    for report in days:
        org_slug = report.get("_org_slug", "default")
        day_totals = report.get("day_totals", [])

        # If the record itself is a flat day (legacy format fallback)
        if not day_totals and report.get("date"):
            day_totals = [report]

        for day_obj in day_totals:
            date_str = day_obj.get("day", "") or day_obj.get("date", "")
            if not date_str:
                continue

            # Convert date string to date object for PostgreSQL
            try:
                parts = date_str.split("-")
                report_date = date(int(parts[0]), int(parts[1]), int(parts[2]))
            except (ValueError, IndexError):
                continue

            active_users = day_obj.get("daily_active_users", 0) or day_obj.get(
                "total_active_users", 0
            )
            # monthly_active_users as engaged proxy
            engaged_users = day_obj.get("monthly_active_users", 0) or day_obj.get(
                "total_engaged_users", 0
            )

            # Aggregate suggestions/acceptances from totals_by_feature
            total_suggestions = day_obj.get("code_generation_activity_count", 0)
            total_acceptances = day_obj.get("code_acceptance_activity_count", 0)
            rate = (
                round(total_acceptances / total_suggestions * 100, 2)
                if total_suggestions > 0
                else None
            )

            # Summary row
            rows.append(
                {
                    "date": report_date,
                    "org_slug": org_slug,
                    "metric_type": "summary",
                    "language": None,
                    "editor": None,
                    "model": None,
                    "active_users": active_users,
                    "engaged_users": engaged_users,
                    "total_suggestions": total_suggestions,
                    "total_acceptances": total_acceptances,
                    "total_lines_suggested": day_obj.get("loc_suggested_to_add_sum", 0),
                    "total_lines_accepted": day_obj.get("loc_added_sum", 0),
                    "acceptance_rate": rate,
                }
            )

            # Per-IDE breakdown
            for ide_obj in day_obj.get("totals_by_ide", []):
                ide_name = ide_obj.get("ide", "Unknown")
                sugg = ide_obj.get("code_generation_activity_count", 0)
                acc = ide_obj.get("code_acceptance_activity_count", 0)
                ide_rate = round(acc / sugg * 100, 2) if sugg > 0 else None
                rows.append(
                    {
                        "date": report_date,
                        "org_slug": org_slug,
                        "metric_type": "completions",
                        "language": None,
                        "editor": ide_name,
                        "model": None,
                        "active_users": 0,
                        "engaged_users": 0,
                        "total_suggestions": sugg,
                        "total_acceptances": acc,
                        "total_lines_suggested": ide_obj.get("loc_suggested_to_add_sum", 0),
                        "total_lines_accepted": ide_obj.get("loc_added_sum", 0),
                        "acceptance_rate": ide_rate,
                    }
                )

            # Per-feature breakdown (chat, code_completion, copilot_cli, etc.)
            for feat_obj in day_obj.get("totals_by_feature", []):
                feature_name = feat_obj.get("feature", "Unknown")
                metric_type_map = {
                    "code_completion": "completions",
                    "copilot_chat": "chat",
                    "copilot_cli": "chat",
                    "dotcom_chat": "dotcom_chat",
                    "copilot_pull_request": "pr",
                }
                metric_type = metric_type_map.get(feature_name, feature_name)
                feat_sugg = feat_obj.get("code_generation_activity_count", 0)
                feat_acc = feat_obj.get("code_acceptance_activity_count", 0)
                feat_rate = round(feat_acc / feat_sugg * 100, 2) if feat_sugg > 0 else None
                rows.append(
                    {
                        "date": report_date,
                        "org_slug": org_slug,
                        "metric_type": metric_type,
                        "language": None,
                        "editor": None,
                        "model": None,
                        "active_users": 0,
                        "engaged_users": feat_obj.get("user_initiated_interaction_count", 0),
                        "total_suggestions": feat_sugg,
                        "total_acceptances": feat_acc,
                        "total_lines_suggested": feat_obj.get("loc_suggested_to_add_sum", 0),
                        "total_lines_accepted": feat_obj.get("loc_added_sum", 0),
                        "acceptance_rate": feat_rate,
                    }
                )

            # Per-language-feature breakdown
            for lf_obj in day_obj.get("totals_by_language_feature", []):
                lang_name = lf_obj.get("language", "Unknown")
                lf_sugg = lf_obj.get("code_generation_activity_count", 0)
                lf_acc = lf_obj.get("code_acceptance_activity_count", 0)
                lf_rate = round(lf_acc / lf_sugg * 100, 2) if lf_sugg > 0 else None
                rows.append(
                    {
                        "date": report_date,
                        "org_slug": org_slug,
                        "metric_type": "completions",
                        "language": lang_name,
                        "editor": None,
                        "model": None,
                        "active_users": 0,
                        "engaged_users": 0,
                        "total_suggestions": lf_sugg,
                        "total_acceptances": lf_acc,
                        "total_lines_suggested": lf_obj.get("loc_suggested_to_add_sum", 0),
                        "total_lines_accepted": lf_obj.get("loc_added_sum", 0),
                        "acceptance_rate": lf_rate,
                    }
                )

    if not rows:
        return 0

    # Batch upsert in chunks to stay under PostgreSQL's 32767 parameter limit
    batch_size = 2000
    try:
        for i in range(0, len(rows), batch_size):
            chunk = rows[i : i + batch_size]
            stmt = pg_insert(CopilotDailyMetric).values(chunk)
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
        last_activity_str = seat.get("last_activity_at")
        last_activity = None
        if last_activity_str:
            try:
                last_activity = datetime.fromisoformat(last_activity_str.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass
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
    """Upsert per-user usage data into copilot_usage_reports.

    The users-28-day NDJSON report provides activity counts (interactions,
    generations, acceptances) rather than credit data.  We map activity
    counts into the credit fields for display purposes:
    - total_credits_consumed = user_initiated_interaction_count
    - completions_credits = code_generation_activity_count
    - chat_credits = user_initiated_interaction_count - code_generation_activity_count
    - pr_credits = 0 (not broken out in this report)
    - other_credits = code_acceptance_activity_count
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.models.copilot_usage import CopilotUsageReport

    today = date.today()
    rows: list[dict[str, Any]] = []

    for record in usage_records:
        # New NDJSON format uses user_login
        login = (
            record.get("user_login")
            or record.get("login")
            or record.get("github_login")
            or record.get("user", "")
        )
        if not login:
            assignee = record.get("assignee") or {}
            login = assignee.get("login", "")
        if not login:
            continue

        report_date_str = record.get("day") or record.get("date")
        if report_date_str:
            try:
                from datetime import date as date_type

                parts = report_date_str.split("-")
                report_date = date_type(int(parts[0]), int(parts[1]), int(parts[2]))
            except (ValueError, IndexError):
                report_date = today
        else:
            report_date = today

        org_slug = record.get("_org_slug") or record.get("org", "default")

        # Map activity counts to credit fields
        interactions = float(record.get("user_initiated_interaction_count", 0))
        generations = float(record.get("code_generation_activity_count", 0))
        acceptances = float(record.get("code_acceptance_activity_count", 0))

        # If record has actual credit data (future API), use that
        if record.get("total_credits_consumed"):
            total_credits = float(record["total_credits_consumed"])
            completions_credits = float(record.get("completions_credits", 0))
            chat_credits = float(record.get("chat_credits", 0))
            pr_credits = float(record.get("pr_credits", 0))
            other_credits = float(record.get("other_credits", 0))
        else:
            # Map activity data into credit fields for display
            total_credits = interactions
            completions_credits = generations
            chat_credits = max(0, interactions - generations)
            pr_credits = 0.0
            other_credits = acceptances

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

    # Batch upsert in chunks to stay under PostgreSQL's 32767 parameter limit
    batch_size = 2000
    try:
        for i in range(0, len(rows), batch_size):
            chunk = rows[i : i + batch_size]
            stmt = pg_insert(CopilotUsageReport).values(chunk)
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
