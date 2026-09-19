"""Persistence seen by the orchestrator.

`RunStore` is the only thing the orchestrator knows about storage, so the orchestrator is
tested with `worker.testing.InMemoryRunStore` — no database, no network.
`SqlRunStore` is the production implementation on top of the `db` models.
"""

from __future__ import annotations

import mimetypes
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from contracts.run import ApprovalDecision, NodeStatus, RunStatus, WorkflowGraph
from db.models import AgentOutput, Approval, ExecutionLog, ExecutionRun


@dataclass
class RunSnapshot:
    run_id: UUID
    status: RunStatus
    graph: WorkflowGraph
    node_status: dict[UUID, NodeStatus] = field(default_factory=dict)
    retry_counts: dict[UUID, int] = field(default_factory=dict)
    outputs: dict[UUID, dict[str, Any]] = field(default_factory=dict)


class RunStore(Protocol):
    def load(self, run_id: UUID) -> RunSnapshot: ...
    def run_status(self, run_id: UUID) -> RunStatus: ...
    def set_run_status(self, run_id: UUID, status: RunStatus) -> None: ...
    def set_node_status(
        self,
        run_id: UUID,
        node_id: UUID,
        status: NodeStatus,
        *,
        retry_count: int | None = None,
        error: str | None = None,
    ) -> None: ...
    def save_output(self, run_id: UUID, node_id: UUID, output: dict[str, Any]) -> None: ...
    def approval(self, run_id: UUID, node_id: UUID) -> ApprovalDecision | None: ...


def _now() -> datetime:
    return datetime.now(UTC)


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
            )
            success_ids = {log.id: log.node_id for log in logs if log.status == NodeStatus.SUCCESS}
            if success_ids:
                rows = s.scalars(
                    select(AgentOutput).where(AgentOutput.log_id.in_(success_ids), AgentOutput.output_type == "text")
                ).all()
                for row in rows:
                    snapshot.outputs[success_ids[row.log_id]] = row.content_json or {}
            return snapshot

    def run_status(self, run_id: UUID) -> RunStatus:
        with self._sessions() as s:
            return RunStatus(s.scalar(select(ExecutionRun.status).where(ExecutionRun.id == run_id)))

    def set_run_status(self, run_id: UUID, status: RunStatus) -> None:
        with self._sessions.begin() as s:
            run = s.get(ExecutionRun, run_id)
            run.status = status.value
            if status == RunStatus.RUNNING and run.started_at is None:
                run.started_at = _now()
            if status in (RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED):
                run.completed_at = _now()
                run.failed_nodes = s.scalar(
                    select(func.count()).where(ExecutionLog.run_id == run_id, ExecutionLog.status == NodeStatus.FAILED)
                )

    def set_node_status(self, run_id, node_id, status, *, retry_count=None, error=None) -> None:
        with self._sessions.begin() as s:
            log = s.scalar(select(ExecutionLog).where(ExecutionLog.run_id == run_id, ExecutionLog.node_id == node_id))
            if log is None:
                raise LookupError(f"no execution_logs row for run {run_id} node {node_id}")
            now = _now()
            log.status = status.value
            if retry_count is not None:
                log.retry_count = retry_count
            if error:
                prefix = f"[attempt {log.retry_count + (0 if status == NodeStatus.RETRYING else 1)}] "
                log.error_message = f"{log.error_message}\n{prefix}{error}" if log.error_message else prefix + error
            if status == NodeStatus.RUNNING and log.started_at is None:
                log.started_at = now
            if status in (NodeStatus.SUCCESS, NodeStatus.FAILED, NodeStatus.SKIPPED):
                log.completed_at = now
                if log.started_at is not None:
                    started = log.started_at if log.started_at.tzinfo else log.started_at.replace(tzinfo=UTC)
                    log.duration_ms = int((now - started).total_seconds() * 1000)

    def save_output(self, run_id: UUID, node_id: UUID, output: dict[str, Any]) -> None:
        with self._sessions.begin() as s:
            log_id = s.scalar(
                select(ExecutionLog.id).where(ExecutionLog.run_id == run_id, ExecutionLog.node_id == node_id)
            )
            s.add(AgentOutput(log_id=log_id, output_type="text", content_json=output))
            for key, value in output.items():
                if isinstance(value, str) and key.endswith("_path"):
                    mime, size = self._describe_file(value)
                    s.add(
                        AgentOutput(log_id=log_id, output_type="file", storage_path=value, mime_type=mime, bytes=size)
                    )
                elif isinstance(value, list) and key.endswith("_paths"):
                    for v in value:
                        mime, size = self._describe_file(v)
                        s.add(
                            AgentOutput(log_id=log_id, output_type="file", storage_path=v, mime_type=mime, bytes=size)
                        )
                elif isinstance(value, str) and key == "remote_url":
                    s.add(AgentOutput(log_id=log_id, output_type="url", content=value))

    def approval(self, run_id: UUID, node_id: UUID) -> ApprovalDecision | None:
        with self._sessions() as s:
            decision = s.scalar(
                select(Approval.decision)
                .join(ExecutionLog, ExecutionLog.id == Approval.log_id)
                .where(ExecutionLog.run_id == run_id, ExecutionLog.node_id == node_id)
                .order_by(Approval.decided_at.desc())
                .limit(1)
            )
            return ApprovalDecision(decision) if decision else None

    def mark_interrupted(self, run_id: UUID) -> None:
        """Used when a worker restarts mid-node (RB-01): a `running` node is put back to `pending`."""
        with self._sessions.begin() as s:
            s.execute(
                update(ExecutionLog)
                .where(ExecutionLog.run_id == run_id, ExecutionLog.status.in_(["running", "retrying"]))
                .values(status="pending")
            )
