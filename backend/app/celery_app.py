"""Celery application instance for asynchronous work."""

from __future__ import annotations

from celery import Celery

from app.core.config import settings


celery_app = Celery(
    "build_commit_pipeline",
    broker=settings.broker.url,
    backend=settings.broker.result_backend,
    include=["app.tasks.ingestion", "app.tasks.sonar"],
)

celery_app.conf.update(
    task_default_queue=settings.broker.default_queue,
    task_acks_late=True,
    worker_prefetch_multiplier=2,
    worker_concurrency=settings.pipeline.sonar_parallelism,
    broker_connection_retry_on_startup=True,
    task_default_retry_delay=10,
    task_retry_backoff=True,
    task_retry_backoff_max=180,  # Max 3 minutes
    task_retry_jitter=True,  # Add randomness to avoid thundering herd
    task_routes={
        "app.tasks.sonar.export_metrics": {"queue": settings.broker.default_queue},
        "app.tasks.sonar.run_commit_scan": {"queue": settings.broker.default_queue},
        "app.tasks.ingestion.ingest_data_source": {
            "queue": settings.broker.default_queue
        },
    },
)


@celery_app.task(name="healthcheck")
def healthcheck() -> str:
    return "OK"
