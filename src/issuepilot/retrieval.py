import hashlib
import math
import re

from rank_bm25 import BM25Plus

from issuepilot.domain import KnowledgeDocument, SearchHit

TOKEN_PATTERN = re.compile(r"[a-z0-9_.-]+", re.IGNORECASE)
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "for",
    "in",
    "is",
    "it",
    "not",
    "of",
    "on",
    "or",
    "the",
    "this",
    "to",
    "with",
}
LOW_SIGNAL_TERMS = {"error", "fail", "failed", "failure", "issue", "problem", "version"}


def tokenize(text: str) -> list[str]:
    normalized = (token.lower().strip("._-") for token in TOKEN_PATTERN.findall(text))
    return [token for token in normalized if token and token not in STOPWORDS]


def _hash_vector(tokens: list[str], dimensions: int = 64) -> list[float]:
    vector = [0.0] * dimensions
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        vector[index] += -1.0 if digest[4] & 1 else 1.0
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def _cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


class HybridRetriever:
    def __init__(self, documents: list[KnowledgeDocument]) -> None:
        unique = {document.id: document for document in documents}
        self.documents = [unique[key] for key in sorted(unique)]
        self._tokens = [tokenize(f"{doc.title} {doc.text}") for doc in self.documents]
        self._bm25 = BM25Plus(self._tokens) if self._tokens else None

    def search(self, query: str, limit: int = 5) -> list[SearchHit]:
        if limit < 1:
            raise ValueError("limit must be positive")
        query_tokens = tokenize(query)
        query_vector = _hash_vector(query_tokens)
        lexical_scores = self._bm25.get_scores(query_tokens) if self._bm25 else []
        hits: list[SearchHit] = []
        for index, (document, tokens) in enumerate(zip(self.documents, self._tokens, strict=True)):
            shared_tokens = set(query_tokens) & set(tokens)
            has_specific_match = any(
                token not in LOW_SIGNAL_TERMS and not token.isdigit() for token in shared_tokens
            )
            lexical = float(lexical_scores[index])
            vector = max(0.0, _cosine(query_vector, _hash_vector(tokens)))
            score = lexical * 0.7 + vector * 0.3
            if len(shared_tokens) >= 2 and has_specific_match:
                hits.append(
                    SearchHit(
                        document=document,
                        score=round(score, 6),
                        lexical_score=round(lexical, 6),
                        vector_score=round(vector, 6),
                    )
                )
        return sorted(hits, key=lambda hit: (-hit.score, hit.document.id))[:limit]
