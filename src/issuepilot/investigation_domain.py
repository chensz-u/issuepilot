import re
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

OWNER_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")


class RepositoryRef(BaseModel):
    owner: str
    name: str

    @model_validator(mode="after")
    def validate_full_name(self) -> "RepositoryRef":
        if (
            not OWNER_PATTERN.fullmatch(self.owner)
            or not NAME_PATTERN.fullmatch(self.name)
            or self.name in {".", ".."}
        ):
            raise ValueError("repository must be owner/name")
        return self

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"

    @classmethod
    def parse(cls, value: str) -> "RepositoryRef":
        owner, separator, name = value.partition("/")
        if not separator or "/" in name:
            return cls(owner=value, name="")
        return cls(owner=owner, name=name)


class EvidenceArtifact(BaseModel):
    id: str
    kind: Literal["repository", "issue", "workflow", "commit", "source", "error"]
    title: str
    preview: str = Field(max_length=800)
    source_url: str
    tool: str


class Hypothesis(BaseModel):
    id: str
    statement: str
    status: Literal["proposed", "supported", "rejected", "insufficient_evidence"]
    evidence_ids: tuple[str, ...] = ()


class InvestigationEvent(BaseModel):
    sequence: int
    name: str
    payload: dict[str, Any]


class InvestigationStep(BaseModel):
    id: str
    title: str
    command: tuple[str, ...]
    rationale: str
    evidence_ids: tuple[str, ...]
    status: Literal["proposed"] = "proposed"


class Investigation(BaseModel):
    id: str
    repository: RepositoryRef
    title: str
    body: str
    status: Literal["running", "awaiting_approval", "approved", "rejected", "insufficient_evidence"]
    evidence: tuple[EvidenceArtifact, ...] = ()
    hypotheses: tuple[Hypothesis, ...] = ()
    plan: tuple[InvestigationStep, ...] = ()
    draft: str = ""
    publishable_comment: str | None = None
    published: bool = False
