"""Reports router: metric reports, compliance reports, CSV/XLSX export, and scheduling."""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_db, require_role
from app.schemas.report import (
    ComplianceReportEnvelope,
    ReportEnvelope,
    ReportScheduleCreate,
    ReportScheduleResponse,
    ReportScheduleUpdate,
)
from app.services import report_service
from app.services.compliance_report_service import (
    generate_iso27001_report,
    generate_nist_csf_report,
    generate_soc2_report,
)
from app.services.pdf_service import render_compliance_report_html

router = APIRouter(prefix="/reports", tags=["reports"])
logger = structlog.get_logger(__name__)

_WINDOW_VALUES = {30, 60, 90}
_GRANULARITY_VALUES = {"daily", "weekly", "monthly", "hourly"}
_EXPORT_FORMATS = {"csv", "xlsx"}
_COMPLIANCE_EXPORT_FORMATS = {"html", "pdf", "csv", "xlsx"}


def _window_dep(window_days: int = 30) -> int:
    if window_days not in _WINDOW_VALUES:
        return 30
    return window_days


def _gran_dep(granularity: str = "daily") -> str:
    if granularity not in _GRANULARITY_VALUES:
        return "daily"
    return granularity


@router.get("/catalog", response_model=list[dict[str, Any]])
async def report_catalog(
    current_user: AuthenticatedUser = Depends(require_role(["report_admin", "sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Return the catalog of available report types.

    Each entry describes a report that can be generated on-demand via the
    corresponding ``/reports/{type}`` endpoint or exported via
    ``/reports/export/{type}``.
    """
    return [
        {
            "id": "mau",
            "type": "mau",
            "title": "Monthly Active Users",
            "description": ("Unique actors performing audit-logged actions per time bucket."),
            "data_source": "Audit Events",
            "generated_at": None,
            "status": "available",
            "tags": ["usage", "activity"],
        },
        {
            "id": "seat-utilization",
            "type": "seat-utilization",
            "title": "Platform Seat Utilization",
            "description": (
                "Active users vs. peak user count from GHEC"
                " audit events. Uses distinct actors as a"
                " proxy for seat usage."
            ),
            "data_source": "Audit Events",
            "generated_at": None,
            "status": "available",
            "tags": ["licensing", "platform"],
        },
        {
            "id": "actions-volume",
            "type": "actions-volume",
            "title": "Actions Volume",
            "description": ("GitHub Actions workflow run volume and trends from audit events."),
            "data_source": "Audit Events",
            "generated_at": None,
            "status": "available",
            "tags": ["ci-cd", "actions"],
        },
        {
            "id": "copilot-seats",
            "type": "copilot-seats",
            "title": "Copilot Seats",
            "description": (
                "Copilot seat assignment, revocation, and net change from Copilot audit events."
            ),
            "data_source": "Audit Events (Copilot)",
            "generated_at": None,
            "status": "available",
            "tags": ["licensing", "copilot"],
        },
        {
            "id": "repo-creation-rate",
            "type": "repo-creation-rate",
            "title": "Repository Creation Rate",
            "description": ("New repository creation volume over time from audit events."),
            "data_source": "Audit Events",
            "generated_at": None,
            "status": "available",
            "tags": ["repos", "growth"],
        },
        {
            "id": "pat-counts",
            "type": "pat-counts",
            "title": "Personal Access Tokens",
            "description": ("PAT creation and revocation events over time from audit events."),
            "data_source": "Audit Events",
            "generated_at": None,
            "status": "available",
            "tags": ["security", "tokens"],
        },
        {
            "id": "webhook-counts",
            "type": "webhook-counts",
            "title": "Webhook Activity",
            "description": ("Webhook creation and delivery events over time from audit events."),
            "data_source": "Audit Events",
            "generated_at": None,
            "status": "available",
            "tags": ["integrations", "webhooks"],
        },
        {
            "id": "codespace-hours",
            "type": "codespace-hours",
            "title": "Codespace Hours",
            "description": ("GitHub Codespaces usage hours over time from audit events."),
            "data_source": "Audit Events",
            "generated_at": None,
            "status": "available",
            "tags": ["usage", "codespaces"],
        },
        {
            "id": "soc2",
            "type": "soc2",
            "title": "SOC 2 Type II Evidence Report",
            "description": (
                "SOC 2 Trust Services Criteria evidence: CC6.1 logical access, "
                "CC6.2 authentication, CC6.3 access removal, CC8.1 change management, "
                "CC7.1 monitoring."
            ),
            "data_source": "Audit Events (Compliance)",
            "generated_at": None,
            "status": "available",
            "tags": ["compliance", "soc2"],
        },
        {
            "id": "iso27001",
            "type": "iso27001",
            "title": "ISO 27001 Annex A Report",
            "description": (
                "ISO 27001 Annex A controls: A.9 access control, A.12 operations security, "
                "A.14 system development, A.16 incident management, A.18 compliance."
            ),
            "data_source": "Audit Events (Compliance)",
            "generated_at": None,
            "status": "available",
            "tags": ["compliance", "iso27001"],
        },
        {
            "id": "nist-csf",
            "type": "nist-csf",
            "title": "NIST Cybersecurity Framework Report",
            "description": (
                "NIST CSF functions: Identify, Protect, Detect, Respond, Recover — "
                "mapped to GitHub audit log evidence."
            ),
            "data_source": "Audit Events (Compliance)",
            "generated_at": None,
            "status": "available",
            "tags": ["compliance", "nist"],
        },
    ]


@router.get("/mau", response_model=ReportEnvelope)
async def report_mau(
    window_days: int = Depends(_window_dep),
    granularity: str = Depends(_gran_dep),
    org: str | None = Query(None, description="Filter to a specific GitHub org"),
    current_user: AuthenticatedUser = Depends(require_role(["report_admin", "sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> ReportEnvelope:
    """Monthly Active Users report."""
    data = await report_service.get_mau_report(
        db, window_days=window_days, granularity=granularity, org=org
    )
    return ReportEnvelope(
        report_type="mau",
        window_days=window_days,
        granularity=granularity,
        data_source="Audit Events",
        data=data,
    )


@router.get("/seat-utilization", response_model=ReportEnvelope)
async def report_seat_utilization(
    window_days: int = Depends(_window_dep),
    granularity: str = Depends(_gran_dep),
    org: str | None = Query(None),
    current_user: AuthenticatedUser = Depends(require_role(["report_admin", "sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> ReportEnvelope:
    """Seat utilization report per org."""
    data = await report_service.get_seat_utilization_report(
        db, window_days=window_days, granularity=granularity, org=org
    )
    return ReportEnvelope(
        report_type="seat_utilization",
        window_days=window_days,
        granularity=granularity,
        data_source="Audit Events",
        data=data,
    )


@router.get("/repo-creation-rate", response_model=ReportEnvelope)
async def report_repo_creation(
    window_days: int = Depends(_window_dep),
    granularity: str = Depends(_gran_dep),
    org: str | None = Query(None),
    current_user: AuthenticatedUser = Depends(require_role(["report_admin", "sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> ReportEnvelope:
    """Repository creation rate report."""
    data = await report_service.get_repo_creation_rate_report(
        db, window_days=window_days, granularity=granularity, org=org
    )
    return ReportEnvelope(
        report_type="repo_creation_rate",
        window_days=window_days,
        granularity=granularity,
        data_source="Audit Events",
        data=data,
    )


@router.get("/actions-volume", response_model=ReportEnvelope)
async def report_actions_volume(
    window_days: int = Depends(_window_dep),
    granularity: str = Depends(_gran_dep),
    org: str | None = Query(None),
    current_user: AuthenticatedUser = Depends(require_role(["report_admin", "sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> ReportEnvelope:
    """GitHub Actions workflow volume report."""
    data = await report_service.get_actions_volume_report(
        db, window_days=window_days, granularity=granularity, org=org
    )
    return ReportEnvelope(
        report_type="actions_volume",
        window_days=window_days,
        granularity=granularity,
        data_source="Audit Events",
        data=data,
    )


@router.get("/copilot-seats", response_model=ReportEnvelope)
async def report_copilot_seats(
    window_days: int = Depends(_window_dep),
    granularity: str = Depends(_gran_dep),
    org: str | None = Query(None),
    current_user: AuthenticatedUser = Depends(require_role(["report_admin", "sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> ReportEnvelope:
    """Copilot seat assignment/removal trends."""
    data = await report_service.get_copilot_seats_report(
        db, window_days=window_days, granularity=granularity, org=org
    )
    return ReportEnvelope(
        report_type="copilot_seats",
        window_days=window_days,
        granularity=granularity,
        data_source="Audit Events (Copilot)",
        data=data,
    )


@router.get("/codespace-hours", response_model=ReportEnvelope)
async def report_codespace_hours(
    window_days: int = Depends(_window_dep),
    granularity: str = Depends(_gran_dep),
    org: str | None = Query(None),
    current_user: AuthenticatedUser = Depends(require_role(["report_admin", "sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> ReportEnvelope:
    """Codespace billable hours report."""
    data = await report_service.get_codespace_hours_report(
        db, window_days=window_days, granularity=granularity, org=org
    )
    return ReportEnvelope(
        report_type="codespace_hours",
        window_days=window_days,
        granularity=granularity,
        data_source="Audit Events",
        data=data,
    )


@router.get("/pat-counts", response_model=ReportEnvelope)
async def report_pat_counts(
    window_days: int = Depends(_window_dep),
    granularity: str = Depends(_gran_dep),
    org: str | None = Query(None),
    current_user: AuthenticatedUser = Depends(require_role(["report_admin", "sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> ReportEnvelope:
    """Personal Access Token creation/deletion trends."""
    data = await report_service.get_pat_counts_report(
        db, window_days=window_days, granularity=granularity, org=org
    )
    return ReportEnvelope(
        report_type="pat_counts",
        window_days=window_days,
        granularity=granularity,
        data_source="Audit Events",
        data=data,
    )


@router.get("/webhook-counts", response_model=ReportEnvelope)
async def report_webhook_counts(
    window_days: int = Depends(_window_dep),
    granularity: str = Depends(_gran_dep),
    org: str | None = Query(None),
    current_user: AuthenticatedUser = Depends(require_role(["report_admin", "sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> ReportEnvelope:
    """Webhook creation/deletion trends."""
    data = await report_service.get_webhook_counts_report(
        db, window_days=window_days, granularity=granularity, org=org
    )
    return ReportEnvelope(
        report_type="webhook_counts",
        window_days=window_days,
        granularity=granularity,
        data_source="Audit Events",
        data=data,
    )


@router.get("/export/{report_type}")
async def export_report(
    report_type: str,
    window_days: int = Depends(_window_dep),
    granularity: str = Depends(_gran_dep),
    org: str | None = Query(None),
    format: str = Query("csv", description="Export format: csv or xlsx"),
    current_user: AuthenticatedUser = Depends(require_role(["report_admin", "sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Export a metric report as CSV or XLSX."""
    _REPORT_HANDLERS = {
        "mau": report_service.get_mau_report,
        "seat-utilization": report_service.get_seat_utilization_report,
        "seat_utilization": report_service.get_seat_utilization_report,
        "repo-creation-rate": report_service.get_repo_creation_rate_report,
        "repo_creation_rate": report_service.get_repo_creation_rate_report,
        "actions-volume": report_service.get_actions_volume_report,
        "actions_volume": report_service.get_actions_volume_report,
        "copilot-seats": report_service.get_copilot_seats_report,
        "copilot_seats": report_service.get_copilot_seats_report,
        "codespace-hours": report_service.get_codespace_hours_report,
        "codespace_hours": report_service.get_codespace_hours_report,
        "pat-counts": report_service.get_pat_counts_report,
        "pat_counts": report_service.get_pat_counts_report,
        "webhook-counts": report_service.get_webhook_counts_report,
        "webhook_counts": report_service.get_webhook_counts_report,
    }

    handler = _REPORT_HANDLERS.get(report_type)
    if not handler:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown report type: {report_type}",
        )

    fmt = format.lower()
    if fmt not in _EXPORT_FORMATS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported format: {format}. Use csv or xlsx.",
        )

    data = await handler(db, window_days=window_days, granularity=granularity, org=org)

    if fmt == "xlsx":
        from app.services.xlsx_service import generate_xlsx

        xlsx_bytes = generate_xlsx(data, sheet_name=report_type)
        return StreamingResponse(
            iter([xlsx_bytes]),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": (f'attachment; filename="{report_type}_{window_days}d.xlsx"')
            },
        )

    # Default: CSV
    if not data:
        output = io.StringIO()
        output.write("No data available\n")
        output.seek(0)
    else:
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=list(data[0].keys()))
        writer.writeheader()
        writer.writerows(data)
        output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": (f'attachment; filename="{report_type}_{window_days}d.csv"')
        },
    )


