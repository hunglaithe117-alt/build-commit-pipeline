from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.concurrency import run_in_threadpool

from app.celery_app import celery_app
from app.core.config import settings
from app.models import Job
from app.services import repository

router = APIRouter()


@router.get("/")
async def list_jobs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=1000),
    sort_by: Optional[str] = Query(default=None),
    sort_dir: str = Query(default="desc"),
    filters: Optional[str] = Query(default=None),
) -> dict:

    parsed_filters = json.loads(filters) if filters else None
    result = await run_in_threadpool(
        repository.list_jobs_paginated,
        page,
        page_size,
        sort_by,
        sort_dir,
        parsed_filters,
    )
    
    # Add failed_count for each job
    items_with_failed = []
    for job in result["items"]:
        job_dict = dict(job)
        # Count dead letters for this job
        failed_count = await run_in_threadpool(
            repository.count_dead_letters_by_job,
            job_dict["id"]
        )
        job_dict["failed_count"] = failed_count
        items_with_failed.append(Job(**job_dict))
    
    return {"items": items_with_failed, "total": result["total"]}


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
        
        # Calculate total workers and concurrency
        total_workers = len(stats)
        max_concurrency = settings.pipeline.sonar_parallelism
        
        # Process active tasks to get worker details
        workers = []
        for worker_name, tasks in active_tasks.items():
            worker_info = {
                "name": worker_name,
                "active_tasks": len(tasks),
                "max_concurrency": max_concurrency,
                "tasks": []
            }
            
            for task in tasks:
                task_args = task.get("args", [])
                task_kwargs = task.get("kwargs", {})
                
                # Extract commit and repo info from task arguments
                current_commit = None
                current_repo = None
                
                if task.get("name") == "app.tasks.sonar.run_commit_scan":
                    # Arguments: job_id, data_source_id, commit (dict)
                    if len(task_args) >= 3:
                        commit_data = task_args[2]
                        if isinstance(commit_data, dict):
                            current_commit = commit_data.get("commit_sha")
                            current_repo = commit_data.get("repo_url") or commit_data.get("project_key")
                    elif "commit" in task_kwargs:
                        commit_data = task_kwargs["commit"]
                        if isinstance(commit_data, dict):
                            current_commit = commit_data.get("commit_sha")
                            current_repo = commit_data.get("repo_url") or commit_data.get("project_key")
                
                worker_info["tasks"].append({
                    "id": task.get("id"),
                    "name": task.get("name"),
                    "current_commit": current_commit,
                    "current_repo": current_repo,
                })
            
            workers.append(worker_info)
        
        # Count total active scan tasks
        total_active_scans = sum(
            len([t for t in tasks if t.get("name") == "app.tasks.sonar.run_commit_scan"])
            for tasks in active_tasks.values()
        )
        
        # Count reserved scan tasks
        total_reserved_scans = sum(
            len([t for t in tasks if t.get("name") == "app.tasks.sonar.run_commit_scan"])
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
