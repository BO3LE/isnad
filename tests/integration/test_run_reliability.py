"""What a run does when things go wrong: retries run out, errors that must not be retried, a person
cancels, the worker dies mid-run and the job is redelivered.

GP-plan W10 (C7). Same set-up as `test_run_lifecycle.py`: real PostgreSQL, the real orchestrator and
`SqlRunStore`, the installed agents, fake adapters; backoff sleeps are recorded, never waited out.
Tests marked `xfail(strict=True)` pin down behaviour that is wrong today — each reason says what and
where. When the code is fixed the test starts passing, strict mode turns that into a failure, and the
marker should be removed.
"""

from __future__ import annotations

import dataclasses
import uuid
from collections.abc import Callable
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from contracts.errors import AgentError, NonRetryableAgentError
from contracts.run import MAX_RETRIES, NodeStatus, RunStatus, WorkflowGraph
from db.models import AgentOutput, ExecutionLog, ExecutionRun
from worker.orchestrator import Orchestrator

pytestmark = pytest.mark.integration

BLOG = "Blog post"  # researcher → writer
EMAIL = "Research → PDF → Email"  # researcher → writer → email (approval-gated)


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


def _texts(db, log_id: uuid.UUID) -> list[AgentOutput]:
    return [o for o in _outputs(db, log_id) if o.output_type == "text"]


class WorkerKilled(BaseException):
    """Stands in for SIGKILL / OOM / a lost node: not an `Exception`, so no `except` in the worker sees it
    and nothing after the point it is raised gets to run — the rows stay exactly as the dead worker left them."""


class Search:
    """The fake search port, scripted: `behaviour(call_number)` may raise, return a result, or return None
    to fall through to the real fake."""

    def __init__(self, inner, behaviour: Callable[[int], object] = lambda _: None):
        self.inner, self.behaviour, self.calls = inner, behaviour, 0

    async def search(self, query: str, n: int):
        self.calls += 1
        result = self.behaviour(self.calls)
        return await self.inner.search(query, n) if result is None else result


class LLM:
    """The fake LLM port, counting calls, with a hook run before the call it wraps."""

    def __init__(self, inner, before: Callable[[int], None] = lambda _: None):
        self.inner, self.before, self.calls = inner, before, 0

    async def complete(self, prompt: str, **kwargs):
        self.calls += 1
        self.before(self.calls)
        return await self.inner.complete(prompt, **kwargs)


def _always(exc_factory: Callable[[], BaseException]) -> Callable[[int], object]:
    def behaviour(_: int) -> object:
        raise exc_factory()

    return behaviour


def _orchestrator(store, registry, ports, sleeps, **port_overrides) -> Orchestrator:
    return Orchestrator(
        store, registry, dataclasses.replace(ports, **port_overrides), sleep=sleeps, jitter=lambda: 0.25
    )


def _assert_skipped(log: ExecutionLog) -> None:
    assert log.status == NodeStatus.SKIPPED, (log.agent_type, log.status)
    assert log.started_at is None, f"{log.agent_type} was skipped but has a start time"
    assert log.retry_count == 0
    assert log.error_message is None


# ------------------------------------------------------------------ retry exhaustion


@pytest.mark.parametrize(
    ("make_error", "message"),
    [
        (lambda: AgentError("Couldn't reach the search service."), "Couldn't reach the search service."),
        # Anything that is not an AgentError has no `retryable` attribute and is retried by default.
        (lambda: ConnectionResetError("connection reset by peer"), "connection reset by peer"),
        (lambda: TimeoutError(), "TimeoutError"),
    ],
    ids=["agent-error", "connection-reset", "timeout"],
)
async def test_retries_run_out_then_the_step_fails_and_the_rest_are_skipped(
    db, store, registry, ports, sleeps, make_error, message
):
    search = Search(ports.search, _always(make_error))
    llm = LLM(ports.llm)
    run_id = db.start_run(db.template(EMAIL).id)

    status = await _orchestrator(store, registry, ports, sleeps, search=search, llm=llm).execute(run_id)

    assert status == RunStatus.FAILED
    # One first attempt + MAX_RETRIES retries, and not one more: the DB caps retry_count at 3.
    assert MAX_RETRIES == 3
    assert search.calls == MAX_RETRIES + 1
    # 2**attempt + jitter, for attempts 1..3 (M2 §7.3.3). No sleep after the last failure.
    assert sleeps == [2.25, 4.25, 8.25]

    research, write, email = _logs(db, run_id)
    assert store.node_transitions(research.node_id) == ["running"] + ["retrying", "running"] * 3 + ["failed"]
    assert research.status == NodeStatus.FAILED
    assert research.retry_count == MAX_RETRIES
    assert research.error_message.splitlines() == [f"[attempt {n}] {message}" for n in range(1, 5)]
    assert research.started_at is not None and research.completed_at is not None
    assert research.duration_ms is not None

    for downstream in (write, email):
        _assert_skipped(downstream)
    assert llm.calls == 0
    assert ports.email.sent == []
    for log in (research, write, email):
        assert _outputs(db, log.id) == [], f"{log.agent_type} left agent_outputs rows behind"

    run = _run(db, run_id)
    assert run.status == RunStatus.FAILED
    assert store.run_transitions() == ["running", "failed"]
    assert run.failed_nodes == 1
    assert run.completed_at is not None

    # A failed run is finished: the worker picking it up again (a redelivery) changes nothing.
    history = list(store.history)
    assert await _orchestrator(store, registry, ports, sleeps, search=search).execute(run_id) == RunStatus.FAILED
    assert store.history == history and search.calls == MAX_RETRIES + 1


