from __future__ import annotations

from pathlib import Path

from celery.utils.log import get_task_logger

from app.celery_app import celery_app
from app.core.config import settings
import pandas as pd

from pipeline.ingestion import CSVIngestionPipeline
from pipeline.sonar import normalize_repo_url
from app.services import repository
from app.tasks.sonar import run_commit_scan

logger = get_task_logger(__name__)


@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
)
def ingest_data_source(self, data_source_id: str) -> dict:
    data_source = repository.get_data_source(data_source_id)
    if not data_source:
        raise ValueError(f"Data source {data_source_id} not found")

    repository.update_data_source(data_source_id, status="processing")
    csv_path = Path(data_source["file_path"])
    pipeline = CSVIngestionPipeline(csv_path)
    summary = pipeline.summarise()
    repository.update_data_source(data_source_id, stats=summary)
    # Use pandas to load and deduplicate commits by (project_key, commit_sha)
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

    total = int(len(df_unique))
    job = repository.create_job(
        data_source_id=data_source_id,
        job_type="ingestion",
        total=total,
        status="running" if total else "succeeded",
    )

    if total == 0:
        repository.update_data_source(data_source_id, status="ready")
        return {"job_id": job["id"], "queued": 0}

    repository.update_job(job["id"], status="running")

    queued = 0

    for _, row in df_unique.iterrows():
        project_key = row["project_key"]
        commit = row["commit"]
        repo_slug = row["repo_slug"] or None
        repo_url = row.get("repository_url") or None
        if not repo_url and repo_slug:
            repo_url = f"https://github.com/{repo_slug}.git"

        payload = {
            "project_key": project_key,
            "repo_slug": repo_slug,
            "repository_url": repo_url,
            "commit_sha": commit,
        }
        payload["repo_url"] = normalize_repo_url(
            payload.get("repository_url"), payload.get("repo_slug")
        )

        run_commit_scan.delay(job["id"], data_source_id, payload)
        queued += 1

    logger.info("Queued %d commits for job %s", queued, job["id"])
    return {"job_id": job["id"], "queued": queued}
