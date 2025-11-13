from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Tuple

from celery.utils.log import get_task_logger

from app.celery_app import celery_app
from app.core.config import settings
from pipeline.sonar import MetricsExporter, get_runner_for_instance
from app.services import repository

logger = get_task_logger(__name__)


def _sanitize_segment(value: Optional[str], fallback: str) -> str:
    candidate = (value or "").strip() or fallback
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in candidate)


def _build_metrics_destination(
    project_key: Optional[str], job_id: Optional[str], data_source_id: Optional[str]
) -> Path:
    project_part = _sanitize_segment(project_key, "project")
    job_part = _sanitize_segment(job_id, "ad-hoc")
    data_source_part = _sanitize_segment(data_source_id, "unknown")
    return (
        Path(settings.paths.exports)
        / project_part
        / data_source_part
        / f"{job_part}_metrics.csv"
    )


def process_commit(
    job_id: str,
    data_source_id: str,
    commit: Dict[str, str],
    runner,
    config_path: Optional[str] = None,
) -> Tuple[str, bool]:
    commit_sha = commit.get("commit_sha")
    project_key = commit.get("project_key")
    repo_url = commit.get("repo_url")
    if not all([commit_sha, project_key, repo_url]):
        raise ValueError("Commit payload missing mandatory fields.")

    instance = runner.instance
    component_key = f"{project_key}_{commit_sha}"
    repository.update_job(job_id, status="running", current_commit=commit_sha)
    repository.upsert_sonar_run(
        data_source_id=data_source_id,
        project_key=project_key,
        commit_sha=commit_sha,
        job_id=job_id,
        status="running",
        component_key=component_key,
        sonar_instance=instance.name,
        sonar_host=instance.host,
    )
    try:
        result = runner.scan_commit(
            repo_url=repo_url,
            commit_sha=commit_sha,
            repo_slug=commit.get("repo_slug"),
            config_path=config_path,
        )
    except Exception as exc:
        message = str(exc)
        repository.upsert_sonar_run(
            data_source_id=data_source_id,
            project_key=project_key,
            commit_sha=commit_sha,
            job_id=job_id,
            status="failed",
            message=message,
            sonar_instance=instance.name,
            sonar_host=instance.host,
        )
        repository.update_job(
            job_id,
            status="failed",
            last_error=message,
            current_commit=None,
        )
        repository.update_data_source(data_source_id, status="failed")
        repository.insert_dead_letter(
            payload={
                "job_id": job_id,
                "data_source_id": data_source_id,
                "commit": commit,
                "error": message,
            },
            reason="sonar-commit",
        )
        logger.exception("Commit %s failed", commit_sha)
        raise

    if result.skipped:
        repository.upsert_sonar_run(
            data_source_id=data_source_id,
            project_key=project_key,
            commit_sha=commit_sha,
            job_id=job_id,
            status="skipped",
            log_path=str(result.log_path),
            message=result.output,
            component_key=result.component_key,
            sonar_instance=result.instance_name,
            sonar_host=instance.host,
        )
        try:
            export_metrics.delay(result.component_key, job_id, data_source_id)
            logger.info(
                "Queued export_metrics for existing component %s (job=%s, data_source=%s)",
                result.component_key,
                job_id,
                data_source_id,
            )
        except Exception:
            logger.exception(
                "Failed to enqueue export_metrics for component %s",
                result.component_key,
            )
    else:
        repository.upsert_sonar_run(
            data_source_id=data_source_id,
            project_key=project_key,
            commit_sha=commit_sha,
            job_id=job_id,
            status="submitted",
            log_path=str(result.log_path),
            component_key=result.component_key,
            sonar_instance=result.instance_name,
            sonar_host=instance.host,
        )

    updated_job = repository.update_job(
        job_id,
        processed_delta=1,
        current_commit=None,
    )
    job_finished = bool(
        updated_job and updated_job.get("processed", 0) >= updated_job.get("total", 0)
    )
    if job_finished:
        repository.update_job(job_id, status="succeeded")
        repository.update_data_source(data_source_id, status="ready")

    logger.info(
        "Processed commit %s on %s (component %s)",
        commit_sha,
        instance.name,
        result.component_key,
    )
    return result.component_key, job_finished


