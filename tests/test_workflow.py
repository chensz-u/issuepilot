import pytest

from issuepilot.domain import DiagnoseRequest, KnowledgeDocument
from issuepilot.retrieval import HybridRetriever
from issuepilot.trace import InMemoryTraceStore
from issuepilot.workflow import DiagnosisWorkflow


def test_diagnosis_is_grounded_traced_and_requires_approval() -> None:
    documents = [
        KnowledgeDocument(
            id="resolution-7",
            title="Windows upgrade error",
            text="On Windows, clear the stale wheel cache and retry the locked upgrade.",
            source_url="https://github.com/acme/widget/issues/7",
            kind="resolved_issue",
        ),
        KnowledgeDocument(
            id="docs-cache",
            title="Cache recovery",
            text="The cache command is safe and does not delete project files.",
            source_url="https://acme.example/docs/cache",
            kind="documentation",
        ),
    ]
    traces = InMemoryTraceStore()
    workflow = DiagnosisWorkflow(HybridRetriever(documents), traces)

    result = workflow.diagnose(
        DiagnoseRequest(
            title="Upgrade fails on Windows",
            body="Version 2.1 throws a locked cache error. token=super-secret",
        )
    )

    assert result.mode == "deterministic_fallback"
    assert len(result.citations) == 1
    assert result.selected_tools == ("search_similar_issues", "get_repository_context")
    assert [execution.name for execution in result.tool_executions] == [
        "search_similar_issues",
        "get_repository_context",
    ]
    assert all(execution.status == "completed" for execution in result.tool_executions)
    assert result.approval.status == "pending"
    assert result.approval.publishable_comment is None
    trace = traces.get(result.trace_id)
    assert [span.name for span in trace.spans] == [
        "retrieve",
        "select_tools",
        "execute_tools",
        "generate",
    ]
    assert "super-secret" not in trace.model_dump_json()


def test_approval_returns_comment_without_publishing() -> None:
    document = KnowledgeDocument(
        id="docs-1",
        title="Install",
        text="Use the supported installer.",
        source_url="https://example.com/install",
        kind="documentation",
    )
    workflow = DiagnosisWorkflow(HybridRetriever([document]), InMemoryTraceStore())
    result = workflow.diagnose(DiagnoseRequest(title="Install fails", body="installer error"))

    approval = workflow.approve(result.approval.id)

    assert approval.status == "approved"
    assert approval.publishable_comment == result.draft
    assert approval.published is False


def test_trace_redacts_authorization_bearer_credentials() -> None:
    traces = InMemoryTraceStore()
    workflow = DiagnosisWorkflow(HybridRetriever([]), traces)

    result = workflow.diagnose(
        DiagnoseRequest(
            title="Authentication failure",
            body="Authorization: Bearer ghp_supersecret credential rejected",
        )
    )

    assert "ghp_supersecret" not in traces.get(result.trace_id).model_dump_json()


def test_no_evidence_blocks_approval_and_unsupported_draft() -> None:
    unrelated = KnowledgeDocument(
        id="version-docs",
        title="Supported Python versions",
        text="Version 2 requires Python 3.12 or newer.",
        source_url="https://example.com/version-docs",
        kind="documentation",
    )
    workflow = DiagnosisWorkflow(HybridRetriever([unrelated]), InMemoryTraceStore())

    result = workflow.diagnose(
        DiagnoseRequest(
            title="Printer firmware version failure",
            body="Version 2 cyan toner cartridge is jammed",
        )
    )

    assert result.citations == ()
    assert result.tool_executions == ()
    assert result.approval.status == "blocked"
    assert "No grounded evidence" in result.draft
    with pytest.raises(ValueError, match="cannot be approved"):
        workflow.approve(result.approval.id)


def test_ungrounded_model_output_falls_back_to_cited_draft() -> None:
    class UngroundedGenerator:
        name = "ungrounded"

        def generate(self, query: str, evidence: str) -> str:
            return "Restart everything."

    document = KnowledgeDocument(
        id="doc-1",
        title="Worker restart",
        text="Restart only the worker.",
        source_url="https://example.com/doc-1",
        kind="documentation",
    )
    workflow = DiagnosisWorkflow(
        HybridRetriever([document]), InMemoryTraceStore(), generator=UngroundedGenerator()
    )

    result = workflow.diagnose(
        DiagnoseRequest(title="Worker restart failure", body="Worker cannot restart")
    )

    assert result.mode == "deterministic_fallback"
    assert "[doc-1]" in result.draft
