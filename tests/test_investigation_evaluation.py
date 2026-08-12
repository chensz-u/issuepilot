import json
from pathlib import Path

import pytest

from issuepilot.investigation_evaluation import (
    InvestigationBenchmarkCase,
    evaluate_investigations,
    require_investigation_quality,
)


@pytest.mark.asyncio
async def test_investigation_evaluation_measures_full_evidence_chain() -> None:
    cases = [
        InvestigationBenchmarkCase(
            id="cache",
            repository="acme/widget",
            title="Cache lock",
            body="CI package cache is locked",
            evidence=[
                {
                    "id": "issue-7",
                    "kind": "issue",
                    "title": "Cache lock repair",
                    "preview": "Stop the worker before clearing the locked cache.",
                    "source_url": "https://github.com/acme/widget/issues/7",
                    "tool": "search_issues",
                }
            ],
            expected_evidence_ids=("issue-7",),
            expected_hypothesis_statuses={"issue-7": "supported"},
        ),
        InvestigationBenchmarkCase(
            id="none",
            repository="acme/widget",
            title="Printer jam",
            body="Cyan toner is stuck",
            evidence=[],
            expected_evidence_ids=(),
            expected_hypothesis_statuses={},
        ),
    ]

    report = await evaluate_investigations(cases)

    assert report.evidence_recall == 1.0
    assert report.relevance_precision == 1.0
    assert report.hypothesis_support_rate == 1.0
    assert report.citation_grounding_rate == 1.0
    assert report.trajectory_completeness == 1.0
    assert report.approval_safety == 1.0
    require_investigation_quality(report)


def test_committed_investigation_benchmark_is_not_trivial() -> None:
    cases = json.loads(Path("data/investigation_benchmark.json").read_text(encoding="utf-8"))

    assert len(cases) >= 5
    assert any(not case["expected_evidence_ids"] for case in cases)
    assert all(
        any(status == "rejected" for status in case["expected_hypothesis_statuses"].values())
        for case in cases
    )
    assert {item["kind"] for case in cases for item in case["evidence"]} >= {
        "issue",
        "workflow",
        "commit",
        "repository",
    }
