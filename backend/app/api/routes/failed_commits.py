from __future__ import annotations

from typing import Optional
import json
import os

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.models import FailedCommit, ScanJobStatus
from app.services import repository
from app.tasks.sonar import run_scan_job
from pipeline.github_fork_finder import GitHubForkFinder, GitHubRateLimitError
from pipeline.fork_commit_resolver import resolve_record

router = APIRouter()


class FailedCommitUpdateRequest(BaseModel):
    config_override: str = Field(
        ..., description="sonar-project.properties content override"
    )
    config_source: Optional[str] = Field(default="text")


class FailedCommitRetryRequest(BaseModel):
    config_override: Optional[str] = None
    config_source: Optional[str] = None


class ForkDiscoveryRequest(BaseModel):
    enqueue: bool = Field(default=False, description="Automatically requeue job if fork is found")
    force: bool = Field(
        default=False,
        description="Run discovery even if previous fork search data exists",
    )
    github_token: Optional[str] = Field(
        default=None,
        description="GitHub token override (defaults to server environment value)",
    )


@router.get("/")
async def list_failed_commits(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=1000),
    sort_by: Optional[str] = Query(default=None),
    sort_dir: str = Query(default="desc"),
    filters: Optional[str] = Query(default=None),
) -> dict:

    parsed_filters = json.loads(filters) if filters else None
    result = await run_in_threadpool(
        repository.list_failed_commits_paginated,
        page,
        page_size,
        sort_by,
        sort_dir,
        parsed_filters,
    )
    return {
        "items": [FailedCommit(**record) for record in result["items"]],
        "total": result["total"],
    }


@router.get("/{record_id}", response_model=FailedCommit)
async def get_failed_commit(record_id: str) -> FailedCommit:
    record = await run_in_threadpool(repository.get_failed_commit, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Failed commit not found")
    return FailedCommit(**record)


@router.put("/{record_id}", response_model=FailedCommit)
async def update_failed_commit(
    record_id: str, payload: FailedCommitUpdateRequest
) -> FailedCommit:
    updated = await run_in_threadpool(
        repository.update_failed_commit,
        record_id,
        config_override=payload.config_override,
        config_source=payload.config_source,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Failed commit not found")
    return FailedCommit(**updated)


@router.post("/{record_id}/retry", response_model=FailedCommit)
async def retry_failed_commit(
    record_id: str, payload: FailedCommitRetryRequest
) -> FailedCommit:
    record = await run_in_threadpool(repository.get_failed_commit, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Failed commit not found")

    stored_payload = record.get("payload") or {}
    job_id = stored_payload.get("job_id")
    project_id = stored_payload.get("project_id")

    if not job_id or not project_id:
        raise HTTPException(
            status_code=400,
            detail="Failed commit record missing job or project details",
        )

    config_override = payload.config_override or record.get("config_override")
    config_source = payload.config_source or record.get("config_source") or "text"

    await run_in_threadpool(
        repository.update_scan_job,
        job_id,
        config_override=config_override,
        config_source=config_source if config_override else None,
        last_error=None,
        status=ScanJobStatus.pending.value,
        retry_count_delta=1,
        retry_count=None,
    )

    run_scan_job.delay(job_id)
    updated = await run_in_threadpool(
        repository.update_failed_commit,
        record_id,
        config_override=config_override,
        config_source=config_source if config_override else record.get("config_source"),
        status="queued",
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Failed to update record")
    return FailedCommit(**updated)


@router.post("/{record_id}/discover", response_model=FailedCommit)
async def discover_failed_commit(
    record_id: str, payload: ForkDiscoveryRequest
) -> FailedCommit:
    record = await run_in_threadpool(repository.get_failed_commit, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Failed commit not found")
    if record.get("fork_search") and not payload.force:
        raise HTTPException(
            status_code=400,
            detail="Fork search already recorded for this commit. Set force=true to rerun.",
        )

    github_token = payload.github_token or os.getenv("GITHUB_TOKEN")
    fork_pages = int(os.getenv("GITHUB_FORK_PAGES", "5") or "5")
    finder = GitHubForkFinder(token=github_token, max_pages=fork_pages)
    task_runner_cache = [None]

    def _run():
        _, updated = resolve_record(
            record,
            finder,
            enqueue=payload.enqueue,
            dry_run=False,
            task_runner_cache=task_runner_cache,
        )
        return updated

    try:
        updated_record = await run_in_threadpool(_run)
    except GitHubRateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        finder.close()

    if not updated_record:
        updated_record = await run_in_threadpool(repository.get_failed_commit, record_id)
    return FailedCommit(**updated_record)
