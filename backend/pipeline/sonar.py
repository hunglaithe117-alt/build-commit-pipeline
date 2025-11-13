from __future__ import annotations

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

LOG = logging.getLogger("pipeline.sonar")
_RUNNER_CACHE: Dict[tuple[str, str], "SonarCommitRunner"] = {}


@dataclass
class CommitScanResult:
    component_key: str
    log_path: Path
    output: str
    instance_name: str
    skipped: bool = False


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
        self.logs_dir = self.work_dir / "logs"
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
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

    def checkout_commit(self, commit_sha: str) -> None:
        run_command(["git", "checkout", "-f", commit_sha], cwd=self.repo_dir)
        run_command(["git", "clean", "-fdx"], cwd=self.repo_dir, allow_fail=True)

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
            log_path = self.logs_dir / f"{commit_sha}.log"
            message = f"Component {component_key} already exists on {self.instance.name}; skipping scan."
            log_path.write_text(message, encoding="utf-8")
            LOG.info(message)
            return CommitScanResult(
                component_key=component_key,
                log_path=log_path,
                output=message,
                instance_name=self.instance.name,
                skipped=True,
            )

        worktree: Optional[Path] = None
        log_path = self.logs_dir / f"{commit_sha}.log"
        try:
            with self.repo_mutex():
                self.refresh_repo(repo_url)
                worktree = self.create_worktree(commit_sha)

            project_type = self.detect_project_type(worktree)
            effective_config = Path(config_path) if config_path else None
            cmd = self.build_scan_command(
                component_key, project_type, worktree, effective_config
            )
            LOG.debug("Scanning commit %s with command: %s", commit_sha, " ".join(cmd))
            output = run_command(cmd, cwd=worktree)
            log_path.write_text(output, encoding="utf-8")
            return CommitScanResult(
                component_key=component_key,
                log_path=log_path,
                output=output,
                instance_name=self.instance.name,
            )
        except Exception as exc:
            log_path.write_text(str(exc), encoding="utf-8")
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
        with destination.open("w", encoding="utf-8") as handle:
            handle.write(",".join(headers) + "\n")
            row = [
                project_key,
                *[str(measures.get(metric, "")) for metric in self.metrics],
            ]
            handle.write(",".join(row) + "\n")
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
        with destination.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                handle.seek(0, os.SEEK_END)
                file_was_empty = handle.tell() == 0
                if file_was_empty:
                    handle.write(",".join(headers) + "\n")
                handle.write(",".join(row) + "\n")
                handle.flush()
                handle.seek(0)
                record_count = max(sum(1 for _ in handle) - 1, 0)
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
