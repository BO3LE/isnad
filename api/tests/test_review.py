"""Deciding on a step's result: approve it as it is or edited, reject it, or send it back with a note."""

from __future__ import annotations

from conftest import CATALOG, graph

from api.catalog import StaticCatalog
from api.deps import get_catalog
from db.models import AgentOutput, Approval, ExecutionLog, ExecutionRun

ARTICLE = {
    "title": "Solar in Riyadh",
    "summary": "Why the sun matters.",
    "article_md": "# Solar in Riyadh\n\nThe sun is strong.",
    "pdf_path": "artifacts/articles/ab12/solar-in-riyadh.pdf",
    "docx_path": None,
}


def _reviewed_run(client, headers, sessions, *, result: dict | None = ARTICLE):
    """A run whose Writer has run and waits with its result — as the worker leaves it."""
    wf = client.post(
        "/workflows", json={"graph": graph("researcher", "writer", configs=[{"topic": "solar"}, {}])}, headers=headers
    ).json()
    run_id = client.post(f"/workflows/{wf['id']}/run", headers=headers).json()["run_id"]
    with sessions() as s:
        log = s.query(ExecutionLog).filter(ExecutionLog.position_order == 1).one()
        log.status = "awaiting_approval"
        s.query(ExecutionRun).one().status = "awaiting_approval"
        if result is not None:
            s.add(AgentOutput(log_id=log.id, output_type="text", content_json=dict(result)))
        s.commit()
        return run_id, str(log.node_id)


def _decide(client, headers, run_id, node_id, **body):
    return client.post(f"/runs/{run_id}/nodes/{node_id}/approve", json=body, headers=headers)


def _content(sessions) -> dict:
    with sessions() as s:
        return s.query(AgentOutput).filter(AgentOutput.output_type == "text").one().content_json


def _worker_redoes(sessions, result: dict) -> None:
    """What the worker does with a redo: the step runs again and waits with its new result."""
    with sessions() as s:
        log = s.query(ExecutionLog).filter(ExecutionLog.position_order == 1).one()
        log.revision += 1
        s.query(AgentOutput).filter(AgentOutput.log_id == log.id).one().content_json = result
        s.query(ExecutionRun).one().status = "awaiting_approval"
        s.commit()


def test_a_result_is_sent_back_with_a_note_and_its_redone_result_is_decided_in_turn(
    client, headers, sessions, enqueuer
):
    run_id, node_id = _reviewed_run(client, headers, sessions)

    assert _decide(client, headers, run_id, node_id, decision="redo", note="Focus on costs.").status_code == 202
    assert len(enqueuer.runs) == 2
    again = _decide(client, headers, run_id, node_id, decision="approve")
    assert (again.status_code, again.json()["detail"]) == (409, "This step has already been decided.")

    _worker_redoes(sessions, {**ARTICLE, "title": "What solar costs"})
    assert _decide(client, headers, run_id, node_id, decision="approve").status_code == 202

    trail = client.get(f"/runs/{run_id}/approvals", headers=headers).json()
    assert [(d["decision"], d["revision"], d["note"]) for d in trail] == [
        ("redo", 0, "Focus on costs."),
        ("approve", 1, None),
    ]
    step = next(n for n in client.get(f"/runs/{run_id}", headers=headers).json()["nodes"] if n["node_id"] == node_id)
    assert step["revision"] == 1
    assert step["approval"]["decision"] == "approve"  # the decision on its latest result


def test_a_redo_needs_no_note(client, headers, sessions):
    run_id, node_id = _reviewed_run(client, headers, sessions)
    assert _decide(client, headers, run_id, node_id, decision="redo").status_code == 202


def test_a_step_waiting_to_send_cant_be_sent_back(client, headers, sessions, enqueuer):
    run_id, node_id = _reviewed_run(client, headers, sessions, result=None)

    response = _decide(client, headers, run_id, node_id, decision="redo", note="again")

    assert response.status_code == 409
    assert "hasn't run yet" in response.json()["detail"]
    assert client.get(f"/runs/{run_id}/approvals", headers=headers).json() == []
    assert len(enqueuer.runs) == 1


