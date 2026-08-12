from pathlib import Path

import httpx
import pytest
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from issuepilot.api import create_app
from issuepilot.investigation_domain import EvidenceArtifact, RepositoryRef
from issuepilot.investigation_graph import InvestigationService
from issuepilot.investigation_store import InvestigationStore
from issuepilot.retrieval import HybridRetriever
from issuepilot.trace import InMemoryTraceStore
from issuepilot.workflow import DiagnosisWorkflow


class ApiTools:
    names = ("search_issues",)

    async def execute(
        self, name: str, repository: RepositoryRef, query: str
    ) -> list[EvidenceArtifact]:
        return [
            EvidenceArtifact(
                id="issue-7",
                kind="issue",
                title="Cache lock repair",
                preview="Stop the worker and clear only its locked cache.",
                source_url="https://github.com/acme/widget/issues/7",
                tool=name,
            )
        ]


@pytest.mark.asyncio
async def test_investigation_create_replay_get_and_approval_api(tmp_path: Path) -> None:
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "checkpoint.db")) as checkpointer:
        service = InvestigationService(
            checkpointer,
            InvestigationStore(tmp_path / "projection.db"),
            ApiTools(),
        )
        legacy = DiagnosisWorkflow(HybridRetriever([]), InMemoryTraceStore())
        app = create_app(legacy, investigation_service=service)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            created_response = await client.post(
                "/api/investigations",
                json={
                    "repository": "acme/widget",
                    "title": "Cache failure",
                    "body": "CI package cache is locked",
                },
            )
            assert created_response.status_code == 201
            created = created_response.json()

            loaded = await client.get(f"/api/investigations/{created['id']}")
            replay = await client.get(f"/api/investigations/{created['id']}/events")
            approval = await client.post(
                f"/api/investigations/{created['id']}/approval",
                json={"decision": "approve"},
            )

    assert loaded.json()["status"] == "awaiting_approval"
    assert replay.headers["content-type"].startswith("text/event-stream")
    assert "event: tools" in replay.text
    assert "id: 1" in replay.text
    assert approval.json()["status"] == "approved"
    assert approval.json()["published"] is False


@pytest.mark.asyncio
async def test_missing_investigation_returns_404(tmp_path: Path) -> None:
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "checkpoint.db")) as checkpointer:
        service = InvestigationService(
            checkpointer,
            InvestigationStore(tmp_path / "projection.db"),
            ApiTools(),
        )
        app = create_app(
            DiagnosisWorkflow(HybridRetriever([]), InMemoryTraceStore()),
            investigation_service=service,
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/investigations/missing")

    assert response.status_code == 404