@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def run_commit_scan(
    self, job_id: str, data_source_id: str, commit: Dict[str, str]
) -> str:
    """Run SonarQube scan for a single commit."""
    project_key = commit.get("project_key")
    commit_sha = commit.get("commit_sha")

    if not project_key:
        raise ValueError("Commit payload missing project_key")

    instance = settings.sonarqube.get_instance()
    runner = get_runner_for_instance(project_key, instance.name)
    repository.update_job(job_id, sonar_instance=instance.name)

    data_source = repository.get_data_source(data_source_id)
    default_config_path = None
    if data_source:
        default_config_path = (data_source.get("sonar_config") or {}).get("file_path")

    override_text = commit.get("config_override")
    if override_text:
        config_path = runner.ensure_override_config(override_text)
    else:
        config_path = default_config_path

    logger.info(
        f"Processing commit '{commit_sha}' on instance '{instance.name}' (job '{job_id}')"
    )

    component_key, job_finished = process_commit(
        job_id,
        data_source_id,
        commit,
        runner,
        config_path=config_path,
    )

    logger.info(
        f"Successfully processed commit '{commit_sha}' on instance '{instance.name}' "
        f"(component: {component_key}, job_finished: {job_finished})"
    )

    return component_key


@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def export_metrics(
    self,
    component_key: str,
    job_id: Optional[str] = None,
    data_source_id: Optional[str] = None,
    analysis_id: Optional[str] = None,
) -> str:
    run_doc = repository.find_sonar_run_by_component(component_key)
    logger.info(
        "Exporting metrics for component_key=%s, run_doc=%s", component_key, run_doc
    )
    if run_doc:
        instance = settings.sonarqube.get_instance(run_doc.get("sonar_instance"))
        target_job_id = job_id or run_doc.get("job_id") or "ad-hoc"
        target_ds = data_source_id or run_doc.get("data_source_id")
        project_key = run_doc.get("project_key", "unknown")
        commit_sha = run_doc.get("commit_sha")
    else:
        instance = settings.sonarqube.get_instance()
        target_job_id = job_id or "ad-hoc"
        target_ds = data_source_id
        parts = component_key.rsplit("_", 1)
        project_key = parts[0] if len(parts) > 1 else component_key
        commit_sha = parts[1] if len(parts) > 1 else None

    exporter = MetricsExporter.from_instance(instance)

    destination = _build_metrics_destination(project_key, target_job_id, target_ds)

    measures, record_count = exporter.append_commit_metrics(
        component_key, destination, commit_sha
    )

    if not measures:
        logger.warning(f"No measures exported for {component_key}")
        return str(destination)

    repo_name: Optional[str] = None
    data_source = repository.get_data_source(target_ds) if target_ds else None
    if data_source:
        stats = data_source.get("stats") or {}
        repo_name = stats.get("project_name") or data_source.get("name")

    # Create or update output record
    if target_job_id:
        existing_output = repository.find_output_by_job_and_path(
            target_job_id, str(destination)
        )
        if existing_output:
            # Update existing output with new record count
            update_kwargs = {
                "metrics": list(measures.keys()),
                "record_count": record_count,
                "project_key": project_key,
            }
            resolved_repo_name = repo_name or existing_output.get("repo_name")
            if resolved_repo_name:
                update_kwargs["repo_name"] = resolved_repo_name
            if target_ds:
                update_kwargs["data_source_id"] = target_ds
            repository.update_output(existing_output["id"], **update_kwargs)
        else:
            add_kwargs = {
                "job_id": target_job_id,
                "path": str(destination),
                "metrics": list(measures.keys()),
                "record_count": record_count,
                "project_key": project_key,
            }
            if target_ds:
                add_kwargs["data_source_id"] = target_ds
            if repo_name:
                add_kwargs["repo_name"] = repo_name
            repository.add_output(**add_kwargs)

    if target_ds:
        repository.upsert_sonar_run(
            data_source_id=target_ds,
            project_key=project_key,
            commit_sha=commit_sha,
            job_id=target_job_id,
            status="succeeded",
            analysis_id=analysis_id,
            metrics_path=str(destination),
            component_key=component_key,
            sonar_instance=instance.name,
            sonar_host=instance.host,
        )

    logger.info(
        "Metrics for %s appended to %s (total records: %d)",
        component_key,
        destination,
        record_count,
    )
    return str(destination)
