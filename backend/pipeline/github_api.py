from __future__ import annotations

import logging
import threading
import time
from typing import List, Optional
from urllib.parse import quote

import requests

from app.core.config import settings

LOG = logging.getLogger("pipeline.github")


class GitHubAPIError(RuntimeError):
    """Raised when the GitHub API returns an error response."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(message)


class GitHubTokenPool:
    """Simple round-robin pool that rotates GitHub tokens and tracks cooldowns."""

    def __init__(self, tokens: List[str]) -> None:
        cleaned = [token.strip() for token in tokens if token and token.strip()]
        if not cleaned:
            raise RuntimeError(
                "GitHub token pool is empty. Provide github.tokens in pipeline.yml"
            )
        self.tokens = cleaned
        self._cooldowns: dict[str, float] = {token: 0.0 for token in cleaned}
        self._cursor = 0
        self._lock = threading.Lock()

    @property
    def size(self) -> int:
        return len(self.tokens)

    def acquire(self) -> str:
        now = time.time()
        with self._lock:
            for _ in range(len(self.tokens)):
                token = self.tokens[self._cursor]
                self._cursor = (self._cursor + 1) % len(self.tokens)
                if self._cooldowns.get(token, 0.0) <= now:
                    return token
        raise RuntimeError(
            "All GitHub tokens are temporarily rate limited. Wait for reset and retry."
        )

    def mark_rate_limited(self, token: str, reset_epoch: Optional[int]) -> None:
        if token not in self._cooldowns:
            return
        cooldown = float(reset_epoch) if reset_epoch else time.time() + 60.0
        with self._lock:
            self._cooldowns[token] = max(cooldown, time.time() + 1.0)
        reset_text = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(cooldown))
        LOG.warning("GitHub token exhausted, cooling down until %s", reset_text)


class GitHubAPI:
    """Thin wrapper around the GitHub REST API with token rotation."""

    def __init__(self, base_url: str, tokens: List[str], *, timeout: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.token_pool = GitHubTokenPool(tokens)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "build-commit-pipeline/sonar",
        })
        self.timeout = timeout

    def _request(
        self,
        method: str,
        path: str,
        *,
        accept: str,
        params: Optional[dict[str, str]] = None,
    ) -> requests.Response:
        url = f"{self.base_url}{path}"
        errors: list[str] = []
        attempts = 0
        max_attempts = max(self.token_pool.size * 4, self.token_pool.size)
        while attempts < max_attempts:
            attempts += 1
            try:
                token = self.token_pool.acquire()
            except RuntimeError as exc:
                raise GitHubAPIError(403, str(exc)) from exc
            headers = {
                "Accept": accept,
                "Authorization": f"token {token}",
            }
            try:
                resp = self.session.request(
                    method,
                    url,
                    params=params,
                    headers=headers,
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                errors.append(str(exc))
                continue
            if resp.status_code == 403 and resp.headers.get("X-RateLimit-Remaining") == "0":
                reset_header = resp.headers.get("X-RateLimit-Reset")
                reset_epoch = int(reset_header) if reset_header and reset_header.isdigit() else None
                self.token_pool.mark_rate_limited(token, reset_epoch)
                continue
            if resp.status_code >= 400:
                snippet = (resp.text or "")[:200]
                message = f"GitHub API {resp.status_code} for {path}: {snippet}"
                raise GitHubAPIError(resp.status_code, message)
            return resp
        raise GitHubAPIError(503, "All GitHub API attempts failed: " + "; ".join(errors))

    @staticmethod
    def _encode_slug(repo_slug: str) -> str:
        return quote(repo_slug, safe="/")

    def get_commit(self, repo_slug: str, commit_sha: str) -> dict:
        slug = self._encode_slug(repo_slug)
        resp = self._request(
            "GET",
            f"/repos/{slug}/commits/{commit_sha}",
            accept="application/vnd.github+json",
        )
        return resp.json()

    def get_commit_patch(self, repo_slug: str, commit_sha: str) -> str:
        slug = self._encode_slug(repo_slug)
        resp = self._request(
            "GET",
            f"/repos/{slug}/commits/{commit_sha}",
            accept="application/vnd.github.v3.patch",
        )
        return resp.text


_CLIENT: Optional[GitHubAPI] = None


def get_github_client() -> Optional[GitHubAPI]:
    """Return a cached GitHub client instance, if tokens are configured."""

    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT
    tokens = settings.github.tokens if hasattr(settings, "github") else []
    cleaned = [token for token in tokens if token]
    if not cleaned:
        LOG.warning(
            "GitHub token pool is empty; missing-fork commits cannot be replayed until tokens are configured."
        )
        return None
    _CLIENT = GitHubAPI(
        base_url=getattr(settings.github, "api_url", "https://api.github.com"),
        tokens=cleaned,
    )
    return _CLIENT
