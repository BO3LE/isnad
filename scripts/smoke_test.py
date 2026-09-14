#!/usr/bin/env python3
"""End-to-end smoke test against a running stack (`docker compose up`), with FAKE_ADAPTERS=true.

    python scripts/smoke_test.py [--api http://localhost:8000]

Signs in as the seeded demo user, runs all three template workflows through the real API,
Redis, worker, agents and PostgreSQL, approves every approval gate, and checks every run
succeeds. Standard library only, so it runs anywhere.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

TERMINAL = {"succeeded", "failed", "cancelled"}


class Client:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.token: str | None = None

    def call(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict | list | None]:
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.base + path, data=data, method=method)
        request.add_header("Content-Type", "application/json")
        if self.token:
            request.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read()
                return response.status, json.loads(raw) if raw else None
        except urllib.error.HTTPError as err:
            raw = err.read()
            return err.code, json.loads(raw) if raw else None


def wait_for(client: Client, what: str, check, timeout: float = 120) -> object:
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = check()
        if result:
            return result
        time.sleep(1)
    raise SystemExit(f"✗ timed out waiting for {what}")


def run_template(client: Client, workflow: dict) -> bool:
    status, created = client.call("POST", f"/workflows/{workflow['id']}/run")
    if status != 202:
        print(f"✗ {workflow['name']}: run returned {status} {created}")
        return False
    run_id = created["run_id"]
    approvals = 0
    while True:
        state = wait_for(
            client,
            f"run {run_id}",
            lambda: (
                (s := client.call("GET", f"/runs/{run_id}")[1])
                and s["status"] in TERMINAL | {"awaiting_approval"}
                and s
            ),
            timeout=180,
        )
        if state["status"] != "awaiting_approval":
            break
        parked = next((n for n in state["nodes"] if n["status"] == "awaiting_approval"), None)
        if parked is None:
            time.sleep(1)
            continue
        code, _ = client.call(
            "POST", f"/runs/{run_id}/nodes/{parked['node_id']}/approve", {"decision": "approve", "note": "smoke test"}
        )
        if code != 202:
            print(f"✗ {workflow['name']}: approve returned {code}")
            return False
        approvals += 1

    steps = " → ".join(f"{n['agent_type']}:{n['status']}" for n in state["nodes"])
    ok = state["status"] == "succeeded"
    print(f"{'✓' if ok else '✗'} {workflow['name']}: {state['status']} ({approvals} approval(s)) — {steps}")
    if not ok:
        for node in state["nodes"]:
            if node["error_message"]:
                print(f"    {node['agent_type']}: {node['error_message']}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--email", default="demo@gp.local")
    args = parser.parse_args()
    client = Client(args.api)

    wait_for(client, "the API", lambda: client.call("GET", "/health")[0] == 200 if _up(client) else False, timeout=90)
    wait_for(
        client,
        "the worker to publish the agent catalog",
        lambda: "agents" in client.call("GET", "/health/ready")[1]["checks"]["worker_catalog"],
        timeout=120,
    )
    print("✓ API healthy and worker catalog published")

    status, token = client.call("POST", "/auth/dev-login", {"email": args.email})
    if status != 200:
        print(f"✗ dev-login returned {status}: {token}")
        return 1
    client.token = token["access_token"]

    catalog = client.call("GET", "/agents/catalog")[1]
    print(f"✓ catalog: {', '.join(a['name'] for a in catalog)}")

    workflows = client.call("GET", "/workflows")[1]
    if len(workflows) < 3:
        print(f"✗ expected 3 seeded workflows, found {len(workflows)}")
        return 1
    results = [run_template(client, wf) for wf in sorted(workflows, key=lambda w: w["name"])]
    return 0 if all(results) else 1


def _up(client: Client) -> bool:
    try:
        client.call("GET", "/health")
        return True
    except (urllib.error.URLError, ConnectionError, TimeoutError):
        return False


if __name__ == "__main__":
    sys.exit(main())
