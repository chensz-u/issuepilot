from typing import Literal

from pydantic import BaseModel, Field


class KnowledgeDocument(BaseModel):
    id: str
    title: str
    text: str
    source_url: str
    kind: Literal["resolved_issue", "documentation"]


class ImportedIssue(BaseModel):
    id: str
    number: int
    title: str
    body: str
    source_url: str
    labels: tuple[str, ...] = ()

    def as_document(self) -> KnowledgeDocument:
        return KnowledgeDocument(
            id=self.id,
            title=self.title,
            text=self.body,
            source_url=self.source_url,
            kind="resolved_issue",
        )


class SearchHit(BaseModel):
    document: KnowledgeDocument
    score: float
    lexical_score: float
    vector_score: float


class DiagnoseRequest(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    body: str = Field(min_length=3, max_length=10_000)


class Citation(BaseModel):
    document_id: str
    title: str
    source_url: str
    score: float


class ToolExecution(BaseModel):
    name: Literal["search_similar_issues", "get_repository_context"]
    status: Literal["completed"] = "completed"
    summary: str


class Approval(BaseModel):
    id: str
    status: Literal["pending", "approved", "blocked"] = "pending"
    publishable_comment: str | None = None
    published: bool = False


class DiagnosisResult(BaseModel):
    draft: str
    mode: Literal["deterministic_fallback", "model"]
    citations: tuple[Citation, ...]
    selected_tools: tuple[str, ...]
    tool_executions: tuple[ToolExecution, ...]
    approval: Approval
    trace_id: str
