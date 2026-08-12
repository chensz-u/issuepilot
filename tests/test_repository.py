from issuepilot.domain import KnowledgeDocument
from issuepilot.repository import SQLiteRepository
from issuepilot.trace import TraceSpan, WorkflowTrace


def test_repository_upserts_documents_and_persists_traces(tmp_path) -> None:
    repository = SQLiteRepository(tmp_path / "issuepilot.db")
    first = KnowledgeDocument(
        id="doc-1",
        title="Old title",
        text="old",
        source_url="https://example.com/1",
        kind="documentation",
    )
    updated = first.model_copy(update={"title": "New title", "text": "new"})
    repository.upsert_documents([first, updated])
    trace = WorkflowTrace(
        id="trace-1",
        mode="deterministic_fallback",
        spans=(TraceSpan(name="retrieve", duration_ms=1.2, attributes={"hit_count": 1}),),
    )
    repository.save(trace)

    assert repository.list_documents() == [updated]
    assert repository.get("trace-1") == trace
