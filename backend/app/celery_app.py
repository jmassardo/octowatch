"""Celery application, queue definitions, and beat schedule.

Uses Valkey as both broker and result backend via the redis-py compatible
connection URL. Queue routing separates ingestion, detection, baseline, and
notification workloads so each can be scaled independently.
"""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.config import settings

app = Celery("audit_log_analyzer")

app.config_from_object(
    {
        # ─── Broker & Result Backend ─────────────────────────────────────────
        "broker_url": settings.VALKEY_URL,
        "result_backend": settings.VALKEY_URL,
        # ─── Serialization ───────────────────────────────────────────────────
        "task_serializer": "json",
        "result_serializer": "json",
        "accept_content": ["json"],
        # ─── Reliability ─────────────────────────────────────────────────────
        "task_acks_late": True,
        "worker_prefetch_multiplier": 4,
        "task_reject_on_worker_lost": True,
        # ─── Result expiry ───────────────────────────────────────────────────
        "result_expires": 3600,
        # ─── Timezone ────────────────────────────────────────────────────────
        "timezone": "UTC",
        "enable_utc": True,
        # ─── Queue definitions ───────────────────────────────────────────────
        "task_routes": {
            "app.workers.ingestion.*": {"queue": "ingestion"},
            "app.workers.detection_worker.*": {"queue": "detection"},
            "app.workers.baseline_worker.*": {"queue": "baseline"},
            "app.workers.notification.*": {"queue": "notification"},
        },
        # ─── Soft / hard time limits ─────────────────────────────────────────
        "task_soft_time_limit": 1800,  # 30 minutes
        "task_time_limit": 2400,  # 40 minutes hard kill
        # ─── Beat schedule ───────────────────────────────────────────────────
        "beat_schedule": {
            # Poll S3 / Azure Blob sources every 5 minutes
            "poll-ingestion-sources": {
                "task": "app.workers.ingestion.s3_worker.poll_s3_sources",
                "schedule": 300.0,  # seconds
                "options": {"queue": "ingestion"},
            },
            "poll-azure-sources": {
                "task": "app.workers.ingestion.azure_worker.poll_azure_sources",
                "schedule": 300.0,
                "options": {"queue": "ingestion"},
            },
            # Behavioral baseline computation — hourly
            "compute-baselines": {
                "task": "app.workers.baseline_worker.compute_rolling_baselines",
                "schedule": crontab(minute=0),  # top of every hour
                "options": {"queue": "baseline"},
            },
            # Ticket status sync — every 15 minutes
            "sync-ticket-statuses": {
                "task": "app.workers.detection_worker.sync_ticket_statuses",
                "schedule": 900.0,
                "options": {"queue": "detection"},
            },
            # Dedup table pruning — daily at 03:00 UTC
            "prune-event-dedup": {
                "task": "app.workers.ingestion.base.prune_event_dedup",
                "schedule": crontab(hour=3, minute=0),
                "options": {"queue": "ingestion"},
            },
        },
    }
)

# Auto-discover tasks in all worker modules
app.autodiscover_tasks(
    [
        "app.workers.ingestion",
        "app.workers",
    ]
)
