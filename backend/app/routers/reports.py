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
