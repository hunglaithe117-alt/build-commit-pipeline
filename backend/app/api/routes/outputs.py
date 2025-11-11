from __future__ import annotations

from pathlib import Path
from typing import List

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from app.models import OutputDataset
from app.services import repository

router = APIRouter()


@router.get("/", response_model=List[OutputDataset])
async def list_outputs() -> List[OutputDataset]:
    data = await run_in_threadpool(repository.list_outputs)
    return [OutputDataset(**doc) for doc in data]


@router.get("/{output_id}/download")
async def download_output(output_id: str) -> FileResponse:
    record = await run_in_threadpool(repository.get_output, output_id)
    if not record:
        raise HTTPException(status_code=404, detail="Output not found")
    path = Path(record["path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Output file missing on disk")
    return FileResponse(path, filename=path.name)
