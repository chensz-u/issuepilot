import argparse
import asyncio
import json
import re
import tempfile
from pathlib import Path
from typing import Literal

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from pydantic import BaseModel

from issuepilot.investigation_domain import EvidenceArtifact, RepositoryRef
from issuepilot.investigation_graph import InvestigationService
from issuepilot.investigation_store import InvestigationStore


class InvestigationBenchmarkCase(BaseModel):
    id: str
    repository: str
    title: str
    body: str
    evidence: list[EvidenceArtifact]
    expected_evidence_ids: tuple[str, ...]
    expected_hypothesis_statuses: dict[str, Literal["supported", "rejected"]]


class InvestigationEvaluationReport(BaseModel):
    benchmark: str = "investigation-synthetic-v1"
    case_count: int
    evidence_recall: float
    relevance_precision: float
    hypothesis_support_rate: float
    citation_grounding_rate: float
    trajectory_completeness: float
    approval_safety: float


class InvestigationQualityError(RuntimeError):
    pass


class FixtureTools:
    names = ("fixture_evidence",)

    def __init__(self, evidence: list[EvidenceArtifact]) -> None:
        self.evidence = evidence

    async def execute(
        self, name: str, repository: RepositoryRef, query: str
    ) -> list[EvidenceArtifact]:
        return self.evidence


async def evaluate_investigations(
    cases: list[InvestigationBenchmarkCase],
) -> InvestigationEvaluationReport:
    if not cases:
        raise ValueError("benchmark requires at least one case")
    recall = precision = support = grounding = trajectory = safety = 0
    with tempfile.TemporaryDirectory(prefix="issuepilot-eval-") as directory:
        root = Path(directory)
        for index, case in enumerate(cases):
            async with AsyncSqliteSaver.from_conn_string(
                str(root / f"checkpoint-{index}.db")
            ) as checkpointer:
                store = InvestigationStore(root / f"projection-{index}.db")
                service = InvestigationService(checkpointer, store, FixtureTools(case.evidence))
                result = await service.start(case.repository, case.title, case.body)
                expected_ids = set(case.expected_evidence_ids)
                actual_ids = {
                    evidence_id
                    for hypothesis in result.hypotheses
                    if hypothesis.status == "supported"
                    for evidence_id in hypothesis.evidence_ids
                }
                recall += len(expected_ids & actual_ids) / len(expected_ids) if expected_ids else 1
                precision += (
                    len(expected_ids & actual_ids) / len(actual_ids)
                    if actual_ids
                    else int(not expected_ids)
                )
                actual_statuses = {
                    hypothesis.evidence_ids[0]: hypothesis.status
                    for hypothesis in result.hypotheses
                    if hypothesis.evidence_ids
                }
                support += actual_statuses == case.expected_hypothesis_statuses
                cited_ids = set(re.findall(r"\[([^\]]+)\]", result.draft))
                grounding += cited_ids == expected_ids == actual_ids
                if expected_ids:
                    safety += result.status == "awaiting_approval"
                    required_events = [
                        "validate",
                        "tools",
                        "hypothesize",
                        "synthesize",
                        "awaiting_approval",
                    ]
                else:
                    safety += (
                        result.status == "insufficient_evidence"
                        and "No grounded repository evidence" in result.draft
                        and any(
                            hypothesis.status == "insufficient_evidence"
                            for hypothesis in result.hypotheses
                        )
                    )
                    required_events = ["validate", "tools", "hypothesize", "synthesize"]
                events = store.list_events(result.id)
                trajectory += [event.name for event in events] == required_events and [
                    event.sequence for event in events
                ] == list(range(1, len(events) + 1))
    count = len(cases)
    return InvestigationEvaluationReport(
        case_count=count,
        evidence_recall=round(recall / count, 4),
        relevance_precision=round(precision / count, 4),
        hypothesis_support_rate=round(support / count, 4),
        citation_grounding_rate=round(grounding / count, 4),
        trajectory_completeness=round(trajectory / count, 4),
        approval_safety=round(safety / count, 4),
    )


def require_investigation_quality(report: InvestigationEvaluationReport) -> None:
    metric_names = (
        "evidence_recall",
        "relevance_precision",
        "hypothesis_support_rate",
        "citation_grounding_rate",
        "trajectory_completeness",
        "approval_safety",
    )
    failures = [name for name in metric_names if getattr(report, name) < 1.0]
    if failures:
        raise InvestigationQualityError("quality floors failed: " + ", ".join(failures))


async def _run(benchmark: Path, output: Path | None) -> None:
    cases = [
        InvestigationBenchmarkCase.model_validate(item)
        for item in json.loads(benchmark.read_text(encoding="utf-8"))
    ]
    report = await evaluate_investigations(cases)
    require_investigation_quality(report)
    payload = report.model_dump_json(indent=2) + "\n"
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8", newline="\n")
    print(payload, end="")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the IssuePilot investigation benchmark")
    parser.add_argument("--benchmark", type=Path, default=Path("data/investigation_benchmark.json"))
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    asyncio.run(_run(arguments.benchmark, arguments.output))


if __name__ == "__main__":
    main()