# ═══════════════════════════════════════════════════════════════════════════
# Compliance report endpoints
# ═══════════════════════════════════════════════════════════════════════════

_DEFAULT_WINDOW_DAYS = 90


def _parse_date_range(
    start_date: str | None,
    end_date: str | None,
    window_days: int = _DEFAULT_WINDOW_DAYS,
) -> tuple[datetime, datetime]:
    """Parse ISO 8601 date strings or fall back to a rolling window."""
    now = datetime.now(UTC)
    if end_date:
        end_dt = datetime.fromisoformat(end_date)
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=UTC)
    else:
        end_dt = now

    if start_date:
        start_dt = datetime.fromisoformat(start_date)
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=UTC)
    else:
        start_dt = end_dt - timedelta(days=window_days)

    return start_dt, end_dt


@router.get("/compliance/soc2", response_model=ComplianceReportEnvelope)
async def compliance_soc2(
    start_date: str | None = Query(None, description="ISO 8601 start date"),
    end_date: str | None = Query(None, description="ISO 8601 end date"),
    org: str | None = Query(None),
    current_user: AuthenticatedUser = Depends(require_role(["report_admin", "sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Generate SOC 2 Type II evidence report."""
    start_dt, end_dt = _parse_date_range(start_date, end_date)
    return await generate_soc2_report(db, start_dt, end_dt, org=org)


@router.get("/compliance/soc2/export", response_model=None)
async def compliance_soc2_export(
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    org: str | None = Query(None),
    format: str = Query("html", description="Export format: html, pdf, csv, xlsx"),
    current_user: AuthenticatedUser = Depends(require_role(["report_admin", "sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse | HTMLResponse:
    """Export SOC 2 Type II evidence report."""
    start_dt, end_dt = _parse_date_range(start_date, end_date)
    report_data = await generate_soc2_report(db, start_dt, end_dt, org=org)
    return _compliance_export_response(report_data, format, "soc2")


@router.get("/compliance/iso27001", response_model=ComplianceReportEnvelope)
async def compliance_iso27001(
    start_date: str | None = Query(None, description="ISO 8601 start date"),
    end_date: str | None = Query(None, description="ISO 8601 end date"),
    org: str | None = Query(None),
    current_user: AuthenticatedUser = Depends(require_role(["report_admin", "sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Generate ISO 27001 Annex A compliance report."""
    start_dt, end_dt = _parse_date_range(start_date, end_date)
    return await generate_iso27001_report(db, start_dt, end_dt, org=org)


@router.get("/compliance/iso27001/export", response_model=None)
async def compliance_iso27001_export(
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    org: str | None = Query(None),
    format: str = Query("html"),
    current_user: AuthenticatedUser = Depends(require_role(["report_admin", "sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse | HTMLResponse:
    """Export ISO 27001 Annex A compliance report."""
    start_dt, end_dt = _parse_date_range(start_date, end_date)
    report_data = await generate_iso27001_report(db, start_dt, end_dt, org=org)
    return _compliance_export_response(report_data, format, "iso27001")


@router.get("/compliance/nist-csf", response_model=ComplianceReportEnvelope)
async def compliance_nist_csf(
    start_date: str | None = Query(None, description="ISO 8601 start date"),
    end_date: str | None = Query(None, description="ISO 8601 end date"),
    org: str | None = Query(None),
    current_user: AuthenticatedUser = Depends(require_role(["report_admin", "sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Generate NIST Cybersecurity Framework report."""
    start_dt, end_dt = _parse_date_range(start_date, end_date)
    return await generate_nist_csf_report(db, start_dt, end_dt, org=org)


@router.get("/compliance/nist-csf/export", response_model=None)
async def compliance_nist_csf_export(
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    org: str | None = Query(None),
    format: str = Query("html"),
    current_user: AuthenticatedUser = Depends(require_role(["report_admin", "sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse | HTMLResponse:
    """Export NIST Cybersecurity Framework report."""
    start_dt, end_dt = _parse_date_range(start_date, end_date)
    report_data = await generate_nist_csf_report(db, start_dt, end_dt, org=org)
    return _compliance_export_response(report_data, format, "nist-csf")


def _compliance_export_response(
    report_data: dict[str, Any],
    fmt: str,
    report_type: str,
) -> StreamingResponse | HTMLResponse:
    """Build the appropriate export response for a compliance report."""
    fmt = fmt.lower()
    if fmt not in _COMPLIANCE_EXPORT_FORMATS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported format: {fmt}. Use html, pdf, csv, or xlsx.",
        )

    if fmt in ("html", "pdf"):
        html_content = render_compliance_report_html(
            report_data,
            print_ready=(fmt == "pdf"),
        )
        if fmt == "pdf":
            return StreamingResponse(
                iter([html_content.encode("utf-8")]),
                media_type="text/html",
                headers={
                    "Content-Disposition": (f'attachment; filename="{report_type}_report.html"')
                },
            )
        return HTMLResponse(content=html_content)

    # Flatten for tabular export
    flat_data = _flatten_compliance_report(report_data)

    if fmt == "xlsx":
        from app.services.xlsx_service import generate_xlsx

        xlsx_bytes = generate_xlsx(flat_data, sheet_name=report_type)
        return StreamingResponse(
            iter([xlsx_bytes]),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": (f'attachment; filename="{report_type}_report.xlsx"')},
        )

    # CSV
    if not flat_data:
        csv_content = "No data available\n"
    else:
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=list(flat_data[0].keys()))
        writer.writeheader()
        writer.writerows(flat_data)
        csv_content = output.getvalue()

    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{report_type}_report.csv"'},
    )


def _flatten_compliance_report(report_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten a compliance report dict into rows for CSV/XLSX export."""
    rows: list[dict[str, Any]] = []
    sections: list[dict[str, Any]] = report_data.get("controls", []) or report_data.get(
        "functions", []
    )
    for section in sections:
        section_id = section.get("control_id") or section.get("function_id", "")
        title = section.get("title", "")
        evidence = section.get("evidence", {})
        for metric_key, metric_val in evidence.items():
            rows.append(
                {
                    "section_id": section_id,
                    "section_title": title,
                    "metric": metric_key,
                    "value": (
                        str(metric_val) if not isinstance(metric_val, (int, float)) else metric_val
                    ),
                }
            )
    return rows


# ═══════════════════════════════════════════════════════════════════════════
# Report schedule CRUD endpoints
# ═══════════════════════════════════════════════════════════════════════════


@router.post("/schedules", response_model=ReportScheduleResponse, status_code=201)
async def create_schedule(
    payload: ReportScheduleCreate,
    current_user: AuthenticatedUser = Depends(require_role(["report_admin", "sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> ReportScheduleResponse:
    """Create a new report delivery schedule."""
    from app.models.report_schedule import ReportSchedule

    schedule = ReportSchedule(
        report_type=payload.report_type,
        org=payload.org,
        cron_expression=payload.cron_expression,
        export_format=payload.export_format,
        recipients=payload.recipients,
        enabled=payload.enabled,
        created_by=current_user.github_login,
    )
    db.add(schedule)
    await db.flush()
    await db.refresh(schedule)
    return ReportScheduleResponse.model_validate(schedule)


@router.get("/schedules", response_model=list[ReportScheduleResponse])
async def list_schedules(
    current_user: AuthenticatedUser = Depends(require_role(["report_admin", "sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> list[ReportScheduleResponse]:
    """List all report delivery schedules."""
    from app.models.report_schedule import ReportSchedule

    result = await db.execute(select(ReportSchedule).order_by(ReportSchedule.created_at.desc()))
    schedules = list(result.scalars().all())
    return [ReportScheduleResponse.model_validate(s) for s in schedules]


@router.patch("/schedules/{schedule_id}", response_model=ReportScheduleResponse)
async def update_schedule(
    schedule_id: int,
    payload: ReportScheduleUpdate,
    current_user: AuthenticatedUser = Depends(require_role(["report_admin", "sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> ReportScheduleResponse:
    """Update an existing report schedule."""
    from app.models.report_schedule import ReportSchedule

    result = await db.execute(select(ReportSchedule).where(ReportSchedule.id == schedule_id))
    schedule = result.scalar_one_or_none()
    if schedule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule {schedule_id} not found",
        )

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(schedule, field, value)
    schedule.updated_at = datetime.now(UTC)

    await db.flush()
    await db.refresh(schedule)
    return ReportScheduleResponse.model_validate(schedule)


@router.delete("/schedules/{schedule_id}", status_code=204)
async def delete_schedule(
    schedule_id: int,
    current_user: AuthenticatedUser = Depends(require_role(["report_admin", "sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a report schedule."""
    from app.models.report_schedule import ReportSchedule

    result = await db.execute(select(ReportSchedule).where(ReportSchedule.id == schedule_id))
    schedule = result.scalar_one_or_none()
    if schedule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule {schedule_id} not found",
        )

    await db.delete(schedule)
    await db.flush()


# ─── Executive summary ────────────────────────────────────────────────────────


@router.get("/executive-summary")
async def get_executive_summary(
    period: int = Query(30, description="Lookback period in days (7, 30, or 90)"),
    current_user: AuthenticatedUser = Depends(
        require_role(["analyst", "report_admin", "rule_author", "sys_admin"])
    ),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Executive summary for CISO dashboards.

    Returns posture score with delta, detection trends, compliance summary,
    top risks, and month-over-month comparison metrics.
    """
    from sqlalchemy import func

    from app.models.audit_event import AuditEvent
    from app.models.detection import Detection
    from app.services.rbac_service import get_user_scope

    scope = await get_user_scope(db, current_user.github_login, current_user.roles)

    if period not in (7, 30, 90):
        period = 30

    now = datetime.now(UTC)
    period_start = now - timedelta(days=period)
    previous_start = period_start - timedelta(days=period)

    # ── Posture score (current vs previous period) ────────────────────────
    severity_weight = {"critical": 10, "high": 7, "medium": 4, "low": 2, "info": 1}
    open_statuses = ("open", "investigating")

    # Current open detections
    current_det_stmt = select(
        Detection.severity,
        func.count(Detection.id).label("cnt"),
    ).where(
        Detection.status.in_(open_statuses),
        Detection.triggered_at >= period_start,
    )
    if scope.scoped_orgs:
        current_det_stmt = current_det_stmt.where(Detection.org.in_(scope.scoped_orgs))
    current_det_stmt = current_det_stmt.group_by(Detection.severity)
    current_sev_rows = (await db.execute(current_det_stmt)).all()

    sev_breakdown: dict[str, int] = {}
    total_weight = 0
    for row in current_sev_rows:
        sev_breakdown[row.severity] = row.cnt
        w = severity_weight.get(row.severity, 1) * row.cnt
        total_weight += w

    # Score: detections reduce score from 100
    posture_score = max(0.0, round(100.0 - min(total_weight, 100), 1))

    # Previous period score
    prev_det_stmt = select(
        Detection.severity,
        func.count(Detection.id).label("cnt"),
    ).where(
        Detection.triggered_at >= previous_start,
        Detection.triggered_at < period_start,
    )
    if scope.scoped_orgs:
        prev_det_stmt = prev_det_stmt.where(Detection.org.in_(scope.scoped_orgs))
    prev_det_stmt = prev_det_stmt.group_by(Detection.severity)
    prev_sev_rows = (await db.execute(prev_det_stmt)).all()

    prev_weight = sum(severity_weight.get(r.severity, 1) * r.cnt for r in prev_sev_rows)
    prev_score = max(0.0, round(100.0 - min(prev_weight, 100), 1))

    score_delta = round(posture_score - prev_score, 1)
    score_delta_pct = round((score_delta / prev_score * 100) if prev_score > 0 else 0, 1)

    # ── Detection trend (7/30/90 day counts) ──────────────────────────────
    trend: dict[str, int] = {}
    for days in (7, 30, 90):
        trend_stmt = select(func.count(Detection.id)).where(
            Detection.triggered_at >= now - timedelta(days=days)
        )
        if scope.scoped_orgs:
            trend_stmt = trend_stmt.where(Detection.org.in_(scope.scoped_orgs))
        trend[f"{days}d"] = (await db.execute(trend_stmt)).scalar_one()

    # ── Compliance summary ────────────────────────────────────────────────
    compliance_summary: list[dict[str, Any]] = []
    for framework, generator in [
        ("SOC 2", generate_soc2_report),
        ("ISO 27001", generate_iso27001_report),
        ("NIST CSF", generate_nist_csf_report),
    ]:
        try:
            report = await generator(db, period_days=period, org=None)
            es = report.get("executive_summary", {})
            assessed = es.get("controls_assessed", 0) or es.get("functions_assessed", 0)
            with_evidence = es.get("controls_with_evidence", 0) or es.get(
                "functions_with_evidence", 0
            )
            pct = round((with_evidence / assessed * 100) if assessed > 0 else 0, 1)
            compliance_summary.append(
                {
                    "framework": framework,
                    "controls_assessed": assessed,
                    "controls_with_evidence": with_evidence,
                    "compliance_pct": pct,
                }
            )
        except Exception:
            logger.warning("executive_summary.compliance_failed", framework=framework)
            compliance_summary.append(
                {
                    "framework": framework,
                    "controls_assessed": 0,
                    "controls_with_evidence": 0,
                    "compliance_pct": 0,
                }
            )

    # ── Top risks ─────────────────────────────────────────────────────────
    top_risk_stmt = (
        select(
            Detection.title,
            Detection.severity,
            Detection.actor,
            func.count(Detection.id).label("cnt"),
        )
        .where(
            Detection.status.in_(open_statuses),
            Detection.triggered_at >= period_start,
        )
        .group_by(Detection.title, Detection.severity, Detection.actor)
        .order_by(func.count(Detection.id).desc())
        .limit(5)
    )
    if scope.scoped_orgs:
        top_risk_stmt = top_risk_stmt.where(Detection.org.in_(scope.scoped_orgs))
    top_risk_rows = (await db.execute(top_risk_stmt)).all()

    top_risks = [
        {
            "title": r.title,
            "severity": r.severity,
            "category": "",
            "count": r.cnt,
            "actor": r.actor,
        }
        for r in top_risk_rows
    ]

    # ── Month-over-month ──────────────────────────────────────────────────
    current_det_count_stmt = select(func.count(Detection.id)).where(
        Detection.triggered_at >= period_start
    )
    if scope.scoped_orgs:
        current_det_count_stmt = current_det_count_stmt.where(Detection.org.in_(scope.scoped_orgs))
    current_det_count = (await db.execute(current_det_count_stmt)).scalar_one()

    prev_det_count_stmt = select(func.count(Detection.id)).where(
        Detection.triggered_at >= previous_start,
        Detection.triggered_at < period_start,
    )
    if scope.scoped_orgs:
        prev_det_count_stmt = prev_det_count_stmt.where(Detection.org.in_(scope.scoped_orgs))
    prev_det_count = (await db.execute(prev_det_count_stmt)).scalar_one()

    current_event_stmt = select(func.count(AuditEvent.id)).where(
        AuditEvent.created_at >= period_start
    )
    if scope.scoped_orgs:
        current_event_stmt = current_event_stmt.where(AuditEvent.org.in_(scope.scoped_orgs))
    current_events = (await db.execute(current_event_stmt)).scalar_one()

    prev_event_stmt = select(func.count(AuditEvent.id)).where(
        AuditEvent.created_at >= previous_start,
        AuditEvent.created_at < period_start,
    )
    if scope.scoped_orgs:
        prev_event_stmt = prev_event_stmt.where(AuditEvent.org.in_(scope.scoped_orgs))
    prev_events = (await db.execute(prev_event_stmt)).scalar_one()

    det_change = round(
        ((current_det_count - prev_det_count) / prev_det_count * 100) if prev_det_count > 0 else 0,
        1,
    )
    event_change = round(
        ((current_events - prev_events) / prev_events * 100) if prev_events > 0 else 0,
        1,
    )

    return {
        "posture_score": posture_score,
        "posture_score_previous": prev_score,
        "score_delta": score_delta,
        "score_delta_pct": score_delta_pct,
        "detection_trend": trend,
        "severity_breakdown": sev_breakdown,
        "compliance_summary": compliance_summary,
        "top_risks": top_risks,
        "month_over_month": {
            "current_detections": current_det_count,
            "previous_detections": prev_det_count,
            "current_events": current_events,
            "previous_events": prev_events,
            "detection_change_pct": det_change,
            "event_change_pct": event_change,
        },
    }


@router.get("/executive-summary/pdf")
async def export_executive_summary_pdf(
    period: int = Query(30, description="Lookback period in days (7, 30, or 90)"),
    current_user: AuthenticatedUser = Depends(
        require_role(["analyst", "report_admin", "rule_author", "sys_admin"])
    ),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Generate a print-ready HTML page for the executive summary.

    Use the browser's print-to-PDF function for presentation-ready output.
    """

    # Re-use the summary endpoint logic
    summary = await get_executive_summary(period=period, current_user=current_user, db=db)

    # Build an HTML page for print/PDF
    html = _render_executive_html(summary)
    return HTMLResponse(content=html)


def _render_executive_html(summary: dict[str, Any]) -> str:
    """Render executive summary to print-ready HTML."""
    compliance_rows = ""
    for c in summary.get("compliance_summary", []):
        compliance_rows += (
            f"<tr><td>{c['framework']}</td>"
            f"<td>{c['controls_assessed']}</td>"
            f"<td>{c['controls_with_evidence']}</td>"
            f"<td>{c['compliance_pct']}%</td></tr>"
        )

    risk_rows = ""
    for r in summary.get("top_risks", []):
        risk_rows += (
            f"<tr><td>{r['title']}</td>"
            f"<td>{r['severity']}</td>"
            f"<td>{r['count']}</td>"
            f"<td>{r.get('actor', '—')}</td></tr>"
        )

    score = summary["posture_score"]
    delta = summary["score_delta"]
    delta_class = "delta-down" if delta < 0 else "delta-up"
    delta_arrow = "▼" if delta < 0 else "▲"

    mom = summary["month_over_month"]
    trend = summary["detection_trend"]
    generated = datetime.now(UTC).strftime("%B %d, %Y")

    # Build metric divs as variables to keep lines short
    t7 = trend.get("7d", 0)
    t30 = trend.get("30d", 0)
    t90 = trend.get("90d", 0)
    cur_det = mom["current_detections"]
    prev_det = mom["previous_detections"]
    cur_ev = mom["current_events"]
    prev_ev = mom["previous_events"]
    det_pct = mom["detection_change_pct"]
    ev_pct = mom["event_change_pct"]
    delta_pct = summary["score_delta_pct"]

    parts = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="UTF-8">',
        "<title>OctoWatch Executive Summary</title>",
        "<style>",
        "  body { font-family: -apple-system, sans-serif;",
        "    color: #24292e; background: #fff;",
        "    padding: 40px 60px; line-height: 1.6; }",
        "  h1 { font-size: 28px; margin-bottom: 4px; }",
        "  .subtitle { color: #6a737d; margin-bottom: 32px; }",
        "  .score-card { display: inline-block;",
        "    background: #f6f8fa; border: 1px solid #e1e4e8;",
        "    border-radius: 8px; padding: 24px 36px;",
        "    margin-bottom: 24px; text-align: center; }",
        "  .score-value { font-size: 48px; font-weight: 700; }",
        "  .delta-up { color: #28a745; }",
        "  .delta-down { color: #cb2431; }",
        "  .delta { font-size: 18px; font-weight: 600; }",
        "  table { border-collapse: collapse;",
        "    width: 100%; margin-bottom: 24px; }",
        "  th, td { border: 1px solid #e1e4e8;",
        "    padding: 8px 12px; text-align: left; font-size: 14px; }",
        "  th { background: #f6f8fa; font-weight: 600; }",
        "  .section { margin-top: 32px; }",
        "  .section h2 { font-size: 18px;",
        "    border-bottom: 1px solid #e1e4e8;",
        "    padding-bottom: 8px; }",
        "  .metrics { display: flex; gap: 24px;",
        "    flex-wrap: wrap; margin-bottom: 24px; }",
        "  .metric { background: #f6f8fa;",
        "    border-radius: 6px; padding: 16px 20px;",
        "    border: 1px solid #e1e4e8; min-width: 140px; }",
        "  .metric .val { font-size: 24px; font-weight: 700; }",
        "  .metric .lbl { font-size: 12px; color: #6a737d; }",
        "  @media print { body { padding: 20px; } }",
        "</style>",
        "</head>",
        "<body>",
        "<h1>OctoWatch Executive Security Summary</h1>",
        f'<div class="subtitle">Generated {generated}</div>',
        '<div class="score-card">',
        f'  <div class="score-value">{score}</div>',
        "  <div>Security Posture Score</div>",
        f'  <div class="delta {delta_class}">',
        f"    {delta_arrow} {abs(delta)} ({delta_pct}%)",
        "  </div>",
        "</div>",
        '<div class="section">',
        "  <h2>Detection Trend</h2>",
        '  <div class="metrics">',
        '    <div class="metric">',
        f'      <div class="val">{t7}</div>',
        '      <div class="lbl">Last 7 days</div>',
        "    </div>",
        '    <div class="metric">',
        f'      <div class="val">{t30}</div>',
        '      <div class="lbl">Last 30 days</div>',
        "    </div>",
        '    <div class="metric">',
        f'      <div class="val">{t90}</div>',
        '      <div class="lbl">Last 90 days</div>',
        "    </div>",
        "  </div>",
        "</div>",
        '<div class="section">',
        "  <h2>Compliance Status</h2>",
        "  <table>",
        "    <thead><tr>",
        "      <th>Framework</th>",
        "      <th>Controls Assessed</th>",
        "      <th>With Evidence</th>",
        "      <th>Score</th>",
        "    </tr></thead>",
        f"    <tbody>{compliance_rows}</tbody>",
        "  </table>",
        "</div>",
        '<div class="section">',
        "  <h2>Top Risks</h2>",
        "  <table>",
        "    <thead><tr>",
        "      <th>Risk</th><th>Severity</th>",
        "      <th>Count</th><th>Actor</th>",
        "    </tr></thead>",
        f"    <tbody>{risk_rows}</tbody>",
        "  </table>",
        "</div>",
        '<div class="section">',
        "  <h2>Month-over-Month</h2>",
        '  <div class="metrics">',
        '    <div class="metric">',
        f'      <div class="val">{cur_det}</div>',
        '      <div class="lbl">',
        f"        Current Detections ({det_pct:+.1f}%)",
        "      </div>",
        "    </div>",
        '    <div class="metric">',
        f'      <div class="val">{prev_det}</div>',
        '      <div class="lbl">Previous Detections</div>',
        "    </div>",
        '    <div class="metric">',
        f'      <div class="val">{cur_ev}</div>',
        '      <div class="lbl">',
        f"        Current Events ({ev_pct:+.1f}%)",
        "      </div>",
        "    </div>",
        '    <div class="metric">',
        f'      <div class="val">{prev_ev}</div>',
        '      <div class="lbl">Previous Events</div>',
        "    </div>",
        "  </div>",
        "</div>",
        "</body>",
        "</html>",
    ]
    return "\n".join(parts)
