"""A full run lifecycle: API-shaped rows in → real orchestrator + SqlRunStore + installed agents → rows out.

GP-plan W3 (C7). Everything is real except the outside world: adapters are the fakes that
`FAKE_ADAPTERS=true` selects, and there is no Celery broker — the test calls the orchestrator
exactly as `worker.celery_app.run_workflow` does.
"""

from __future__ import annotations

import dataclasses
import itertools
import uuid

import pytest
from sqlalchemy import select

from contracts.errors import AgentError
from contracts.graph import topological_order
from contracts.run import REJECTED_BY_REVIEWER, ApprovalDecision, NodeStatus, RunStatus, WorkflowGraph
from db.models import AgentOutput, Approval, ExecutionLog, ExecutionRun
from worker.orchestrator import Orchestrator

pytestmark = pytest.mark.integration

BLOG = "Blog post"
VIDEO = "Blog → Video → YouTube"
EMAIL = "Research → PDF → Email"


# ------------------------------------------------------------------ helpers


def _run(db, run_id: uuid.UUID) -> ExecutionRun:
    with db.sessions() as s:
        return s.get(ExecutionRun, run_id)


def _logs(db, run_id: uuid.UUID) -> list[ExecutionLog]:
    with db.sessions() as s:
        return list(
            s.scalars(
                select(ExecutionLog).where(ExecutionLog.run_id == run_id).order_by(ExecutionLog.position_order)
            ).all()
        )


def _outputs(db, log_id: uuid.UUID) -> list[AgentOutput]:
    with db.sessions() as s:
        return list(s.scalars(select(AgentOutput).where(AgentOutput.log_id == log_id)).all())


def _decide(db, run_id: uuid.UUID, node_id: uuid.UUID, decision: ApprovalDecision, note: str | None = None) -> None:
    """Mirror of `POST /runs/{id}/nodes/{node}/approve` (api/routers/runs.py) up to the enqueue."""
    with db.sessions.begin() as s:
        row = s.scalar(select(ExecutionLog).where(ExecutionLog.run_id == run_id, ExecutionLog.node_id == node_id))
        assert row.status == NodeStatus.AWAITING_APPROVAL
        s.add(Approval(log_id=row.id, decision=decision.value, decided_by=db.demo_user_id(), note=note))
        s.get(ExecutionRun, run_id).status = RunStatus.QUEUED.value


def _assert_finished_in_order(db, run_id: uuid.UUID, store) -> list[ExecutionLog]:
    """Every node succeeded, one after another, in topological order, with its timings recorded."""
    run = _run(db, run_id)
    graph = WorkflowGraph.model_validate(run.graph_snapshot)
    logs = _logs(db, run_id)

    assert [log.node_id for log in logs] == [n.id for n in topological_order(graph)]
    for log in logs:
        assert log.status == NodeStatus.SUCCESS, (log.agent_type, log.status, log.error_message)
        assert log.started_at is not None and log.completed_at is not None
        assert log.completed_at >= log.started_at
        assert log.duration_ms is not None and log.duration_ms >= 0
    for before, after in itertools.pairwise(logs):
        assert after.started_at >= before.completed_at, f"{after.agent_type} started before {before.agent_type} ended"

    # The same order as the orchestrator wrote it: a node only starts once the one before it succeeded.
    node_events = [nid for kind, nid, status in store.history if kind == "node" and status == "running"]
    assert list(dict.fromkeys(node_events)) == [log.node_id for log in logs]

    assert run.status == RunStatus.SUCCEEDED
    assert run.started_at is not None and run.completed_at is not None
    assert run.failed_nodes == 0
    assert run.total_nodes == len(logs)
    return logs


# ------------------------------------------------------------------ happy path


async def test_blog_template_runs_queued_to_succeeded(db, store, registry, ports):
    run_id = db.start_run(db.template(BLOG).id)
    assert _run(db, run_id).status == RunStatus.QUEUED
    assert {log.status for log in _logs(db, run_id)} == {NodeStatus.PENDING}

    status = await Orchestrator(store, registry, ports).execute(run_id)

    assert status == RunStatus.SUCCEEDED
    assert store.run_transitions() == ["running", "succeeded"]
    logs = _assert_finished_in_order(db, run_id, store)
    for log in logs:
        assert store.node_transitions(log.node_id) == ["running", "success"]
        assert log.retry_count == 0
        texts = [o for o in _outputs(db, log.id) if o.output_type == "text"]
        assert len(texts) == 1 and texts[0].content_json

    research, write = logs
    assert _outputs(db, research.id)[0].content_json["sources"]
    assert _outputs(db, write.id)[0].content_json["article_md"]


@pytest.mark.usefixtures("ffmpeg")
async def test_video_template_records_the_rendered_file(db, store, registry, ports, storage_root):
    """Blog → Video → YouTube: the video is a real MP4 on disk and an `agent_outputs` file row."""
    run_id = db.start_run(db.template(VIDEO).id)
    orchestrator = Orchestrator(store, registry, ports)

    assert await orchestrator.execute(run_id) == RunStatus.AWAITING_APPROVAL
    publish = _logs(db, run_id)[-1]
    assert publish.agent_type == "publisher"
    _decide(db, run_id, publish.node_id, ApprovalDecision.APPROVE)
    assert await orchestrator.execute(run_id) == RunStatus.SUCCEEDED

    logs = _assert_finished_in_order(db, run_id, store)
    video = next(log for log in logs if log.agent_type == "video")
    files = [o for o in _outputs(db, video.id) if o.output_type == "file"]
    assert len(files) == 1
    assert files[0].mime_type == "video/mp4"
    assert files[0].bytes and files[0].bytes > 0
    assert (storage_root / files[0].storage_path).stat().st_size == files[0].bytes

    urls = [o for o in _outputs(db, logs[-1].id) if o.output_type == "url"]
    assert len(urls) == 1 and urls[0].content


