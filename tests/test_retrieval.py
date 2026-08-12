from issuepilot.domain import KnowledgeDocument
from issuepilot.retrieval import HybridRetriever


def test_hybrid_retrieval_ranks_matching_resolution_first() -> None:
    documents = [
        KnowledgeDocument(
            id="issue-1",
            title="Startup fails after configuration rename",
            text="Version 2 renamed server.host to api.host. Update the environment setting.",
            source_url="https://github.com/example/project/issues/1",
            kind="resolved_issue",
        ),
        KnowledgeDocument(
            id="docs-1",
            title="UI colors",
            text="Change the dashboard theme from the settings page.",
            source_url="https://example.com/docs/theme",
            kind="documentation",
        ),
    ]

    hits = HybridRetriever(documents).search("server.host startup version 2", limit=2)

    assert len(hits) == 1
    assert hits[0].document.id == "issue-1"
    assert hits[0].lexical_score > 0
    assert hits[0].vector_score > 0


def test_hybrid_retrieval_is_deterministic_for_ties() -> None:
    documents = [
        KnowledgeDocument(
            id="b",
            title="same",
            text="same text",
            source_url="https://example.com/b",
            kind="documentation",
        ),
        KnowledgeDocument(
            id="a",
            title="same",
            text="same text",
            source_url="https://example.com/a",
            kind="documentation",
        ),
    ]

    ids = [hit.document.id for hit in HybridRetriever(documents).search("same text", limit=2)]

    assert ids == ["a", "b"]


def test_hybrid_retrieval_returns_no_evidence_without_lexical_overlap() -> None:
    document = KnowledgeDocument(
        id="package-doc",
        title="Package cache",
        text="Clear wheel files before install.",
        source_url="https://example.com/package",
        kind="documentation",
    )

    assert HybridRetriever([document]).search("printer toner cartridge", limit=2) == []


def test_common_words_do_not_create_false_evidence() -> None:
    document = KnowledgeDocument(
        id="doc-1",
        title="Package support",
        text="The package is supported on Linux.",
        source_url="https://example.com/doc-1",
        kind="documentation",
    )

    assert HybridRetriever([document]).search("The issue is not working") == []


def test_weak_version_overlap_does_not_ground_unrelated_issue() -> None:
    document = KnowledgeDocument(
        id="version-docs",
        title="Supported Python versions",
        text="Version 2 requires Python 3.12 or newer.",
        source_url="https://example.com/version-docs",
        kind="documentation",
    )

    hits = HybridRetriever([document]).search(
        "Printer firmware version failure Version 2 cyan toner cartridge is jammed"
    )

    assert hits == []
