import re
import time
from uuid import uuid4

import httpx

from issuepilot.domain import Approval, Citation, DiagnoseRequest, DiagnosisResult
from issuepilot.generator import DraftGenerator
from issuepilot.retrieval import HybridRetriever
from issuepilot.tools import execute_read_only_tools
from issuepilot.trace import TraceSpan, TraceStore, WorkflowTrace

SECRET_PATTERN = re.compile(r"(?i)(token|api[_-]?key|password)\s*[=:]\s*\S+")
AUTHORIZATION_PATTERN = re.compile(r"(?i)authorization\s*:\s*bearer\s+\S+")


def redact_sensitive_text(text: str) -> str:
    redacted = AUTHORIZATION_PATTERN.sub("Authorization: Bearer [REDACTED]", text)
    return SECRET_PATTERN.sub(r"\1=[REDACTED]", redacted)


class DiagnosisWorkflow:
    def __init__(
        self,
        retriever: HybridRetriever,
        traces: TraceStore,
        generator: DraftGenerator | None = None,
    ) -> None:
        self.retriever = retriever
        self.traces = traces
        self.generator = generator
        self._approvals: dict[str, tuple[Approval, str]] = {}

    def diagnose(self, request: DiagnoseRequest) -> DiagnosisResult:
        query = f"{request.title} {request.body}"
        start = time.perf_counter()
        hits = self.retriever.search(query, limit=2)
        retrieval_ms = (time.perf_counter() - start) * 1000
        selected_tools = self._select_tools(query) if hits else ()
        tool_executions = execute_read_only_tools(selected_tools, hits)
        citations = tuple(
            Citation(
                document_id=hit.document.id,
                title=hit.document.title,
                source_url=hit.document.source_url,
                score=hit.score,
            )
            for hit in hits
        )
        evidence = "\n".join(
            f"- [{hit.document.id}] {hit.document.title}: {hit.document.text}" for hit in hits
        )
        fallback_draft = (
            f"## Diagnosis\n\nLikely relevant evidence:\n{evidence}\n\n"
            "## Next step\n\nVerify the cited resolution in a non-production "
            "environment before applying it."
        )
        mode = "deterministic_fallback"
        draft = (
            fallback_draft if hits else "No grounded evidence was found; no diagnosis is proposed."
        )
        provider = "deterministic"
        if self.generator is not None and hits:
            try:
                generated = self.generator.generate(query, evidence)
                if all(f"[{citation.document_id}]" in generated for citation in citations):
                    draft = generated
                    mode = "model"
                    provider = self.generator.name
            except (httpx.HTTPError, ValueError):
                pass
        approval = Approval(id=str(uuid4()), status="pending" if hits else "blocked")
        self._approvals[approval.id] = (approval, draft)
        trace_id = str(uuid4())
        trace = WorkflowTrace(
            id=trace_id,
            mode=mode,
            spans=(
                TraceSpan(
                    name="retrieve",
                    duration_ms=round(retrieval_ms, 3),
                    attributes={
                        "hit_count": len(hits),
                        "query": redact_sensitive_text(query),
                    },
                ),
                TraceSpan(
                    name="select_tools",
                    duration_ms=0.0,
                    attributes={"tools": ",".join(selected_tools)},
                ),
                TraceSpan(
                    name="execute_tools",
                    duration_ms=0.0,
                    attributes={
                        "execution_count": len(tool_executions),
                        "summaries": " | ".join(item.summary for item in tool_executions),
                    },
                ),
                TraceSpan(
                    name="generate",
                    duration_ms=0.0,
                    attributes={"provider": provider, "citation_count": len(citations)},
                ),
            ),
        )
        self.traces.save(trace)
        return DiagnosisResult(
            draft=draft,
            mode=mode,
            citations=citations,
            selected_tools=selected_tools,
            tool_executions=tool_executions,
            approval=approval,
            trace_id=trace_id,
        )

    def approve(self, approval_id: str) -> Approval:
        approval, draft = self._approvals[approval_id]
        if approval.status == "blocked":
            raise ValueError("diagnosis without grounded evidence cannot be approved")
        approved = approval.model_copy(
            update={"status": "approved", "publishable_comment": draft, "published": False}
        )
        self._approvals[approval_id] = (approved, draft)
        return approved

    @staticmethod
    def _select_tools(text: str) -> tuple[str, ...]:
        lowered = text.lower()
        tools = ["search_similar_issues"]
        if "version" in lowered or re.search(r"\bv?\d+\.\d+", lowered):
            tools.append("get_repository_context")
        return tuple(tools)
