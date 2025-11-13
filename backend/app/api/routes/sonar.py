from __future__ import annotations

import hashlib
import hmac
import json
from typing import List, Optional

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from app.core.config import settings
from app.models import SonarRun
from app.services import repository
from app.tasks.sonar import export_metrics
import logging

router = APIRouter()
LOG = logging.getLogger("sonar_api")

@router.get("/runs", response_model=List[SonarRun])
async def list_runs() -> List[SonarRun]:
    runs = await run_in_threadpool(repository.list_sonar_runs)
    return [SonarRun(**run) for run in runs]


def _validate_signature(body: bytes, signature: Optional[str], token_header: Optional[str]) -> None:
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
    LOG.info("Received SonarQube webhook: %s", payload)
    component_key = payload.get("project", {}).get("key")
    if not component_key:
        raise HTTPException(status_code=400, detail="project key missing")

    sonar_run = await run_in_threadpool(
        repository.find_sonar_run_by_component, component_key
    )
    if not sonar_run:
        raise HTTPException(status_code=404, detail="Run not tracked")

    analysis_id = payload.get("analysis", {}).get("key") or payload.get("analysisId")
    status = payload.get("qualityGate", {}).get("status") or payload.get("status")
    status_normalised = (status or "").lower()

    await run_in_threadpool(
        repository.upsert_sonar_run,
        data_source_id=sonar_run["data_source_id"],
        project_key=sonar_run["project_key"],
        commit_sha=sonar_run.get("commit_sha"),
        job_id=sonar_run.get("job_id"),
        status=status or "unknown",
        analysis_id=analysis_id,
        component_key=component_key,
    )

    if status_normalised in {"ok", "success"}:
        export_metrics.delay(
            component_key,
            job_id=sonar_run.get("job_id"),
            data_source_id=sonar_run["data_source_id"],
            analysis_id=analysis_id,
        )
    return {"received": True}
