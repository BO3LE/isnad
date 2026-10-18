"""A step the person reviews after it runs: it waits with its result, which they approve (as it is or
edited), reject, or send back with a note to be done again."""

from uuid import uuid4

from conftest import DraftAgent, ReverseAgent, SendAgent, chain

from contracts.run import REJECTED_BY_REVIEWER, ApprovalDecision, NodeStatus, RunStatus
from worker.orchestrator import Orchestrator
from worker.store import Decision


def _run(store, graph):
    run_id = uuid4()
    store.create_run(run_id, graph)
    return run_id


def _runs_of(store, node) -> int:
    return sum(1 for who, status in store.history if who == str(node.id) and status == NodeStatus.RUNNING)


async def test_a_reviewed_step_waits_with_its_result_and_nothing_after_it_runs(store, registry, ports):
    graph = chain("draft", "reverse", config={"text": "solar"}, review=(0,))
    run_id = _run(store, graph)

    assert await Orchestrator(store, registry, ports).execute(run_id) == RunStatus.AWAITING_APPROVAL

    assert store.status_of(run_id, graph.nodes[0].id) == NodeStatus.AWAITING_APPROVAL
    assert store.outputs[(run_id, graph.nodes[0].id)] == {"text": "draft of solar"}
    assert store.status_of(run_id, graph.nodes[1].id) == NodeStatus.PENDING
    assert ReverseAgent.calls == 0


async def test_an_approved_result_goes_on_to_the_next_step_without_running_again(store, registry, ports):
    graph = chain("draft", "reverse", config={"text": "solar"}, review=(0,))
    run_id = _run(store, graph)
    orchestrator = Orchestrator(store, registry, ports)
    await orchestrator.execute(run_id)

    store.approvals[(run_id, graph.nodes[0].id)] = ApprovalDecision.APPROVE
    assert await orchestrator.execute(run_id) == RunStatus.SUCCEEDED

    assert _runs_of(store, graph.nodes[0]) == 1
    assert store.outputs[(run_id, graph.nodes[1].id)] == {"text": "ralos fo tfard"}
    assert DraftAgent.edits == []  # not edited: the agent isn't asked to keep anything


async def test_a_rejected_result_stops_the_run(store, registry, ports):
    graph = chain("draft", "reverse", config={"text": "solar"}, review=(0,))
    run_id = _run(store, graph)
    orchestrator = Orchestrator(store, registry, ports)
    await orchestrator.execute(run_id)

    store.approvals[(run_id, graph.nodes[0].id)] = Decision(ApprovalDecision.REJECT, note="Wrong topic.")
    assert await orchestrator.execute(run_id) == RunStatus.FAILED

    assert store.status_of(run_id, graph.nodes[0].id) == NodeStatus.FAILED
    assert store.nodes[(run_id, graph.nodes[0].id)]["errors"] == [REJECTED_BY_REVIEWER]
    assert store.status_of(run_id, graph.nodes[1].id) == NodeStatus.SKIPPED
    assert ReverseAgent.calls == 0


async def test_a_result_sent_back_is_redone_with_the_note_and_waits_again(store, registry, ports):
    graph = chain("draft", "reverse", config={"text": "solar"}, review=(0,))
    run_id = _run(store, graph)
    orchestrator = Orchestrator(store, registry, ports)
    await orchestrator.execute(run_id)

    store.approvals[(run_id, graph.nodes[0].id)] = Decision(ApprovalDecision.REDO, note="make it about costs")
    assert await orchestrator.execute(run_id) == RunStatus.AWAITING_APPROVAL

    # The agent is told what it made and what the person wants changed.
    (revision,) = DraftAgent.revisions
    assert (revision.note, dict(revision.previous)) == ("make it about costs", {"text": "draft of solar"})
    assert store.outputs[(run_id, graph.nodes[0].id)] == {"text": "draft of solar, make it about costs"}
    assert store.status_of(run_id, graph.nodes[0].id) == NodeStatus.AWAITING_APPROVAL
    assert store.nodes[(run_id, graph.nodes[0].id)]["revision"] == 1
    assert ReverseAgent.calls == 0

    store.approvals[(run_id, graph.nodes[0].id)] = ApprovalDecision.APPROVE
    assert await orchestrator.execute(run_id) == RunStatus.SUCCEEDED
    assert store.outputs[(run_id, graph.nodes[1].id)] == {"text": "stsoc tuoba ti ekam ,ralos fo tfard"}


async def test_a_result_can_be_sent_back_more_than_once(store, registry, ports):
    graph = chain("draft", config={"text": "solar"}, review=(0,))
    run_id = _run(store, graph)
    orchestrator = Orchestrator(store, registry, ports)
    await orchestrator.execute(run_id)

    for note in ("shorter", "simpler"):
        store.approvals[(run_id, graph.nodes[0].id)] = Decision(ApprovalDecision.REDO, note=note)
        assert await orchestrator.execute(run_id) == RunStatus.AWAITING_APPROVAL

    assert [r.note for r in DraftAgent.revisions] == ["shorter", "simpler"]
    assert store.outputs[(run_id, graph.nodes[0].id)] == {"text": "draft of solar, shorter, simpler"}
    assert store.nodes[(run_id, graph.nodes[0].id)]["revision"] == 2


async def test_an_agent_that_cant_use_the_note_simply_runs_again(store, registry, ports):
    graph = chain("shout", config={"text": "solar"}, review=(0,))
    run_id = _run(store, graph)
    orchestrator = Orchestrator(store, registry, ports)
    await orchestrator.execute(run_id)

    store.approvals[(run_id, graph.nodes[0].id)] = Decision(ApprovalDecision.REDO, note="louder")
    assert await orchestrator.execute(run_id) == RunStatus.AWAITING_APPROVAL
    assert _runs_of(store, graph.nodes[0]) == 2
    assert store.outputs[(run_id, graph.nodes[0].id)] == {"text": "SOLAR"}


