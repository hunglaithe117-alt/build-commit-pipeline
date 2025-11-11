from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional

from app.core.config import settings

PROJECT_FIELDS = [
    "gh_project_name",
    "gh_project",
    "repository_slug",
    "github_slug",
    "project",
]

COMMIT_FIELDS = [
    "git_trigger_commit",
    "git_commit",
    "commit",
    "sha",
    "git_sha",
]

BRANCH_FIELDS = ["git_trigger_branch", "branch", "git_branch"]
REPO_URL_FIELDS = ["gh_project_url", "repo", "repository"]


@dataclass
class CommitWorkItem:
    project_key: str
    repo_slug: Optional[str]
    repository_url: Optional[str]
    commit_sha: str
    branch: Optional[str]

    def to_dict(self) -> Dict[str, Optional[str]]:
        return {
            "project_key": self.project_key,
            "repo_slug": self.repo_slug,
            "repository_url": self.repository_url,
            "commit_sha": self.commit_sha,
            "branch": self.branch,
        }


class CSVIngestionPipeline:
    """Utility helpers to summarise TravisTorrent CSVs and chunk commit work."""

    def __init__(self, csv_path: Path) -> None:
        self.csv_path = Path(csv_path)
        self.encoding = settings.pipeline.csv_encoding

    def _load_rows(self) -> Iterator[Dict[str, str]]:
        with self.csv_path.open("r", encoding=self.encoding, newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                raise ValueError("CSV missing header row.")
            for row in reader:
                yield row

    @staticmethod
    def _first_value(row: Dict[str, str], keys: List[str]) -> Optional[str]:
        for key in keys:
            value = row.get(key)
            if value:
                value = value.strip()
                if value:
                    return value
        return None

    def summarise(self) -> Dict[str, Optional[str] | int]:
        total_builds = 0
        commits: List[str] = []
        repos: set[str] = set()
        branches: set[str] = set()
        project_name: Optional[str] = None

        for row in self._load_rows():
            total_builds += 1
            commit = self._first_value(row, COMMIT_FIELDS)
            if commit:
                commits.append(commit)
            slug = self._first_value(row, PROJECT_FIELDS)
            if slug:
                repos.add(slug)
                project_name = project_name or slug
            branch = self._first_value(row, BRANCH_FIELDS)
            if branch:
                branches.add(branch)
            repo_url = self._first_value(row, REPO_URL_FIELDS)
            if repo_url:
                repos.add(repo_url)

        unique_commits = list(dict.fromkeys(commits))
        return {
            "project_name": project_name,
            "project_key": self.csv_path.stem,
            "total_builds": total_builds,
            "total_commits": len(unique_commits),
            "unique_branches": len(branches),
            "unique_repos": len(repos),
            "first_commit": unique_commits[0] if unique_commits else None,
            "last_commit": unique_commits[-1] if unique_commits else None,
        }

    def iter_commit_chunks(self, chunk_size: int) -> Iterable[List[CommitWorkItem]]:
        chunk: List[CommitWorkItem] = []
        for row in self._load_rows():
            commit = self._first_value(row, COMMIT_FIELDS)
            if not commit:
                continue
            item = CommitWorkItem(
                project_key=self.csv_path.stem,
                repo_slug=self._first_value(row, PROJECT_FIELDS),
                repository_url=self._first_value(row, REPO_URL_FIELDS),
                commit_sha=commit,
                branch=self._first_value(row, BRANCH_FIELDS),
            )
            chunk.append(item)
            if len(chunk) >= chunk_size:
                yield chunk
                chunk = []
        if chunk:
            yield chunk
