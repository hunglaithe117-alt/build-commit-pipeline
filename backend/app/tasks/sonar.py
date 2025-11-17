from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from celery.utils.log import get_task_logger

from app.celery_app import celery_app
from app.core.config import settings
from app.models import ProjectStatus, ScanJobStatus
from app.services import repository
from pipeline.commit_replay import MissingForkCommitError
from pipeline.sonar import MetricsExporter, get_runner_for_instance, normalize_repo_url

logger = get_task_logger(__name__)


class PermanentScanError(Exception):
    """Raised when a scan failure should not be retried."""


def _safe_int(value: Optional[str | int]) -> int:
    try:
        return int(value) if value is not None else 0
    except (TypeError, ValueError):
        return 0


def _check_project_completion(project_id: str) -> None:
    project = repository.get_project(project_id)
    if not project:
        return
    total_commits = _safe_int(project.get("total_commits"))
    if not total_commits:
        return
    completed = (project.get("processed_commits") or 0) + (
        project.get("failed_commits") or 0
    )
    if completed >= total_commits:
        repository.update_project(project_id, status=ProjectStatus.finished.value)


def _record_failed_commit(
    job: Dict[str, Any],
    project: Optional[Dict[str, Any]],
    *,
    reason: str,
    error: str,
) -> None:
    project_id = (project or {}).get("id") or job.get("project_id")
    project_key = (project or {}).get("project_key") or job.get("project_key")
    payload = {
        "job_id": job["id"],
        "project_id": project_id,
        "project_key": project_key,
        "commit_sha": job.get("commit_sha"),
        "repository_url": job.get("repository_url"),
        "repo_slug": job.get("repo_slug"),
        "error": error,
    }
    existing = repository.get_failed_commit_by_job(job["id"])
    already_counted = (existing or {}).get("counted", True)
    should_increment = bool(project) and (existing is None or not already_counted)

    if existing:
        repository.update_failed_commit(
            existing["id"],
            payload=payload,
            status="pending",
            counted=True,
        )
    else:
        repository.insert_failed_commit(
            payload=payload,
            reason=reason,
        )

    if should_increment and project:
        repository.update_project(project["id"], failed_delta=1)


def _handle_scan_failure(
    task,
    job: Dict[str, Any],
    project: Dict[str, Any],
    exc: Exception,
    *,
    failure_reason: str = "scan-failed",
) -> str:
    now = datetime.utcnow()
    message = str(exc)
    permanent = isinstance(exc, PermanentScanError)
    status = (
        ScanJobStatus.failed_permanent.value
        if permanent
        else ScanJobStatus.failed_temp.value
    )
    updated = repository.update_scan_job(
        job["id"],
        status=status,
        last_error=message,
        retry_count_delta=1,
        last_finished_at=now,
    )
    retry_count = (updated or job).get("retry_count", 0)
    max_retries = job.get("max_retries") or settings.pipeline.default_retry_limit

    if permanent or retry_count >= max_retries:
        repository.update_scan_job(
            job["id"],
            status=ScanJobStatus.failed_permanent.value,
            last_error=message,
            last_finished_at=now,
        )
        _record_failed_commit(job, project, reason=failure_reason, error=message)
        _check_project_completion(project["id"])
        logger.error(
            "Scan job %s failed permanently after %s attempts: %s",
            job["id"],
            retry_count,
            message,
        )
        return job["id"]

    try:
        task.max_retries = max_retries
    except Exception:
        pass
    logger.warning(
        "Scan job %s failed temporarily (attempt %s/%s): %s",
        job["id"],
        retry_count,
        max_retries,
        message,
    )
    raise task.retry(exc=exc, countdown=0)


