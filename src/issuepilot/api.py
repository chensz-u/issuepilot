import os

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from issuepilot.domain import Approval, DiagnoseRequest, DiagnosisResult, KnowledgeDocument
from issuepilot.generator import OpenAIResponsesGenerator
from issuepilot.repository import SQLiteRepository
from issuepilot.retrieval import HybridRetriever
from issuepilot.trace import WorkflowTrace
from issuepilot.workflow import DiagnosisWorkflow

DEMO_SOURCE_URL = "https://github.com/chenyi-c/issuepilot/blob/main/data/demo_documents.json"


def create_app(workflow: DiagnosisWorkflow) -> FastAPI:
    app = FastAPI(title="IssuePilot", version="0.1.0")
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
