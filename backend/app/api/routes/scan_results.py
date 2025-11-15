from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from app.models import ScanResult
from app.services import repository

router = APIRouter()


@router.get("/")
async def list_scan_results(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=1000),
    sort_by: Optional[str] = Query(default=None),
    sort_dir: str = Query(default="desc"),
    filters: Optional[str] = Query(default=None),
) -> dict:

    parsed_filters = json.loads(filters) if filters else None
    result = await run_in_threadpool(
        repository.list_scan_results_paginated,
        page,
        page_size,
        sort_by,
        sort_dir,
        parsed_filters,
    )
    return {
        "items": [ScanResult(**doc) for doc in result["items"]],
        "total": result["total"],
    }


@router.get("/{result_id}", response_model=ScanResult)
async def get_scan_result(result_id: str) -> ScanResult:
    record = await run_in_threadpool(repository.get_scan_result, result_id)
    if not record:
        raise HTTPException(status_code=404, detail="Scan result not found")
    return ScanResult(**record)
