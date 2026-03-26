"""Placeholder models for reports — reports use views, not ORM models."""

# Reports (MAU, seat utilization, etc.) are served from TimescaleDB continuous
# aggregate views (events_hourly, events_daily_actor, detections_daily).
# No additional ORM models are needed for the v1 reporting endpoints.
