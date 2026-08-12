import base64
import hashlib
import re
from collections.abc import Awaitable, Callable
from pathlib import PurePosixPath
from urllib.parse import quote

import httpx

from issuepilot.investigation_domain import EvidenceArtifact, RepositoryRef
from issuepilot.retrieval import tokenize

TOKEN_PATTERN = re.compile(r"(?i)(?:ghp|github_pat)_[A-Za-z0-9_]+")
SEARCH_TERM_PATTERN = re.compile(r"[\w.-]+")
SOURCE_SUFFIXES = {".go", ".java", ".js", ".jsx", ".py", ".rs", ".ts", ".tsx"}
MAX_SOURCE_BYTES = 200_000
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


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

    async def inspect_source_code(
        self, repository: RepositoryRef, query: str
    ) -> list[EvidenceArtifact]:
        metadata = await self.http.get(
            f"https://api.github.com/repos/{repository.full_name}", headers=self.headers
        )
        metadata.raise_for_status()
        branch = metadata.json()["default_branch"]
        tree_url = (
            f"https://api.github.com/repos/{repository.full_name}/git/trees/"
            f"{quote(branch, safe='')}"
        )
        tree = await self.http.get(
            tree_url,
            params={"recursive": "1"},
            headers=self.headers,
        )
        tree.raise_for_status()
        query_tokens = set(tokenize(query))
        candidates: list[tuple[int, str, str]] = []
        for item in tree.json().get("tree", []):
            path = item.get("path", "")
            sha = item.get("sha", "")
            parsed = PurePosixPath(path)
            if (
                item.get("type") != "blob"
                or not path
                or parsed.is_absolute()
                or ".." in parsed.parts
                or parsed.suffix.lower() not in SOURCE_SUFFIXES
                or item.get("size", MAX_SOURCE_BYTES + 1) > MAX_SOURCE_BYTES
                or not SHA_PATTERN.fullmatch(sha)
            ):
                continue
            path_terms = re.sub(r"[/_.-]+", " ", path)
            score = len(query_tokens & set(tokenize(path_terms)))
            if score:
                candidates.append((score, path, sha))
        evidence: list[EvidenceArtifact] = []
        for _, path, sha in sorted(candidates, key=lambda item: (-item[0], item[1]))[:3]:
            content_url = f"https://api.github.com/repos/{repository.full_name}/git/blobs/{sha}"
            response = await self.http.get(
                content_url,
                headers=self.headers,
            )
            response.raise_for_status()
            payload = response.json()
            encoded = "".join(payload.get("content", "").split())
            max_encoded_bytes = ((MAX_SOURCE_BYTES + 2) // 3) * 4
            if payload.get("encoding") != "base64" or len(encoded) > max_encoded_bytes:
                continue
            try:
                decoded = base64.b64decode(encoded, validate=True)
            except ValueError:
                continue
            if len(decoded) > MAX_SOURCE_BYTES:
                continue
            preview = decoded.decode("utf-8", errors="replace")
            artifact_id = hashlib.sha256(path.encode("utf-8")).hexdigest()[:16]
            evidence.append(
                EvidenceArtifact(
                    id=f"source-{artifact_id}",
                    kind="source",
                    title=path,
                    preview=_safe(preview, self.token),
                    source_url=(
                        f"https://github.com/{repository.full_name}/blob/{sha}/"
                        f"{quote(path, safe='/')}"
                    ),
                    tool="inspect_source_code",
                )
            )
        return evidence


class InvestigationToolRegistry:
    names = (
        "read_repository_context",
        "search_issues",
        "inspect_failed_workflows",
        "inspect_recent_commits",
        "inspect_source_code",
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
