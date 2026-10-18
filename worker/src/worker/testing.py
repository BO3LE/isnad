"""An in-memory RunStore for orchestrator tests. No database, no network."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from contracts.agent import Revision
from contracts.run import TERMINAL_RUN_STATUSES, ApprovalDecision, NodeStatus, RunStatus, WorkflowGraph
from worker.store import Decision, RunSnapshot


class InMemoryRunStore:
    def __init__(self) -> None:
        self.runs: dict[UUID, RunStatus] = {}
        self.graphs: dict[UUID, WorkflowGraph] = {}
        self.nodes: dict[tuple[UUID, UUID], dict[str, Any]] = {}
        self.outputs: dict[tuple[UUID, UUID], dict[str, Any]] = {}
        # The decision on what a step waits with now: a plain ApprovalDecision, or a Decision with a note.
        self.approvals: dict[tuple[UUID, UUID], ApprovalDecision | Decision] = {}
        # Decisions on a step's earlier results, oldest first (each redo moves one here).
        self.decided: dict[tuple[UUID, UUID], list[Decision]] = {}
        self.history: list[tuple[str, NodeStatus | RunStatus]] = []
        self.users: dict[UUID, UUID] = {}

    def create_run(self, run_id: UUID, graph: WorkflowGraph, user_id: UUID | None = None) -> None:
        self.runs[run_id] = RunStatus.QUEUED
        if user_id is not None:
            self.users[run_id] = user_id
        self.graphs[run_id] = graph
        for node in graph.nodes:
            self.nodes[(run_id, node.id)] = {
                "status": NodeStatus.PENDING,
                "retry_count": 0,
                "errors": [],
                "revision": 0,
            }

    def load(self, run_id: UUID) -> RunSnapshot:
        snap = RunSnapshot(
            run_id=run_id, status=self.runs[run_id], graph=self.graphs[run_id], user_id=self.users.get(run_id)
        )
        for (rid, nid), row in self.nodes.items():
            if rid == run_id:
                snap.node_status[nid] = row["status"]
                snap.retry_counts[nid] = row["retry_count"]
                if (rid, nid) in self.outputs:
                    snap.outputs[nid] = self.outputs[(rid, nid)]
        return snap

    def run_status(self, run_id: UUID) -> RunStatus:
        return self.runs[run_id]

    def set_run_status(self, run_id: UUID, status: RunStatus) -> RunStatus:
        if self.runs[run_id] not in TERMINAL_RUN_STATUSES:  # as SqlRunStore: a finished run stays finished
            self.runs[run_id] = status
            self.history.append(("run", status))
        return self.runs[run_id]

    def set_node_status(self, run_id, node_id, status, *, retry_count=None, error=None) -> None:
        row = self.nodes[(run_id, node_id)]
        row["status"] = status
        if retry_count is not None:
            row["retry_count"] = retry_count
        if error:
            row["errors"].append(error)
        self.history.append((str(node_id), status))

    def complete_node(
        self,
        run_id: UUID,
        node_id: UUID,
        output: dict[str, Any],
        *,
        retry_count: int,
        status: NodeStatus = NodeStatus.SUCCESS,
    ) -> None:
        self.outputs[(run_id, node_id)] = output
        self.set_node_status(run_id, node_id, status, retry_count=retry_count)

    def approval(self, run_id: UUID, node_id: UUID) -> Decision | None:
        decision = self.approvals.get((run_id, node_id))
        return Decision(decision) if isinstance(decision, ApprovalDecision) else decision

    def accept_result(self, run_id: UUID, node_id: UUID, output: dict[str, Any] | None = None) -> None:
        if output is not None:
            self.outputs[(run_id, node_id)] = output
        self.set_node_status(run_id, node_id, NodeStatus.SUCCESS)

    def start_redo(self, run_id: UUID, node_id: UUID) -> None:
        key = (run_id, node_id)
        self.decided.setdefault(key, []).append(self.approval(run_id, node_id))
        del self.approvals[key]
        self.nodes[key]["revision"] += 1
        self.nodes[key]["retry_count"] = 0
        self.set_node_status(run_id, node_id, NodeStatus.PENDING)

    def revision_request(self, run_id: UUID, node_id: UUID) -> Revision | None:
        earlier = self.decided.get((run_id, node_id))
        if not earlier or earlier[-1].decision != ApprovalDecision.REDO:
            return None
        return Revision(note=earlier[-1].note or "", previous=self.outputs.get((run_id, node_id), {}))

    def status_of(self, run_id: UUID, node_id: UUID) -> NodeStatus:
        return self.nodes[(run_id, node_id)]["status"]
