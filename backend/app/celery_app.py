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
            "app.workers.ingest_webhook_worker.*": {"queue": "ingestion"},
            "app.workers.detection_worker.*": {"queue": "detection"},
            "app.workers.baseline_worker.*": {"queue": "baseline"},
            "app.workers.notification.*": {"queue": "notification"},
            "app.workers.report_worker.*": {"queue": "notification"},
            "app.workers.github_sync.*": {"queue": "github_sync"},
            "app.workers.copilot_metrics_worker.*": {"queue": "github_sync"},
            "app.workers.siem_export_worker.*": {"queue": "notification"},
            "app.workers.threat_intel_worker.*": {"queue": "baseline"},
            "app.workers.retention_worker.*": {"queue": "baseline"},
            "app.workers.ingestion_health.*": {"queue": "baseline"},
            "app.workers.github_ip_allowlist_worker.*": {"queue": "baseline"},
            "app.workers.workflow_scan_worker.*": {"queue": "baseline"},
        },
        # ─── Soft / hard time limits ─────────────────────────────────────────
        "task_soft_time_limit": 1800,  # 30 minutes
        "task_time_limit": 2400,  # 40 minutes hard kill
        # ─── Beat schedule ───────────────────────────────────────────────────
        "beat_schedule": {
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
            # Retention enforcement — daily at 02:30 UTC
            "enforce-retention-policies": {
                "task": "app.workers.retention_worker.enforce_all_retention_policies",
                "schedule": crontab(hour=2, minute=30),
                "options": {"queue": "baseline"},
            },
            # Ingestion gap detection — every 60 minutes
            "check-ingestion-gaps": {
                "task": "app.workers.ingestion_health.check_ingestion_gaps",
                "schedule": 3600.0,  # every 60 minutes
                "options": {"queue": "baseline"},
            },
            # Notification digest — daily at 08:00 UTC
            "send-notification-digest": {
                "task": "app.workers.notification.send_digest",
                "schedule": crontab(hour=8, minute=0),
                "options": {"queue": "notification"},
            },
            # Scheduled report delivery — every hour at :30
            "run-scheduled-reports": {
                "task": "app.workers.report_worker.run_scheduled_reports",
                "schedule": crontab(minute=30),
                "options": {"queue": "notification"},
            },
            # Copilot metrics sync — daily at 06:00 UTC
            "sync-copilot-metrics": {
                "task": "app.workers.copilot_metrics_worker.sync_copilot_metrics",
                "schedule": crontab(hour=6, minute=0),
                "options": {"queue": "github_sync"},
            },
            # Workflow security scan — daily at 04:00 UTC
            "scan-workflow-security": {
                "task": "app.workers.workflow_scan_worker.scan_all_workflows",
                "schedule": crontab(hour=4, minute=0),
                "options": {"queue": "baseline"},
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

# autodiscover only finds tasks.py; explicitly include other task modules
app.conf.include = [
    "app.workers.github_sync_worker",
    "app.workers.notification_worker",
    "app.workers.baseline_worker",
    "app.workers.detection_worker",
    "app.workers.report_worker",
    "app.workers.retention_worker",
    "app.workers.copilot_metrics_worker",
    "app.workers.ingestion.base",
    "app.workers.ingest_webhook_worker",
    "app.workers.siem_export_worker",
    "app.workers.ingestion_health",
    "app.workers.threat_intel_worker",
    "app.workers.workflow_scan_worker",
]

# Conditionally add GitHub sync heartbeat to beat schedule
if settings.github_app.GITHUB_SYNC_ENABLED:
    app.conf.beat_schedule["enterprise-sync-heartbeat"] = {
        "task": "app.workers.github_sync.check_sync_schedule",
        "schedule": crontab(hour=2, minute=0),
        "options": {"queue": "github_sync"},
    }

# GitHub IP allowlist refresh — every 6 hours
if settings.github_app.GITHUB_IP_ALLOWLIST_ENABLED:
    app.conf.beat_schedule["refresh-github-ip-allowlist"] = {
        "task": "app.workers.github_ip_allowlist_worker.refresh_github_ip_allowlist",
        "schedule": crontab(minute=0, hour="*/6"),
        "options": {"queue": "baseline"},
    }
    # Include the task module so Celery can discover it
    app.conf.include = list(app.conf.include or []) + [
        "app.workers.github_ip_allowlist_worker",
    ]

# Alias for import convenience: `from app.celery_app import celery_app`
celery_app = app
