import pytest

from issuepilot.domain import Approval, Citation, DiagnosisResult, KnowledgeDocument
from issuepilot.evaluation import BenchmarkCase, QualityGateError, evaluate, require_quality_floors
from issuepilot.retrieval import HybridRetriever
from issuepilot.trace import InMemoryTraceStore
from issuepilot.workflow import DiagnosisWorkflow


def test_evaluation_reports_retrieval_citations_and_tool_accuracy() -> None:
    documents = [
        KnowledgeDocument(
            id="cache-resolution",
            title="Windows cache lock",
            text="Close wheel processes and clear the package cache.",
            source_url="https://example.com/cache",
            kind="resolved_issue",
        ),
        KnowledgeDocument(
            id="version-docs",
            title="Version support",
            text="Version 2 requires Python 3.12.",
            source_url="https://example.com/versions",
            kind="documentation",
        ),
    ]
    cases = [
        BenchmarkCase(
            id="case-1",
            title="Windows cache error",
            body="The wheel cache is locked",
            expected_document_id="cache-resolution",
            expected_tools=("search_similar_issues",),
        ),
        BenchmarkCase(
            id="case-2",
            title="Version 2 startup failure",
            body="Python version is unsupported",
            expected_document_id="version-docs",
            expected_tools=("search_similar_issues", "get_repository_context"),
        ),
    ]
    workflow = DiagnosisWorkflow(HybridRetriever(documents), InMemoryTraceStore())

    report = evaluate(workflow, cases)

    assert report.case_count == 2
    assert report.retrieval_hit_at_2 == 1.0
    assert report.citation_grounding_rate == 1.0
    assert report.tool_selection_accuracy == 1.0
    require_quality_floors(report)


def test_quality_gate_rejects_regression() -> None:
    workflow = DiagnosisWorkflow(HybridRetriever([]), InMemoryTraceStore())
    report = evaluate(
        workflow,
        [
            BenchmarkCase(
                id="missing",
                title="Unknown failure",
                body="No evidence exists",
                expected_document_id="absent",
                expected_tools=("search_similar_issues",),
            )
        ],
    )

    with pytest.raises(QualityGateError, match="retrieval_hit_at_2"):
        require_quality_floors(report)


def test_evaluation_rejects_model_draft_without_citation_ids() -> None:
    class UngroundedWorkflow:
        def diagnose(self, request: object) -> DiagnosisResult:
            return DiagnosisResult(
                draft="Restart everything without citing evidence.",
                mode="model",
                citations=(
                    Citation(
                        document_id="doc-1",
                        title="Restart guide",
                        source_url="https://example.com/restart",
                        score=1.0,
                    ),
                ),
                selected_tools=("search_similar_issues",),
                tool_executions=(),
                approval=Approval(id="approval-1"),
                trace_id="trace-1",
            )

    workflow = UngroundedWorkflow()
    case = BenchmarkCase(
        id="case",
        title="Worker restart failure",
        body="worker cannot restart",
        expected_document_id="doc-1",
        expected_tools=("search_similar_issues",),
    )

    report = evaluate(workflow, [case])  # type: ignore[arg-type]

    assert report.citation_grounding_rate == 0.0
    with pytest.raises(QualityGateError, match="citation_grounding_rate"):
        require_quality_floors(report)
