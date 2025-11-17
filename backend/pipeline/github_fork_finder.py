from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

import requests

from app.core.config import settings

LOG = logging.getLogger("pipeline.github")


@dataclass
class ForkMatch:
    repo_slug: str
    clone_url: str


class GitHubRateLimitError(RuntimeError):
    """Raised when GitHub refuses a request because of rate limits."""


def parse_github_token_pool(raw: Optional[str]) -> List[str]:
    """Split comma/whitespace-delimited tokens into a clean list."""
    if not raw:
        return []
    tokens: List[str] = []
    for piece in raw.replace("\n", ",").replace(";", ",").split(","):
        token = piece.strip()
        if token:
            tokens.append(token)
    return tokens


def resolve_github_token_pool(
    override: Optional[str] = None,
) -> tuple[List[str], Optional[str]]:
    """
    Determine which token pool should be used.

    Returns (token_list, fallback_single_token). If the returned list is empty, callers
    can still use the fallback token (e.g. the classic $GITHUB_TOKEN env).
    """
    tokens = parse_github_token_pool(override)
    if not tokens:
        config_tokens = [token.strip() for token in settings.github.tokens if token]
        tokens = config_tokens
    fallback = None
    return tokens, fallback


class GitHubForkFinder:
    """Utility that locates which fork contains a specific commit."""

    def __init__(
        self,
        *,
        token: Optional[str] = None,
        tokens: Optional[Sequence[str]] = None,
        max_pages: int = 5,
        per_page: int = 100,
        timeout: int = 10,
    ) -> None:
        self.max_pages = max_pages
        self.per_page = per_page
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "User-Agent": os.getenv("GITHUB_USER_AGENT", "build-commit-pipeline"),
            }
        )
        pool = [t for t in (tokens or []) if t]
        if not pool and token:
            pool = [token]
        self.tokens = pool
        self._token_index = 0
        self.graphql_endpoint = "https://api.github.com/graphql"
        self.graphql_chunk_size = int(os.getenv("GITHUB_GRAPHQL_CHUNK", "10") or "10")

    def close(self) -> None:
        try:
            self.session.close()
        except Exception:  # pragma: no cover - best effort cleanup
            pass

    def _next_token(self) -> Optional[str]:
        if not self.tokens:
            return None
        token = self.tokens[self._token_index]
        self._token_index = (self._token_index + 1) % len(self.tokens)
        return token

    def _request(self, url: str, **kwargs) -> requests.Response:
        headers = kwargs.pop("headers", {}) or {}
        token = self._next_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            return self.session.get(
                url, timeout=self.timeout, headers=headers or None, **kwargs
            )
        except requests.RequestException as exc:  # pragma: no cover - network
            raise RuntimeError(str(exc)) from exc

    def _graphql_request(self, payload: Dict[str, object]) -> Dict[str, object]:
        token = self._next_token()
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if not token:
            raise RuntimeError("GitHub GraphQL API requires authentication token")
        headers["Authorization"] = f"Bearer {token}"
        try:
            resp = self.session.post(
                self.graphql_endpoint,
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:  # pragma: no cover - network
            raise RuntimeError(str(exc)) from exc
        if resp.status_code == 401:
            raise RuntimeError("GitHub GraphQL authentication failed")
        data = resp.json()
        errors = data.get("errors") if isinstance(data, dict) else None
        if errors:
            message = errors[0].get("message") if isinstance(errors, list) else None
            if message and "rate limit" in message.lower():
                raise GitHubRateLimitError(message)
            raise RuntimeError(message or "GitHub GraphQL call failed")
        return data

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

    def _split_repo_slug(self, repo_slug: str) -> tuple[str, str]:
        if "/" not in repo_slug:
            raise ValueError(f"Invalid repo slug: {repo_slug}")
        owner, name = repo_slug.split("/", 1)
        return owner, name

    def _commit_in_repo_rest(self, repo_slug: str, commit_sha: str) -> bool:
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

    def _commits_in_repo_graphql(
        self, repo_slug: str, commit_shas: List[str]
    ) -> Dict[str, bool]:
        if not self.tokens:
            raise RuntimeError("No GitHub token available for GraphQL")
        owner, name = self._split_repo_slug(repo_slug)
        result: Dict[str, bool] = {}
        for idx in range(0, len(commit_shas), self.graphql_chunk_size):
            chunk = commit_shas[idx : idx + self.graphql_chunk_size]
            variables: Dict[str, object] = {"owner": owner, "name": name}
            alias_parts: List[str] = []
            for alias_idx, sha in enumerate(chunk):
                var_name = f"exp{alias_idx}"
                alias_name = f"sha_{idx + alias_idx}"
                variables[var_name] = sha
                alias_parts.append(
                    f"""{alias_name}: object(expression: ${var_name}) {{
                        ... on Commit {{ oid }}
                    }}"""
                )
            query = (
                "query($owner:String!, $name:String!"
                + "".join(
                    f", $exp{alias_idx}:String!" for alias_idx in range(len(chunk))
                )
                + "){ repository(owner:$owner, name:$name) {"
                + " ".join(alias_parts)
                + " } }"
            )
            payload = {"query": query, "variables": variables}
            data = self._graphql_request(payload)
            repository_data = (
                data.get("data", {}).get("repository")
                if isinstance(data, dict)
                else None
            )
            for alias_idx, sha in enumerate(chunk):
                alias_name = f"sha_{idx + alias_idx}"
                found = bool(repository_data and repository_data.get(alias_name))
                result[sha] = found
        return result

    def _commits_in_repo(
        self, repo_slug: str, commit_shas: List[str]
    ) -> Dict[str, bool]:
        normalized = [sha for sha in commit_shas if sha]
        if not normalized:
            return {}
        result: Dict[str, bool] = {}
        try:
            gql_result = self._commits_in_repo_graphql(repo_slug, normalized)
            result.update(gql_result)
        except GitHubRateLimitError:
            raise
        except Exception as exc:
            LOG.debug("GraphQL lookup failed for %s: %s", repo_slug, exc)
        remaining = [sha for sha in normalized if sha not in result]
        for sha in remaining:
            result[sha] = self._commit_in_repo_rest(repo_slug, sha)
        return result

    def find_commit_repo(self, repo_slug: str, commit_sha: str) -> Optional[ForkMatch]:
        """Return fork details that contain the commit, if any."""

        repo_results = self._commits_in_repo(repo_slug, [commit_sha])
        if repo_results.get(commit_sha):
            return ForkMatch(
                repo_slug=repo_slug, clone_url=f"https://github.com/{repo_slug}.git"
            )

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
                fork_results = self._commits_in_repo(fork_full_name, [commit_sha])
                if fork_results.get(commit_sha):
                    LOG.info("Found commit %s in fork %s", commit_sha, fork_full_name)
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

    def find_commits_across_forks(
        self, repo_slug: str, commit_shas: List[str]
    ) -> Dict[str, str]:
        """Return mapping of commit SHA -> repo slug that contains it."""
        pending = {sha for sha in commit_shas if sha}
        matches: Dict[str, str] = {}
        repo_results = self._commits_in_repo(repo_slug, list(pending))
        for sha, exists in repo_results.items():
            if exists:
                matches[sha] = repo_slug
                pending.discard(sha)
        if not pending:
            return matches

        params = {"per_page": self.per_page}
        forks_url = f"https://api.github.com/repos/{repo_slug}/forks"
        for page in range(1, self.max_pages + 1):
            params["page"] = page
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
                fork_results = self._commits_in_repo(fork_full_name, list(pending))
                for sha, exists in fork_results.items():
                    if exists and sha not in matches:
                        matches[sha] = fork_full_name
                        pending.discard(sha)
                if not pending:
                    break
            if not pending:
                break
        if pending:
            LOG.warning(
                "Commits %s not found in repo %s or first %s pages of forks",
                list(pending),
                repo_slug,
                self.max_pages,
            )
        return matches


__all__ = [
    "GitHubForkFinder",
    "GitHubRateLimitError",
    "ForkMatch",
    "parse_github_token_pool",
    "resolve_github_token_pool",
]
