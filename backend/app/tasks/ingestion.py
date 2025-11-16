from __future__ import annotations

from pathlib import Path

import pandas as pd
from celery.utils.log import get_task_logger

from app.celery_app import celery_app
from app.core.config import settings
from app.models import ProjectStatus
from app.services import repository
from pipeline.ingestion import CSVIngestionPipeline
from pipeline.sonar import normalize_repo_url
from app.tasks.sonar import run_scan_job

logger = get_task_logger(__name__)


@celery_app.task(bind=True)
def ingest_project(self, project_id: str) -> dict:
    project = repository.get_project(project_id)
    if not project:
        raise ValueError(f"Project {project_id} not found")

    source_path = project.get("source_path")
    if not source_path:
        raise ValueError(f"Project {project_id} missing source_path for ingestion")

    csv_path = Path(source_path)
    pipeline = CSVIngestionPipeline(csv_path)
    summary = pipeline.summarise()

    repository.update_project(
        project_id,
        status=ProjectStatus.processing.value,
        total_builds=summary.get("total_builds", 0),
        total_commits=summary.get("total_commits", 0),
    )

    default_project_key = Path(csv_path).stem
    df = pd.read_csv(csv_path, encoding=settings.pipeline.csv_encoding, dtype=str)
    df = df.fillna("")

    df["commit"] = df.get("git_trigger_commit", "").astype(str).str.strip()
    df["repo_slug"] = df.get("gh_project_name", "").astype(str).str.strip()

    def _derive_key(slug: str) -> str:
        return slug.replace("/", "_") if slug else default_project_key

    df["project_key"] = df["repo_slug"].apply(_derive_key)
    df = df[df["commit"] != ""]
    df_unique = df.drop_duplicates(subset=["project_key", "commit"], keep="first")

    total_commits = int(len(df_unique))
    if total_commits == 0:
        repository.update_project(project_id, status=ProjectStatus.finished.value)
        return {"project_id": project_id, "queued": 0}

    queued = 0
    max_retries = project.get("max_retries", settings.pipeline.default_retry_limit)

    for _, row in df_unique.iterrows():
        project_key = row["project_key"]
        commit = row["commit"]
        repo_slug = row["repo_slug"] or None
        repo_url = row.get("repository_url") or None
        repo_url = normalize_repo_url(repo_url, repo_slug)

        job_doc = repository.create_scan_job(
            project_id=project_id,
            commit_sha=commit,
            repository_url=repo_url,
            repo_slug=repo_slug,
            project_key=project_key,
            max_retries=max_retries,
        )
        run_scan_job.delay(job_doc["id"])
        queued += 1

    logger.info("Queued %d scan jobs for project %s", queued, project_id)
    return {"project_id": project_id, "queued": queued}
