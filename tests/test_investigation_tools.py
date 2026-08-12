import re

import httpx
import pytest
from pydantic import ValidationError

from issuepilot.investigation_domain import RepositoryRef
from issuepilot.investigation_tools import GitHubEvidenceClient, InvestigationToolRegistry


def test_repository_ref_accepts_only_owner_name() -> None:
    assert RepositoryRef.parse("acme/widget").full_name == "acme/widget"
    with pytest.raises(ValidationError):
        RepositoryRef.parse("https://github.com/acme/widget")
    with pytest.raises(ValidationError):
        RepositoryRef.parse("acme/widget/extra")
    with pytest.raises(ValidationError):
        RepositoryRef.parse("../x")
    with pytest.raises(ValidationError):
        RepositoryRef.parse("acme/..")


@pytest.mark.asyncio
async def test_source_tool_reads_only_relevant_bounded_repository_files() -> None:
    calls: list[str] = []
    blob_sha = "a" * 40

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/repos/acme/widget":
            return httpx.Response(200, json={"default_branch": "main"})
        if request.url.path == "/repos/acme/widget/git/trees/main":
            assert request.url.params["recursive"] == "1"
            return httpx.Response(
                200,
                json={
                    "tree": [
                        {"type": "blob", "path": "src/cache_lock.py", "size": 120, "sha": blob_sha},
                        {"type": "blob", "path": "docs/printer.md", "size": 90},
                        {"type": "blob", "path": "../escape.py", "size": 10},
                        {"type": "blob", "path": "large/cache_lock.bin", "size": 900_000},
                    ]
                },
            )
        if request.url.path == f"/repos/acme/widget/git/blobs/{blob_sha}":
            return httpx.Response(
                200,
                json={
                    "content": "ZGVmIHJlbGVhc2VfY2FjaGVfbG9jaygpOiBwYXNz",
                    "encoding": "base64",
                },
            )
        raise AssertionError(f"unexpected request: {request.url}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = GitHubEvidenceClient(http)
        evidence = await client.inspect_source_code(
            RepositoryRef.parse("acme/widget"), "Windows package cache lock"
        )

    assert len(evidence) == 1
    assert re.fullmatch(r"source-[0-9a-f]{16}", evidence[0].id)
    assert evidence[0].kind == "source"
    assert "release_cache_lock" in evidence[0].preview
    assert calls == [
        "/repos/acme/widget",
        "/repos/acme/widget/git/trees/main",
        f"/repos/acme/widget/git/blobs/{blob_sha}",
    ]


@pytest.mark.asyncio
async def test_source_tool_rejects_moved_oversized_blob_and_ids_do_not_collide() -> None:
    first_sha = "a" * 40
    second_sha = "b" * 40
    large_sha = "c" * 40

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/repos/acme/widget":
            return httpx.Response(200, json={"default_branch": "main"})
        if request.url.path == "/repos/acme/widget/git/trees/main":
            return httpx.Response(
                200,
                json={
                    "tree": [
                        {"type": "blob", "path": "src/cache-lock.py", "size": 10, "sha": first_sha},
                        {
                            "type": "blob",
                            "path": "src/cache/lock.py",
                            "size": 10,
                            "sha": second_sha,
                        },
                        {"type": "blob", "path": "src/cache_lock.py", "size": 10, "sha": large_sha},
                    ]
                },
            )
        if request.url.path.endswith(large_sha):
            return httpx.Response(
                200,
                json={"encoding": "base64", "content": "YQ==" * 100_001},
            )
        return httpx.Response(200, json={"encoding": "base64", "content": "Y2FjaGUgbG9jaw=="})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        evidence = await GitHubEvidenceClient(http).inspect_source_code(
            RepositoryRef.parse("acme/widget"), "cache lock"
        )

    assert len(evidence) == 2
    assert len({item.id for item in evidence}) == 2


@pytest.mark.asyncio
async def test_real_read_only_tools_use_fixed_github_endpoints() -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.path)
        if request.url.path.endswith("/readme"):
            return httpx.Response(
                200,
                json={"html_url": "https://github.com/acme/widget#readme", "content": "V2lkZ2V0"},
            )
        if request.url.path == "/search/issues":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "number": 7,
                            "title": "Cache lock fixed",
                            "body": "Close the worker before clearing cache.",
                            "html_url": "https://github.com/acme/widget/issues/7",
                            "repository_url": "https://api.github.com/repos/acme/widget",
                        }
                    ]
                },
            )
        if request.url.path.endswith("/actions/runs"):
            return httpx.Response(
                200,
                json={
                    "workflow_runs": [
                        {
                            "id": 9,
                            "name": "CI",
                            "conclusion": "failure",
                            "html_url": "https://github.com/acme/widget/actions/runs/9",
                        }
                    ]
                },
            )
        if request.url.path.endswith("/commits"):
            return httpx.Response(
                200,
                json=[
                    {
                        "sha": "abcdef123456",
                        "html_url": "https://github.com/acme/widget/commit/abcdef123456",
                        "commit": {"message": "fix cache lock"},
                    }
                ],
            )
        if request.url.path == "/repos/acme/widget":
            return httpx.Response(200, json={"default_branch": "main"})
        if request.url.path == "/repos/acme/widget/git/trees/main":
            return httpx.Response(
                200,
                json={
                    "tree": [
                        {
                            "type": "blob",
                            "path": "src/cache_lock.py",
                            "size": 50,
                            "sha": "d" * 40,
                        }
                    ]
                },
            )
        if request.url.path == f"/repos/acme/widget/git/blobs/{'d' * 40}":
            return httpx.Response(
                200,
                json={
                    "content": "Y2FjaGVfbG9jayA9IFRydWU=",
                    "encoding": "base64",
                },
            )
        raise AssertionError(request.url)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        registry = InvestigationToolRegistry(GitHubEvidenceClient(http, token="ghp_secret"))
        repository = RepositoryRef.parse("acme/widget")
        evidence = []
        for tool in registry.names:
            evidence.extend(await registry.execute(tool, repository, "cache lock"))

    assert requested == [
        "/repos/acme/widget/readme",
        "/search/issues",
        "/repos/acme/widget/actions/runs",
        "/repos/acme/widget/commits",
        "/repos/acme/widget",
        "/repos/acme/widget/git/trees/main",
        f"/repos/acme/widget/git/blobs/{'d' * 40}",
    ]
    assert {item.kind for item in evidence} == {
        "repository",
        "issue",
        "workflow",
        "commit",
        "source",
    }
    assert all(item.source_url.startswith("https://github.com/acme/widget") for item in evidence)
    assert "ghp_secret" not in " ".join(item.preview for item in evidence)


