from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import json

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool

from app.models import DataSource
from pipeline.ingestion import CSVIngestionPipeline
from app.services import file_service, repository
from app.tasks.ingestion import ingest_data_source

router = APIRouter()


def _build_sonar_config(
    upload: Optional[UploadFile],
    repo_key: Optional[str],
    existing: Optional[dict] = None,
) -> Optional[dict]:
    if upload is None:
        return existing
    saved_path = file_service.save_config_upload(
        upload,
        repo_key=repo_key,
        existing_path=existing.get("file_path") if existing else None,
    )
    return {
        "content": "",
        "source": "upload",
        "filename": upload.filename,
        "file_path": str(saved_path),
        "updated_at": datetime.utcnow(),
    }


@router.get("/")
async def list_data_sources(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=1000),
    sort_by: Optional[str] = Query(default=None),
    sort_dir: str = Query(default="desc"),
    filters: Optional[str] = Query(default=None),
) -> dict:

    parsed_filters = json.loads(filters) if filters else None
    result = await run_in_threadpool(
        repository.list_data_sources_paginated,
        page,
        page_size,
        sort_by,
        sort_dir,
        parsed_filters,
    )
    return {
        "items": [DataSource(**record) for record in result["items"]],
        "total": result["total"],
    }


@router.get("/{data_source_id}", response_model=DataSource)
async def get_data_source(data_source_id: str) -> DataSource:
    record = await run_in_threadpool(repository.get_data_source, data_source_id)
    if not record:
        raise HTTPException(status_code=404, detail="Data source not found")
    return DataSource(**record)


@router.post("/", response_model=DataSource)
async def upload_data_source(
    file: UploadFile = File(...),
    name_form: Optional[str] = Form(
        default=None, description="Friendly name for the dataset"
    ),
    name_query: Optional[str] = Query(
        default=None, description="Friendly name for the dataset"
    ),
    sonar_config_file: Optional[UploadFile] = File(
        default=None, description="Optional sonar.properties file for this dataset"
    ),
) -> DataSource:
    name = name_form or name_query
    if not name:
        raise HTTPException(status_code=400, detail="Dataset name is required.")
    saved_path = await file_service.save_upload(file)
    pipeline = CSVIngestionPipeline(Path(saved_path))
    stats = await run_in_threadpool(pipeline.summarise)
    sonar_config = _build_sonar_config(sonar_config_file, repo_key=name or "dataset")
    created = await run_in_threadpool(
        repository.create_data_source,
        name=name,
        filename=file.filename or Path(saved_path).name,
        file_path=str(saved_path),
        stats=stats,
        sonar_config=sonar_config,
    )
    return DataSource(**created)


@router.post("/{data_source_id}/collect")
async def trigger_collection(data_source_id: str) -> dict:
    record = await run_in_threadpool(repository.get_data_source, data_source_id)
    if not record:
        raise HTTPException(status_code=404, detail="Data source not found")
    ingest_data_source.delay(data_source_id)
    return {"status": "queued"}


@router.post("/{data_source_id}/config", response_model=DataSource)
async def update_sonar_config(
    data_source_id: str, config_file: UploadFile = File(...)
) -> DataSource:
    record = await run_in_threadpool(repository.get_data_source, data_source_id)
    if not record:
        raise HTTPException(status_code=404, detail="Data source not found")
    repo_key = record.get("stats", {}).get("project_key") or record.get("name")
    sonar_config = _build_sonar_config(
        config_file,
        repo_key,
        record.get("sonar_config"),
    )
    updated = await run_in_threadpool(
        repository.update_data_source, data_source_id, sonar_config=sonar_config
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Failed to update config")
    return DataSource(**updated)
