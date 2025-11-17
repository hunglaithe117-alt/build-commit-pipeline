from __future__ import annotations

import os
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.models import ScanJobStatus
from app.services import repository
from app.tasks.sonar import run_scan_job
from pipeline.github_fork_finder import (
    GitHubForkFinder,
    GitHubRateLimitError,
    resolve_github_token_pool,
)

router = APIRouter()


class ForkResolverRepo(BaseModel):
    repo_slug: str
    count: int
    commit_shas: List[str]
    record_ids: List[str]
    updated_at: Optional[str] = None


class ForkResolverDiscoverRequest(BaseModel):
    enqueue: bool = Field(default=False)
    force: bool = Field(
        default=False,
        description="Run fork discovery even if fork_search already exists on the record.",
    )
    github_token: Optional[str] = Field(
        default=None, description="Override token list for this request."
    )


@router.get("/repos", response_model=List[ForkResolverRepo])
async def list_missing_fork_repos(limit: int = 100) -> List[ForkResolverRepo]:
    items = await run_in_threadpool(repository.aggregate_missing_forks, limit=limit)
    return [ForkResolverRepo(**item) for item in items]


@router.post("/repos/{repo_slug}/discover", response_model=List[ForkResolverRepo])
async def discover_repo_forks(
    repo_slug: str, payload: ForkResolverDiscoverRequest
) -> List[ForkResolverRepo]:
    records = await run_in_threadpool(
        repository.list_failed_commits_by_repo, repo_slug, reason="missing-fork"
    )
    if not records:
        raise HTTPException(status_code=404, detail="No failed commits for repo slug.")

    target_records = [
        record for record in records if payload.force or not record.get("fork_search")
    ]
    if not target_records:
        raise HTTPException(
            status_code=400,
            detail="All failed commits already have fork search data. Set force=true to reprocess.",
        )

    fork_pages = int(os.getenv("GITHUB_FORK_PAGES", "5") or "5")
    token_pool, fallback_token = resolve_github_token_pool(payload.github_token)
    finder = GitHubForkFinder(
        tokens=token_pool or None,
        token=fallback_token,
        max_pages=fork_pages,
    )

    def _run():
        commit_map = {
            record["id"]: record.get("payload", {}).get("commit_sha")
            for record in target_records
        }
        commit_shas = [sha for sha in commit_map.values() if sha]
        matches = finder.find_commits_across_forks(repo_slug, commit_shas)
        now = datetime.utcnow()
        refreshed_records: List[ForkResolverRepo] = []
        for record in target_records:
            payload_data = {**(record.get("payload") or {})}
            commit_sha = payload_data.get("commit_sha")
            match_slug = matches.get(commit_sha)
            fork_url = None
            status = "found" if match_slug else "not_found"
            search_payload = {
                "status": status,
                "checked_at": now,
                "fork_full_name": match_slug,
                "fork_clone_url": None,
                "message": None,
            }
            if match_slug:
                fork_url = f"https://github.com/{match_slug}.git"
                search_payload["fork_clone_url"] = fork_url
                payload_data["fork_repo_slug"] = match_slug
                payload_data["fork_repo_url"] = fork_url
            update_kwargs = {
                "payload": payload_data,
                "fork_search": search_payload,
            }
            job_id = payload_data.get("job_id")
            if match_slug and payload.enqueue:
                update_kwargs["status"] = "queued"
            repository.update_failed_commit(record["id"], **update_kwargs)
            if match_slug and job_id:
                repository.update_scan_job(
                    job_id,
                    fork_repo_slug=match_slug,
                    fork_repo_url=fork_url,
                )
                if payload.enqueue:
                    repository.update_scan_job(
                        job_id,
                        status=ScanJobStatus.pending.value,
                        last_error=None,
                        retry_count_delta=1,
                        retry_count=None,
                    )
                    run_scan_job.delay(job_id)
        refreshed = repository.aggregate_missing_forks(limit=200)
        refreshed_records = [ForkResolverRepo(**item).model_dump() for item in refreshed]
        return refreshed_records

    try:
        return await run_in_threadpool(_run)
    except GitHubRateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    finally:
        finder.close()
