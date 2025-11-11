from __future__ import annotations

from pathlib import Path

from celery.utils.log import get_task_logger

from app.celery_app import celery_app
from app.core.config import settings
from app.pipeline.ingestion import CSVIngestionPipeline
from app.services import repository

logger = get_task_logger(__name__)


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def ingest_data_source(self, data_source_id: str) -> dict:
    from app.pipeline.sonar import normalize_repo_url
    from app.tasks.sonar import run_commit_scan

    data_source = repository.get_data_source(data_source_id)
    if not data_source:
        raise ValueError(f"Data source {data_source_id} not found")

    repository.update_data_source(data_source_id, status="processing")
    csv_path = Path(data_source["file_path"])
    pipeline = CSVIngestionPipeline(csv_path)
    summary = pipeline.summarise()
    repository.update_data_source(data_source_id, stats=summary)

    total = summary.get("total_commits") or 0
    job = repository.create_job(
        data_source_id=data_source_id,
        job_type="ingestion",
        total=total,
        status="running" if total else "succeeded",
    )

    if total == 0:
        repository.update_data_source(data_source_id, status="ready")
        return {"job_id": job["id"], "queued": 0}

    queued = 0
    for chunk in pipeline.iter_commit_chunks(settings.pipeline.ingestion_chunk_size):
        for item in chunk:
            payload = item.to_dict()
            payload["repo_url"] = normalize_repo_url(
                payload.get("repository_url"), payload.get("repo_slug")
            )
            run_commit_scan.delay(job["id"], data_source_id, payload)
            queued += 1

    logger.info("Queued %d commits for job %s", queued, job["id"])
    return {"job_id": job["id"], "queued": queued}
