from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.core.config import settings

LOG = logging.getLogger("pipeline.sonar")


@dataclass
class CommitScanResult:
    component_key: str
    log_path: Path
    output: str


def normalize_repo_url(repo_url: Optional[str], repo_slug: Optional[str]) -> str:
    if repo_url:
        cleaned = repo_url.rstrip("/")
        if not cleaned.endswith(".git"):
            cleaned += ".git"
        return cleaned
    if repo_slug:
        return f"https://github.com/{repo_slug}.git"
    raise ValueError("Repository URL or slug is required to clone the project.")


def run_command(cmd: List[str], *, cwd: Optional[Path] = None, allow_fail: bool = False) -> str:
    LOG.debug("Running command: %s", " ".join(cmd))
    completed = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    if completed.returncode != 0 and not allow_fail:
        raise RuntimeError(f"Command failed ({completed.returncode}): {' '.join(cmd)}\n{output}")
    return output


class SonarCommitRunner:
    """Lightweight re-implementation of sonar_scan_csv_multi for Celery tasks."""

    def __init__(self, project_key: str) -> None:
        self.project_key = project_key
        base_dir = Path(settings.paths.default_workdir or (Path("/tmp") / "sonar-work"))
        self.work_dir = base_dir / project_key
        self.repo_dir = self.work_dir / "repo"
        self.logs_dir = self.work_dir / "logs"
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.scanner_bin = settings.sonarqube.scanner_bin
        self.host = settings.sonarqube.host.rstrip("/")
        self.token = settings.sonar_token

    def ensure_repo(self, repo_url: str) -> Path:
        if self.repo_dir.exists() and (self.repo_dir / ".git").exists():
            run_command(["git", "fetch", "--all"], cwd=self.repo_dir, allow_fail=True)
        else:
            if self.repo_dir.exists():
                shutil.rmtree(self.repo_dir)
            run_command(["git", "clone", repo_url, str(self.repo_dir)])
        return self.repo_dir

    def checkout_commit(self, commit_sha: str) -> None:
        run_command(["git", "checkout", "-f", commit_sha], cwd=self.repo_dir)
        run_command(["git", "clean", "-fdx"], cwd=self.repo_dir, allow_fail=True)

    def detect_language(self) -> str:
        ruby_hits = 0
        for path in self.repo_dir.rglob("*.rb"):
            ruby_hits += 1
            if ruby_hits >= 5:
                break
        return "ruby" if ruby_hits else "unknown"

    def build_scan_command(self, component_key: str, language: str) -> List[str]:
        base_cmd = [
            self.scanner_bin,
            f"-Dsonar.projectKey={component_key}",
            f"-Dsonar.projectName={self.project_key}",
            "-Dsonar.sources=.",
            f"-Dsonar.host.url={self.host}",
            f"-Dsonar.login={self.token}",
            "-Dsonar.sourceEncoding=UTF-8",
            "-Dsonar.exclusions=**/spec/**,**/test/**,**/vendor/**,**/tmp/**",
        ]
        if language == "ruby":
            base_cmd.extend(
                [
                    "-Dsonar.language=ruby",
                    "-Dsonar.java.binaries=target/classes",
                ]
            )
        return base_cmd

    def scan_commit(
        self,
        *,
        repo_url: str,
        commit_sha: str,
        repo_slug: Optional[str] = None,
    ) -> CommitScanResult:
        repo = self.ensure_repo(repo_url)
        self.checkout_commit(commit_sha)
        language = self.detect_language()
        component_key = f"{self.project_key}_{commit_sha}"
        cmd = self.build_scan_command(component_key, language)
        log_path = self.logs_dir / f"{commit_sha}.log"
        try:
            output = run_command(cmd, cwd=repo)
        except Exception as exc:
            log_path.write_text(str(exc), encoding="utf-8")
            raise
        else:
            log_path.write_text(output, encoding="utf-8")
            return CommitScanResult(component_key=component_key, log_path=log_path, output=output)


class MetricsExporter:
    """Lightweight exporter inspired by batch_fetch_all_measures.py."""

    def __init__(self) -> None:
        self.settings = settings
        self.session = self._build_session()
        self.metrics = self.settings.sonarqube.measures.keys
        self.chunk_size = self.settings.sonarqube.measures.chunk_size

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
        session.headers.update(
            {
                "Authorization": f"Bearer {settings.sonar_token}",
                "Accept": "application/json",
            }
        )
        return session

    def _chunks(self, items: List[str]) -> Iterable[List[str]]:
        for idx in range(0, len(items), self.chunk_size):
            yield items[idx : idx + self.chunk_size]

    def _fetch_measures(self, project_key: str, metrics: List[str]) -> Dict[str, str]:
        url = f"{self.settings.sonarqube.host.rstrip('/')}/api/measures/component"
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
            row = [project_key, *[str(measures.get(metric, "")) for metric in self.metrics]]
            handle.write(",".join(row) + "\n")
        return measures


__all__ = ["SonarCommitRunner", "MetricsExporter", "CommitScanResult", "normalize_repo_url"]