def test_the_result_shows_what_its_reviewer_may_change(client, headers, sessions):
    run_id, node_id = _reviewed_run(client, headers, sessions)

    result = client.get(f"/runs/{run_id}/nodes/{node_id}/result", headers=headers).json()

    assert (result["agent_type"], result["revision"]) == ("writer", 0)
    assert [(f["name"], f["title"], f["kind"], f["value"]) for f in result["editable"]] == [
        ("title", "title", "text", "Solar in Riyadh"),
        ("summary", "summary", "text", "Why the sun matters."),
        ("article_md", "article", "text", "# Solar in Riyadh\n\nThe sun is strong."),
    ]


def test_a_step_that_hasnt_run_has_no_result(client, headers, sessions):
    run_id, node_id = _reviewed_run(client, headers, sessions, result=None)
    assert client.get(f"/runs/{run_id}/nodes/{node_id}/result", headers=headers).status_code == 404


def test_an_approved_edit_takes_the_results_place(client, headers, sessions):
    run_id, node_id = _reviewed_run(client, headers, sessions)

    response = _decide(
        client, headers, run_id, node_id, decision="approve", edits={"article_md": "  My own article.  "}
    )

    assert response.status_code == 202
    assert _content(sessions) == {**ARTICLE, "article_md": "My own article."}
    (decision,) = client.get(f"/runs/{run_id}/approvals", headers=headers).json()
    assert (decision["decision"], decision["edited"]) == ("approve", True)


def test_an_edit_that_changes_nothing_isnt_an_edit(client, headers, sessions):
    run_id, node_id = _reviewed_run(client, headers, sessions)
    _decide(client, headers, run_id, node_id, decision="approve", edits={"title": "Solar in Riyadh"})
    with sessions() as s:
        assert s.query(Approval).one().edited is False


def test_files_and_links_are_never_edited(client, headers, sessions):
    """An edited path could name another person's file."""
    run_id, node_id = _reviewed_run(client, headers, sessions)

    response = _decide(
        client, headers, run_id, node_id, decision="approve", edits={"pdf_path": "someone-else/run/secret.pdf"}
    )

    assert response.status_code == 422
    assert "can't be edited: pdf_path" in response.json()["detail"]
    assert _content(sessions) == ARTICLE


def test_an_edit_the_agent_wouldnt_accept_is_refused(client, headers, sessions):
    run_id, node_id = _reviewed_run(client, headers, sessions)

    response = _decide(client, headers, run_id, node_id, decision="approve", edits={"title": "   "})

    assert response.status_code == 422
    assert "title" in response.json()["detail"]
    assert _content(sessions) == ARTICLE
    assert client.get(f"/runs/{run_id}/approvals", headers=headers).json() == []


def test_edits_are_kept_only_on_approval(client, headers, sessions):
    run_id, node_id = _reviewed_run(client, headers, sessions)
    response = _decide(client, headers, run_id, node_id, decision="redo", edits={"title": "New"})
    assert response.status_code == 422
    assert _content(sessions) == ARTICLE


def test_an_edit_isnt_kept_when_the_worker_never_hears_of_the_decision(client, headers, sessions, enqueuer):
    run_id, node_id = _reviewed_run(client, headers, sessions)
    enqueuer.down = True

    response = _decide(client, headers, run_id, node_id, decision="approve", edits={"title": "New title"})

    assert response.status_code == 503
    assert _content(sessions) == ARTICLE
    assert client.get(f"/runs/{run_id}/approvals", headers=headers).json() == []


def test_edits_wait_for_the_agent_list(client, headers, sessions):
    """Which fields can be edited is the agent's to say; without its manifest nothing is guessed."""
    run_id, node_id = _reviewed_run(client, headers, sessions)
    client.app.dependency_overrides[get_catalog] = lambda: StaticCatalog(None)
    try:
        response = _decide(client, headers, run_id, node_id, decision="approve", edits={"title": "New"})
    finally:
        client.app.dependency_overrides[get_catalog] = lambda: StaticCatalog(CATALOG)
    assert response.status_code == 503
    assert _content(sessions) == ARTICLE