@celery_app.task(bind=True, max_retries=None)
def run_scan_job(self, scan_job_id: str) -> str:
    job = repository.get_scan_job(scan_job_id)
    if not job:
        raise ValueError(f"Scan job {scan_job_id} not found")
    if job.get("status") in {
        ScanJobStatus.success.value,
        ScanJobStatus.failed_permanent.value,
    }:
        return job["id"]

    worker_id = getattr(self.request, "hostname", "worker")
    claimed = repository.claim_scan_job(scan_job_id, worker_id)
    if not claimed:
        logger.info("Scan job %s is already being processed", scan_job_id)
        return job["id"]
    job = claimed

    project = repository.get_project(job["project_id"])
    if not project:
        repository.update_scan_job(
            job["id"],
            status=ScanJobStatus.failed_permanent.value,
            last_error="Project not found",
            last_finished_at=datetime.utcnow(),
        )
        _record_failed_commit(
            job,
            None,
            reason="project-missing",
            error="Project not found",
        )
        return job["id"]

    repo_url = normalize_repo_url(job.get("repository_url"), job.get("repo_slug"))
    sonar_config = (project.get("sonar_config") or {}).get("file_path")
    project_key = job.get("project_key") or project.get("project_key")
    runner = get_runner_for_instance(project_key)
    repository.update_scan_job(
        job["id"],
        sonar_instance=runner.instance.name,
    )

    override_text = job.get("config_override")
    if override_text:
        config_path = str(runner.ensure_override_config(override_text))
    else:
        config_path = sonar_config

    try:
        result = runner.scan_commit(
            repo_url=repo_url,
            commit_sha=job["commit_sha"],
            repo_slug=job.get("repo_slug"),
            config_path=config_path,
        )
    except MissingForkCommitError as exc:
        return _handle_scan_failure(
            self,
            job,
            project,
            PermanentScanError(str(exc)),
            failure_reason="missing-fork",
        )
    except Exception as exc:
        message = str(exc).lower()
        if "not found" in message and "commit" in message:
            exc = PermanentScanError(str(exc))
        return _handle_scan_failure(self, job, project, exc)

    repository.update_scan_job(
        job["id"],
        component_key=result.component_key,
        last_error=None,
        last_finished_at=datetime.utcnow(),
        s3_log_key=result.s3_log_key,
    )

    return result.component_key


@celery_app.task(bind=True, autoretry_for=(Exception,))
def export_metrics(
    self,
    component_key: str,
    *,
    job_id: str,
    project_id: str,
    analysis_id: Optional[str] = None,
    commit_sha: Optional[str] = None,
) -> Dict[str, str]:
    job = repository.get_scan_job(job_id)
    if not job:
        raise ValueError(f"Scan job {job_id} not found for export")
    project = repository.get_project(project_id)
    if not project:
        raise ValueError(f"Project {project_id} missing for export")

    instance = settings.sonarqube.get_instance(job.get("sonar_instance"))
    exporter = MetricsExporter.from_instance(instance)
    metrics = exporter.collect_metrics(component_key)
    if not metrics:
        raise RuntimeError(f"No metrics available for {component_key}")

    repository.upsert_scan_result(
        project_id=project_id,
        job_id=job_id,
        sonar_project_key=component_key,
        metrics=metrics,
    )

    repository.update_scan_job(
        job_id,
        status=ScanJobStatus.success.value,
        last_error=None,
        last_finished_at=datetime.utcnow(),
    )
    failed_record = repository.get_failed_commit_by_job(job_id)
    update_kwargs: Dict[str, Any] = {"processed_delta": 1}
    if failed_record and failed_record.get("counted", True):
        repository.update_failed_commit(
            failed_record["id"],
            status="resolved",
            resolved_at=datetime.utcnow(),
            counted=False,
        )
        update_kwargs["failed_delta"] = -1
    repository.update_project(project_id, **update_kwargs)
    _check_project_completion(project_id)
    logger.info(
        "Stored metrics for component %s (job=%s, project=%s)",
        component_key,
        job_id,
        project_id,
    )
    return metrics


@celery_app.task()
def reconcile_scan_jobs() -> dict:
    now = datetime.utcnow()
    stalled = repository.find_stalled_scan_jobs(
        running_stale_before=now - timedelta(minutes=15),
        pending_before=now - timedelta(minutes=30),
        limit=200,
    )
    requeued = 0
    for job in stalled:
        repository.update_scan_job(
            job["id"],
            status=ScanJobStatus.pending.value,
            last_worker_id=None,
        )
        run_scan_job.delay(job["id"])
        requeued += 1
    if requeued:
        logger.info("Requeued %d stalled scan jobs", requeued)
    return {"requeued": requeued}


@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(
        600.0, reconcile_scan_jobs.s(), name="requeue-stalled-scan-jobs"
    )
