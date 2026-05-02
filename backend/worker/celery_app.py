from celery import Celery
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
        "worker.tasks.retention_task.*": {"queue": "default"},
        "worker.tasks.session_health_task.*": {"queue": "default"},
        "worker.tasks.notification_task.*": {"queue": "default"},
    },
)

# Explicitly import task modules so they register with this app
import worker.tasks.scrape_task  # noqa: F401, E402
import worker.tasks.retention_task  # noqa: F401, E402
import worker.tasks.session_health_task  # noqa: F401, E402
import worker.tasks.notification_task  # noqa: F401, E402
import worker.tasks.poll_task  # noqa: F401, E402
