import asyncio
from uuid import uuid4

import pytest
from conftest import ReverseAgent, SendAgent, chain

from contracts.run import ApprovalDecision, NodeStatus, RunStatus
from worker.orchestrator import Orchestrator, StepTimedOut, scrub


def _run(store, graph):
    run_id = uuid4()
    store.create_run(run_id, graph)
    return run_id


async def test_nodes_run_in_order_and_outputs_flow_downstream(store, registry, ports):
    graph = chain("shout", "reverse", config={"text": "hello"})
    run_id = _run(store, graph)
    status = await Orchestrator(store, registry, ports).execute(run_id)
    assert status == RunStatus.SUCCEEDED
    assert store.outputs[(run_id, graph.nodes[1].id)] == {"text": "OLLEH"}
    node_events = [s for who, s in store.history if who != "run"]
    assert node_events == [NodeStatus.RUNNING, NodeStatus.SUCCESS, NodeStatus.RUNNING, NodeStatus.SUCCESS]


async def test_retry_then_succeed_uses_exponential_backoff(store, registry, ports, sleeps):
    ReverseAgent.failures_before_success = 2
    graph = chain("shout", "reverse", config={"text": "abc"})
    run_id = _run(store, graph)
    status = await Orchestrator(store, registry, ports, sleep=sleeps, jitter=lambda: 0.5).execute(run_id)
    assert status == RunStatus.SUCCEEDED
    assert sleeps == [2.5, 4.5]
    assert store.nodes[(run_id, graph.nodes[1].id)]["retry_count"] == 2


async def test_retry_exhaustion_halts_run_and_skips_downstream(store, registry, ports, sleeps):
    """AT-06 / FR-06: exactly three retries, then failed; everything after it is skipped."""
    ReverseAgent.failures_before_success = 99
    graph = chain("shout", "reverse", "shout", config={"text": "abc"})
    run_id = _run(store, graph)
    status = await Orchestrator(store, registry, ports, sleep=sleeps, jitter=lambda: 0).execute(run_id)
    assert status == RunStatus.FAILED
    assert ReverseAgent.calls == 4
    assert sleeps == [2, 4, 8]
    assert store.nodes[(run_id, graph.nodes[1].id)]["retry_count"] == 3
    assert store.status_of(run_id, graph.nodes[1].id) == NodeStatus.FAILED
    assert store.status_of(run_id, graph.nodes[2].id) == NodeStatus.SKIPPED


async def test_non_retryable_error_fails_immediately(store, registry, ports, sleeps):
    ReverseAgent.failures_before_success = 1
    ReverseAgent.non_retryable = True
    graph = chain("shout", "reverse", config={"text": "abc"})
    run_id = _run(store, graph)
    assert await Orchestrator(store, registry, ports, sleep=sleeps).execute(run_id) == RunStatus.FAILED
    assert sleeps == []
    assert store.nodes[(run_id, graph.nodes[1].id)]["errors"] == ["Your Google connection has expired."]


async def test_approval_parks_then_resumes_without_rerunning_finished_nodes(store, registry, ports):
    """AT-09 / UC-04: nothing after the gate runs until someone approves."""
    graph = chain("shout", "gate", "reverse", config={"text": "abc"})
    run_id = _run(store, graph)
    orchestrator = Orchestrator(store, registry, ports)

    assert await orchestrator.execute(run_id) == RunStatus.AWAITING_APPROVAL
    assert store.status_of(run_id, graph.nodes[1].id) == NodeStatus.AWAITING_APPROVAL
    assert store.status_of(run_id, graph.nodes[2].id) == NodeStatus.PENDING

    store.approvals[(run_id, graph.nodes[1].id)] = ApprovalDecision.APPROVE
    assert await orchestrator.execute(run_id) == RunStatus.SUCCEEDED
    shout_runs = [s for who, s in store.history if who == str(graph.nodes[0].id) and s == NodeStatus.RUNNING]
    assert len(shout_runs) == 1
    assert store.outputs[(run_id, graph.nodes[2].id)] == {"text": "CBA:dehsilbup"}


