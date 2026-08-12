import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from issuepilot.investigation_domain import EvidenceArtifact, RepositoryRef
from issuepilot.investigation_graph import InvestigationService
from issuepilot.investigation_store import InvestigationStore


def test_event_sequences_are_atomic_across_concurrent_writers(tmp_path: Path) -> None:
    store = InvestigationStore(tmp_path / "projection.db")

    with ThreadPoolExecutor(max_workers=8) as executor:
        events = list(
            executor.map(
                lambda value: store.append_event("investigation-1", "tool", {"value": value}),
                range(20),
            )
        )

    assert sorted(event.sequence for event in events) == list(range(1, 21))
    assert [event.sequence for event in store.list_events("investigation-1")] == list(range(1, 21))


def test_expired_owner_is_fenced_from_saving_projection(tmp_path: Path) -> None:
    now = [1_000.0]
    store = InvestigationStore(tmp_path / "projection.db", clock=lambda: now[0])
    investigation = InvestigationService._project(
        {
            "id": "investigation-1",
            "repository": {"owner": "acme", "name": "widget"},
            "title": "Cache lock",
            "body": "CI cache lock failure",
            "status": "awaiting_approval",
            "evidence": [],
            "hypotheses": [],
            "draft": "",
            "published": False,
        }
    )
    assert store.claim_decision(investigation.id, "old-owner")
    now[0] += 31

    with pytest.raises(ValueError, match="lease was lost"):
        store.save(investigation, "old-owner")


class FakeTools:
    names = ("search_issues", "inspect_failed_workflows")

    async def execute(
        self, name: str, repository: RepositoryRef, query: str
    ) -> list[EvidenceArtifact]:
        if name == "search_issues":
            return [
                EvidenceArtifact(
                    id="issue-7",
                    kind="issue",
                    title="Cache lock fixed",
                    preview="Close the worker before clearing the cache.",
                    source_url="https://github.com/acme/widget/issues/7",
                    tool=name,
                )
            ]
        return [
            EvidenceArtifact(
                id="workflow-9",
                kind="workflow",
                title="CI",
                preview="CI package cache workflow conclusion: failure",
                source_url="https://github.com/acme/widget/actions/runs/9",
                tool=name,
            )
        ]


@pytest.mark.asyncio
async def test_investigation_pauses_and_resumes_after_service_restart(tmp_path: Path) -> None:
    checkpoint_path = tmp_path / "checkpoints.db"
    projection_path = tmp_path / "investigations.db"

    async with AsyncSqliteSaver.from_conn_string(str(checkpoint_path)) as checkpointer:
        service = InvestigationService(
            checkpointer=checkpointer,
            store=InvestigationStore(projection_path),
            tools=FakeTools(),
        )
        awaiting = await service.start(
            repository="acme/widget",
            title="Windows cache lock",
            body="The package cache is locked during CI install",
        )

    assert awaiting.status == "awaiting_approval"
    assert [item.status for item in awaiting.hypotheses] == ["supported", "supported"]
    assert "[issue-7]" in awaiting.draft
    assert "[workflow-9]" in awaiting.draft

    async with AsyncSqliteSaver.from_conn_string(str(checkpoint_path)) as checkpointer:
        restarted = InvestigationService(
            checkpointer=checkpointer,
            store=InvestigationStore(projection_path),
            tools=FakeTools(),
        )
        approved = await restarted.decide(awaiting.id, "approve")

    assert approved.status == "approved"
    assert approved.publishable_comment == approved.draft
    assert approved.published is False
    events = InvestigationStore(projection_path).list_events(awaiting.id)
    assert [event.sequence for event in events] == list(range(1, len(events) + 1))
    assert events[-1].name == "approval"


class EmptyTools:
    names = ("search_issues",)

    async def execute(
        self, name: str, repository: RepositoryRef, query: str
    ) -> list[EvidenceArtifact]:
        return []


@pytest.mark.asyncio
async def test_no_evidence_blocks_investigation_approval(tmp_path: Path) -> None:
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "checkpoint.db")) as checkpointer:
        service = InvestigationService(
            checkpointer=checkpointer,
            store=InvestigationStore(tmp_path / "projection.db"),
            tools=EmptyTools(),
        )
        result = await service.start("acme/widget", "Printer jam", "Cyan toner is stuck")

        assert result.status == "insufficient_evidence"
        assert result.hypotheses[0].status == "insufficient_evidence"
        with pytest.raises(ValueError, match="cannot be approved"):
            await service.decide(result.id, "approve")


@pytest.mark.asyncio
async def test_rejection_is_terminal_and_cannot_be_replayed(tmp_path: Path) -> None:
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "checkpoint.db")) as checkpointer:
        service = InvestigationService(
            checkpointer=checkpointer,
            store=InvestigationStore(tmp_path / "projection.db"),
            tools=FakeTools(),
        )
        awaiting = await service.start("acme/widget", "Cache lock", "CI cache lock failure")
        rejected = await service.decide(awaiting.id, "reject")

        assert rejected.status == "rejected"
        assert rejected.publishable_comment is None
        with pytest.raises(ValueError, match="already rejected"):
            await service.decide(awaiting.id, "approve")


