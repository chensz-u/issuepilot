import httpx
import pytest

from issuepilot.domain import ImportedIssue
from issuepilot.ingest import github_error_message, import_repository
from issuepilot.repository import SQLiteRepository


@pytest.mark.asyncio
async def test_import_repository_persists_github_issues(tmp_path) -> None:
    class Client:
        async def list_closed_issues(self, owner: str, name: str, limit: int):
            assert (owner, name, limit) == ("acme", "widget", 2)
            return [
                ImportedIssue(
                    id="acme/widget#1",
                    number=1,
                    title="Resolved bug",
                    body="Fixed by clearing the cache",
                    source_url="https://github.com/acme/widget/issues/1",
                )
            ]

    repository = SQLiteRepository(tmp_path / "issuepilot.db")

    count = await import_repository(Client(), repository, "acme", "widget", 2)

    assert count == 1
    assert repository.list_documents()[0].id == "acme/widget#1"


def test_rate_limit_error_recommends_authenticated_retry() -> None:
    request = httpx.Request("GET", "https://api.github.com/repos/acme/widget/issues")
    response = httpx.Response(403, request=request, headers={"x-ratelimit-remaining": "0"})
    error = httpx.HTTPStatusError("rate limit", request=request, response=response)

    assert github_error_message(error) == (
        "GitHub API rate limit exhausted; set GITHUB_TOKEN or retry after the reset window"
    )
