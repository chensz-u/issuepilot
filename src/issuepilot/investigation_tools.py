import base64
import re
from collections.abc import Awaitable, Callable

import httpx

from issuepilot.investigation_domain import EvidenceArtifact, RepositoryRef

TOKEN_PATTERN = re.compile(r"(?i)(?:ghp|github_pat)_[A-Za-z0-9_]+")
SEARCH_TERM_PATTERN = re.compile(r"[\w.-]+")


def _safe(text: str, token: str | None = None) -> str:
    redacted = TOKEN_PATTERN.sub("[REDACTED]", text)
    return redacted.replace(token, "[REDACTED]")[:800] if token else redacted[:800]


class GitHubEvidenceClient:
    def __init__(self, http: httpx.AsyncClient, token: str | None = None) -> None:
        self.http = http
        self.token = token

    @property
    def headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def read_repository_context(
        self, repository: RepositoryRef, query: str
    ) -> list[EvidenceArtifact]:
        response = await self.http.get(
            f"https://api.github.com/repos/{repository.full_name}/readme", headers=self.headers
        )
        response.raise_for_status()
        payload = response.json()
        preview = base64.b64decode(payload.get("content", "")).decode("utf-8", errors="replace")
        return [
            EvidenceArtifact(
                id="repository-readme",
                kind="repository",
                title=f"{repository.full_name} README",
                preview=_safe(preview, self.token),
                source_url=payload["html_url"],
                tool="read_repository_context",
            )
        ]

    async def search_issues(self, repository: RepositoryRef, query: str) -> list[EvidenceArtifact]:
        terms = " ".join(SEARCH_TERM_PATTERN.findall(query))[:500]
        response = await self.http.get(
            "https://api.github.com/search/issues",
            params={
                "q": f'repo:{repository.full_name} is:issue in:title,body "{terms}"',
                "per_page": 5,
            },
            headers=self.headers,
        )
        response.raise_for_status()
        repository_url = f"https://api.github.com/repos/{repository.full_name}".lower()
        return [
            EvidenceArtifact(
                id=f"issue-{item['number']}",
                kind="issue",
                title=item["title"],
                preview=_safe(item.get("body") or "", self.token),
                source_url=item["html_url"],
                tool="search_issues",
            )
            for item in response.json().get("items", [])[:5]
            if item.get("repository_url", "").lower() == repository_url
        ]

    async def inspect_failed_workflows(
        self, repository: RepositoryRef, query: str
    ) -> list[EvidenceArtifact]:
        response = await self.http.get(
            f"https://api.github.com/repos/{repository.full_name}/actions/runs",
            params={"status": "failure", "per_page": 5},
            headers=self.headers,
        )
        response.raise_for_status()
        return [
            EvidenceArtifact(
                id=f"workflow-{item['id']}",
                kind="workflow",
                title=item["name"],
                preview=_safe(f"Workflow conclusion: {item.get('conclusion')}", self.token),
                source_url=item["html_url"],
                tool="inspect_failed_workflows",
            )
            for item in response.json().get("workflow_runs", [])[:5]
        ]

    async def inspect_recent_commits(
        self, repository: RepositoryRef, query: str
    ) -> list[EvidenceArtifact]:
        response = await self.http.get(
            f"https://api.github.com/repos/{repository.full_name}/commits",
            params={"per_page": 5},
            headers=self.headers,
        )
        response.raise_for_status()
        return [
            EvidenceArtifact(
                id=f"commit-{item['sha'][:12]}",
                kind="commit",
                title=item["commit"]["message"].splitlines()[0],
                preview=_safe(item["commit"]["message"], self.token),
                source_url=item["html_url"],
                tool="inspect_recent_commits",
            )
            for item in response.json()[:5]
        ]


class InvestigationToolRegistry:
    names = (
        "read_repository_context",
        "search_issues",
        "inspect_failed_workflows",
        "inspect_recent_commits",
    )

    def __init__(self, client: GitHubEvidenceClient) -> None:
        self.client = client

    async def execute(
        self, name: str, repository: RepositoryRef, query: str
    ) -> list[EvidenceArtifact]:
        if name not in self.names:
            raise ValueError(f"tool is not allowlisted: {name}")
        method: Callable[[RepositoryRef, str], Awaitable[list[EvidenceArtifact]]] = getattr(
            self.client, name
        )
        try:
            return await method(repository, query)
        except httpx.HTTPStatusError as error:
            return [
                EvidenceArtifact(
                    id=f"error-{name}",
                    kind="error",
                    title=f"{name} unavailable",
                    preview=_safe(
                        f"GitHub returned HTTP {error.response.status_code}", self.client.token
                    ),
                    source_url=f"https://github.com/{repository.full_name}",
                    tool=name,
                )
            ]
