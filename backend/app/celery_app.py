"""Celery application instance for asynchronous work."""

from __future__ import annotations

from celery import Celery

from app.core.config import settings


celery_app = Celery(
    "build_commit_pipeline",
    broker=settings.redis.url,
    backend=settings.redis.url,
    include=["app.tasks.ingestion", "app.tasks.sonar"],
)

celery_app.conf.update(
    task_default_queue=settings.redis.default_queue,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    task_default_retry_delay=10,
    task_routes={
        "app.tasks.sonar.export_metrics": {"queue": settings.redis.default_queue},
        "app.tasks.sonar.run_project_scan": {"queue": settings.redis.default_queue},
        "app.tasks.ingestion.ingest_data_source": {"queue": settings.redis.default_queue},
    },
)


@celery_app.task(name="healthcheck")
def healthcheck() -> str:
    return "OK"
