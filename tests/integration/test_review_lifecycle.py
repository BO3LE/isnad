"""Reviewing each step's result, end to end: real PostgreSQL, real SqlRunStore, the installed agents.

Researcher → Writer, both reviewed. The research is sent back with a note and redone, then approved
with the person's own notes; the article is approved with the person's edit, and its PDF is made
again from it. The decisions are written as `POST /runs/{id}/nodes/{node}/approve` writes them.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import select

from contracts.run import ApprovalDecision, GraphEdge, GraphNode, NodeStatus, Position, RunStatus, WorkflowGraph
from db.models import AgentOutput, Approval, ExecutionLog, ExecutionRun
from worker.orchestrator import Orchestrator

pytestmark = pytest.mark.integration

TOPIC = "Solar panels in deserts"


def _graph() -> WorkflowGraph:
    research = GraphNode(
        id=uuid.uuid4(),
        agent_type="researcher",
        configuration={"topic": TOPIC, "num_sources": 2},
        requires_approval=True,
    )
    write = GraphNode(
        id=uuid.uuid4(),
        agent_type="writer",
        configuration={"length": "short", "save_docx": False},
        requires_approval=True,
        position=Position(x=300),
    )
    return WorkflowGraph(nodes=[research, write], edges=[GraphEdge(id="e0", source=research.id, target=write.id)])


def _log(db, run_id: uuid.UUID, node_id: uuid.UUID) -> ExecutionLog:
    with db.sessions() as s:
        return s.scalar(select(ExecutionLog).where(ExecutionLog.run_id == run_id, ExecutionLog.node_id == node_id))


def _outputs(db, log_id: uuid.UUID) -> list[AgentOutput]:
    with db.sessions() as s:
        return list(s.scalars(select(AgentOutput).where(AgentOutput.log_id == log_id)).all())


def _result(db, log_id: uuid.UUID) -> dict[str, Any]:
    (text,) = (o for o in _outputs(db, log_id) if o.output_type == "text")
    return text.content_json


def _decide(db, run_id, node_id, decision: ApprovalDecision, *, note=None, edits: dict | None = None) -> None:
    """Mirror of the API's decide: on the step's current result, with any edit saved in its place."""
    with db.sessions.begin() as s:
        log = s.scalar(select(ExecutionLog).where(ExecutionLog.run_id == run_id, ExecutionLog.node_id == node_id))
        assert log.status == NodeStatus.AWAITING_APPROVAL
        if edits:
            result = s.scalar(
                select(AgentOutput).where(AgentOutput.log_id == log.id, AgentOutput.output_type == "text")
            )
            result.content_json = {**result.content_json, **edits}
        s.add(
            Approval(
                log_id=log.id,
                revision=log.revision,
                decision=decision.value,
                decided_by=db.demo_user_id(),
                note=note,
                edited=bool(edits),
            )
        )
        s.get(ExecutionRun, run_id).status = RunStatus.QUEUED.value


async def test_each_result_is_reviewed_redone_with_a_note_edited_and_approved(db, store, registry, ports, storage_root):
    graph = _graph()
    research, write = graph.nodes
    run_id = db.start_run(db.create_workflow("Reviewed research and writing", graph))
    orchestrator = Orchestrator(store, registry, ports)

    # 1. The research runs and waits with its result; the Writer hasn't started.
    assert await orchestrator.execute(run_id) == RunStatus.AWAITING_APPROVAL
    first = _log(db, run_id, research.id)
    assert (first.status, first.revision) == (NodeStatus.AWAITING_APPROVAL, 0)
    assert first.completed_at is not None  # its work is done; the wait is the reviewer's
    assert _log(db, run_id, write.id).status == NodeStatus.PENDING

    # 2. Sent back with a note: it searches again with the note, and waits with its new result.
    _decide(db, run_id, research.id, ApprovalDecision.REDO, note="only projects since 2024")
    assert await orchestrator.execute(run_id) == RunStatus.AWAITING_APPROVAL
    redone = _log(db, run_id, research.id)
    assert (redone.status, redone.revision) == (NodeStatus.AWAITING_APPROVAL, 1)
    assert len(_outputs(db, redone.id)) == 1  # the new result replaced the first
    titles = [s["title"] for s in _result(db, redone.id)["sources"]]
    assert all(f"{TOPIC} — only projects since 2024" in t for t in titles)

    # 3. Approved with the person's own notes: the Writer writes from them, and waits in its turn.
    _decide(db, run_id, research.id, ApprovalDecision.APPROVE, edits={"notes": ["Desert sun is strong."]})
    assert await orchestrator.execute(run_id) == RunStatus.AWAITING_APPROVAL
    assert _log(db, run_id, research.id).status == NodeStatus.SUCCESS
    assert "- Desert sun is strong." in ports.llm.prompts[0]
    article = _result(db, _log(db, run_id, write.id).id)
    assert article["pdf_path"]

    # 4. The article approved with the person's edit: its PDF is made again from the edit.
    _decide(db, run_id, write.id, ApprovalDecision.APPROVE, edits={"article_md": "# My title\n\nMy own words."})
    assert await orchestrator.execute(run_id) == RunStatus.SUCCEEDED
    written = _log(db, run_id, write.id)
    kept = _result(db, written.id)
    assert kept["article_md"] == "# My title\n\nMy own words."
    assert kept["pdf_path"] != article["pdf_path"]
    files = [o for o in _outputs(db, written.id) if o.output_type == "file"]
    assert [f.storage_path for f in files] == [kept["pdf_path"]]
    assert (storage_root / kept["pdf_path"]).read_bytes().startswith(b"%PDF-")

    with db.sessions() as s:
        decisions = s.execute(
            select(ExecutionLog.agent_type, Approval.revision, Approval.decision, Approval.edited)
            .join(ExecutionLog, ExecutionLog.id == Approval.log_id)
            .where(ExecutionLog.run_id == run_id)
            .order_by(Approval.decided_at)
        ).all()
    assert [tuple(d) for d in decisions] == [
        ("researcher", 0, "redo", False),
        ("researcher", 1, "approve", True),
        ("writer", 0, "approve", True),
    ]
