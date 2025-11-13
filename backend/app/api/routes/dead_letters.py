from __future__ import annotations

from typing import Optional
import json

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.models import DeadLetter
from app.services import repository
from app.tasks.sonar import run_commit_scan

router = APIRouter()


class DeadLetterUpdateRequest(BaseModel):
    config_override: str = Field(
        ..., description="sonar-project.properties content override"
    )
    config_source: Optional[str] = Field(default="text")


class DeadLetterRetryRequest(BaseModel):
    config_override: Optional[str] = None
    config_source: Optional[str] = None


@router.get("/")
async def list_dead_letters(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=1000),
    sort_by: Optional[str] = Query(default=None),
    sort_dir: str = Query(default="desc"),
    filters: Optional[str] = Query(default=None),
) -> dict:

    parsed_filters = json.loads(filters) if filters else None
    result = await run_in_threadpool(
        repository.list_dead_letters_paginated,
        page,
        page_size,
        sort_by,
        sort_dir,
        parsed_filters,
    )
    return {
        "items": [DeadLetter(**record) for record in result["items"]],
        "total": result["total"],
    }


@router.get("/{dead_letter_id}", response_model=DeadLetter)
async def get_dead_letter(dead_letter_id: str) -> DeadLetter:
    record = await run_in_threadpool(repository.get_dead_letter, dead_letter_id)
    if not record:
        raise HTTPException(status_code=404, detail="Dead letter not found")
    return DeadLetter(**record)


@router.put("/{dead_letter_id}", response_model=DeadLetter)
async def update_dead_letter(
    dead_letter_id: str, payload: DeadLetterUpdateRequest
) -> DeadLetter:
    updated = await run_in_threadpool(
        repository.update_dead_letter,
        dead_letter_id,
        config_override=payload.config_override,
        config_source=payload.config_source,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Dead letter not found")
    return DeadLetter(**updated)


@router.post("/{dead_letter_id}/retry", response_model=DeadLetter)
async def retry_dead_letter(
    dead_letter_id: str, payload: DeadLetterRetryRequest
) -> DeadLetter:
    record = await run_in_threadpool(repository.get_dead_letter, dead_letter_id)
    if not record:
        raise HTTPException(status_code=404, detail="Dead letter not found")

    stored_payload = record.get("payload") or {}
    commit = dict(stored_payload.get("commit") or {})
    job_id = stored_payload.get("job_id")
    data_source_id = stored_payload.get("data_source_id")

    if not job_id or not data_source_id or not commit:
        raise HTTPException(
            status_code=400,
            detail="Dead letter missing job, data source, or commit details",
        )

    config_override = payload.config_override or record.get("config_override")
    config_source = payload.config_source or record.get("config_source") or "text"
    if config_override:
        commit["config_override"] = config_override
        commit["config_source"] = config_source

    run_commit_scan.apply_async(
        args=(job_id, data_source_id, commit),
        queue="pipeline.scan",
        priority=9,
    )
    updated = await run_in_threadpool(
        repository.update_dead_letter,
        dead_letter_id,
        config_override=config_override,
        config_source=config_source if config_override else record.get("config_source"),
        status="queued",
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Failed to update dead letter")
    return DeadLetter(**updated)
