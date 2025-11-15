from __future__ import annotations

import hashlib
import hmac
import json
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request, Query
from fastapi.concurrency import run_in_threadpool

from app.core.config import settings
from app.models import ScanJobStatus, ScanResult
from app.services import repository
from app.tasks.sonar import export_metrics
import logging

router = APIRouter()
LOG = logging.getLogger("sonar_api")


@router.get("/runs")
async def list_runs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=1000),
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
        "items": [ScanResult(**run) for run in result["items"]],
        "total": result["total"],
    }


def _validate_signature(
    body: bytes, signature: Optional[str], token_header: Optional[str]
) -> None:
    secret = settings.sonarqube.webhook_secret
    if token_header:
        if token_header != secret:
            raise HTTPException(status_code=401, detail="Invalid webhook secret")
        return
    if signature:
        computed = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(computed, signature):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
    else:
        raise HTTPException(status_code=401, detail="Webhook secret missing")


@router.post("/webhook")
async def sonar_webhook(
    request: Request,
    x_sonar_webhook_hmac_sha256: Optional[str] = Header(default=None),
    x_sonar_secret: Optional[str] = Header(default=None),
) -> dict:
    body = await request.body()
    _validate_signature(body, x_sonar_webhook_hmac_sha256, x_sonar_secret)
    payload = json.loads(body.decode("utf-8") or "{}")
    LOG.debug("Received SonarQube webhook: %s", payload)
    component_key = payload.get("project", {}).get("key")
    if not component_key:
        raise HTTPException(status_code=400, detail="project key missing")

    scan_job = await run_in_threadpool(
        repository.find_scan_job_by_component, component_key
    )
    if not scan_job:
        raise HTTPException(status_code=404, detail="Scan job not tracked")

    await run_in_threadpool(
        repository.update_scan_job,
        scan_job["id"],
        status=ScanJobStatus.running.value,
    )

    export_metrics.delay(
        component_key,
        job_id=scan_job["id"],
        project_id=scan_job["project_id"],
        commit_sha=scan_job.get("commit_sha"),
    )
    return {"received": True}