@pytest.mark.asyncio
async def test_concurrent_decisions_resume_graph_only_once(tmp_path: Path) -> None:
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "checkpoint.db")) as checkpointer:
        service = InvestigationService(
            checkpointer=checkpointer,
            store=InvestigationStore(tmp_path / "projection.db"),
            tools=FakeTools(),
        )
        awaiting = await service.start("acme/widget", "Cache lock", "CI cache lock failure")

        outcomes = await asyncio.gather(
            service.decide(awaiting.id, "approve"),
            service.decide(awaiting.id, "reject"),
            return_exceptions=True,
        )

    assert sum(not isinstance(outcome, Exception) for outcome in outcomes) == 1
    assert sum(isinstance(outcome, ValueError) for outcome in outcomes) == 1


@pytest.mark.asyncio
async def test_expired_decision_lease_allows_restart_to_resume_checkpoint(tmp_path: Path) -> None:
    now = [1_000.0]
    checkpoint_path = tmp_path / "checkpoint.db"
    projection_path = tmp_path / "projection.db"
    crashed_store = InvestigationStore(projection_path, clock=lambda: now[0])
    async with AsyncSqliteSaver.from_conn_string(str(checkpoint_path)) as checkpointer:
        crashed_service = InvestigationService(checkpointer, crashed_store, FakeTools())
        awaiting = await crashed_service.start("acme/widget", "Cache lock", "CI cache lock failure")
    assert crashed_store.claim_decision(awaiting.id, "crashed-process")

    async with AsyncSqliteSaver.from_conn_string(str(checkpoint_path)) as checkpointer:
        blocked = InvestigationService(
            checkpointer,
            InvestigationStore(projection_path, clock=lambda: now[0]),
            FakeTools(),
        )
        with pytest.raises(ValueError, match="already in progress"):
            await blocked.decide(awaiting.id, "approve")

    now[0] += 31
    async with AsyncSqliteSaver.from_conn_string(str(checkpoint_path)) as checkpointer:
        restarted = InvestigationService(
            checkpointer,
            InvestigationStore(projection_path, clock=lambda: now[0]),
            FakeTools(),
        )
        approved = await restarted.decide(awaiting.id, "approve")

    assert approved.status == "approved"


@pytest.mark.asyncio
async def test_running_decision_renews_lease_and_blocks_opposite_takeover(tmp_path: Path) -> None:
    checkpoint_path = tmp_path / "checkpoint.db"
    projection_path = tmp_path / "projection.db"
    entered = asyncio.Event()
    proceed = asyncio.Event()

    async with (
        AsyncSqliteSaver.from_conn_string(str(checkpoint_path)) as first_checkpointer,
        AsyncSqliteSaver.from_conn_string(str(checkpoint_path)) as second_checkpointer,
    ):
        first = InvestigationService(
            first_checkpointer,
            InvestigationStore(projection_path, lease_seconds=0.12),
            FakeTools(),
        )
        second = InvestigationService(
            second_checkpointer,
            InvestigationStore(projection_path, lease_seconds=0.12),
            FakeTools(),
        )
        awaiting = await first.start("acme/widget", "Cache lock", "CI cache lock failure")
        original_run = first._run

        async def delayed_run(investigation_id, value, decision_owner=None):  # type: ignore[no-untyped-def]
            if decision_owner:
                entered.set()
                await proceed.wait()
            await original_run(investigation_id, value, decision_owner)

        first._run = delayed_run  # type: ignore[method-assign]
        approval = asyncio.create_task(first.decide(awaiting.id, "approve"))
        await entered.wait()
        await asyncio.sleep(0.2)

        with pytest.raises(ValueError, match="already in progress"):
            await second.decide(awaiting.id, "reject")
        proceed.set()
        approved = await approval

    assert approved.status == "approved"


@pytest.mark.asyncio
async def test_same_terminal_decision_is_idempotent(tmp_path: Path) -> None:
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "checkpoint.db")) as checkpointer:
        service = InvestigationService(
            checkpointer=checkpointer,
            store=InvestigationStore(tmp_path / "projection.db"),
            tools=FakeTools(),
        )
        awaiting = await service.start("acme/widget", "Cache lock", "CI cache lock failure")
        first = await service.decide(awaiting.id, "approve")
        second = await service.decide(awaiting.id, "approve")

        assert first == second
        with pytest.raises(ValueError, match="already approved"):
            await service.decide(awaiting.id, "reject")
        assert [event.name for event in service.store.list_events(awaiting.id)].count(
            "approval"
        ) == 1


@pytest.mark.asyncio
async def test_distractor_tool_evidence_cannot_be_approved(tmp_path: Path) -> None:
    class DistractorTools:
        names = ("read_repository_context", "inspect_recent_commits")

        async def execute(
            self, name: str, repository: RepositoryRef, query: str
        ) -> list[EvidenceArtifact]:
            return [
                EvidenceArtifact(
                    id=f"distractor-{name}",
                    kind="repository" if name == "read_repository_context" else "commit",
                    title="Python runtime documentation",
                    preview="Python 3.12 supports async web servers.",
                    source_url="https://github.com/acme/widget",
                    tool=name,
                )
            ]

    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "checkpoint.db")) as checkpointer:
        service = InvestigationService(
            checkpointer=checkpointer,
            store=InvestigationStore(tmp_path / "projection.db"),
            tools=DistractorTools(),
        )
        result = await service.start(
            "acme/widget", "Printer firmware failure", "Cyan toner cartridge is jammed"
        )

    assert result.status == "insufficient_evidence"
    assert {item.status for item in result.hypotheses} == {"rejected", "insufficient_evidence"}
    assert "distractor" not in result.draft
