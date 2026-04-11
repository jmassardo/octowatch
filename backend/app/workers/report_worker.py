"""Celery worker for scheduled report generation and email delivery.

Runs every hour via Celery beat, checks which report schedules are due
based on their cron expressions, generates the report, and emails it to
the configured recipients.
"""

from __future__ import annotations

import asyncio
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from celery import Task
from sqlalchemy.ext.asyncio import AsyncSession

from app.celery_app import celery_app
from app.database import AsyncSessionLocal
from app.models.report_schedule import ReportSchedule

logger = structlog.get_logger(__name__)


def _cron_is_due(cron_expression: str, last_run_at: datetime | None) -> bool:
    """Check if a cron schedule is due based on the current time.

    Uses a simplified cron parser that handles the most common patterns:
    ``minute hour day_of_month month day_of_week``.

    If the schedule has never run (``last_run_at`` is None), it is considered due
    provided the cron expression is valid.
    """
    now = datetime.now(UTC)
    parts = cron_expression.strip().split()
    if len(parts) != 5:
        logger.warning("report_worker.invalid_cron", cron=cron_expression)
        return False

    if last_run_at is None:
        return True

    minute_spec, hour_spec, dom_spec, month_spec, dow_spec = parts

    if not _matches_field(minute_spec, now.minute):
        return False
    if not _matches_field(hour_spec, now.hour):
        return False
    if not _matches_field(dom_spec, now.day):
        return False
    if not _matches_field(month_spec, now.month):
        return False
    if not _matches_field(dow_spec, now.weekday()):
        return False

    # Ensure we don't re-run within the same hour
    if last_run_at and (now - last_run_at) < timedelta(minutes=55):
        return False

    return True


def _matches_field(spec: str, value: int) -> bool:
    """Check if a single cron field matches the current value."""
    if spec == "*":
        return True

    # Handle */N step values
    if spec.startswith("*/"):
        step = int(spec[2:])
        return step > 0 and value % step == 0

    # Handle comma-separated values
    if "," in spec:
        return value in {int(v) for v in spec.split(",")}

    # Handle ranges (e.g. 1-5)
    if "-" in spec:
        low, high = spec.split("-", 1)
        return int(low) <= value <= int(high)

    # Exact match
    return value == int(spec)


@celery_app.task(
    name="app.workers.report_worker.run_scheduled_reports",
    bind=True,
    max_retries=2,
)
def run_scheduled_reports_task(self: Task) -> dict[str, object]:
    """Celery beat task: check all enabled schedules and run those that are due."""
    try:
        result = asyncio.run(_run_scheduled_reports())
        return {"status": "ok", **result}
    except Exception as exc:
        logger.error("report_worker.task_failed", error=str(exc))
        backoff = min(60 * (2**self.request.retries), 600)
        jitter = secrets.randbelow(max(int(backoff * 0.1), 1))
        raise self.retry(exc=exc, countdown=backoff + jitter) from exc


async def _run_scheduled_reports() -> dict[str, object]:
    """Async entry point: load due schedules, generate reports, and email them."""
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        stmt = select(ReportSchedule).where(ReportSchedule.enabled.is_(True))
        result = await session.execute(stmt)
        schedules = list(result.scalars().all())

        if not schedules:
            return {"schedules_checked": 0, "reports_sent": 0}

        sent = 0
        checked = len(schedules)

        for schedule in schedules:
            if not _cron_is_due(schedule.cron_expression, schedule.last_run_at):
                continue

            try:
                await _generate_and_send(session, schedule)
                schedule.last_run_at = datetime.now(UTC)
                schedule.last_status = "success"
                sent += 1
            except Exception as exc:
                logger.error(
                    "report_worker.schedule_failed",
                    schedule_id=schedule.id,
                    error=str(exc),
                )
                schedule.last_run_at = datetime.now(UTC)
                schedule.last_status = "failed"

        await session.commit()
        return {"schedules_checked": checked, "reports_sent": sent}


