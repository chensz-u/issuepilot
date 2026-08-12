from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import StateGraph
from rank_bm25 import BM25Plus


def test_licensed_agent_dependencies_are_available() -> None:
    scorer = BM25Plus([["cache", "lock"], ["printer", "toner"], ["network", "timeout"]])

    assert scorer.get_scores(["cache"])[0] > scorer.get_scores(["cache"])[1]
    assert StateGraph is not None
    assert SqliteSaver is not None
