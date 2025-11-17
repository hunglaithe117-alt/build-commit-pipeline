from __future__ import annotations

from app.models import ScanJobStatus
from app.services.repository import repository
from pipeline.github_fork_finder import (
    GitHubForkFinder,
    GitHubRateLimitError,
    resolve_github_token_pool,
)

import argparse
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.append(str(BACKEND_ROOT))

LOG = logging.getLogger("pipeline.fork_resolver")


def _derive_repo_slug(payload: Dict[str, Any]) -> Optional[str]:
    slug = payload.get("repo_slug")
    if slug:
        return slug
    repo_url = payload.get("repository_url") or payload.get("repo_url")
    if not repo_url:
        return None
    if repo_url.startswith("git@github.com:"):
        slug = repo_url[len("git@github.com:") :]
    elif "github.com/" in repo_url:
        slug = repo_url.split("github.com/", 1)[1]
    else:
        return None
    slug = slug.rstrip("/")
    if slug.endswith(".git"):
        slug = slug[: -len(".git")]
    return slug or None


def _should_process(
    record: Dict[str, Any],
    statuses: List[str],
    include_processed: bool,
    include_non_missing: bool,
) -> bool:
    if statuses and record.get("status") not in statuses:
        return False
    if record.get("fork_search") and not include_processed:
        return False
    payload = record.get("payload") or {}
    commit_sha = payload.get("commit_sha")
    repo_slug = _derive_repo_slug(payload)
    if not commit_sha or not repo_slug:
        return False
    if include_non_missing:
        return True
    error_message = (payload.get("error") or "").lower()
    return "commit" in error_message and "not found" in error_message


def resolve_record(
    record: Dict[str, Any],
    finder: GitHubForkFinder,
    *,
    enqueue: bool = False,
    dry_run: bool = False,
    task_runner_cache: Optional[List[Any]] = None,
) -> tuple[Dict[str, int], Dict[str, Any]]:
    payload = {**(record.get("payload") or {})}
    repo_slug = _derive_repo_slug(payload)
    commit_sha = payload.get("commit_sha")
    if not repo_slug or not commit_sha:
        raise ValueError("Failed commit missing repo_slug or commit_sha")

    summary = {
        "processed": 1,
        "matched": 0,
        "queued": 0,
        "errors": 0,
        "skipped": 0,
    }
    match = None
    message: Optional[str] = None
    status = "not_found"
    try:
        match = finder.find_commit_repo(repo_slug, commit_sha)
        if match:
            status = "found"
            summary["matched"] = 1
    except GitHubRateLimitError:
        raise
    except Exception as exc:  # pragma: no cover - defensive logging
        status = "error"
        message = str(exc)
        summary["errors"] = 1
        LOG.warning(
            "Unexpected error while searching for commit %s: %s",
            commit_sha,
            exc,
        )

    now = datetime.utcnow()
    search_payload: Dict[str, Any] = {
        "status": status,
        "checked_at": now,
        "message": message,
    }
    if match:
        search_payload["fork_full_name"] = match.repo_slug
        search_payload["fork_clone_url"] = match.clone_url
        payload["fork_repo_slug"] = match.repo_slug
        payload["fork_repo_url"] = match.clone_url

    updated_record = record
    if not dry_run:
        repository.update_failed_commit(
            record["id"],
            payload=payload,
            fork_search=search_payload,
        )

        job_id = payload.get("job_id")
        if match and job_id:
            repository.update_scan_job(
                job_id,
                fork_repo_url=match.clone_url,
                fork_repo_slug=match.repo_slug,
            )
            if enqueue:
                runner = None
                if task_runner_cache is not None and task_runner_cache[0] is not None:
                    runner = task_runner_cache[0]
                else:
                    from app.tasks.sonar import run_scan_job as runner  # type: ignore

                    if task_runner_cache is not None:
                        task_runner_cache[0] = runner
                repository.update_scan_job(
                    job_id,
                    status=ScanJobStatus.pending.value,
                    last_error=None,
                    retry_count_delta=1,
                    retry_count=None,
                )
                runner.delay(job_id)
                repository.update_failed_commit(record["id"], status="queued")
                summary["queued"] = 1
        elif match and not job_id:
            LOG.warning(
                "Failed commit %s lacks job_id; fork info recorded but job was not requeued",
                record.get("id"),
            )

        updated_record = repository.get_failed_commit(record["id"]) or updated_record

    return summary, updated_record