async def _generate_and_send(
    session: AsyncSession,
    schedule: ReportSchedule,
) -> None:
    """Generate a report for the given schedule and email it to recipients."""
    from email import encoders
    from email.mime.base import MIMEBase
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    import aiosmtplib

    from app.config import settings
    from app.services.compliance_report_service import (
        generate_iso27001_report,
        generate_nist_csf_report,
        generate_soc2_report,
    )
    from app.services.pdf_service import render_compliance_report_html

    now = datetime.now(UTC)
    start_date = now - timedelta(days=90)
    end_date = now

    # Generate report based on type
    compliance_types = {
        "soc2": generate_soc2_report,
        "iso27001": generate_iso27001_report,
        "nist-csf": generate_nist_csf_report,
    }

    report_data: dict[str, Any] | None = None
    generator = compliance_types.get(schedule.report_type)
    if generator:
        report_data = await generator(session, start_date, end_date, org=schedule.org)

    if report_data is None:
        logger.warning(
            "report_worker.unsupported_type",
            report_type=schedule.report_type,
            schedule_id=schedule.id,
        )
        return

    # Generate export content
    fmt = schedule.export_format
    if fmt in ("html", "pdf"):
        content = render_compliance_report_html(report_data, print_ready=(fmt == "pdf"))
        filename = f"{schedule.report_type}_report.html"
        content_bytes = content.encode("utf-8")
    elif fmt == "xlsx":
        from app.services.xlsx_service import generate_xlsx

        flat_data = _flatten_compliance_report(report_data)
        content_bytes = generate_xlsx(flat_data, sheet_name=schedule.report_type)
        filename = f"{schedule.report_type}_report.xlsx"
    elif fmt == "csv":
        import csv
        import io

        flat_data = _flatten_compliance_report(report_data)
        output = io.StringIO()
        if flat_data:
            writer = csv.DictWriter(output, fieldnames=list(flat_data[0].keys()))
            writer.writeheader()
            writer.writerows(flat_data)
        content_bytes = output.getvalue().encode("utf-8")
        filename = f"{schedule.report_type}_report.csv"
    else:
        logger.warning("report_worker.unsupported_format", fmt=fmt)
        return

    # Send email
    if not schedule.recipients:
        return

    smtp_cfg = settings.INTEGRATIONS
    msg = MIMEMultipart()
    msg["Subject"] = f"OctoWatch {schedule.report_type.upper()} Report — {now.strftime('%Y-%m-%d')}"
    msg["From"] = smtp_cfg.SMTP_FROM_ADDRESS or "noreply@octowatch.io"
    msg["To"] = ", ".join(schedule.recipients)

    body_text = (
        f"Please find the attached {schedule.report_type.upper()} compliance report.\n"
        f"Period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}\n"
    )
    msg.attach(MIMEText(body_text, "plain"))

    attachment = MIMEBase("application", "octet-stream")
    attachment.set_payload(content_bytes)
    encoders.encode_base64(attachment)
    attachment.add_header("Content-Disposition", f"attachment; filename={filename}")
    msg.attach(attachment)

    await aiosmtplib.send(
        msg,
        hostname=smtp_cfg.SMTP_HOST or "localhost",
        port=smtp_cfg.SMTP_PORT,
        username=smtp_cfg.SMTP_USERNAME if smtp_cfg.SMTP_USERNAME else None,
        password=smtp_cfg.SMTP_PASSWORD if smtp_cfg.SMTP_PASSWORD else None,
        use_tls=smtp_cfg.SMTP_USE_TLS,
    )

    logger.info(
        "report_worker.report_sent",
        schedule_id=schedule.id,
        report_type=schedule.report_type,
        recipients=schedule.recipients,
    )


def _flatten_compliance_report(
    report_data: dict[str, Any],
) -> list[dict[str, Any]]:
    """Flatten a compliance report into a list of dicts suitable for CSV/XLSX export."""
    rows: list[dict[str, Any]] = []

    # Process controls (SOC 2 / ISO 27001)
    sections = report_data.get("controls", []) or report_data.get("functions", [])
    for section in sections:
        section_id = section.get("control_id") or section.get("function_id", "")
        title = section.get("title", "")
        evidence = section.get("evidence", {})
        for metric_key, metric_val in evidence.items():
            value = metric_val if isinstance(metric_val, (int, float)) else str(metric_val)
            rows.append(
                {
                    "section_id": section_id,
                    "section_title": title,
                    "metric": metric_key,
                    "value": value,
                }
            )

    return rows
