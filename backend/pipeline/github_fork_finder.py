from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

import requests

LOG = logging.getLogger("pipeline.github")


@dataclass
class ForkMatch:
    repo_slug: str
    clone_url: str


class GitHubRateLimitError(RuntimeError):
    """Raised when GitHub refuses a request because of rate limits."""


class GitHubForkFinder:
    """Utility that locates which fork contains a specific commit."""

    def __init__(
        self,
        *,
        token: Optional[str] = None,
        max_pages: int = 5,
        per_page: int = 100,
        timeout: int = 10,
    ) -> None:
        self.max_pages = max_pages
        self.per_page = per_page
        self.timeout = timeout
        self.session = requests.Session()
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": os.getenv("GITHUB_USER_AGENT", "build-commit-pipeline"),
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.session.headers.update(headers)

    def close(self) -> None:
        try:
            self.session.close()
        except Exception:  # pragma: no cover - best effort cleanup
            pass

    def _request(self, url: str, **kwargs) -> requests.Response:
        try:
            return self.session.get(url, timeout=self.timeout, **kwargs)
        except requests.RequestException as exc:  # pragma: no cover - network
            raise RuntimeError(str(exc)) from exc

    @staticmethod
    def _is_rate_limited(resp: requests.Response) -> bool:
        if resp.status_code != 403:
            return False
        remaining = resp.headers.get("X-RateLimit-Remaining")
        return remaining == "0"

    def _handle_rate_limit(self, resp: requests.Response, context: str) -> None:
        if self._is_rate_limited(resp):
            reset = resp.headers.get("X-RateLimit-Reset")
            suffix = f" (resets at {reset})" if reset else ""
            raise GitHubRateLimitError(f"Rate limit exceeded while {context}{suffix}")

    def _commit_in_repo(self, repo_slug: str, commit_sha: str) -> bool:
        url = f"https://api.github.com/repos/{repo_slug}/commits/{commit_sha}"
        resp = self._request(url)
        if resp.status_code == 200:
            return True
        if resp.status_code not in {404, 422}:
            self._handle_rate_limit(resp, f"checking {repo_slug}")
            LOG.debug(
                "GitHub commit lookup for %s returned %s: %s",
                repo_slug,
                resp.status_code,
                resp.text[:200],
            )
        return False

    def find_commit_repo(self, repo_slug: str, commit_sha: str) -> Optional[ForkMatch]:
        """Return fork details that contain the commit, if any."""

        if self._commit_in_repo(repo_slug, commit_sha):
            return ForkMatch(repo_slug=repo_slug, clone_url=f"https://github.com/{repo_slug}.git")

        params = {"per_page": self.per_page}
        for page in range(1, self.max_pages + 1):
            params["page"] = page
            forks_url = f"https://api.github.com/repos/{repo_slug}/forks"
            resp = self._request(forks_url, params=params)
            if resp.status_code != 200:
                self._handle_rate_limit(resp, f"listing forks for {repo_slug}")
                LOG.warning(
                    "Failed to fetch forks for %s (page %s): %s %s",
                    repo_slug,
                    page,
                    resp.status_code,
                    resp.text[:200],
                )
                break

            forks = resp.json()
            if not forks:
                break

            for fork in forks:
                fork_full_name = fork.get("full_name")
                if not fork_full_name:
                    continue
                if self._commit_in_repo(fork_full_name, commit_sha):
                    LOG.info(
                        "Found commit %s in fork %s", commit_sha, fork_full_name
                    )
                    return ForkMatch(
                        repo_slug=fork_full_name,
                        clone_url=f"https://github.com/{fork_full_name}.git",
                    )
        LOG.warning(
            "Commit %s not found in main repo %s or first %s pages of forks",
            commit_sha,
            repo_slug,
            self.max_pages,
        )
        return None


__all__ = ["GitHubForkFinder", "GitHubRateLimitError", "ForkMatch"]