@pytest.mark.asyncio
async def test_issue_search_sanitizes_qualifiers_and_discards_foreign_repository() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        query = request.url.params["q"]
        assert query.count("repo:") == 1
        assert query.startswith('repo:acme/widget is:issue in:title,body "')
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "number": 1,
                        "title": "Foreign issue",
                        "body": "cache lock",
                        "html_url": "https://github.com/evil/project/issues/1",
                        "repository_url": "https://api.github.com/repos/evil/project",
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = GitHubEvidenceClient(http)
        evidence = await client.search_issues(
            RepositoryRef.parse("acme/widget"), 'cache repo:evil/project is:pr "escape"'
        )

    assert evidence == []


@pytest.mark.asyncio
async def test_registry_rejects_unknown_tool_and_returns_safe_github_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "rate limit for token ghp_secret"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        registry = InvestigationToolRegistry(GitHubEvidenceClient(http, token="ghp_secret"))
        with pytest.raises(ValueError, match="not allowlisted"):
            await registry.execute("run_shell", RepositoryRef.parse("acme/widget"), "cache")
        evidence = await registry.execute(
            "read_repository_context", RepositoryRef.parse("acme/widget"), "cache"
        )

    assert evidence[0].kind == "error"
    assert "403" in evidence[0].preview
    assert "ghp_secret" not in evidence[0].preview
