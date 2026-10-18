"""Persistence seen by the orchestrator.

`RunStore` is the only thing the orchestrator knows about storage, so the orchestrator is
tested with `worker.testing.InMemoryRunStore` — no database, no network.
`SqlRunStore` is the production implementation on top of the `db` models.
"""

from __future__ import annotations

import mimetypes
from collections.abc import Collection
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from contracts.agent import Revision
from contracts.run import TERMINAL_RUN_STATUSES, ApprovalDecision, NodeStatus, RunStatus, WorkflowGraph
from db.models import AgentOutput, Approval, ExecutionLog, ExecutionRun, Workflow

# DESIGN-SYSTEM §23.5 ("Worker lost"), and why it isn't simply run again.
INTERRUPTED_SEND = (
    "This step was interrupted because the server restarted. It may already have sent or published, so it "
    "isn't repeated by itself: check first, then run again if it didn't."
)


@dataclass(frozen=True)
class Decision:
    """A person's decision on a step — on what it is about to send, or on the result it made."""

    decision: ApprovalDecision
    note: str | None = None
    edited: bool = False  # they changed the result's text before approving it


@dataclass
class RunSnapshot:
    run_id: UUID
    status: RunStatus
    graph: WorkflowGraph
    node_status: dict[UUID, NodeStatus] = field(default_factory=dict)
    retry_counts: dict[UUID, int] = field(default_factory=dict)
    # Of every step that has run: done, or waiting with its result for a person.
    outputs: dict[UUID, dict[str, Any]] = field(default_factory=dict)
    # The workflow's owner — files a run writes are stored under `{user_id}/{run_id}/`.
    user_id: UUID | None = None


class RunStore(Protocol):
    def load(self, run_id: UUID) -> RunSnapshot: ...
    def run_status(self, run_id: UUID) -> RunStatus: ...
    def set_run_status(self, run_id: UUID, status: RunStatus) -> RunStatus:
        """Returns the status the run has afterwards: a finished run keeps the one it finished with."""
        ...

    def set_node_status(
        self,
        run_id: UUID,
        node_id: UUID,
        status: NodeStatus,
        *,
        retry_count: int | None = None,
        error: str | None = None,
    ) -> None: ...
    def complete_node(
        self,
        run_id: UUID,
        node_id: UUID,
        output: dict[str, Any],
        *,
        retry_count: int,
        status: NodeStatus = NodeStatus.SUCCESS,
    ) -> None:
        """Saves the step's output and marks it `status` — both, or neither if the worker is lost.
        `awaiting_approval`: the result waits for a person. A redone step's output replaces the last."""
        ...

    def approval(self, run_id: UUID, node_id: UUID) -> Decision | None:
        """The decision on what the step waits with now — for a redone step, on its latest result."""
        ...

    def accept_result(self, run_id: UUID, node_id: UUID, output: dict[str, Any] | None = None) -> None:
        """A person approved the step's result: it is done, with `output` in place of it when edited."""
        ...

    def start_redo(self, run_id: UUID, node_id: UUID) -> None:
        """A person sent the result back: the step runs again, and what it makes is its next revision."""
        ...

    def revision_request(self, run_id: UUID, node_id: UUID) -> Revision | None:
        """What the person asked for when they sent the step's last result back; None on a first run."""
        ...


def _now() -> datetime:
    return datetime.now(UTC)


# The Writer's Word document (FR-04). Python's own table lacks it where the system has no MIME
# database — the worker image (python:3.13-slim) among them — so its type would be recorded as unknown.
mimetypes.add_type("application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx")


