from __future__ import annotations

from pathlib import Path
from typing import List

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool

from app.models import DataSource
from app.pipeline.ingestion import CSVIngestionPipeline
from app.services import file_service, repository
from app.tasks.ingestion import ingest_data_source

router = APIRouter()


@router.get("/", response_model=List[DataSource])
async def list_data_sources() -> List[DataSource]:
    records = await run_in_threadpool(repository.list_data_sources)
    return [DataSource(**record) for record in records]


@router.post("/", response_model=DataSource)
async def upload_data_source(
    file: UploadFile = File(...),
    name: str = Query(..., description="Friendly name for the dataset"),
) -> DataSource:
    saved_path = await file_service.save_upload(file)
    pipeline = CSVIngestionPipeline(Path(saved_path))
    stats = await run_in_threadpool(pipeline.summarise)
    created = await run_in_threadpool(
        repository.create_data_source,
        name=name,
        filename=file.filename or Path(saved_path).name,
        file_path=str(saved_path),
        stats=stats,
    )
    return DataSource(**created)


@router.post("/{data_source_id}/collect")
async def trigger_collection(data_source_id: str) -> dict:
    record = await run_in_threadpool(repository.get_data_source, data_source_id)
    if not record:
        raise HTTPException(status_code=404, detail="Data source not found")
    ingest_data_source.delay(data_source_id)
    return {"status": "queued"}
