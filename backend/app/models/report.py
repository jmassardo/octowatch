"""Report models: placeholder for time-series views + re-export of schedule model."""

# Reports (MAU, seat utilization, etc.) are served from TimescaleDB continuous
# aggregate views (events_hourly, events_daily_actor, detections_daily).
# No additional ORM models are needed for the v1 reporting endpoints.

# The ReportSchedule model lives in its own module for clean imports.
from app.models.report_schedule import ReportSchedule

__all__ = ["ReportSchedule"]
