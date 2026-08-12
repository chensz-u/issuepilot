import argparse
import json
from pathlib import Path

from pydantic import BaseModel

from issuepilot.domain import DiagnoseRequest, KnowledgeDocument
from issuepilot.retrieval import HybridRetriever
from issuepilot.trace import InMemoryTraceStore
from issuepilot.workflow import DiagnosisWorkflow


class BenchmarkCase(BaseModel):
    id: str
    title: str
    body: str
    expected_document_id: str
    expected_tools: tuple[str, ...]


class EvaluationReport(BaseModel):
    benchmark: str = "synthetic-v1"
    case_count: int
    retrieval_hit_at_2: float
    citation_grounding_rate: float
    tool_selection_accuracy: float
    generation_mode: str = "deterministic_fallback"


class QualityGateError(RuntimeError):
    pass


def evaluate(workflow: DiagnosisWorkflow, cases: list[BenchmarkCase]) -> EvaluationReport:
    if not cases:
        raise ValueError("benchmark requires at least one case")
    retrieval_hits = 0
    grounded = 0
    correct_tools = 0
    for case in cases:
        result = workflow.diagnose(DiagnoseRequest(title=case.title, body=case.body))
        ids = {citation.document_id for citation in result.citations}
        retrieval_hits += case.expected_document_id in ids
        grounded += bool(result.citations) and all(
            f"[{citation.document_id}]" in result.draft for citation in result.citations
        )
        correct_tools += result.selected_tools == case.expected_tools
    count = len(cases)
    return EvaluationReport(
        case_count=count,
        retrieval_hit_at_2=round(retrieval_hits / count, 4),
        citation_grounding_rate=round(grounded / count, 4),
        tool_selection_accuracy=round(correct_tools / count, 4),
    )


def require_quality_floors(report: EvaluationReport) -> None:
    floors = {
        "retrieval_hit_at_2": 0.75,
        "citation_grounding_rate": 1.0,
        "tool_selection_accuracy": 1.0,
    }
    failures = [
        f"{name}={getattr(report, name):.4f} below {floor:.4f}"
        for name, floor in floors.items()
        if getattr(report, name) < floor
    ]
    if failures:
        raise QualityGateError("; ".join(failures))


def _load_models(path: Path, model: type[BaseModel]) -> list[BaseModel]:
    return [model.model_validate(item) for item in json.loads(path.read_text(encoding="utf-8"))]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the deterministic IssuePilot benchmark")
    parser.add_argument("--documents", type=Path, default=Path("data/demo_documents.json"))
    parser.add_argument("--benchmark", type=Path, default=Path("data/benchmark.json"))
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    documents = _load_models(arguments.documents, KnowledgeDocument)
    cases = _load_models(arguments.benchmark, BenchmarkCase)
    workflow = DiagnosisWorkflow(HybridRetriever(documents), InMemoryTraceStore())
    report = evaluate(workflow, cases)  # type: ignore[arg-type]
    require_quality_floors(report)
    payload = report.model_dump_json(indent=2) + "\n"
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(payload, encoding="utf-8", newline="\n")
    print(payload, end="")


if __name__ == "__main__":
    main()
