from __future__ import annotations

from pathlib import Path

from celery.utils.log import get_task_logger

from app.celery_app import celery_app
from app.core.config import settings
from app.pipeline.ingestion import CSVIngestionPipeline
from app.pipeline.sonar import get_runner_for_instance, normalize_repo_url
from app.services import repository
from app.tasks.sonar import process_commit

logger = get_task_logger(__name__)


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def ingest_data_source(self, data_source_id: str) -> dict:
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

    instances = settings.sonarqube.get_instances()
    assigned_instance = None
    for candidate in instances:
        if repository.acquire_instance_lock(candidate.name, job["id"], data_source_id):
            assigned_instance = candidate
            break
    if not assigned_instance:
        logger.info("No SonarQube instance available; retrying later.")
        repository.update_job(job["id"], status="queued")
        raise self.retry(countdown=60)

    repository.update_job(job["id"], status="running", sonar_instance=assigned_instance.name)
    runner_project_key = summary.get("project_key") or data_source.get("name") or job["id"]
    runner = get_runner_for_instance(runner_project_key, assigned_instance.name)

    processed = 0
    job_finished = False
    try:
        for chunk in pipeline.iter_commit_chunks(settings.pipeline.ingestion_chunk_size):
            for item in chunk:
                payload = item.to_dict()
                payload["repo_url"] = normalize_repo_url(
                    payload.get("repository_url"), payload.get("repo_slug")
                )
                payload["sonar_instance"] = assigned_instance.name
                _, job_finished = process_commit(job["id"], data_source_id, payload, runner)
                processed += 1
                if job_finished:
                    break
            if job_finished:
                break
    finally:
        repository.release_instance_lock(assigned_instance.name)

    logger.info(
        "Completed %d commits for job %s on instance %s",
        processed,
        job["id"],
        assigned_instance.name,
    )
    return {"job_id": job["id"], "processed": processed, "sonar_instance": assigned_instance.name}
