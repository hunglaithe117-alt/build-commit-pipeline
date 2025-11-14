from __future__ import annotations

import csv
import logging
import os
from hashlib import sha256
import shutil
import subprocess
from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.core.config import SonarInstanceSettings, settings
from app.services.s3_service import s3_service

LOG = logging.getLogger("pipeline.sonar")
_RUNNER_CACHE: Dict[tuple[str, str], "SonarCommitRunner"] = {}


@dataclass
class CommitScanResult:
    component_key: str
    log_path: Optional[Path]
    output: str
    instance_name: str
    skipped: bool = False
    s3_log_key: Optional[str] = None  # S3 key if uploaded to S3


def normalize_repo_url(repo_url: Optional[str], repo_slug: Optional[str]) -> str:
    if repo_url:
        cleaned = repo_url.rstrip("/")
        if not cleaned.endswith(".git"):
            cleaned += ".git"
        return cleaned
    if repo_slug:
        return f"https://github.com/{repo_slug}.git"
    raise ValueError("Repository URL or slug is required to clone the project.")


def run_command(
    cmd: List[str], *, cwd: Optional[Path] = None, allow_fail: bool = False
) -> str:
    LOG.debug("Running command: %s", " ".join(cmd))
    completed = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    if completed.returncode != 0 and not allow_fail:
        raise RuntimeError(
            f"Command failed ({completed.returncode}): {' '.join(cmd)}\n{output}"
        )
    return output


