from celery.schedules import crontab
from worker.celery_app import celery_app

celery_app.conf.beat_schedule = {
    # ------------------------------------------------------------------ #
    # Core scraping
    # ------------------------------------------------------------------ #
    "poll-due-listings": {
        "task": "worker.tasks.poll_task.dispatch_due_polls",
        "schedule": crontab(minute="*/5"),  # every 5 minutes
    },

    # ------------------------------------------------------------------ #
    # Notifications
    # ------------------------------------------------------------------ #
    "daily-summary": {
        "task": "worker.tasks.notification_task.send_daily_summary",
        "schedule": crontab(minute=0, hour=8),  # 08:00 Bangkok time
    },

    # ------------------------------------------------------------------ #
    # Housekeeping
    # ------------------------------------------------------------------ #
    "session-health-check": {
        "task": "worker.tasks.session_health_task.check_all_sessions",
        "schedule": crontab(minute=0, hour="*/6"),
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
}
