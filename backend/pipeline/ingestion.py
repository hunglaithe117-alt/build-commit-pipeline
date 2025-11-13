from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Set

from app.core.config import settings

REPO_COLUMN = "gh_project_name"
COMMIT_COLUMN = "git_trigger_commit"
BRANCH_COLUMN = "git_branch"


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
        self.default_project_key = self.csv_path.stem

    def _load_rows(self) -> Iterator[Dict[str, str]]:
        with self.csv_path.open("r", encoding=self.encoding, newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                raise ValueError("CSV missing header row.")
            for row in reader:
                yield row

    @staticmethod
    def _clean(value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        return value or None

    def _derive_project_key(self, repo_slug: Optional[str]) -> str:
        if repo_slug:
            return repo_slug.replace("/", "_")
        return self.default_project_key

    def summarise(self) -> Dict[str, Optional[str] | int]:
        total_builds = 0
        seen_commits: Set[str] = set()
        first_commit: Optional[str] = None
        last_commit: Optional[str] = None
        repos: set[str] = set()
        branches: set[str] = set()
        project_name: Optional[str] = None

        for row in self._load_rows():
            total_builds += 1
            commit = self._clean(row.get(COMMIT_COLUMN))
            if commit and commit not in seen_commits:
                seen_commits.add(commit)
                if first_commit is None:
                    first_commit = commit
                last_commit = commit
            slug = self._clean(row.get(REPO_COLUMN))
            if slug:
                repos.add(slug)
                project_name = project_name or slug
            branch = self._clean(row.get(BRANCH_COLUMN))
            if branch:
                branches.add(branch)

        unique_commit_count = len(seen_commits)
        primary_repo = project_name
        return {
            "project_name": project_name,
            "project_key": self._derive_project_key(primary_repo),
            "total_builds": total_builds,
            "total_commits": unique_commit_count,
            "unique_branches": len(branches),
            "first_commit": first_commit,
            "last_commit": last_commit,
        }

    def iter_commit_chunks(self, chunk_size: int) -> Iterable[List[CommitWorkItem]]:
        chunk: List[CommitWorkItem] = []
        for row in self._load_rows():
            commit = self._clean(row.get(COMMIT_COLUMN))
            if not commit:
                continue
            repo_slug = self._clean(row.get(REPO_COLUMN))
            repo_url = None
            if not repo_url and repo_slug:
                repo_url = f"https://github.com/{repo_slug}.git"
            project_key = self._derive_project_key(repo_slug)
            item = CommitWorkItem(
                project_key=project_key,
                repo_slug=repo_slug,
                repository_url=repo_url,
                commit_sha=commit,
                branch=self._clean(row.get(BRANCH_COLUMN)),
            )
            chunk.append(item)
            if len(chunk) >= chunk_size:
                yield chunk
                chunk = []
        if chunk:
            yield chunk
