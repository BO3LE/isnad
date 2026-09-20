from uuid import uuid4

from conftest import auth_headers, graph

from db.models import AgentOutput, ExecutionLog, ExecutionRun


def test_health_needs_nothing(client):
    assert client.get("/health").json()["status"] == "ok"


def test_endpoints_require_a_session(client):
    response = client.get("/workflows")
    assert response.status_code == 401
    assert response.json()["detail"] == "Sign in to continue."


def test_dev_login_issues_a_working_token(client):
    token = client.post("/auth/dev-login", json={"email": "Zain@GP.local"}).json()["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["email"] == "zain@gp.local"


def test_workflow_crud_round_trip(client, headers):
    created = client.post(
        "/workflows", json={"name": "Weekly digest", "graph": graph("researcher", "writer")}, headers=headers
    )
    assert created.status_code == 201
    wf = created.json()
    assert len(wf["graph"]["nodes"]) == 2

    renamed = client.put(f"/workflows/{wf['id']}", json={"name": "Weekly tech digest"}, headers=headers).json()
    assert renamed["name"] == "Weekly tech digest"

    listed = client.get("/workflows", headers=headers).json()
    assert listed[0]["agent_types"] == ["researcher", "writer"]

    assert client.delete(f"/workflows/{wf['id']}", headers=headers).status_code == 204
    assert client.get(f"/workflows/{wf['id']}", headers=headers).status_code == 404


def test_other_users_workflows_are_not_found(client, sessions, headers):
    wf = client.post("/workflows", json={"name": "Mine"}, headers=headers).json()
    stranger = auth_headers(sessions, "stranger@gp.local")
    assert client.get(f"/workflows/{wf['id']}", headers=stranger).status_code == 404


def test_validation_messages_are_human(client, headers):
    g = graph("researcher", "writer", "writer", connect=False)
    g["edges"] = [{"id": "a", "source": g["nodes"][0]["id"], "target": g["nodes"][1]["id"]}]
    g["nodes"][2]["agent_type"] = "tiktok"
    wf = client.post("/workflows", json={"graph": g}, headers=headers).json()
    result = client.post(f"/workflows/{wf['id']}/validate", headers=headers).json()
    messages = {i["code"]: i["message"] for i in result["issues"]}
    assert result["valid"] is False
    assert messages["missing_config"] == "Researcher is missing topic."
    assert messages["orphan_node"] == "Tiktok isn't connected to anything."
    assert messages["unknown_agent"] == "No agent is installed for “tiktok”."


def test_cycles_are_named(client, headers):
    g = graph("researcher", "writer", configs=[{"topic": "solar"}, {}])
    g["edges"].append({"id": "back", "source": g["nodes"][1]["id"], "target": g["nodes"][0]["id"]})
    wf = client.post("/workflows", json={"graph": g}, headers=headers).json()
    issue = client.post(f"/workflows/{wf['id']}/validate", headers=headers).json()["issues"][0]
    assert issue["code"] == "cycle_detected" and "Researcher → Writer → Researcher" in issue["message"]


def test_run_returns_202_and_enqueues_only_the_run_id(client, headers, enqueuer, sessions):
    """The decoupling test for C2: no worker is running, and the API's job is done at 202."""
    wf = client.post(
        "/workflows", json={"graph": graph("researcher", "writer", configs=[{"topic": "solar"}, {}])}, headers=headers
    ).json()
    response = client.post(f"/workflows/{wf['id']}/run", headers=headers)
    assert response.status_code == 202
    run_id = response.json()["run_id"]
    assert [str(r) for r in enqueuer.runs] == [run_id]

    state = client.get(f"/runs/{run_id}", headers=headers).json()
    assert state["status"] == "queued"
    assert [n["status"] for n in state["nodes"]] == ["pending", "pending"]
    assert [n["agent_type"] for n in state["nodes"]] == ["researcher", "writer"]


def test_invalid_workflow_is_not_run(client, headers, enqueuer):
    wf = client.post("/workflows", json={"graph": graph("researcher")}, headers=headers).json()
    response = client.post(f"/workflows/{wf['id']}/run", headers=headers)
    assert response.status_code == 422
    assert enqueuer.runs == []


def _parked_run(client, headers, sessions):
    wf = client.post(
        "/workflows", json={"graph": graph("researcher", "writer", configs=[{"topic": "solar"}, {}])}, headers=headers
    ).json()
    run_id = client.post(f"/workflows/{wf['id']}/run", headers=headers).json()["run_id"]
    with sessions() as s:
        log = s.query(ExecutionLog).filter(ExecutionLog.position_order == 1).one()
        log.status = "awaiting_approval"
        s.query(ExecutionRun).one().status = "awaiting_approval"
        s.commit()
        return run_id, str(log.node_id)


def test_approve_records_decision_and_hands_back_to_worker(client, headers, sessions, enqueuer):
    run_id, node_id = _parked_run(client, headers, sessions)
    response = client.post(f"/runs/{run_id}/nodes/{node_id}/approve", json={"decision": "approve"}, headers=headers)
    assert response.status_code == 202
    assert len(enqueuer.runs) == 2
    again = client.post(f"/runs/{run_id}/nodes/{uuid4()}/approve", json={"decision": "approve"}, headers=headers)
    assert again.status_code == 404


def test_reject_needs_a_note(client, headers, sessions):
    run_id, node_id = _parked_run(client, headers, sessions)
    response = client.post(f"/runs/{run_id}/nodes/{node_id}/approve", json={"decision": "reject"}, headers=headers)
    assert response.status_code == 422


def test_cancel_skips_steps_that_have_not_started(client, headers, sessions):
    run_id, _ = _parked_run(client, headers, sessions)
    state = client.post(f"/runs/{run_id}/cancel", headers=headers).json()
    assert state["status"] == "cancelled"
    assert {n["status"] for n in state["nodes"]} == {"skipped"}
    assert client.post(f"/runs/{run_id}/cancel", headers=headers).status_code == 409


def test_catalog_is_served_from_the_worker_published_source(client, headers):
    names = [a["name"] for a in client.get("/agents/catalog", headers=headers).json()]
    assert names == ["researcher", "writer"]


# ---------------------------------------------------------------- what a run produced (Part 3)


def _finished_run(client, headers, sessions, *, rejected: bool = False):
    """A run whose two steps have finished, with an output recorded against each."""
    wf = client.post(
        "/workflows", json={"graph": graph("researcher", "writer", configs=[{"topic": "solar"}, {}])}, headers=headers
    ).json()
    run_id = client.post(f"/workflows/{wf['id']}/run", headers=headers).json()["run_id"]
    with sessions() as s:
        logs = s.query(ExecutionLog).order_by(ExecutionLog.position_order).all()
        for log in logs:
            log.status = "success"
        s.add(AgentOutput(log_id=logs[0].id, output_type="text", content="notes about solar"))
        s.add(
            AgentOutput(
                log_id=logs[1].id,
                output_type="file",
                storage_path="runs/abc/article.md",
                mime_type="text/markdown",
                bytes=2048,
            )
        )
        run = s.query(ExecutionRun).one()
        if rejected:
            run.status = "failed"
            logs[1].status = "failed"
            logs[1].error_message = "[attempt 1] Rejected by reviewer."
        else:
            run.status = "succeeded"
        s.commit()
    return wf["id"], run_id


def test_a_run_lists_what_it_produced_in_step_order(client, headers, sessions):
    _, run_id = _finished_run(client, headers, sessions)
    outputs = client.get(f"/runs/{run_id}/outputs", headers=headers).json()

    assert [o["agent_type"] for o in outputs] == ["researcher", "writer"]
    assert outputs[0]["kind"] == "text"
    assert outputs[0]["filename"] is None
    # A stored file is named by the last segment of its path — there is no filename column.
    assert outputs[1]["filename"] == "article.md"
    assert outputs[1]["mime_type"] == "text/markdown"
    assert outputs[1]["bytes"] == 2048
    # Every id has to lead somewhere: a file to a download, and text to its content.
    link = client.get(f"/outputs/{outputs[1]['id']}", headers=headers).json()
    assert link["url"].endswith("runs/abc/article.md")
    written = client.get(f"/outputs/{outputs[0]['id']}", headers=headers)
    assert written.status_code == 200
    assert written.json()["text"] == "notes about solar"


def test_an_agents_own_output_shape_is_readable_whatever_it_is(client, headers, sessions):
    """AT-12 reaches the preview too: the platform cannot know which fields an agent publishes."""
    _, run_id = _finished_run(client, headers, sessions)
    with sessions() as s:
        log = s.query(ExecutionLog).order_by(ExecutionLog.position_order).all()[0]
        s.add(
            AgentOutput(
                log_id=log.id,
                output_type="text",
                content_json={
                    "notes": ["Finding one", "Finding two"],
                    "sources": [{"title": "IRENA", "url": "https://example.org/1"}],
                    "confidence": 0.9,
                    "checked": True,
                    "nothing": None,
                },
            )
        )
        s.commit()

    outputs = client.get(f"/runs/{run_id}/outputs", headers=headers).json()
    written = [client.get(f"/outputs/{o['id']}", headers=headers).json() for o in outputs if o["kind"] == "text"]
    shaped = next(w for w in written if "Finding one" in (w.get("text") or ""))["text"]

    assert "notes:" in shaped and "- Finding one" in shaped and "- Finding two" in shaped
    assert "title: IRENA" in shaped and "https://example.org/1" in shaped
    assert "confidence: 0.9" in shaped and "checked: yes" in shaped
    # A field with nothing in it is not shown as an empty line.
    assert "nothing" not in shaped


def test_another_users_outputs_are_not_listed(client, headers, sessions):
    _, run_id = _finished_run(client, headers, sessions)
    # Assert the owner is served first: a bare 404 for the stranger is also what a missing route
    # returns, so on its own it would pass against an API with no ownership check at all.
    mine = client.get(f"/runs/{run_id}/outputs", headers=headers)
    assert mine.status_code == 200 and mine.json() != []

    other = auth_headers(sessions, email="someone-else@gp.local")
    assert client.get(f"/runs/{run_id}/outputs", headers=other).status_code == 404


def test_a_run_with_nothing_to_show_says_so_rather_than_failing(client, headers, sessions):
    run_id, _ = _parked_run(client, headers, sessions)
    response = client.get(f"/runs/{run_id}/outputs", headers=headers)
    assert response.status_code == 200
    assert response.json() == []


def test_a_rejected_run_is_not_reported_as_a_failure(client, headers, sessions):
    workflow_id, _run_id = _finished_run(client, headers, sessions, rejected=True)

    listed = client.get("/workflows", headers=headers).json()
    summary = next(w for w in listed if w["id"] == workflow_id)["last_run"]
    assert summary["status"] == "failed"
    assert summary["reason"] == "rejected"

    history = client.get(f"/workflows/{workflow_id}/runs", headers=headers).json()
    assert history[0]["reason"] == "rejected"


def test_a_genuine_failure_carries_no_reason(client, headers, sessions):
    workflow_id, _ = _finished_run(client, headers, sessions)
    with sessions() as s:
        run = s.query(ExecutionRun).one()
        run.status = "failed"
        log = s.query(ExecutionLog).order_by(ExecutionLog.position_order).all()[1]
        log.status = "failed"
        log.error_message = "[attempt 3] YouTube refused the file"
        s.commit()

    summary = next(w for w in client.get("/workflows", headers=headers).json() if w["id"] == workflow_id)["last_run"]
    assert summary["status"] == "failed"
    assert summary["reason"] is None