# ------------------------------------------------------------------ approval gate


async def test_email_template_parks_for_approval_then_resumes(db, store, registry, ports):
    run_id = db.start_run(db.template(EMAIL).id)
    orchestrator = Orchestrator(store, registry, ports)

    assert await orchestrator.execute(run_id) == RunStatus.AWAITING_APPROVAL

    run = _run(db, run_id)
    assert run.status == RunStatus.AWAITING_APPROVAL
    assert run.completed_at is None
    research, write, email = _logs(db, run_id)
    assert (research.status, write.status) == (NodeStatus.SUCCESS, NodeStatus.SUCCESS)
    assert email.agent_type == "email"
    assert email.status == NodeStatus.AWAITING_APPROVAL
    assert email.started_at is None
    assert _outputs(db, email.id) == []
    assert ports.email.sent == []  # the side effect has not happened

    # Parked again, not re-run, if the worker picks the run up before anyone decides.
    assert await orchestrator.execute(run_id) == RunStatus.AWAITING_APPROVAL
    assert ports.email.sent == []

    _decide(db, run_id, email.node_id, ApprovalDecision.APPROVE, note="looks good")
    assert _run(db, run_id).status == RunStatus.QUEUED
    assert await orchestrator.execute(run_id) == RunStatus.SUCCEEDED

    logs = _assert_finished_in_order(db, run_id, store)
    assert len(ports.email.sent) == 1
    # Researcher and writer ran once: the resume skipped them and fed their stored outputs forward.
    assert store.node_transitions(research.node_id) == ["running", "success"]
    assert store.node_transitions(write.node_id) == ["running", "success"]
    assert store.run_transitions() == [
        "running",
        "awaiting_approval",
        "running",
        "awaiting_approval",
        "running",
        "succeeded",
    ]
    subject = ports.email.sent[0][1]
    assert subject == _outputs(db, logs[1].id)[0].content_json["title"]


async def test_a_rejection_halts_the_run_and_skips_what_follows(db, store, registry, ports):
    """The email template with the writer gated too, so the rejected step has a step after it."""
    template = WorkflowGraph.model_validate(db.template(EMAIL).graph_definition)
    nodes = [
        n.model_copy(update={"requires_approval": True}) if n.agent_type == "writer" else n for n in template.nodes
    ]
    workflow_id = db.create_workflow(
        f"integration reject {uuid.uuid4().hex[:6]}", template.model_copy(update={"nodes": nodes})
    )
    run_id = db.start_run(workflow_id)
    orchestrator = Orchestrator(store, registry, ports)

    assert await orchestrator.execute(run_id) == RunStatus.AWAITING_APPROVAL
    research, write, email = _logs(db, run_id)
    assert (research.status, write.status, email.status) == ("success", "awaiting_approval", "pending")

    _decide(db, run_id, write.node_id, ApprovalDecision.REJECT, note="off-topic")
    assert await orchestrator.execute(run_id) == RunStatus.FAILED

    run = _run(db, run_id)
    research, write, email = _logs(db, run_id)
    assert run.status == RunStatus.FAILED
    assert run.completed_at is not None
    assert run.failed_nodes == 1
    assert research.status == NodeStatus.SUCCESS
    assert write.status == NodeStatus.FAILED
    assert REJECTED_BY_REVIEWER in write.error_message
    assert _outputs(db, write.id) == []
    assert email.status == NodeStatus.SKIPPED
    assert email.started_at is None
    assert ports.email.sent == []


# ------------------------------------------------------------------ retry


class FlakySearch:
    """Fails the first call the way a network blip does, then behaves like the fake it wraps."""

    def __init__(self, inner, failures: int = 1):
        self.inner, self.failures, self.calls = inner, failures, 0

    async def search(self, query: str, n: int):
        self.calls += 1
        if self.calls <= self.failures:
            raise AgentError("Couldn't reach the search service.")
        return await self.inner.search(query, n)


async def test_a_transient_failure_is_retried_and_recorded(db, store, registry, ports, sleeps):
    flaky = FlakySearch(ports.search)
    run_id = db.start_run(db.template(BLOG).id)

    status = await Orchestrator(
        store, registry, dataclasses.replace(ports, search=flaky), sleep=sleeps, jitter=lambda: 0.0
    ).execute(run_id)

    assert status == RunStatus.SUCCEEDED
    assert flaky.calls == 2
    assert sleeps == [2.0]  # 2**1 + jitter(0)
    research, write = _assert_finished_in_order(db, run_id, store)
    assert store.node_transitions(research.node_id) == ["running", "retrying", "running", "success"]
    assert research.retry_count == 1
    assert research.error_message == "[attempt 1] Couldn't reach the search service."
    assert write.retry_count == 0
