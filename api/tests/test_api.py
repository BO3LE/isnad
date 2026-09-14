from uuid import uuid4

from conftest import auth_headers, graph

from db.models import ExecutionLog, ExecutionRun


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