async def test_rejection_halts_the_run(store, registry, ports):
    graph = chain("shout", "gate", "reverse", config={"text": "abc"})
    run_id = _run(store, graph)
    store.approvals[(run_id, graph.nodes[1].id)] = ApprovalDecision.REJECT
    assert await Orchestrator(store, registry, ports).execute(run_id) == RunStatus.FAILED
    assert store.status_of(run_id, graph.nodes[1].id) == NodeStatus.FAILED
    assert store.status_of(run_id, graph.nodes[2].id) == NodeStatus.SKIPPED


async def test_a_distribute_agent_waits_even_when_manifest_and_graph_say_it_neednt(store, registry, ports):
    """UC-04 can't rest on data the client writes: nothing goes out until a person approves."""
    graph = chain("shout", "send", config={"text": "abc"})
    assert graph.nodes[1].requires_approval is False
    run_id = _run(store, graph)
    orchestrator = Orchestrator(store, registry, ports)

    assert await orchestrator.execute(run_id) == RunStatus.AWAITING_APPROVAL
    assert store.status_of(run_id, graph.nodes[1].id) == NodeStatus.AWAITING_APPROVAL
    assert SendAgent.calls == 0

    store.approvals[(run_id, graph.nodes[1].id)] = ApprovalDecision.APPROVE
    assert await orchestrator.execute(run_id) == RunStatus.SUCCEEDED
    assert SendAgent.calls == 1


async def test_a_rejected_distribute_agent_never_sends(store, registry, ports):
    graph = chain("shout", "send", config={"text": "abc"})
    run_id = _run(store, graph)
    store.approvals[(run_id, graph.nodes[1].id)] = ApprovalDecision.REJECT
    assert await Orchestrator(store, registry, ports).execute(run_id) == RunStatus.FAILED
    assert SendAgent.calls == 0


async def test_unknown_agent_fails_with_a_readable_message(store, registry, ports):
    graph = chain("shout", "tiktok", config={"text": "abc"})
    run_id = _run(store, graph)
    assert await Orchestrator(store, registry, ports).execute(run_id) == RunStatus.FAILED
    assert "tiktok" in store.nodes[(run_id, graph.nodes[1].id)]["errors"][0]


async def test_cancelled_run_skips_remaining_nodes(store, registry, ports):
    graph = chain("shout", "reverse", config={"text": "abc"})
    run_id = _run(store, graph)
    store.runs[run_id] = RunStatus.RUNNING
    original = store.set_node_status

    def cancel_after_first_success(rid, nid, status, **kw):
        original(rid, nid, status, **kw)
        if status == NodeStatus.SUCCESS:
            store.runs[rid] = RunStatus.CANCELLED

    store.set_node_status = cancel_after_first_success
    assert await Orchestrator(store, registry, ports).execute(run_id) == RunStatus.CANCELLED
    assert store.status_of(run_id, graph.nodes[1].id) == NodeStatus.SKIPPED


async def test_an_attempt_past_the_step_deadline_is_stopped_and_not_retried(
    store, registry, ports, sleeps, monkeypatch
):
    calls = []

    async def hangs(self, input_data, ports):
        calls.append(1)
        await asyncio.sleep(30)  # a call with no timeout of its own

    monkeypatch.setattr(ReverseAgent, "execute", hangs)
    graph = chain("shout", "reverse", "shout", config={"text": "abc"})
    run_id = _run(store, graph)

    status = await Orchestrator(store, registry, ports, sleep=sleeps, step_timeout_s=0.05).execute(run_id)

    assert status == RunStatus.FAILED
    assert calls == [1] and sleeps == []  # stopped once, not retried
    assert store.nodes[(run_id, graph.nodes[1].id)]["errors"] == [
        "Reverse took longer than 0.05 seconds and was stopped."
    ]
    assert store.status_of(run_id, graph.nodes[2].id) == NodeStatus.SKIPPED