# ------------------------------------------------------------------ non-retryable failures


def _no_sources(_: int) -> object:
    return []  # the Researcher itself raises NonRetryableAgentError("No sources found …")


def _malformed(_: int) -> object:
    # Not a `Source`: the Researcher's output fails validation — a pydantic ValidationError.
    return [SimpleNamespace(title="t", url="https://example.org", snippet="s")]


@pytest.mark.parametrize(
    ("behaviour", "fragment"),
    [
        (_no_sources, "No sources found for"),
        (_always(lambda: NonRetryableAgentError("The search API key was rejected.")), "API key was rejected"),
        (_always(lambda: AgentError("Quota used up for today.", retryable=False)), "Quota used up"),
        (_malformed, "sources.0"),
    ],
    ids=["agent-raises-non-retryable", "non-retryable-subclass", "retryable-false", "validation-error"],
)
async def test_a_non_retryable_error_fails_the_step_at_once(db, store, registry, ports, sleeps, behaviour, fragment):
    search = Search(ports.search, behaviour)
    run_id = db.start_run(db.template(EMAIL).id)

    status = await _orchestrator(store, registry, ports, sleeps, search=search).execute(run_id)

    assert status == RunStatus.FAILED
    assert search.calls == 1
    assert sleeps == []
    research, write, email = _logs(db, run_id)
    assert store.node_transitions(research.node_id) == ["running", "failed"]
    assert research.status == NodeStatus.FAILED
    assert research.retry_count == 0
    [line] = research.error_message.splitlines()
    assert line.startswith("[attempt 1] ") and fragment in line, line
    for downstream in (write, email):
        _assert_skipped(downstream)
    assert all(_outputs(db, log.id) == [] for log in (research, write, email))
    run = _run(db, run_id)
    assert (run.status, run.failed_nodes) == (RunStatus.FAILED, 1)
    assert run.completed_at is not None


async def test_missing_input_fails_the_step_before_it_runs(db, store, registry, ports, sleeps):
    """A ValidationError on the step's input: nothing is called, nothing is retried."""
    template = WorkflowGraph.model_validate(db.template(BLOG).graph_definition)
    nodes = [
        n.model_copy(update={"configuration": {k: v for k, v in n.configuration.items() if k != "topic"}})
        if n.agent_type == "researcher"
        else n
        for n in template.nodes
    ]
    workflow_id = db.create_workflow(
        f"integration no-topic {uuid.uuid4().hex[:6]}", template.model_copy(update={"nodes": nodes})
    )
    search = Search(ports.search)
    run_id = db.start_run(workflow_id)

    assert await _orchestrator(store, registry, ports, sleeps, search=search).execute(run_id) == RunStatus.FAILED

    assert search.calls == 0 and sleeps == []
    research, write = _logs(db, run_id)
    assert research.status == NodeStatus.FAILED
    assert research.retry_count == 0
    assert research.started_at is None  # it never ran
    assert "is missing input: topic" in research.error_message
    _assert_skipped(write)
    assert _run(db, run_id).failed_nodes == 1


# ------------------------------------------------------------------ cancel


async def test_cancel_mid_run_stops_at_the_next_step_and_keeps_what_was_made(db, store, registry, ports, sleeps):
    """Cancelled while the writer runs: the writer finishes, the email step never starts."""
    run_id = db.start_run(db.template(EMAIL).id)
    llm = LLM(ports.llm, before=lambda call: db.cancel_run(run_id) if call == 1 else None)

    status = await _orchestrator(store, registry, ports, sleeps, llm=llm).execute(run_id)

    assert status == RunStatus.CANCELLED
    run = _run(db, run_id)
    assert run.status == RunStatus.CANCELLED
    assert run.failed_nodes == 0
    research, write, email = _logs(db, run_id)
    # Already-produced outputs are kept — the step that was running when the cancel landed included.
    assert (research.status, write.status) == (NodeStatus.SUCCESS, NodeStatus.SUCCESS)
    assert len(_texts(db, research.id)) == 1
    assert len(_texts(db, write.id)) == 1
    _assert_skipped(email)
    assert _outputs(db, email.id) == []
    assert ports.email.sent == []
    assert llm.calls == 1
    assert "succeeded" not in store.run_transitions()

    # Cancelled is final: a later pick-up of the same job does nothing.
    history = list(store.history)
    assert await _orchestrator(store, registry, ports, sleeps).execute(run_id) == RunStatus.CANCELLED
    assert store.history == history


