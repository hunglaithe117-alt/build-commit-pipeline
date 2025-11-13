from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from app.models import OutputDataset
from app.services import repository

router = APIRouter()


@router.get("/")
async def list_outputs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=1000),
    sort_by: Optional[str] = Query(default=None),
    sort_dir: str = Query(default="desc"),
    filters: Optional[str] = Query(default=None),
) -> dict:

    parsed_filters = json.loads(filters) if filters else None
    result = await run_in_threadpool(
        repository.list_outputs_paginated,
        page,
        page_size,
        sort_by,
        sort_dir,
        parsed_filters,
    )
    return {
        "items": [OutputDataset(**doc) for doc in result["items"]],
        "total": result["total"],
    }


@router.get("/{output_id}/download")
async def download_output(output_id: str) -> FileResponse:
    record = await run_in_threadpool(repository.get_output, output_id)
    if not record:
        raise HTTPException(status_code=404, detail="Output not found")
    path = Path(record["path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Output file missing on disk")
    return FileResponse(path, filename=path.name)
