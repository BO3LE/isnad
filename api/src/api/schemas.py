"""HTTP request and response models. Anything that also crosses into the worker lives in `contracts`."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from contracts.run import ApprovalDecision, RunStatus, WorkflowGraph


class Message(BaseModel):
    detail: str


class DevLoginRequest(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=320)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"


class Me(BaseModel):
    id: UUID
    email: str


class RunSummary(BaseModel):
    id: UUID
    status: RunStatus
    created_at: datetime
    completed_at: datetime | None = None
    # A failed run and a run a person stopped look identical from the outside, so the list called
    # both "Failed". Present only when the run ended for a reason the status cannot express.
    reason: Literal["rejected"] | None = None


class WorkflowCreate(BaseModel):
    name: str = Field("Untitled workflow", min_length=1, max_length=200)
    graph: WorkflowGraph = Field(default_factory=WorkflowGraph)


class WorkflowUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    graph: WorkflowGraph | None = None


class WorkflowOut(BaseModel):
    id: UUID
    name: str
    status: str
    graph: WorkflowGraph
    created_at: datetime
    updated_at: datetime


class WorkflowSummary(BaseModel):
    id: UUID
    name: str
    status: str
    agent_types: list[str]
    updated_at: datetime
    last_run: RunSummary | None = None


class ValidationIssue(BaseModel):
    code: str
    message: str
    severity: Literal["error", "warning"] = "error"
    node_id: UUID | None = None
    edge_id: str | None = None


class ValidationResult(BaseModel):
    valid: bool
    issues: list[ValidationIssue]


class RunCreated(BaseModel):
    run_id: UUID
    status: RunStatus


class ApprovalRequest(BaseModel):
    decision: ApprovalDecision
    note: str | None = Field(None, max_length=2000)


class OutputLink(BaseModel):
    id: UUID
    url: str
    expires_in: int


class RunOutput(BaseModel):
    """One thing a run produced. `id` is what GET /outputs/{id} turns into a download URL."""

    id: UUID
    node_id: UUID
    agent_type: str
    kind: Literal["text", "file", "url"]
    filename: str | None = None
    mime_type: str | None = None
    bytes: int | None = None
    created_at: datetime
