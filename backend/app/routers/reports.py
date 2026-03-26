"""Reports router: 8 metric report endpoints + CSV export."""

from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import AuthenticatedUser, get_db, require_role
from app.schemas.report import ReportEnvelope
from app.services import report_service

router = APIRouter(prefix="/reports", tags=["reports"])

_WINDOW_VALUES = {30, 60, 90}
_GRANULARITY_VALUES = {"daily", "weekly", "monthly", "hourly"}


def _window_dep(window_days: int = 30) -> int:
    if window_days not in _WINDOW_VALUES:
        return 30
    return window_days


def _gran_dep(granularity: str = "daily") -> str:
    if granularity not in _GRANULARITY_VALUES:
        return "daily"
    return granularity


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
        report_type="mau", window_days=window_days, granularity=granularity, data=data
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
        report_type="seat_utilization", window_days=window_days, granularity=granularity, data=data
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
        report_type="actions_volume", window_days=window_days, granularity=granularity, data=data
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
        report_type="copilot_seats", window_days=window_days, granularity=granularity, data=data
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
        report_type="codespace_hours", window_days=window_days, granularity=granularity, data=data
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
        report_type="pat_counts", window_days=window_days, granularity=granularity, data=data
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
        report_type="webhook_counts", window_days=window_days, granularity=granularity, data=data
    )


@router.get("/export/{report_type}")
async def export_report_csv(
    report_type: str,
    window_days: int = Depends(_window_dep),
    granularity: str = Depends(_gran_dep),
    org: str | None = Query(None),
    current_user: AuthenticatedUser = Depends(require_role(["report_admin", "sys_admin"])),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Export a report as CSV."""
    _REPORT_HANDLERS = {
        "mau": report_service.get_mau_report,
        "seat_utilization": report_service.get_seat_utilization_report,
        "repo_creation_rate": report_service.get_repo_creation_rate_report,
        "actions_volume": report_service.get_actions_volume_report,
        "copilot_seats": report_service.get_copilot_seats_report,
        "codespace_hours": report_service.get_codespace_hours_report,
        "pat_counts": report_service.get_pat_counts_report,
        "webhook_counts": report_service.get_webhook_counts_report,
    }

    handler = _REPORT_HANDLERS.get(report_type)
    if not handler:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown report type: {report_type}",
        )

    data = await handler(db, window_days=window_days, granularity=granularity, org=org)

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
        headers={"Content-Disposition": f'attachment; filename="{report_type}_{window_days}d.csv"'},
    )