class SqlRunStore:
    def __init__(self, session_factory: sessionmaker[Session], storage_root: str | None = None):
        self._sessions = session_factory
        self._storage_root = Path(storage_root) if storage_root else None

    def _describe_file(self, storage_path: str) -> tuple[str | None, int | None]:
        """What a person needs to recognise a file before opening it: its type and its size.

        Both are columns the schema has always had and nothing filled, so every run reported a file
        with no size. The type comes from the name, which is enough for the kinds an agent writes;
        the size needs the file itself, and is left unset if it is not where we expect it.
        """
        mime, _ = mimetypes.guess_type(storage_path)
        size: int | None = None
        if self._storage_root is not None:
            candidate = self._storage_root / storage_path
            try:
                size = candidate.stat().st_size
            except OSError:
                size = None
        return mime, size

    def load(self, run_id: UUID) -> RunSnapshot:
        with self._sessions() as s:
            run = s.get(ExecutionRun, run_id)
            if run is None:
                raise LookupError(f"run {run_id} not found")
            logs = s.scalars(select(ExecutionLog).where(ExecutionLog.run_id == run_id)).all()
            snapshot = RunSnapshot(
                run_id=run_id,
                status=RunStatus(run.status),
                graph=WorkflowGraph.model_validate(run.graph_snapshot),
                node_status={log.node_id: NodeStatus(log.status) for log in logs},
                retry_counts={log.node_id: log.retry_count for log in logs},
                user_id=s.scalar(select(Workflow.user_id).where(Workflow.id == run.workflow_id)),
            )
            ran = {
                log.id: log.node_id for log in logs if log.status in (NodeStatus.SUCCESS, NodeStatus.AWAITING_APPROVAL)
            }
            if ran:
                rows = s.scalars(
                    select(AgentOutput).where(AgentOutput.log_id.in_(ran), AgentOutput.output_type == "text")
                ).all()
                for row in rows:
                    snapshot.outputs[ran[row.log_id]] = row.content_json or {}
            return snapshot

    def run_status(self, run_id: UUID) -> RunStatus:
        with self._sessions() as s:
            return RunStatus(s.scalar(select(ExecutionRun.status).where(ExecutionRun.id == run_id)))

    def set_run_status(self, run_id: UUID, status: RunStatus) -> RunStatus:
        """Record the run's status, and return the one it has afterwards.

        A finished run stays finished: succeeded, failed and cancelled are never replaced, so a cancel
        that lands while the last step runs isn't turned into `succeeded` — nor into `failed` by a step
        that then fails. The row is locked, as the API's cancel locks it, so the two can't interleave.
        The API cancels without `completed_at` while a step is still running; the worker's next write
        here, once that step has ended, is what records when the run ended.
        """
        with self._sessions.begin() as s:
            run = s.get(ExecutionRun, run_id, with_for_update=True)
            current = RunStatus(run.status)
            if current not in TERMINAL_RUN_STATUSES:
                run.status, current = status.value, status
                if status == RunStatus.RUNNING and run.started_at is None:
                    run.started_at = _now()
            if current in TERMINAL_RUN_STATUSES:
                run.completed_at = run.completed_at or _now()
                run.failed_nodes = s.scalar(
                    select(func.count()).where(ExecutionLog.run_id == run_id, ExecutionLog.status == NodeStatus.FAILED)
                )
            return current

    def set_node_status(self, run_id, node_id, status, *, retry_count=None, error=None) -> None:
        with self._sessions.begin() as s:
            _apply_node_status(self._log(s, run_id, node_id), status, retry_count=retry_count, error=error)

    def complete_node(
        self,
        run_id: UUID,
        node_id: UUID,
        output: dict[str, Any],
        *,
        retry_count: int,
        status: NodeStatus = NodeStatus.SUCCESS,
    ) -> None:
        """The step's output and its status, in one transaction.

        Two commits left a window: a worker lost between them left the step `running` with its output
        saved, and the redelivery ran it again and saved a second copy. Now a lost worker leaves
        neither, and the step simply runs again. A redone step's earlier result is replaced in the
        same transaction, so until then it is still there to be shown.
        """
        with self._sessions.begin() as s:
            log = self._log(s, run_id, node_id)
            self._replace_outputs(s, log.id, output)
            _apply_node_status(log, status, retry_count=retry_count)

    @staticmethod
    def _log(s: Session, run_id: UUID, node_id: UUID) -> ExecutionLog:
        log = s.scalar(select(ExecutionLog).where(ExecutionLog.run_id == run_id, ExecutionLog.node_id == node_id))
        if log is None:
            raise LookupError(f"no execution_logs row for run {run_id} node {node_id}")
        return log

    def _replace_outputs(self, s: Session, log_id: UUID, output: dict[str, Any]) -> None:
        s.execute(delete(AgentOutput).where(AgentOutput.log_id == log_id))
        s.add(AgentOutput(log_id=log_id, output_type="text", content_json=output))
        for key, value in output.items():
            if isinstance(value, str) and key.endswith("_path"):
                mime, size = self._describe_file(value)
                s.add(AgentOutput(log_id=log_id, output_type="file", storage_path=value, mime_type=mime, bytes=size))
            elif isinstance(value, list) and key.endswith("_paths"):
                for v in value:
                    mime, size = self._describe_file(v)
                    s.add(AgentOutput(log_id=log_id, output_type="file", storage_path=v, mime_type=mime, bytes=size))
            elif isinstance(value, str) and key == "remote_url":
                s.add(AgentOutput(log_id=log_id, output_type="url", content=value))

    def approval(self, run_id: UUID, node_id: UUID) -> Decision | None:
        with self._sessions() as s:
            row = s.execute(
                select(Approval.decision, Approval.note, Approval.edited)
                .join(ExecutionLog, ExecutionLog.id == Approval.log_id)
                .where(
                    ExecutionLog.run_id == run_id,
                    ExecutionLog.node_id == node_id,
                    Approval.revision == ExecutionLog.revision,
                )
                .order_by(Approval.decided_at.desc())
                .limit(1)
            ).first()
            return Decision(ApprovalDecision(row.decision), row.note, row.edited) if row else None

    def accept_result(self, run_id: UUID, node_id: UUID, output: dict[str, Any] | None = None) -> None:
        with self._sessions.begin() as s:
            log = self._log(s, run_id, node_id)
            if output is not None:
                self._replace_outputs(s, log.id, output)
            _apply_node_status(log, NodeStatus.SUCCESS)

    def start_redo(self, run_id: UUID, node_id: UUID) -> None:
        """The result stays until the new one replaces it (complete_node): it is what the agent is
        told it made, and what the person still sees meanwhile."""
        with self._sessions.begin() as s:
            log = self._log(s, run_id, node_id)
            log.revision += 1
            log.status = NodeStatus.PENDING.value
            log.retry_count = 0
            log.started_at = log.completed_at = log.duration_ms = log.error_message = None

    def revision_request(self, run_id: UUID, node_id: UUID) -> Revision | None:
        with self._sessions() as s:
            log = self._log(s, run_id, node_id)
            if log.revision == 0:
                return None
            asked = s.scalar(
                select(Approval).where(
                    Approval.log_id == log.id,
                    Approval.revision == log.revision - 1,
                    Approval.decision == ApprovalDecision.REDO.value,
                )
            )
            if asked is None:
                return None
            previous = s.scalar(
                select(AgentOutput.content_json).where(AgentOutput.log_id == log.id, AgentOutput.output_type == "text")
            )
            return Revision(note=(asked.note or "").strip(), previous=previous or {})

    def mark_interrupted(self, run_id: UUID, *, unrepeatable: Collection[str] = ()) -> None:
        """Used when a worker restarts mid-node (RB-01): a `running` node is put back to `pending`, so
        the new worker runs it again.

        Not a node whose agent type is in `unrepeatable` (those that send content out — Email,
        Publisher): the dead worker may have sent the email or finished the upload, and running it
        again could do it twice. It fails, saying so (INTERRUPTED_SEND), and the run stops there. A
        `retrying` node is waiting out a backoff after an error that said a retry is safe, so it
        resumes either way.
        """
        with self._sessions.begin() as s:
            for log in s.scalars(
                select(ExecutionLog)
                .where(ExecutionLog.run_id == run_id, ExecutionLog.status.in_(["running", "retrying"]))
                .with_for_update()
            ):
                if log.status == "running" and log.agent_type in unrepeatable:
                    _apply_node_status(log, NodeStatus.FAILED, error=INTERRUPTED_SEND)
                else:
                    log.status = "pending"


def _apply_node_status(
    log: ExecutionLog, status: NodeStatus, *, retry_count: int | None = None, error: str | None = None
) -> None:
    now = _now()
    log.status = status.value
    if retry_count is not None:
        log.retry_count = retry_count
    if error:
        prefix = f"[attempt {log.retry_count + (0 if status == NodeStatus.RETRYING else 1)}] "
        log.error_message = f"{log.error_message}\n{prefix}{error}" if log.error_message else prefix + error
    if status == NodeStatus.RUNNING and log.started_at is None:
        log.started_at = now
    # A step that ran and waits with its result has finished its work: the time a person then takes
    # to review it isn't the step's. One that waits before it runs hasn't started.
    finished = status in (NodeStatus.SUCCESS, NodeStatus.FAILED, NodeStatus.SKIPPED) or (
        status == NodeStatus.AWAITING_APPROVAL and log.started_at is not None
    )
    if finished and log.completed_at is None:
        log.completed_at = now
        if log.started_at is not None:
            started = log.started_at if log.started_at.tzinfo else log.started_at.replace(tzinfo=UTC)
            log.duration_ms = int((now - started).total_seconds() * 1000)
