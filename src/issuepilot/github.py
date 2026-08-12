import httpx

from issuepilot.domain import ImportedIssue


class GitHubIssueClient:
    def __init__(self, http: httpx.AsyncClient, token: str | None = None) -> None:
        self.http = http
        self.token = token

    async def list_closed_issues(
        self, owner: str, repository: str, limit: int = 30
    ) -> list[ImportedIssue]:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        headers = {"Accept": "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        response = await self.http.get(
            f"https://api.github.com/repos/{owner}/{repository}/issues",
            params={"state": "closed", "per_page": min(100, limit + 1)},
            headers=headers,
        )
        response.raise_for_status()
        imported = []
        for item in response.json():
            if "pull_request" in item:
                continue
            imported.append(
                ImportedIssue(
                    id=f"{owner}/{repository}#{item['number']}",
                    number=item["number"],
                    title=item["title"],
                    body=item.get("body") or "",
                    source_url=item["html_url"],
                    labels=tuple(label["name"] for label in item.get("labels", [])),
                )
            )
            if len(imported) == limit:
                break
        return imported
