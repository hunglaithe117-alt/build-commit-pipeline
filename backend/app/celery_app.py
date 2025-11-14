"""Celery application instance for asynchronous work."""

from __future__ import annotations

from celery import Celery
from kombu import Queue

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
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    task_reject_on_worker_lost=True,
    task_retry_backoff=True,
    task_retry_jitter=True,
    task_default_max_retries=3,
    task_routes={
        "app.tasks.sonar.export_metrics": {"queue": "pipeline.exports"},
        "app.tasks.sonar.run_commit_scan": {"queue": "pipeline.scan"},
        "app.tasks.ingestion.ingest_data_source": {"queue": "pipeline.ingest"},
    },
)

celery_app.conf.task_queues = (
    Queue("pipeline.ingest"),
    Queue("pipeline.scan", queue_arguments={"x-max-priority": 10}),
    Queue("pipeline.exports"),
)


@celery_app.task(name="healthcheck")
def healthcheck() -> str:
    return "OK"
