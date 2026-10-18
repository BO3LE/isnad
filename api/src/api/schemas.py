"""HTTP request and response models. Anything that also crosses into the worker lives in `contracts`."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from contracts.run import ApprovalDecision, ApprovalInfo, RunStatus, WorkflowGraph


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
    # For a reject, why (required); for a redo, what to change.
    note: str | None = Field(None, max_length=2000)
    # Approving a step's result: the person's own version of its editable fields (GET …/result),
    # by name. A "text" field takes a string; a "lines" field a list of them.
    edits: dict[str, str | list[str]] | None = None


class EditableField(BaseModel):
    """One part of a step's result a person may change before approving it."""

    name: str
    title: str = Field(description="What the agent calls it, e.g. 'article'")
    kind: Literal["text", "lines"]
    value: str | list[str]


class StepResult(BaseModel):
    """What a step that has run made, as its reviewer edits it — GET /runs/{run_id}/nodes/{node_id}/result."""

    node_id: UUID
    agent_type: str
    revision: int = Field(description="0 for the step's first result, 1 after one redo, and so on")
    editable: list[EditableField] = Field(description="Empty when nothing in it is text a person may change")


class ApprovalRecord(ApprovalInfo):
    """One decision in a run's audit trail — GET /runs/{run_id}/approvals (UC-04, S-06)."""

    node_id: UUID
    agent_type: str


class OutputLink(BaseModel):
    """How to get at one output: a URL for a file, the words themselves for text."""

    id: UUID
    url: str | None = None
    expires_in: int = 0
    text: str | None = None


class RunOutput(BaseModel):
    """One thing a run produced.

    `id` is what GET /outputs/{id} resolves: a download URL for a file, the content itself for
    text. `filename`, `mime_type` and `bytes` are a file's; text and links carry none of them.
    """

    id: UUID
    node_id: UUID
    agent_type: str
    kind: Literal["text", "file", "url"]
    filename: str | None = None
    mime_type: str | None = None
    bytes: int | None = None
    created_at: datetime


class Connection(BaseModel):
    """A connected account on S-09 and in the credential picker (D-09). Never carries a token.

    `access` is what it was connected for: `youtube`, or `drive_gmail` — Google won't grant both in
    one consent, so one account can have a connection for each (`all`: connected before that split).
    `status`: `expired` once Google has refused the connection or `expires_at` has passed;
    `expiring` within 7 days of `expires_at`; otherwise `connected`. `expires_at` is empty when
    Google gave no end date. `scopes` are the granted services as a person reads them
    ("YouTube", "Drive", "Gmail"). `used_by` counts this user's workflows whose steps reference it.
    """

    id: UUID
    provider: Literal["google"]
    account_email: str
    access: Literal["youtube", "drive_gmail", "all"]
    scopes: list[str]
    status: Literal["connected", "expiring", "expired"]
    expires_at: datetime | None = None
    created_at: datetime
    used_by: int


class ConnectStart(BaseModel):
    """Send the browser (or a popup) here. Valid for 10 minutes, in the browser that asked."""

    authorization_url: str
