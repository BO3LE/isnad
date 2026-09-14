from uuid import uuid4

from conftest import ReverseAgent, chain

from contracts.run import ApprovalDecision, NodeStatus, RunStatus
from worker.orchestrator import Orchestrator


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
