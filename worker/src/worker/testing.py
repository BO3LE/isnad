"""An in-memory RunStore for orchestrator tests. No database, no network."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from contracts.run import ApprovalDecision, NodeStatus, RunStatus, WorkflowGraph
from worker.store import RunSnapshot


class InMemoryRunStore:
    def __init__(self) -> None:
        self.runs: dict[UUID, RunStatus] = {}
        self.graphs: dict[UUID, WorkflowGraph] = {}
        self.nodes: dict[tuple[UUID, UUID], dict[str, Any]] = {}
        self.outputs: dict[tuple[UUID, UUID], dict[str, Any]] = {}
        self.approvals: dict[tuple[UUID, UUID], ApprovalDecision] = {}
        self.history: list[tuple[str, NodeStatus | RunStatus]] = []

    def create_run(self, run_id: UUID, graph: WorkflowGraph) -> None:
        self.runs[run_id] = RunStatus.QUEUED
        self.graphs[run_id] = graph
        for node in graph.nodes:
            self.nodes[(run_id, node.id)] = {"status": NodeStatus.PENDING, "retry_count": 0, "errors": []}

    def load(self, run_id: UUID) -> RunSnapshot:
        snap = RunSnapshot(run_id=run_id, status=self.runs[run_id], graph=self.graphs[run_id])
        for (rid, nid), row in self.nodes.items():
            if rid == run_id:
                snap.node_status[nid] = row["status"]
                snap.retry_counts[nid] = row["retry_count"]
                if (rid, nid) in self.outputs:
                    snap.outputs[nid] = self.outputs[(rid, nid)]
        return snap

    def run_status(self, run_id: UUID) -> RunStatus:
        return self.runs[run_id]

    def set_run_status(self, run_id: UUID, status: RunStatus) -> None:
        self.runs[run_id] = status
        self.history.append(("run", status))

    def set_node_status(self, run_id, node_id, status, *, retry_count=None, error=None) -> None:
        row = self.nodes[(run_id, node_id)]
        row["status"] = status
        if retry_count is not None:
            row["retry_count"] = retry_count
        if error:
            row["errors"].append(error)
        self.history.append((str(node_id), status))

    def save_output(self, run_id: UUID, node_id: UUID, output: dict[str, Any]) -> None:
        self.outputs[(run_id, node_id)] = output

    def approval(self, run_id: UUID, node_id: UUID) -> ApprovalDecision | None:
        return self.approvals.get((run_id, node_id))

    def status_of(self, run_id: UUID, node_id: UUID) -> NodeStatus:
        return self.nodes[(run_id, node_id)]["status"]
