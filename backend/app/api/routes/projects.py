from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional
import csv
import io
import json

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from app.models import Project
from pipeline.ingestion import CSVIngestionPipeline
from app.services import file_service, repository
from app.tasks.ingestion import ingest_project

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
        "filename": upload.filename or "sonar.properties",
        "file_path": str(saved_path),
        "updated_at": datetime.utcnow(),
    }


@router.get("/")
async def list_projects(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=1000),
    sort_by: Optional[str] = Query(default=None),
    sort_dir: str = Query(default="desc"),
    filters: Optional[str] = Query(default=None),
) -> dict:

    parsed_filters = json.loads(filters) if filters else None
    result = await run_in_threadpool(
        repository.list_projects_paginated,
        page,
        page_size,
        sort_by,
        sort_dir,
        parsed_filters,
    )
    return {
        "items": [Project(**record) for record in result["items"]],
        "total": result["total"],
    }


@router.get("/{project_id}", response_model=Project)
async def get_project(project_id: str) -> Project:
    record = await run_in_threadpool(repository.get_project, project_id)
    if not record:
        raise HTTPException(status_code=404, detail="Project not found")
    return Project(**record)


@router.post("/", response_model=Project)
async def upload_project(
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
) -> Project:
    name = name_form or name_query
    if not name:
        raise HTTPException(status_code=400, detail="Project name is required.")
    saved_path = await file_service.save_upload(file)
    pipeline = CSVIngestionPipeline(Path(saved_path))
    stats = await run_in_threadpool(pipeline.summarise)
    sonar_config = _build_sonar_config(
        sonar_config_file, repo_key=stats.get("project_key") or name
    )
    project_key = stats.get("project_key") or Path(saved_path).stem
    created = await run_in_threadpool(
        repository.create_project,
        project_name=name,
        project_key=project_key,
        total_builds=stats.get("total_builds", 0),
        total_commits=stats.get("total_commits", 0),
        source_filename=file.filename or Path(saved_path).name,
        source_path=str(saved_path),
        sonar_config=sonar_config,
    )
    return Project(**created)


@router.post("/{project_id}/collect")
async def trigger_collection(project_id: str) -> dict:
    record = await run_in_threadpool(repository.get_project, project_id)
    if not record:
        raise HTTPException(status_code=404, detail="Project not found")
    ingest_project.delay(project_id)
    return {"status": "queued"}


@router.post("/{project_id}/config", response_model=Project)
async def update_sonar_config(
    project_id: str, config_file: UploadFile = File(...)
) -> Project:
    record = await run_in_threadpool(repository.get_project, project_id)
    if not record:
        raise HTTPException(status_code=404, detail="Project not found")
    repo_key = record.get("project_key") or record.get("project_name")
    sonar_config = _build_sonar_config(
        config_file,
        repo_key,
        record.get("sonar_config"),
    )
    updated = await run_in_threadpool(
        repository.update_project, project_id, sonar_config=sonar_config
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Failed to update config")
    return Project(**updated)


@router.get("/{project_id}/results/export")
async def download_project_results(project_id: str) -> StreamingResponse:
    project = await run_in_threadpool(repository.get_project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    results = await run_in_threadpool(
        repository.list_scan_results_by_project, project_id
    )
    if not results:
        raise HTTPException(status_code=404, detail="No scan results for project")

    metric_keys = sorted(
        {key for item in results for key in (item.get("metrics") or {}).keys()}
    )
    headers = [
        "sonar_project_key",
        "job_id",
        "created_at",
        *metric_keys,
    ]

    async def row_generator():
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(headers)
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)

        for item in results:
            metrics = item.get("metrics") or {}
            row = [
                item.get("sonar_project_key"),
                item.get("job_id"),
                (
                    item.get("created_at").isoformat()
                    if hasattr(item.get("created_at"), "isoformat")
                    else item.get("created_at")
                ),
            ]
            row.extend([metrics.get(key, "") for key in metric_keys])
            writer.writerow(row)

            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate(0)

    filename = f"{project.get('project_key') or project_id}_scan_results.csv"

    return StreamingResponse(
        row_generator(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