async def test_a_timeout_an_adapter_raises_is_still_retried(store, registry, ports, sleeps, monkeypatch):
    original = ReverseAgent.execute
    calls = []

    async def times_out_once(self, input_data, ports):
        calls.append(1)
        if len(calls) == 1:
            raise TimeoutError  # e.g. a read timeout inside an adapter: retryable, as before
        return await original(self, input_data, ports)

    monkeypatch.setattr(ReverseAgent, "execute", times_out_once)
    graph = chain("shout", "reverse", config={"text": "abc"})
    run_id = _run(store, graph)

    status = await Orchestrator(store, registry, ports, sleep=sleeps, jitter=lambda: 0, step_timeout_s=60).execute(
        run_id
    )

    assert status == RunStatus.SUCCEEDED
    assert len(calls) == 2 and sleeps == [2]


def test_minutes_read_as_minutes():
    assert StepTimedOut("Writer", 1800).message == "Writer took longer than 30 minutes and was stopped."


async def test_missing_input_is_reported_not_retried(store, registry, ports, sleeps):
    graph = chain("shout")
    run_id = _run(store, graph)
    assert await Orchestrator(store, registry, ports, sleep=sleeps).execute(run_id) == RunStatus.FAILED
    assert sleeps == []
    assert "missing input" in store.nodes[(run_id, graph.nodes[0].id)]["errors"][0]


def test_registry_catalog_includes_config_schema(registry):
    entry = next(m for m in registry.catalog() if m.name == "shout")
    assert entry.config_schema["properties"]["text"]["default"] == "hello"


async def test_outputs_from_all_ancestors_reach_later_steps(store, registry, ports):
    """Regression: the third step must see the first step's output too, not only its direct parent's."""
    from conftest import GateAgent

    captured = {}
    original = GateAgent.execute

    async def spy(self, input_data, ports):
        captured["text"] = input_data.text
        return await original(self, input_data, ports)

    graph = chain("shout", "reverse", "gate", config={"text": "abc"})
    run_id = _run(store, graph)
    store.approvals[(run_id, graph.nodes[2].id)] = ApprovalDecision.APPROVE
    GateAgent.execute = spy
    try:
        assert await Orchestrator(store, registry, ports).execute(run_id) == RunStatus.SUCCEEDED
    finally:
        GateAgent.execute = original
    assert captured["text"] == "CBA"


async def test_a_librarys_error_reaches_the_step_and_the_log_without_its_credentials(
    store, registry, ports, monkeypatch, caplog
):
    leaky = (
        "Client error '401' for url 'https://api.example.com/v1/search?api_key=tvly-SECRET1&q=x' "
        "via https://user:SECRET2@proxy.example.com with Authorization: Bearer SECRET3 token=SECRET4"
    )

    async def fails(self, input_data, ports):
        raise RuntimeError(leaky)

    monkeypatch.setattr(ReverseAgent, "execute", fails)
    graph = chain("shout", "reverse", config={"text": "abc"})
    run_id = _run(store, graph)

    assert await Orchestrator(store, registry, ports, max_retries=0).execute(run_id) == RunStatus.FAILED

    (shown,) = store.nodes[(run_id, graph.nodes[1].id)]["errors"]
    assert "Client error '401' for url 'https://api.example.com/v1/search?[redacted]'" in shown
    for text in (shown, caplog.text):
        assert "SECRET" not in text


@pytest.mark.parametrize(
    ("raw", "scrubbed"),
    [
        ("GET https://h.example/p?key=abc&x=1 failed", "GET https://h.example/p?[redacted] failed"),
        ("postgresql://isnad:hunter2@db:5432/gp refused", "postgresql://[redacted]@db:5432/gp refused"),
        ("header Authorization: Basic dXNlcjpwYXNz", "header Authorization: [redacted] [redacted]"),
        ('{"access_token": "ya29.abc"}', '{"access_token": "[redacted]"}'),
        ("client_secret=GOCSPX-abc; next", "client_secret=[redacted]; next"),
        ("FFmpeg exited with status 1", "FFmpeg exited with status 1"),
    ],
)
def test_scrub(raw, scrubbed):
    assert scrub(raw) == scrubbed