async def test_cancel_while_awaiting_approval(db, store, registry, ports, sleeps):
    run_id = db.start_run(db.template(EMAIL).id)
    orchestrator = _orchestrator(store, registry, ports, sleeps)
    assert await orchestrator.execute(run_id) == RunStatus.AWAITING_APPROVAL

    db.cancel_run(run_id)

    run = _run(db, run_id)
    research, write, email = _logs(db, run_id)
    assert run.status == RunStatus.CANCELLED
    assert (research.status, write.status) == (NodeStatus.SUCCESS, NodeStatus.SUCCESS)
    # No longer awaiting approval, so the approve endpoint answers 409 for it.
    _assert_skipped(email)
    assert len(_texts(db, research.id)) == 1 and len(_texts(db, write.id)) == 1

    history = list(store.history)
    assert await orchestrator.execute(run_id) == RunStatus.CANCELLED
    assert store.history == history
    assert ports.email.sent == []
    assert _outputs(db, email.id) == []


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason=(
        "BUG: a cancel that lands while the LAST step runs is overwritten — the loop ends and "
        "Orchestrator.execute sets SUCCEEDED (worker/src/worker/orchestrator.py:126) without re-reading the "
        "run status, and SqlRunStore.set_run_status lets a terminal status be replaced."
    ),
)
async def test_cancel_during_the_last_step_leaves_the_run_cancelled(db, store, registry, ports, sleeps):
    run_id = db.start_run(db.template(BLOG).id)
    llm = LLM(ports.llm, before=lambda call: db.cancel_run(run_id) if call == 1 else None)

    await _orchestrator(store, registry, ports, sleeps, llm=llm).execute(run_id)

    assert _run(db, run_id).status == RunStatus.CANCELLED


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason=(
        "BUG: the retry loop never checks for a cancel — _run_with_retry (worker/src/worker/orchestrator.py:"
        "129-157) keeps retrying through every backoff, then _finish_failed overwrites CANCELLED with FAILED."
    ),
)
async def test_cancel_during_a_retry_backoff_stops_retrying(db, store, registry, ports):
    run_id = db.start_run(db.template(EMAIL).id)
    search = Search(ports.search, _always(lambda: AgentError("Couldn't reach the search service.")))

    async def sleep_then_cancel(seconds: float) -> None:
        if search.calls == 1:
            db.cancel_run(run_id)

    await Orchestrator(
        store, registry, dataclasses.replace(ports, search=search), sleep=sleep_then_cancel, jitter=lambda: 0.0
    ).execute(run_id)

    assert _run(db, run_id).status == RunStatus.CANCELLED
    assert search.calls == 1


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason=(
        "BUG: a cancelled run never gets completed_at — the API's cancel (api/src/api/routers/runs.py:144) "
        "only sets status, and the orchestrator's cancel branch (worker/src/worker/orchestrator.py:89-91) "
        "returns without calling store.set_run_status(CANCELLED), the one place completed_at is written."
    ),
)
async def test_a_cancelled_run_records_when_it_ended(db, store, registry, ports, sleeps):
    run_id = db.start_run(db.template(EMAIL).id)
    llm = LLM(ports.llm, before=lambda call: db.cancel_run(run_id) if call == 1 else None)

    assert await _orchestrator(store, registry, ports, sleeps, llm=llm).execute(run_id) == RunStatus.CANCELLED

    assert _run(db, run_id).completed_at is not None


# ------------------------------------------------------------------ worker crash and redelivery


async def _redeliver(store, registry, ports, sleeps, run_id, **port_overrides) -> RunStatus:
    """What `worker.celery_app.run_workflow` does when the broker hands the job to a new worker."""
    store.mark_interrupted(run_id)
    return await _orchestrator(store, registry, ports, sleeps, **port_overrides).execute(run_id)


