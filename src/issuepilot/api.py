import json
import os
from contextlib import asynccontextmanager

import aiosqlite
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from pydantic import BaseModel, Field, ValidationError

from issuepilot.domain import Approval, DiagnoseRequest, DiagnosisResult, KnowledgeDocument
from issuepilot.generator import OpenAIResponsesGenerator
from issuepilot.investigation_domain import Investigation
from issuepilot.investigation_graph import InvestigationService
from issuepilot.investigation_store import InvestigationStore
from issuepilot.investigation_tools import GitHubEvidenceClient, InvestigationToolRegistry
from issuepilot.repository import SQLiteRepository
from issuepilot.retrieval import HybridRetriever
from issuepilot.trace import WorkflowTrace
from issuepilot.workflow import DiagnosisWorkflow

DEMO_SOURCE_URL = "https://github.com/chenyi-c/issuepilot/blob/main/data/demo_documents.json"


class InvestigationRequest(BaseModel):
    repository: str
    title: str = Field(min_length=3, max_length=200)
    body: str = Field(min_length=3, max_length=10_000)


class ApprovalDecision(BaseModel):
    decision: str


def create_app(
    workflow: DiagnosisWorkflow, investigation_service: InvestigationService | None = None
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if investigation_service is not None:
            app.state.investigation_service = investigation_service
            yield
            return
        connection = await aiosqlite.connect(
            os.getenv("ISSUEPILOT_CHECKPOINT_PATH", "issuepilot-checkpoints.db")
        )
        checkpointer = AsyncSqliteSaver(connection)
        await checkpointer.setup()
        async with httpx.AsyncClient(timeout=20) as github_http:
            app.state.investigation_service = InvestigationService(
                checkpointer=checkpointer,
                store=InvestigationStore(
                    os.getenv("ISSUEPILOT_INVESTIGATION_PATH", "issuepilot-investigations.db")
                ),
                tools=InvestigationToolRegistry(
                    GitHubEvidenceClient(github_http, token=os.getenv("GITHUB_TOKEN"))
                ),
            )
            yield
        await connection.close()

    app = FastAPI(title="IssuePilot", version="0.2.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:8080"],
        allow_methods=["GET", "POST"],
        allow_headers=["content-type"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        mode = "model" if workflow.generator is not None else "deterministic_fallback"
        return {"status": "ok", "generation_mode": mode}

    @app.post("/api/diagnoses", response_model=DiagnosisResult)
    def diagnose(request: DiagnoseRequest) -> DiagnosisResult:
        return workflow.diagnose(request)

    @app.get("/api/traces/{trace_id}", response_model=WorkflowTrace)
    def get_trace(trace_id: str) -> WorkflowTrace:
        try:
            return workflow.traces.get(trace_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Trace not found") from error

    @app.post("/api/approvals/{approval_id}", response_model=Approval)
    def approve(approval_id: str) -> Approval:
        try:
            return workflow.approve(approval_id)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Approval not found") from error

    def investigations() -> InvestigationService:
        service = getattr(app.state, "investigation_service", investigation_service)
        if service is None:
            raise HTTPException(status_code=503, detail="Investigation service unavailable")
        return service

    @app.post("/api/investigations", response_model=Investigation, status_code=201)
    async def start_investigation(request: InvestigationRequest) -> Investigation:
        try:
            return await investigations().start(request.repository, request.title, request.body)
        except ValidationError as error:
            raise HTTPException(status_code=422, detail="repository must be owner/name") from error

    @app.get("/api/investigations/{investigation_id}", response_model=Investigation)
    async def get_investigation(investigation_id: str) -> Investigation:
        try:
            return investigations().store.get(investigation_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Investigation not found") from error

    @app.get("/api/investigations/{investigation_id}/events")
    async def get_investigation_events(investigation_id: str) -> Response:
        try:
            investigations().store.get(investigation_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Investigation not found") from error
        events = investigations().store.list_events(investigation_id)
        payload = "".join(
            f"id: {event.sequence}\nevent: {event.name}\n"
            f"data: {json.dumps(event.payload, sort_keys=True)}\n\n"
            for event in events
        )
        return Response(content=payload, media_type="text/event-stream")

    @app.post("/api/investigations/{investigation_id}/approval", response_model=Investigation)
    async def decide_investigation(
        investigation_id: str, request: ApprovalDecision
    ) -> Investigation:
        try:
            return await investigations().decide(investigation_id, request.decision)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Investigation not found") from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    return app


DEMO_DOCUMENTS = [
    KnowledgeDocument(
        id="demo-windows-cache",
        title="Windows package cache recovery",
        text=(
            "Clear only the package-manager cache, close processes holding wheel files, and retry."
        ),
        source_url=DEMO_SOURCE_URL,
        kind="resolved_issue",
    ),
    KnowledgeDocument(
        id="demo-python-version",
        title="Supported Python versions",
        text="Confirm the package supports the active Python version before changing dependencies.",
        source_url=DEMO_SOURCE_URL,
        kind="documentation",
    ),
    KnowledgeDocument(
        id="demo-lockfile",
        title="Reproducible dependency installation",
        text=(
            "Use the committed lock file and a clean environment to distinguish "
            "drift from code defects."
        ),
        source_url=DEMO_SOURCE_URL,
        kind="documentation",
    ),
]

repository = SQLiteRepository(os.getenv("ISSUEPILOT_DATABASE_PATH", "issuepilot.db"))
repository.upsert_documents(DEMO_DOCUMENTS)
api_key = os.getenv("OPENAI_API_KEY")
generator = None
if api_key:
    generator = OpenAIResponsesGenerator(
        api_key=api_key,
        model=os.getenv("OPENAI_MODEL", "gpt-5-mini"),
        http=httpx.Client(),
    )
app = create_app(
    DiagnosisWorkflow(HybridRetriever(repository.list_documents()), repository, generator=generator)
)
