import httpx
import pytest

from issuepilot.github import GitHubIssueClient


@pytest.mark.asyncio
async def test_closed_issue_import_is_bounded_and_skips_pull_requests() -> None:
    payload = [
        {
            "number": 3,
            "title": "Fixed issue",
            "body": "The cache is stale",
            "html_url": "https://github.com/acme/widget/issues/3",
            "labels": [{"name": "bug"}],
            "pull_request": {"url": "https://api.github.com/repos/acme/widget/pulls/3"},
        },
        {
            "number": 2,
            "title": "Real issue",
            "body": "Upgrade fails on Windows",
            "html_url": "https://github.com/acme/widget/issues/2",
            "labels": [{"name": "windows"}],
        },
        {
            "number": 1,
            "title": "Older issue",
            "body": None,
            "html_url": "https://github.com/acme/widget/issues/1",
            "labels": [],
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["state"] == "closed"
        assert request.url.params["per_page"] == "3"
        return httpx.Response(200, json=payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        issues = await GitHubIssueClient(http=http).list_closed_issues("acme", "widget", limit=2)

    assert [issue.id for issue in issues] == ["acme/widget#2", "acme/widget#1"]
    assert issues[0].labels == ("windows",)


@pytest.mark.asyncio
async def test_import_rejects_unbounded_limit() -> None:
    async with httpx.AsyncClient() as http:
        with pytest.raises(ValueError, match="between 1 and 100"):
            await GitHubIssueClient(http=http).list_closed_issues("acme", "widget", limit=101)
