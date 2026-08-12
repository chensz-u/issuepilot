import asyncio
from typing import Any, Protocol, TypedDict
from uuid import uuid4

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from issuepilot.domain import KnowledgeDocument
from issuepilot.investigation_domain import (
    EvidenceArtifact,
    Hypothesis,
    Investigation,
    RepositoryRef,
)
from issuepilot.investigation_store import InvestigationStore
from issuepilot.retrieval import HybridRetriever


class ToolRegistry(Protocol):
    names: tuple[str, ...]

    async def execute(
        self, name: str, repository: RepositoryRef, query: str
    ) -> list[EvidenceArtifact]: ...


class InvestigationState(TypedDict, total=False):
    id: str
    repository: dict[str, str]
    title: str
    body: str
    status: str
    evidence: list[dict[str, Any]]
    hypotheses: list[dict[str, Any]]
    draft: str
    publishable_comment: str | None
    published: bool


class InvestigationService:
    def __init__(
        self,
        checkpointer: BaseCheckpointSaver[Any],
        store: InvestigationStore,
        tools: ToolRegistry,
    ) -> None:
        self.store = store
        self.tools = tools
        builder = StateGraph(InvestigationState)
        builder.add_node("validate", self._validate)
        builder.add_node("tools", self._execute_tools)
        builder.add_node("hypothesize", self._hypothesize)
        builder.add_node("synthesize", self._synthesize)
        builder.add_node("approval", self._approval)
        builder.add_edge(START, "validate")
        builder.add_edge("validate", "tools")
        builder.add_edge("tools", "hypothesize")
        builder.add_edge("hypothesize", "synthesize")
        builder.add_conditional_edges(
            "synthesize",
            lambda state: "stop" if state["status"] == "insufficient_evidence" else "review",
            {"stop": END, "review": "approval"},
        )
        builder.add_edge("approval", END)
        self.graph = builder.compile(checkpointer=checkpointer)

    async def start(self, repository: str, title: str, body: str) -> Investigation:
        reference = RepositoryRef.parse(repository)
        investigation_id = str(uuid4())
        state: InvestigationState = {
            "id": investigation_id,
            "repository": reference.model_dump(),
            "title": title,
            "body": body,
            "status": "running",
            "evidence": [],
            "hypotheses": [],
            "draft": "",
            "publishable_comment": None,
            "published": False,
        }
        await self._run(investigation_id, state)
        return self.store.get(investigation_id)

    async def decide(self, investigation_id: str, decision: str) -> Investigation:
        if decision not in {"approve", "reject"}:
            raise ValueError("decision must be approve or reject")
        current = self.store.get(investigation_id)
        if current.status == "insufficient_evidence":
            raise ValueError("investigation without grounded evidence cannot be approved")
        terminal_decision = {"approved": "approve", "rejected": "reject"}.get(current.status)
        if terminal_decision == decision:
            return current
        if terminal_decision:
            raise ValueError(f"investigation is already {current.status}")
        if current.status != "awaiting_approval":
            raise ValueError("investigation is not awaiting approval")
        lease_owner = str(uuid4())
        if not self.store.claim_decision(investigation_id, lease_owner):
            raise ValueError("investigation decision is already in progress")
        stop_renewal = asyncio.Event()
        lease_lost = asyncio.Event()
        renewal = asyncio.create_task(
            self._renew_decision_lease(investigation_id, lease_owner, stop_renewal, lease_lost)
        )
        try:
            await self._run(investigation_id, Command(resume=decision), lease_owner)
            if lease_lost.is_set():
                raise ValueError("investigation decision lease was lost")
            return self.store.get(investigation_id)
        finally:
            stop_renewal.set()
            await renewal
            self.store.release_decision(investigation_id, lease_owner)

    async def _renew_decision_lease(
        self,
        investigation_id: str,
        owner: str,
        stop: asyncio.Event,
        lost: asyncio.Event,
    ) -> None:
        while True:
            try:
                await asyncio.wait_for(stop.wait(), timeout=self.store.lease_seconds / 3)
                return
            except TimeoutError:
                if not self.store.renew_decision(investigation_id, owner):
                    lost.set()
                    return

    async def _run(
        self,
        investigation_id: str,
        value: InvestigationState | Command,
        decision_owner: str | None = None,
    ) -> None:
        config = {"configurable": {"thread_id": investigation_id}}
        async for update in self.graph.astream(value, config, stream_mode="updates"):
            for name, payload in update.items():
                if name == "__interrupt__":
                    self.store.append_event(investigation_id, "awaiting_approval", {})
                else:
                    safe_payload = {
                        key: item
                        for key, item in (payload or {}).items()
                        if key in {"status", "draft", "published"}
                    }
                    self.store.append_event(investigation_id, name, safe_payload)
        snapshot = await self.graph.aget_state(config)
        investigation = self._project(snapshot.values)
        self.store.save(investigation, decision_owner)

    @staticmethod
    def _validate(state: InvestigationState) -> InvestigationState:
        RepositoryRef.model_validate(state["repository"])
        return {"status": "running"}

    async def _execute_tools(self, state: InvestigationState) -> InvestigationState:
        repository = RepositoryRef.model_validate(state["repository"])
        query = f"{state['title']} {state['body']}"
        evidence: list[EvidenceArtifact] = []
        for name in self.tools.names:
            evidence.extend(await self.tools.execute(name, repository, query))
        return {"evidence": [item.model_dump(mode="json") for item in evidence]}

    @staticmethod
    def _hypothesize(state: InvestigationState) -> InvestigationState:
        evidence = [EvidenceArtifact.model_validate(item) for item in state["evidence"]]
        usable = [item for item in evidence if item.kind != "error"]
        documents = [
            KnowledgeDocument(
                id=item.id,
                title=item.title,
                text=item.preview,
                source_url=item.source_url,
                kind="resolved_issue" if item.kind == "issue" else "documentation",
            )
            for item in usable
        ]
        relevant_ids = {
            hit.document.id
            for hit in HybridRetriever(documents).search(
                f"{state['title']} {state['body']}", limit=max(1, len(documents))
            )
        }
        hypotheses = [
            Hypothesis(
                id=f"hypothesis-{index}",
                statement=f"Evidence from {item.title} may explain the reported failure.",
                status="supported" if item.id in relevant_ids else "rejected",
                evidence_ids=(item.id,),
            )
            for index, item in enumerate(usable, start=1)
        ]
        if not relevant_ids:
            hypotheses.append(
                Hypothesis(
                    id="hypothesis-none",
                    statement="No grounded repository evidence supports a diagnosis.",
                    status="insufficient_evidence",
                )
            )
        return {"hypotheses": [item.model_dump(mode="json") for item in hypotheses]}

    @staticmethod
    def _synthesize(state: InvestigationState) -> InvestigationState:
        evidence = [EvidenceArtifact.model_validate(item) for item in state["evidence"]]
        hypotheses = [Hypothesis.model_validate(item) for item in state["hypotheses"]]
        supported_ids = {
            evidence_id
            for hypothesis in hypotheses
            if hypothesis.status == "supported"
            for evidence_id in hypothesis.evidence_ids
        }
        supported = [item for item in evidence if item.id in supported_ids]
        if not supported:
            return {
                "status": "insufficient_evidence",
                "draft": "No grounded repository evidence was found; no diagnosis is proposed.",
            }
        lines = [f"- [{item.id}] {item.title}: {item.preview}" for item in supported]
        return {
            "status": "awaiting_approval",
            "draft": "## Repository investigation\n\n" + "\n".join(lines),
        }

    @staticmethod
    def _approval(state: InvestigationState) -> InvestigationState:
        decision = interrupt({"draft": state["draft"]})
        if decision == "approve":
            return {
                "status": "approved",
                "publishable_comment": state["draft"],
                "published": False,
            }
        return {"status": "rejected", "publishable_comment": None, "published": False}

    @staticmethod
    def _project(state: InvestigationState) -> Investigation:
        return Investigation(
            id=state["id"],
            repository=RepositoryRef.model_validate(state["repository"]),
            title=state["title"],
            body=state["body"],
            status=state["status"],  # type: ignore[arg-type]
            evidence=tuple(EvidenceArtifact.model_validate(item) for item in state["evidence"]),
            hypotheses=tuple(Hypothesis.model_validate(item) for item in state["hypotheses"]),
            draft=state["draft"],
            publishable_comment=state.get("publishable_comment"),
            published=state.get("published", False),
        )