async def test_a_redelivered_run_resumes_at_the_interrupted_step(db, store, registry, ports, sleeps):
    def die_on_first_call(call: int) -> None:
        if call == 1:
            raise WorkerKilled

    search = Search(ports.search)
    llm = LLM(ports.llm, before=die_on_first_call)
    run_id = db.start_run(db.template(BLOG).id)

    with pytest.raises(WorkerKilled):
        await _orchestrator(store, registry, ports, sleeps, search=search, llm=llm).execute(run_id)

    # What the dead worker left behind.
    research, write = _logs(db, run_id)
    assert _run(db, run_id).status == RunStatus.RUNNING
    assert research.status == NodeStatus.SUCCESS
    assert write.status == NodeStatus.RUNNING
    assert _outputs(db, write.id) == []

    status = await _redeliver(store, registry, ports, sleeps, run_id, search=search, llm=llm)

    assert status == RunStatus.SUCCEEDED
    research, write = _logs(db, run_id)
    # The researcher ran once and was not re-run; its stored output fed the writer.
    assert search.calls == 1
    assert store.node_transitions(research.node_id) == ["running", "success"]
    assert len(_outputs(db, research.id)) == 1
    # The writer ran again from the top — a crash is not a failed attempt, so no retry is counted.
    assert llm.calls == 2
    assert store.node_transitions(write.node_id) == ["running", "running", "success"]
    assert write.status == NodeStatus.SUCCESS
    assert write.retry_count == 0 and write.error_message is None
    [text] = _texts(db, write.id)
    assert text.content_json["article_md"]
    run = _run(db, run_id)
    assert run.status == RunStatus.SUCCEEDED and run.failed_nodes == 0
    assert store.run_transitions() == ["running", "running", "succeeded"]


async def test_a_redelivered_run_keeps_the_retry_budget_it_had_used(db, store, registry, ports):
    """The worker dies during a backoff; the new worker carries on from retry 1, never past retry 3."""
    search = Search(ports.search, _always(lambda: AgentError("Couldn't reach the search service.")))
    run_id = db.start_run(db.template(BLOG).id)

    async def die(seconds: float) -> None:
        raise WorkerKilled

    with pytest.raises(WorkerKilled):
        await Orchestrator(
            store, registry, dataclasses.replace(ports, search=search), sleep=die, jitter=lambda: 0.0
        ).execute(run_id)
    research, _ = _logs(db, run_id)
    assert (research.status, research.retry_count) == (NodeStatus.RETRYING, 1)

    sleeps: list[float] = []

    async def record(seconds: float) -> None:
        sleeps.append(seconds)

    store.mark_interrupted(run_id)
    status = await Orchestrator(
        store, registry, dataclasses.replace(ports, search=search), sleep=record, jitter=lambda: 0.0
    ).execute(run_id)

    assert status == RunStatus.FAILED
    assert search.calls == MAX_RETRIES + 1  # 1 before the crash, 3 after
    assert sleeps == [4.0, 8.0]  # retries 2 and 3; retry 1's backoff died with the first worker
    research, write = _logs(db, run_id)
    assert research.retry_count == MAX_RETRIES
    assert [line.split("]")[0] for line in research.error_message.splitlines()] == [
        "[attempt 1",
        "[attempt 2",
        "[attempt 3",
        "[attempt 4",
    ]
    _assert_skipped(write)
    assert _run(db, run_id).failed_nodes == 1


class DiesBeforeMarkingSuccess:
    """Mixin for the store: the worker dies after `save_output` committed but before the step is marked
    `success` — two separate transactions in `_run_with_retry`."""

    def __init__(self, *args, node_id: uuid.UUID, **kwargs):
        super().__init__(*args, **kwargs)
        self.victim = node_id

    def set_node_status(self, run_id, node_id, status, **kwargs):
        if node_id == self.victim and status == NodeStatus.SUCCESS:
            raise WorkerKilled
        super().set_node_status(run_id, node_id, status, **kwargs)


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason=(
        "BUG: save_output and the SUCCESS status are separate commits (worker/src/worker/orchestrator.py:158-159), "
        "and SqlRunStore.save_output (worker/src/worker/store.py:138) only inserts. A worker lost between the two "
        "leaves the step `running` with its output saved; the redelivery re-runs it and saves a second copy."
    ),
)
async def test_a_crash_between_saving_output_and_marking_success_leaves_one_output(
    db, store, registry, ports, sleeps, session_factory, storage_root
):
    run_id = db.start_run(db.template(BLOG).id)
    _, write = _logs(db, run_id)
    crashing = type("CrashingStore", (DiesBeforeMarkingSuccess, type(store)), {})(
        session_factory, str(storage_root), node_id=write.node_id
    )

    with pytest.raises(WorkerKilled):
        await _orchestrator(crashing, registry, ports, sleeps).execute(run_id)
    _, write = _logs(db, run_id)
    assert write.status == NodeStatus.RUNNING and len(_texts(db, write.id)) == 1

    assert await _redeliver(store, registry, ports, sleeps, run_id) == RunStatus.SUCCEEDED

    assert len(_texts(db, write.id)) == 1
