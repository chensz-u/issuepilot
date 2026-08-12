from fastapi.testclient import TestClient

from issuepilot.api import create_app
from issuepilot.domain import KnowledgeDocument
from issuepilot.retrieval import HybridRetriever
from issuepilot.trace import InMemoryTraceStore
from issuepilot.workflow import DiagnosisWorkflow


def client() -> TestClient:
    documents = [
        KnowledgeDocument(
            id="fixture-1",
            title="Windows cache repair",
            text="Clear only the package cache, then retry installation.",
            source_url="https://example.com/issues/1",
            kind="resolved_issue",
        ),
        KnowledgeDocument(
            id="fixture-2",
            title="Supported versions",
            text="Version 2 requires Python 3.12 or newer.",
            source_url="https://example.com/docs/versions",
            kind="documentation",
        ),
    ]
    workflow = DiagnosisWorkflow(HybridRetriever(documents), InMemoryTraceStore())
    return TestClient(create_app(workflow))


def test_diagnose_trace_and_approval_flow() -> None:
    api = client()

    response = api.post(
        "/api/diagnoses",
        json={"title": "Install fails on Windows", "body": "Version 2 reports a cache error"},
    )

    assert response.status_code == 200
    diagnosis = response.json()
    assert diagnosis["mode"] == "deterministic_fallback"
    trace = api.get(f"/api/traces/{diagnosis['trace_id']}")
    assert trace.status_code == 200
    assert len(trace.json()["spans"]) == 4
    approval = api.post(f"/api/approvals/{diagnosis['approval']['id']}")
    assert approval.json()["published"] is False
    assert approval.json()["status"] == "approved"


def test_health_exposes_truthful_mode() -> None:
    response = client().get("/health")

    assert response.json() == {"status": "ok", "generation_mode": "deterministic_fallback"}


def test_health_exposes_configured_model_mode() -> None:
    class Generator:
        name = "configured-model"

        def generate(self, query: str, evidence: str) -> str:
            return "draft"

    workflow = DiagnosisWorkflow(HybridRetriever([]), InMemoryTraceStore(), generator=Generator())

    response = TestClient(create_app(workflow)).get("/health")

    assert response.json() == {"status": "ok", "generation_mode": "model"}


def test_no_evidence_approval_returns_conflict() -> None:
    workflow = DiagnosisWorkflow(HybridRetriever([]), InMemoryTraceStore())
    api = TestClient(create_app(workflow))
    diagnosis = api.post(
        "/api/diagnoses", json={"title": "Printer failure", "body": "Toner is empty"}
    ).json()

    response = api.post(f"/api/approvals/{diagnosis['approval']['id']}")

    assert diagnosis["approval"]["status"] == "blocked"
    assert response.status_code == 409