class SonarCommitRunner:
    def __init__(
        self, project_key: str, instance: Optional[SonarInstanceSettings] = None
    ) -> None:
        self.project_key = project_key
        self.instance = instance or settings.sonarqube.get_instance()
        base_dir = Path(settings.paths.default_workdir or (Path("/tmp") / "sonar-work"))
        self.work_dir = base_dir / self.instance.name / project_key
        self.repo_dir = self.work_dir / "repo"
        self.worktrees_dir = self.work_dir / "worktrees"
        self.config_dir = self.work_dir / "configs"
        self.worktrees_dir.mkdir(parents=True, exist_ok=True)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.repo_lock_path = self.work_dir / ".repo.lock"
        self.repo_lock_path.touch(exist_ok=True)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.host = self.instance.host.rstrip("/")
        self.token = self.instance.resolved_token()
        self.session = requests.Session()
        self.session.auth = (self.token, "")

    def ensure_repo(self, repo_url: str) -> Path:
        if self.repo_dir.exists() and (self.repo_dir / ".git").exists():
            return self.repo_dir
        if self.repo_dir.exists():
            shutil.rmtree(self.repo_dir)
        run_command(["git", "clone", repo_url, str(self.repo_dir)])
        return self.repo_dir

    @contextmanager
    def repo_mutex(self):
        with self.repo_lock_path.open("r+") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def refresh_repo(self, repo_url: str) -> Path:
        repo = self.ensure_repo(repo_url)
        run_command(
            ["git", "remote", "set-url", "origin", repo_url], cwd=repo, allow_fail=True
        )
        run_command(
            ["git", "fetch", "--all", "--tags", "--prune"], cwd=repo, allow_fail=True
        )
        return repo

    def _commit_exists(self, repo: Path, commit_sha: str) -> bool:
        """Return True if commit object exists in the repository."""
        completed = subprocess.run(
            ["git", "cat-file", "-e", f"{commit_sha}^{{commit}}"],
            cwd=str(repo),
            capture_output=True,
            text=True,
        )
        return completed.returncode == 0

    def _fetch_commit_from_fork(
        self, repo: Path, commit_sha: str, fork_url: str
    ) -> bool:
        """
        Fetch a specific commit from a fork repository.
        Returns True if successful, False otherwise.
        """
        try:
            # Remove existing fork remote if any
            run_command(
                ["git", "remote", "remove", "fork"],
                cwd=repo,
                allow_fail=True,
            )

            # Add fork as temporary remote
            run_command(
                ["git", "remote", "add", "fork", fork_url],
                cwd=repo,
                allow_fail=False,
            )

            # Fetch the specific commit from the fork
            # This is more reliable than fetching all branches
            LOG.info(
                "Fetching commit %s from fork %s",
                commit_sha,
                fork_url,
            )
            run_command(
                ["git", "fetch", "fork", commit_sha],
                cwd=repo,
                allow_fail=False,
            )

            # Verify the commit now exists
            if self._commit_exists(repo, commit_sha):
                LOG.info("Successfully fetched commit %s from fork", commit_sha)
                return True
            else:
                LOG.warning("Commit %s still not found after fork fetch", commit_sha)
                return False

        except Exception as exc:
            LOG.warning(
                "Failed to fetch commit %s from fork %s: %s",
                commit_sha,
                fork_url,
                exc,
            )
            return False

    # def checkout_commit(self, commit_sha: str) -> None:
    #     run_command(["git", "checkout", "-f", commit_sha], cwd=self.repo_dir)
    #     run_command(["git", "clean", "-fdx"], cwd=self.repo_dir, allow_fail=True)

    def create_worktree(self, commit_sha: str) -> Path:
        target = self.worktrees_dir / commit_sha
        if target.exists():
            run_command(
                ["git", "worktree", "remove", str(target), "--force"],
                cwd=self.repo_dir,
                allow_fail=True,
            )
            shutil.rmtree(target, ignore_errors=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        run_command(
            ["git", "worktree", "add", "--detach", str(target), commit_sha],
            cwd=self.repo_dir,
        )
        run_command(["git", "clean", "-fdx"], cwd=target, allow_fail=True)
        return target

    def remove_worktree(self, commit_sha: str) -> None:
        target = self.worktrees_dir / commit_sha
        if target.exists():
            run_command(
                ["git", "worktree", "remove", str(target), "--force"],
                cwd=self.repo_dir,
                allow_fail=True,
            )
            shutil.rmtree(target, ignore_errors=True)

    def ensure_override_config(self, content: str) -> Path:
        digest = sha256(content.encode("utf-8")).hexdigest()
        config_path = self.config_dir / f"override_{digest}.properties"
        if not config_path.exists():
            config_path.write_text(content, encoding="utf-8")
        return config_path

    def build_scan_command(
        self,
        component_key: str,
        project_type: str,
        working_dir: Path,
        config_path: Optional[Path] = None,
    ) -> List[str]:
        scanner_args = [
            f"-Dsonar.projectKey={component_key}",
            f"-Dsonar.projectName={component_key}",
            "-Dsonar.sources=.",
            f"-Dsonar.host.url={self.host}",
            f"-Dsonar.token={self.token}",
            "-Dsonar.sourceEncoding=UTF-8",
            "-Dsonar.scm.exclusions.disabled=true",
            "-Dsonar.java.binaries=.",
        ]

        if config_path:
            scanner_args.append(f"-Dproject.settings=/usr/src/{config_path.name}")

        docker_cmd = [
            "docker",
            "run",
            "--rm",
            "--network=host",
            "-v",
            f"{working_dir}:/usr/src",
            "-v",
            f"{self.work_dir}:{self.work_dir}:ro",
            "sonarsource/sonar-scanner-cli",
        ]
        if config_path:
            container_config_path = "/tmp/sonar-project.properties"
            docker_cmd.extend(["-v", f"{config_path}:{container_config_path}:ro"])
            scanner_args.append(f"-Dproject.settings={container_config_path}")

        docker_cmd.extend(scanner_args)

        return docker_cmd

    def project_exists(self, component_key: str) -> bool:
        url = f"{self.host}/api/projects/search"
        try:
            resp = self.session.get(
                url,
                params={"projects": component_key},
                timeout=10,
            )
            if resp.status_code != 200:
                LOG.warning(
                    "SonarQube lookup failed for %s on %s: %s",
                    component_key,
                    self.instance.name,
                    resp.text[:200],
                )
                return False
            data = resp.json()
            components = data.get("components") or []
            return any(comp.get("key") == component_key for comp in components)
        except Exception as exc:
            LOG.warning(
                "Failed to query SonarQube for %s on %s: %s",
                component_key,
                self.instance.name,
                exc,
            )
            return False

    def scan_commit(
        self,
        *,
        repo_url: str,
        commit_sha: str,
        repo_slug: Optional[str] = None,
        config_path: Optional[str] = None,
    ) -> CommitScanResult:
        component_key = f"{self.project_key}_{commit_sha}"
        if self.project_exists(component_key):
            message = f"Component {component_key} already exists on {self.instance.name}; skipping scan."
            LOG.info(message)

            # Upload log to S3 if enabled
            s3_log_key = s3_service.upload_sonar_log(
                log_content=message,
                project_key=self.project_key,
                commit_sha=commit_sha,
                instance_name=self.instance.name,
            )

            return CommitScanResult(
                component_key=component_key,
                log_path=None,
                output=message,
                instance_name=self.instance.name,
                skipped=True,
                s3_log_key=s3_log_key,
            )

        worktree: Optional[Path] = None
        s3_log_key: Optional[str] = None
        try:
            with self.repo_mutex():
                self.refresh_repo(repo_url)
                repo = self.repo_dir

                # If the commit object is missing after a normal fetch, it may live
                # on a different remote (e.g. a fork). Try to fetch from a fallback
                # remote derived from repo_slug if provided.
                if not self._commit_exists(repo, commit_sha):
                    if repo_slug:
                        try:
                            fallback_url = normalize_repo_url(None, repo_slug)
                        except Exception:
                            fallback_url = None

                        if fallback_url and fallback_url != repo_url:
                            # Try to fetch the specific commit from the fork
                            if self._fetch_commit_from_fork(
                                repo, commit_sha, fallback_url
                            ):
                                LOG.info(
                                    "Successfully retrieved commit %s from fork",
                                    commit_sha,
                                )
                            else:
                                LOG.error(
                                    "Commit %s not found in origin or fork repository %s",
                                    commit_sha,
                                    fallback_url,
                                )
                                raise RuntimeError(
                                    f"Commit {commit_sha} not found in origin or fork repository"
                                )
                    else:
                        LOG.error(
                            "Commit %s not found and no repo_slug provided to fetch from fork",
                            commit_sha,
                        )
                        raise RuntimeError(
                            f"Commit {commit_sha} not found in repository"
                        )

                # Now attempt to create the worktree (will raise if commit still missing)
                worktree = self.create_worktree(commit_sha)

            project_type = self.detect_project_type(worktree)
            effective_config = Path(config_path) if config_path else None
            cmd = self.build_scan_command(
                component_key, project_type, worktree, effective_config
            )
            LOG.debug("Scanning commit %s with command: %s", commit_sha, " ".join(cmd))
            output = run_command(cmd, cwd=worktree)

            # Upload log to S3 if enabled
            s3_log_key = s3_service.upload_sonar_log(
                log_content=output,
                project_key=self.project_key,
                commit_sha=commit_sha,
                instance_name=self.instance.name,
            )

            return CommitScanResult(
                component_key=component_key,
                log_path=None,
                output=output,
                instance_name=self.instance.name,
                s3_log_key=s3_log_key,
            )
        except Exception as exc:
            error_message = str(exc)

            # Upload error log to S3 if enabled
            s3_service.upload_error_log(
                log_content=error_message,
                project_key=self.project_key,
                commit_sha=commit_sha,
                instance_name=self.instance.name,
            )

            raise
        finally:
            if worktree is not None:
                with self.repo_mutex():
                    self.remove_worktree(commit_sha)

    def detect_project_type(self, root: Path) -> str:
        ruby_hits = 0
        if (root / "Gemfile").exists() or ((root / "Rakefile").exists()):
            return "ruby"
        if any(root.glob("*.gemspec")):
            return "ruby"
        for path in root.rglob("*.rb"):
            ruby_hits += 1
            if ruby_hits >= 5:
                break
        if ruby_hits:
            return "ruby"
        return "unknown"


class MetricsExporter:

    def __init__(self, host: str, token: str) -> None:
        self.host = host.rstrip("/")
        self.token = token
        self.settings = settings
        self.session = self._build_session()
        self.metrics = self.settings.sonarqube.measures.keys
        self.chunk_size = self.settings.sonarqube.measures.chunk_size

    @classmethod
    def from_instance(cls, instance: SonarInstanceSettings) -> MetricsExporter:
        return cls(host=instance.host, token=instance.resolved_token())

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        retry = Retry(
            total=3,
            read=3,
            connect=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        session.auth = (self.token, "")
        session.headers.update({"Accept": "application/json"})
        return session

    def _chunks(self, items: List[str]) -> Iterable[List[str]]:
        for idx in range(0, len(items), self.chunk_size):
            yield items[idx : idx + self.chunk_size]

    def _fetch_measures(self, project_key: str, metrics: List[str]) -> Dict[str, str]:
        url = f"{self.host}/api/measures/component"
        payload: Dict[str, str] = {}
        for chunk in self._chunks(metrics):
            resp = self.session.get(
                url,
                params={"component": project_key, "metricKeys": ",".join(chunk)},
                timeout=30,
            )
            resp.raise_for_status()
            component = resp.json().get("component", {})
            for measure in component.get("measures", []):
                payload[measure.get("metric")] = measure.get("value")
        return payload

    def export_project(self, project_key: str, destination: Path) -> Dict[str, str]:
        destination.parent.mkdir(parents=True, exist_ok=True)
        measures = self._fetch_measures(project_key, self.metrics)
        if not measures:
            raise RuntimeError(f"No measures returned for {project_key}")
        headers = ["project_key", *self.metrics]
        with destination.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, quoting=csv.QUOTE_MINIMAL)
            writer.writerow(headers)
            row = [
                project_key,
                *[str(measures.get(metric, "")) for metric in self.metrics],
            ]
            writer.writerow(row)
        return measures

    def append_commit_metrics(
        self, component_key: str, destination: Path, commit_sha: Optional[str] = None
    ) -> tuple[Dict[str, str], int]:
        destination.parent.mkdir(parents=True, exist_ok=True)
        measures = self._fetch_measures(component_key, self.metrics)
        if not measures:
            LOG.warning(f"No measures returned for {component_key}")
            return {}, 0

        headers = ["component_key", "commit_sha", *self.metrics]
        row = [
            component_key,
            commit_sha or "",
            *[str(measures.get(metric, "")) for metric in self.metrics],
        ]

        record_count = 0
        with destination.open("a+", encoding="utf-8", newline="") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                handle.seek(0, os.SEEK_END)
                file_was_empty = handle.tell() == 0

                handle.seek(0)
                if file_was_empty:
                    writer = csv.writer(handle, quoting=csv.QUOTE_MINIMAL)
                    writer.writerow(headers)
                    record_count = 0
                else:
                    record_count = max(sum(1 for _ in handle) - 1, 0)

                handle.seek(0, os.SEEK_END)
                writer = csv.writer(handle, quoting=csv.QUOTE_MINIMAL)
                writer.writerow(row)
                handle.flush()
                record_count += 1
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

        LOG.info(
            "Appended metrics for %s to %s (total rows: %d)",
            component_key,
            destination,
            record_count,
        )
        return measures, record_count


__all__ = [
    "SonarCommitRunner",
    "MetricsExporter",
    "CommitScanResult",
    "normalize_repo_url",
    "get_runner_for_instance",
]


def get_runner_for_instance(
    project_key: str, instance_name: Optional[str] = None
) -> SonarCommitRunner:
    instance = settings.sonarqube.get_instance(instance_name)
    cache_key = (instance.name, project_key)
    if cache_key not in _RUNNER_CACHE:
        _RUNNER_CACHE[cache_key] = SonarCommitRunner(project_key, instance=instance)
    return _RUNNER_CACHE[cache_key]
