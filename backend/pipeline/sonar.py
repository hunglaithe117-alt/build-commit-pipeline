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
from pipeline.commit_replay import (
    MissingForkCommitError,
    apply_replay_plan,
    build_replay_plan,
)
from pipeline.github_api import get_github_client

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
        self.github_client = get_github_client()
        self.github_settings = getattr(settings, "github", None)
        self.max_parent_hops = getattr(self.github_settings, "max_parent_hops", 50)

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
        # Fetch all refs including pull requests which may contain fork commits
        run_command(
            ["git", "fetch", "origin", "+refs/pull/*/head:refs/remotes/origin/pr/*"],
            cwd=repo,
            allow_fail=True,
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

    def _replay_missing_commit(self, repo_slug: str, commit_sha: str) -> Path:
        if not self.github_client:
            raise MissingForkCommitError(
                commit_sha,
                "GitHub token pool is empty; configure github.tokens to replay fork commits.",
            )
        plan = build_replay_plan(
            github=self.github_client,
            repo_slug=repo_slug,
            target_sha=commit_sha,
            commit_exists=lambda sha: self._commit_exists(self.repo_dir, sha),
            max_depth=self.max_parent_hops,
        )
        worktree = self.create_worktree(plan.base_sha, worktree_id=commit_sha)
        apply_replay_plan(worktree, plan)
        return worktree

    # def checkout_commit(self, commit_sha: str) -> None:
    #     run_command(["git", "checkout", "-f", commit_sha], cwd=self.repo_dir)
    #     run_command(["git", "clean", "-fdx"], cwd=self.repo_dir, allow_fail=True)

    def create_worktree(self, commit_sha: str, *, worktree_id: Optional[str] = None) -> Path:
        identifier = worktree_id or commit_sha
        target = self.worktrees_dir / identifier
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

    def remove_worktree(self, worktree_id: str) -> None:
        target = self.worktrees_dir / worktree_id
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

        # Use local sonar-scanner binary installed in the image.
        if config_path:
            scanner_args.append(f"-Dproject.settings={str(config_path)}")

        scanner_exe = os.environ.get("SONAR_SCANNER_HOME", "")
        if scanner_exe:
            scanner_exe = os.path.join(scanner_exe, "bin", "sonar-scanner")
        else:
            scanner_exe = "sonar-scanner"

        cmd = [scanner_exe, *scanner_args]
        return cmd

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
        worktree_id = commit_sha
        s3_log_key: Optional[str] = None
        try:
            with self.repo_mutex():
                self.refresh_repo(repo_url)
                repo = self.repo_dir
                commit_present = self._commit_exists(repo, commit_sha)
                if not commit_present:
                    LOG.warning(
                        "Commit %s not found after initial fetch, trying alternate strategies",
                        commit_sha,
                    )

                    # Strategy 1: Try fetching the specific commit SHA directly from origin
                    try:
                        run_command(
                            ["git", "fetch", "origin", commit_sha],
                            cwd=repo,
                            allow_fail=False,
                        )
                        commit_present = self._commit_exists(repo, commit_sha)
                        if commit_present:
                            LOG.info("Found commit %s via direct SHA fetch", commit_sha)
                        else:
                            LOG.warning(
                                "Direct SHA fetch completed but commit %s is still missing",
                                commit_sha,
                            )
                    except Exception as exc:
                        LOG.debug("Direct SHA fetch failed for %s: %s", commit_sha, exc)

                    # Strategy 2: Try fetching from the fork remote if we can derive a URL
                    if not commit_present and repo_slug:
                        try:
                            fallback_url = normalize_repo_url(None, repo_slug)
                        except Exception:
                            fallback_url = None

                        if fallback_url and fallback_url != repo_url:
                            if self._fetch_commit_from_fork(repo, commit_sha, fallback_url):
                                commit_present = self._commit_exists(repo, commit_sha)
                                if commit_present:
                                    LOG.info(
                                        "Successfully retrieved commit %s from fork %s",
                                        commit_sha,
                                        fallback_url,
                                    )
                            else:
                                LOG.warning(
                                    "Commit %s not found in origin or fork repository %s via git fetch",
                                    commit_sha,
                                    fallback_url,
                                )
                        else:
                            LOG.debug(
                                "No alternate fork URL derived for repo slug %s", repo_slug
                            )

                if commit_present:
                    worktree = self.create_worktree(commit_sha)
                else:
                    if not repo_slug:
                        raise MissingForkCommitError(
                            commit_sha,
                            "Commit missing from origin and no repo slug provided for GitHub replay",
                        )
                    worktree = self._replay_missing_commit(repo_slug, commit_sha)

            effective_config = Path(config_path) if config_path else None
            cmd = self.build_scan_command(component_key, effective_config)
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
                    self.remove_worktree(worktree_id)

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

    def collect_metrics(self, component_key: str) -> Dict[str, str]:
        """Return the latest metrics for a Sonar component without writing to disk."""
        return self._fetch_measures(component_key, self.metrics)


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
