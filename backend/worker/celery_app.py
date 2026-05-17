from celery import Celery
from celery.schedules import crontab
from shared.config import get_settings

settings = get_settings()

celery_app = Celery("finditem", broker=settings.celery_broker_url, backend=settings.celery_result_backend)

celery_app.conf.update(
    # Suppress Celery 6.0 deprecation warning for broker retry on startup
    broker_connection_retry_on_startup=True,
    # Reliability: prevent task loss on worker SIGKILL/OOM
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_acks_on_failure_or_timeout=False,
    worker_prefetch_multiplier=1,
    broker_transport_options={
        "visibility_timeout": 3600,  # 1h — longer than the longest expected task
    },
    # Tracing
    task_protocol=2,
    task_send_sent_event=True,
    worker_send_task_events=True,
    # Serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Timezone
    timezone="Asia/Bangkok",
    enable_utc=True,
    # Task routing
    task_routes={
        "worker.tasks.scrape_task.*": {"queue": "scrape"},
        "worker.tasks.poll_task.*": {"queue": "scrape"},
        "worker.tasks.watchlist_task.*": {"queue": "scrape"},
        "worker.tasks.retention_task.*": {"queue": "default"},
        "worker.tasks.session_health_task.*": {"queue": "default"},
        "worker.tasks.notification_task.*": {"queue": "default"},
    },
    # Beat schedule — single source of truth (beat_schedule.py is deprecated; kept for reference)
    beat_schedule={
        # Core scraping
        "poll-due-listings": {
            "task": "worker.tasks.poll_task.dispatch_due_polls",
            "schedule": crontab(minute="*/5"),
        },
        # Watchlist auto-scan
        "watchlist-check-every-30min": {
            "task": "worker.tasks.watchlist_task.run_watchlist_checks",
            "schedule": crontab(minute="*/30"),
        },
        # Notifications
        "daily-summary": {
            "task": "worker.tasks.notification_task.send_daily_summary",
            "schedule": crontab(minute=0, hour=8),  # 08:00 Bangkok time
        },
        # Housekeeping
        "session-health-check": {
            "task": "worker.tasks.session_health_task.check_all_sessions",
            "schedule": crontab(minute=0, hour="*/6"),
        },
        "source-health-update": {
            "task": "worker.tasks.scrape_task.update_source_health",
            "schedule": crontab(minute=15, hour="*"),
        },
        "data-retention": {
            "task": "worker.tasks.retention_task.run_retention",
            "schedule": crontab(minute=0, hour=3),
        },
        "fx-rate-update": {
            "task": "worker.tasks.scrape_task.update_fx_rates",
            "schedule": crontab(minute=30, hour=0),
        },
        "dedup-recluster": {
            "task": "worker.tasks.scrape_task.recluster_orphan_products",
            "schedule": crontab(minute=0, hour=4, day_of_week=0),  # Sunday 04:00
        },
    },
)

# Explicitly import task modules so they register with this app
import worker.tasks.scrape_task  # noqa: F401, E402
import worker.tasks.retention_task  # noqa: F401, E402
import worker.tasks.session_health_task  # noqa: F401, E402
import worker.tasks.notification_task  # noqa: F401, E402
import worker.tasks.poll_task  # noqa: F401, E402
import worker.tasks.watchlist_task  # noqa: F401, E402
