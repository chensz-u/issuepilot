from typing import Protocol

from pydantic import BaseModel


class TraceSpan(BaseModel):
    name: str
    duration_ms: float
    attributes: dict[str, str | int | float | bool]


class WorkflowTrace(BaseModel):
    id: str
    mode: str
    spans: tuple[TraceSpan, ...]


class TraceStore(Protocol):
    def save(self, trace: WorkflowTrace) -> None: ...

    def get(self, trace_id: str) -> WorkflowTrace: ...


class InMemoryTraceStore:
    def __init__(self) -> None:
        self._traces: dict[str, WorkflowTrace] = {}

    def save(self, trace: WorkflowTrace) -> None:
        self._traces[trace.id] = trace

    def get(self, trace_id: str) -> WorkflowTrace:
        return self._traces[trace_id]
