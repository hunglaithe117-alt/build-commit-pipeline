from __future__ import annotations

from pathlib import Path
from typing import Optional

from celery.utils.log import get_task_logger

from app.celery_app import celery_app
from app.core.config import settings
import pandas as pd

from pipeline.ingestion import CSVIngestionPipeline
from pipeline.sonar import normalize_repo_url
from app.services import repository
from app.tasks.sonar import run_commit_scan
import requests
from urllib.parse import urlparse

logger = get_task_logger(__name__)


@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
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

    def _extract_slug_from_url(url: str) -> Optional[str]:
        try:
            if url.startswith("git@"):
                # git@github.com:owner/repo.git
                parts = url.split(":", 1)
                if len(parts) == 2:
                    slug = parts[1]
                else:
                    return None
            else:
                parsed = urlparse(url)
                slug = parsed.path.lstrip("/")
            if slug.endswith(".git"):
                slug = slug[: -len(".git")]
            return slug or None
        except Exception:
            return None

    def _github_repo_exists(slug: Optional[str]) -> bool:
        if not slug:
            return False
        api_url = f"https://api.github.com/repos/{slug}"
        try:
            resp = requests.get(api_url, timeout=10)
            return resp.status_code == 200
        except Exception:
            return False

    slugs_to_check: set[str] = set()
    row_payloads: list[dict] = []
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

        slug_to_check = payload.get("repo_slug") or _extract_slug_from_url(
            payload.get("repository_url") or ""
        )
        if slug_to_check:
            slugs_to_check.add(slug_to_check)

        row_payloads.append((payload, slug_to_check, commit))

    exists_map: dict[str, bool] = {}
    for slug in slugs_to_check:
        exists_map[slug] = _github_repo_exists(slug)

    # Queue each unique row using the precomputed existence map
    for payload, slug_to_check, commit in row_payloads:
        if slug_to_check and exists_map.get(slug_to_check):
            run_commit_scan.delay(job["id"], data_source_id, payload)
            queued += 1
        else:
            logger.info(
                "Skipping commit %s for repo %s: GitHub repository not found",
                commit,
                slug_to_check or payload.get("repository_url"),
            )

    logger.info("Queued %d commits for job %s", queued, job["id"])
    return {"job_id": job["id"], "queued": queued}
