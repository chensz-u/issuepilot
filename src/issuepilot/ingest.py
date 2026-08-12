import argparse
import asyncio
import os
from typing import Protocol

import httpx

from issuepilot.domain import ImportedIssue
from issuepilot.github import GitHubIssueClient
from issuepilot.repository import SQLiteRepository


class IssueClient(Protocol):
    async def list_closed_issues(
        self, owner: str, repository: str, limit: int
    ) -> list[ImportedIssue]: ...


async def import_repository(
    client: IssueClient,
    repository: SQLiteRepository,
    owner: str,
    name: str,
    limit: int,
) -> int:
    issues = await client.list_closed_issues(owner, name, limit)
    repository.upsert_documents([issue.as_document() for issue in issues])
    return len(issues)


async def _run(owner: str, name: str, limit: int, database: str) -> int:
    async with httpx.AsyncClient() as http:
        client = GitHubIssueClient(http=http, token=os.getenv("GITHUB_TOKEN"))
        return await import_repository(client, SQLiteRepository(database), owner, name, limit)


def github_error_message(error: httpx.HTTPStatusError) -> str:
    response = error.response
    if response.status_code == 403 and response.headers.get("x-ratelimit-remaining") == "0":
        return "GitHub API rate limit exhausted; set GITHUB_TOKEN or retry after the reset window"
    return f"GitHub API request failed with HTTP {response.status_code}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Import bounded public GitHub issue evidence")
    parser.add_argument("repository", help="Repository in owner/name form")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument(
        "--database", default=os.getenv("ISSUEPILOT_DATABASE_PATH", "issuepilot.db")
    )
    arguments = parser.parse_args()
    try:
        owner, name = arguments.repository.split("/", maxsplit=1)
    except ValueError as error:
        raise SystemExit("repository must use owner/name format") from error
    try:
        count = asyncio.run(_run(owner, name, arguments.limit, arguments.database))
    except httpx.HTTPStatusError as error:
        raise SystemExit(github_error_message(error)) from error
    print(f"Imported {count} closed issues from {owner}/{name}")


if __name__ == "__main__":
    main()