async def test_a_redo_a_lost_worker_was_running_still_has_its_note(store, registry, ports):
    graph = chain("draft", config={"text": "solar"}, review=(0,))
    run_id = _run(store, graph)
    orchestrator = Orchestrator(store, registry, ports)
    await orchestrator.execute(run_id)
    store.approvals[(run_id, graph.nodes[0].id)] = Decision(ApprovalDecision.REDO, note="add a summary")
    # The worker took the redo up and was lost while running it: the step is pending again (mark_interrupted).
    store.start_redo(run_id, graph.nodes[0].id)

    assert await orchestrator.execute(run_id) == RunStatus.AWAITING_APPROVAL
    assert [r.note for r in DraftAgent.revisions] == ["add a summary"]


async def test_an_edited_result_is_handed_to_its_agent_and_the_next_step_gets_the_edit(store, registry, ports):
    graph = chain("draft", "reverse", config={"text": "solar"}, review=(0,))
    run_id = _run(store, graph)
    orchestrator = Orchestrator(store, registry, ports)
    await orchestrator.execute(run_id)
    # The API saves the person's edit in place of the result, then records the approval.
    store.outputs[(run_id, graph.nodes[0].id)] = {"text": "my own words"}
    store.approvals[(run_id, graph.nodes[0].id)] = Decision(ApprovalDecision.APPROVE, edited=True)

    assert await orchestrator.execute(run_id) == RunStatus.SUCCEEDED

    assert DraftAgent.edits == ["my own words"]
    assert store.outputs[(run_id, graph.nodes[0].id)] == {"text": "my own words (kept)"}
    assert store.outputs[(run_id, graph.nodes[1].id)] == {"text": ")tpek( sdrow nwo ym"}


async def test_an_edit_its_agent_cant_keep_stops_the_run_and_says_why(store, registry, ports):
    DraftAgent.edit_fails = True
    graph = chain("draft", "reverse", config={"text": "solar"}, review=(0,))
    run_id = _run(store, graph)
    orchestrator = Orchestrator(store, registry, ports)
    await orchestrator.execute(run_id)
    store.approvals[(run_id, graph.nodes[0].id)] = Decision(ApprovalDecision.APPROVE, edited=True)

    assert await orchestrator.execute(run_id) == RunStatus.FAILED
    assert store.nodes[(run_id, graph.nodes[0].id)]["errors"] == ["The edited draft couldn't be saved as a PDF."]
    assert store.status_of(run_id, graph.nodes[1].id) == NodeStatus.SKIPPED


async def test_every_step_can_be_reviewed_in_turn(store, registry, ports):
    graph = chain("draft", "reverse", "shout", config={"text": "solar"}, review=(0, 1, 2))
    run_id = _run(store, graph)
    orchestrator = Orchestrator(store, registry, ports)

    for node in graph.nodes:
        assert await orchestrator.execute(run_id) == RunStatus.AWAITING_APPROVAL
        assert store.status_of(run_id, node.id) == NodeStatus.AWAITING_APPROVAL
        store.approvals[(run_id, node.id)] = ApprovalDecision.APPROVE

    assert await orchestrator.execute(run_id) == RunStatus.SUCCEEDED
    assert store.outputs[(run_id, graph.nodes[2].id)] == {"text": "RALOS FO TFARD"}


async def test_a_step_that_sends_still_waits_before_it_acts_not_after(store, registry, ports):
    """Asking to review a distribute step's result can't let it send first: it waits before, as always."""
    graph = chain("draft", "send", config={"text": "solar"}, review=(0, 1))
    run_id = _run(store, graph)
    orchestrator = Orchestrator(store, registry, ports)
    await orchestrator.execute(run_id)
    store.approvals[(run_id, graph.nodes[0].id)] = ApprovalDecision.APPROVE

    assert await orchestrator.execute(run_id) == RunStatus.AWAITING_APPROVAL
    assert store.status_of(run_id, graph.nodes[1].id) == NodeStatus.AWAITING_APPROVAL
    assert SendAgent.calls == 0


async def test_a_redo_is_never_how_a_step_that_sends_is_approved(store, registry, ports):
    graph = chain("draft", "send", config={"text": "solar"})
    run_id = _run(store, graph)
    store.approvals[(run_id, graph.nodes[1].id)] = Decision(ApprovalDecision.REDO, note="again")

    assert await Orchestrator(store, registry, ports).execute(run_id) == RunStatus.FAILED
    assert SendAgent.calls == 0


async def test_a_step_not_asked_for_review_runs_straight_through(store, registry, ports):
    graph = chain("draft", "reverse", config={"text": "solar"})
    run_id = _run(store, graph)
    assert await Orchestrator(store, registry, ports).execute(run_id) == RunStatus.SUCCEEDED


async def test_a_run_cancelled_while_a_reviewed_step_ran_stays_cancelled(store, registry, ports, monkeypatch):
    graph = chain("draft", "reverse", config={"text": "solar"}, review=(0,))
    run_id = _run(store, graph)
    original = DraftAgent.execute

    async def cancelled_meanwhile(self, input_data, ports):
        store.runs[run_id] = RunStatus.CANCELLED  # the API's cancel lands while the step runs
        return await original(self, input_data, ports)

    monkeypatch.setattr(DraftAgent, "execute", cancelled_meanwhile)
    assert await Orchestrator(store, registry, ports).execute(run_id) == RunStatus.CANCELLED
    assert store.status_of(run_id, graph.nodes[1].id) == NodeStatus.SKIPPED
