from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from celery.utils.log import get_task_logger

from app.celery_app import celery_app
from app.core.config import settings
from app.pipeline.sonar import MetricsExporter, SonarCommitRunner
from app.services import repository

logger = get_task_logger(__name__)


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 2})
def run_commit_scan(self, job_id: str, data_source_id: str, commit: Dict[str, str]) -> str:
    commit_sha = commit.get("commit_sha")
    project_key = commit.get("project_key")
    repo_url = commit.get("repo_url")
    if not all([commit_sha, project_key, repo_url]):
        raise ValueError("Commit payload missing mandatory fields.")

    component_key = f"{project_key}_{commit_sha}"
    repository.update_job(job_id, status="running", current_commit=commit_sha)
    repository.upsert_sonar_run(
        data_source_id=data_source_id,
        project_key=project_key,
        commit_sha=commit_sha,
        job_id=job_id,
        status="running",
        component_key=component_key,
    )
    runner = SonarCommitRunner(project_key)
    try:
        result = runner.scan_commit(
            repo_url=repo_url,
            commit_sha=commit_sha,
            repo_slug=commit.get("repo_slug"),
        )
    except Exception as exc:
        message = str(exc)
        repository.upsert_sonar_run(
            data_source_id=data_source_id,
            project_key=project_key,
            commit_sha=commit_sha,
            job_id=job_id,
            status="failed",
            message=message,
        )
        repository.update_job(
            job_id,
            status="failed",
            last_error=message,
            current_commit=None,
        )
        repository.update_data_source(data_source_id, status="failed")
        repository.insert_dead_letter(
            payload={"job_id": job_id, "commit": commit, "error": message},
            reason="sonar-commit",
        )
        logger.exception("Commit %s failed", commit_sha)
        raise

    repository.upsert_sonar_run(
        data_source_id=data_source_id,
        project_key=project_key,
        commit_sha=commit_sha,
        job_id=job_id,
        status="submitted",
        log_path=str(result.log_path),
        component_key=result.component_key,
    )

    updated_job = repository.update_job(
        job_id,
        processed_delta=1,
        current_commit=None,
    )
    if updated_job and updated_job.get("processed", 0) >= updated_job.get("total", 0):
        repository.update_job(job_id, status="succeeded")
        repository.update_data_source(data_source_id, status="ready")

    logger.info("Submitted commit %s for analysis (component %s)", commit_sha, result.component_key)
    return result.component_key


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def export_metrics(
    self,
    project_key: str,
    job_id: Optional[str] = None,
    data_source_id: Optional[str] = None,
    analysis_id: Optional[str] = None,
) -> str:
    exporter = MetricsExporter()
    destination = Path(settings.paths.exports) / f"{project_key}_metrics.csv"
    measures = exporter.export_project(project_key, destination)
    repository.add_output(
        job_id=job_id or "ad-hoc",
        path=str(destination),
        metrics=list(measures.keys()),
        record_count=1,
    )
    if data_source_id:
        run_doc = repository.find_sonar_run_by_component(project_key) or {}
        repository.upsert_sonar_run(
            data_source_id=data_source_id,
            project_key=run_doc.get("project_key", project_key),
            commit_sha=run_doc.get("commit_sha"),
            job_id=run_doc.get("job_id") or job_id,
            status="succeeded",
            analysis_id=analysis_id,
            metrics_path=str(destination),
            component_key=project_key,
        )
    logger.info("Metrics exported to %s", destination)
    return str(destination)
