from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from app.celery_app import celery_app
from app.core.config import settings
from app.models import ScanJob, ScanJobStatus
from app.services import repository
from app.tasks.sonar import run_scan_job

router = APIRouter()


class RetryScanJobRequest(BaseModel):
    config_override: Optional[str] = None
    config_source: Optional[str] = None


@router.get("/")
async def list_scan_jobs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=1000),
    sort_by: Optional[str] = Query(default=None),
    sort_dir: str = Query(default="desc"),
    filters: Optional[str] = Query(default=None),
) -> dict:

    parsed_filters = json.loads(filters) if filters else None
    result = await run_in_threadpool(
        repository.list_scan_jobs_paginated,
        page,
        page_size,
        sort_by,
        sort_dir,
        parsed_filters,
    )
    return {"items": [ScanJob(**job) for job in result["items"]], "total": result["total"]}


@router.post("/{job_id}/retry", response_model=ScanJob)
async def retry_scan_job(job_id: str, payload: RetryScanJobRequest) -> ScanJob:
    job = await run_in_threadpool(repository.get_scan_job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Scan job not found")

    update_kwargs = {}
    if payload.config_override is not None:
        update_kwargs["config_override"] = payload.config_override
        update_kwargs["config_source"] = (
            payload.config_source or job.get("config_source") or "text"
        )

    updated = await run_in_threadpool(
        repository.update_scan_job,
        job_id,
        status=ScanJobStatus.pending.value,
        last_error=None,
        last_worker_id=None,
        **update_kwargs,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Failed to update scan job")

    run_scan_job.delay(job_id)
    return ScanJob(**updated)


@router.get("/workers-stats")
async def get_workers_stats() -> dict:
    try:
        # Get active workers
        inspect = celery_app.control.inspect()
        active_tasks = inspect.active() or {}

        # Get reserved tasks (queued but not yet running)
        reserved_tasks = inspect.reserved() or {}

        # Get worker stats
        stats = inspect.stats() or {}

        # Calculate total workers and concurrency for the scan queue.
        total_workers = 0
        max_concurrency = 0

        try:
            active_queues = inspect.active_queues() or {}
        except Exception:
            active_queues = {}

        # Helper to extract concurrency from stats for a worker
        def _extract_concurrency(worker_stats: dict) -> int:
            if not isinstance(worker_stats, dict):
                return 0
            pool = worker_stats.get("pool") or {}
            # Try multiple possible keys that may appear depending on pool impl
            for key in (
                "max-concurrency",
                "max_concurrency",
                "processes",
                "maxchildren",
                "max_children",
            ):
                val = pool.get(key) if isinstance(pool, dict) else None
                if isinstance(val, int) and val > 0:
                    return val
                try:
                    if val is not None:
                        ival = int(val)
                        if ival > 0:
                            return ival
                except Exception:
                    pass
            # fallback: some stats expose 'pool' as a string
            try:
                return int(
                    worker_stats.get("max-concurrency")
                    or worker_stats.get("max_concurrency")
                    or 0
                )
            except Exception:
                return 0

        # Sum concurrency for workers that listen on pipeline.scan. If active_queues
        # information isn't available, fall back to summing all workers.
        scan_queue_name = "pipeline.scan"
        scan_worker_concurrency: dict = {}
        for worker_name, wstats in stats.items():
            queues = []
            try:
                qinfo = active_queues.get(worker_name) or []
                queues = [q.get("name") for q in qinfo if isinstance(q, dict)]
            except Exception:
                queues = []

            concurrency = _extract_concurrency(wstats)
            if queues:
                if scan_queue_name in queues:
                    max_concurrency += concurrency
                    scan_worker_concurrency[worker_name] = concurrency
            else:
                # No queue info: include the worker conservatively
                max_concurrency += concurrency
                scan_worker_concurrency[worker_name] = concurrency

        total_workers = (
            len(scan_worker_concurrency) if scan_worker_concurrency else len(stats)
        )

        # Process active tasks to get worker details (only include scan workers)
        workers = []
        for worker_name, tasks in active_tasks.items():
            # Only include workers that are consuming pipeline.scan
            if scan_worker_concurrency and worker_name not in scan_worker_concurrency:
                continue
            worker_max = scan_worker_concurrency.get(worker_name, 0) or 0
            worker_info = {
                "name": worker_name,
                "active_tasks": len(tasks),
                "max_concurrency": worker_max,
                "tasks": [],
            }

            for task in tasks:
                task_args = task.get("args", [])
                task_kwargs = task.get("kwargs", {})

                # Extract commit and repo info from task arguments
                current_commit = None
                current_repo = None

                if task.get("name") == "app.tasks.sonar.run_scan_job":
                    # Arguments: scan_job_id
                    if task_args:
                        current_commit = task_args[0]
                    elif "scan_job_id" in task_kwargs:
                        current_commit = task_kwargs["scan_job_id"]

                worker_info["tasks"].append(
                    {
                        "id": task.get("id"),
                        "name": task.get("name"),
                        "current_commit": current_commit,
                        "current_repo": current_repo,
                    }
                )

            workers.append(worker_info)

        # Count total active scan tasks
        total_active_scans = sum(
            len([t for t in tasks if t.get("name") == "app.tasks.sonar.run_scan_job"])
            for tasks in active_tasks.values()
        )

        # Count reserved scan tasks
        total_reserved_scans = sum(
            len([t for t in tasks if t.get("name") == "app.tasks.sonar.run_scan_job"])
            for tasks in reserved_tasks.values()
        )

        return {
            "total_workers": total_workers,
            "max_concurrency": max_concurrency,
            "active_scan_tasks": total_active_scans,
            "queued_scan_tasks": total_reserved_scans,
            "workers": workers,
        }
    except Exception as e:
        # If workers are not available, return empty stats
        return {
            "total_workers": 0,
            "max_concurrency": settings.pipeline.sonar_parallelism,
            "active_scan_tasks": 0,
            "queued_scan_tasks": 0,
            "workers": [],
            "error": str(e),
        }
