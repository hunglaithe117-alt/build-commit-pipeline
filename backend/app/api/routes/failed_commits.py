from __future__ import annotations

from typing import Optional
import json

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.models import FailedCommit, ScanJobStatus
from app.services import repository
from app.tasks.sonar import run_scan_job

router = APIRouter()


class FailedCommitUpdateRequest(BaseModel):
    config_override: str = Field(
        ..., description="sonar-project.properties content override"
    )
    config_source: Optional[str] = Field(default="text")


class FailedCommitRetryRequest(BaseModel):
    config_override: Optional[str] = None
    config_source: Optional[str] = None


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