def resolve_failed_commits(
    *,
    finder: GitHubForkFinder,
    limit: int,
    statuses: List[str],
    include_processed: bool,
    include_non_missing: bool,
    sleep_time: float,
    enqueue: bool,
    dry_run: bool,
) -> Dict[str, int]:
    summary = {
        "processed": 0,
        "matched": 0,
        "queued": 0,
        "errors": 0,
        "skipped": 0,
    }

    task_runner_cache: List[Any] = [None]

    records = repository.list_failed_commits(limit=limit)

    for record in records:
        if not _should_process(
            record, statuses, include_processed, include_non_missing
        ):
            summary["skipped"] += 1
            continue

        try:
            record_summary, _ = resolve_record(
                record,
                finder,
                enqueue=enqueue,
                dry_run=dry_run,
                task_runner_cache=task_runner_cache,
            )
        except GitHubRateLimitError as exc:
            summary["errors"] += 1
            LOG.error("GitHub rate limit reached: %s", exc)
            break
        except ValueError:
            summary["skipped"] += 1
            continue

        for key in ("processed", "matched", "queued", "errors"):
            summary[key] += record_summary.get(key, 0)

        if sleep_time:
            time.sleep(sleep_time)

    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Search GitHub forks for failed commits and annotate jobs."
    )
    parser.add_argument(
        "--limit", type=int, default=50, help="Max failed commits to examine"
    )
    parser.add_argument(
        "--status",
        dest="statuses",
        action="append",
        default=["pending"],
        help="Filter failed commits by status (can be repeated). Default: pending",
    )
    parser.add_argument(
        "--include-processed",
        action="store_true",
        help="Re-run search even if a previous fork_search exists.",
    )
    parser.add_argument(
        "--include-non-missing",
        action="store_true",
        help="Process every failed commit (not just 'commit not found' errors).",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.0,
        help="Seconds to wait between GitHub API calls (helps avoid rate limits).",
    )
    parser.add_argument(
        "--enqueue",
        action="store_true",
        help="Requeue scan jobs immediately when a fork is found.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not persist changes or enqueue jobs; just log actions.",
    )
    parser.add_argument(
        "--github-token",
        default=None,
        help="GitHub token(s) for lookup (comma/newline separated). Defaults to pool from env.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=int(os.getenv("GITHUB_FORK_PAGES", "5") or "5"),
        help="Maximum number of fork pages to scan per repo (default matches pipeline).",
    )
    parser.add_argument(
        "--log-level",
        default=os.getenv("FORK_RESOLVER_LOG_LEVEL", "INFO"),
        help="Logging level (default INFO).",
    )
    return parser


def main(argv: Optional[Iterable[str]] = None) -> Dict[str, int]:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(levelname)s %(name)s: %(message)s",
    )

    token_pool, fallback_token = resolve_github_token_pool(args.github_token)
    finder = GitHubForkFinder(
        tokens=token_pool or None,
        token=fallback_token,
        max_pages=args.max_pages,
    )
    try:
        summary = resolve_failed_commits(
            finder=finder,
            limit=args.limit,
            statuses=args.statuses,
            include_processed=args.include_processed,
            include_non_missing=args.include_non_missing,
            sleep_time=args.sleep,
            enqueue=args.enqueue,
            dry_run=args.dry_run,
        )
    finally:
        finder.close()

    LOG.info("Fork resolution summary: %s", summary)
    return summary


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
