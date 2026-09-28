#!/usr/bin/env python3
"""W10 — reliability campaign (NFR-02): drive N runs through the real stack, then aggregate.

    python scripts/reliability_campaign.py both --runs 60 --concurrency 2

Two phases, either run together (`both`, the default subcommand) or separately:

  run      Signs in as the seeded demo user (POST /auth/dev-login), spreads `--runs` runs evenly
           across the seeded template workflows, drives each through `POST /workflows/{id}/run`,
           polls `GET /runs/{id}` until it finishes, and auto-approves every parked approval gate
           via `POST /runs/{id}/nodes/{node}/approve`. Standard library only (urllib), like
           scripts/smoke_test.py, so it needs no venv — only a running `docker compose` stack with
           FAKE_ADAPTERS=true (the default; see worker/settings.py). Writes a small "window" JSON
           file recording the campaign's time span and workflow ids, so `report` counts only this
           campaign's runs — never anyone else's traffic against the same database.

  report   Aggregates straight from PostgreSQL (execution_runs, execution_logs, agent_outputs,
           approvals) over that window, using DATABASE_URL (needs `psycopg`, already a dependency
           of `db`/`worker`). Writes docs/metrics/reliability.md and CSVs under
           docs/metrics/data/.

Rerun just the report against a past campaign with `report --window <path-to-window.json>`, or
against an arbitrary window with `report --since <iso> --until <iso> --workflow-ids <id> [<id> ...]`.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock

TERMINAL = {"succeeded", "failed", "cancelled"}
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WINDOW_FILE = REPO_ROOT / "docs" / "metrics" / "data" / "reliability-window.json"
DEFAULT_REPORT_MD = REPO_ROOT / "docs" / "metrics" / "reliability.md"
DEFAULT_CSV_DIR = REPO_ROOT / "docs" / "metrics" / "data"
DEFAULT_DATABASE_URL = "postgresql://postgres:postgres@localhost:5433/gp"


# ---------------------------------------------------------------------------- phase 1: drive runs


class Client:
    """Same shape as scripts/smoke_test.py's — a tiny stdlib HTTP client, thread-safe enough for
    one call at a time per thread (each worker thread gets its own instance)."""

    def __init__(self, base: str, token: str | None = None):
        self.base = base.rstrip("/")
        self.token = token

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


def _wait_for(check, what: str, timeout: float) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if check():
            return
        time.sleep(1)
    raise SystemExit(f"timed out waiting for {what}")


@dataclass
class RunResult:
    run_id: str
    workflow_id: str
    workflow_name: str
    final_status: str | None
    approvals_made: int
    elapsed_s: float
    error: str | None = None


@dataclass
class _Progress:
    total: int
    lock: Lock = field(default_factory=Lock)
    done: int = 0
    counts: Counter = field(default_factory=Counter)

    def report(self, status: str) -> None:
        with self.lock:
            self.done += 1
            self.counts[status] += 1
            print(f"  [{self.done}/{self.total}] {status}  (so far: {dict(self.counts)})", flush=True)


def _drive_one(base: str, token: str, workflow: dict, timeout: float, progress: _Progress) -> RunResult:
    client = Client(base, token)
    start = time.monotonic()
    status_code, created = client.call("POST", f"/workflows/{workflow['id']}/run")
    if status_code != 202:
        progress.report("submit_failed")
        return RunResult(
            run_id="",
            workflow_id=workflow["id"],
            workflow_name=workflow["name"],
            final_status=None,
            approvals_made=0,
            elapsed_s=time.monotonic() - start,
            error=f"run POST returned {status_code}: {created}",
        )
    run_id = created["run_id"]
    approvals = 0
    deadline = time.monotonic() + timeout
    state: dict | None = None
    while time.monotonic() < deadline:
        code, state = client.call("GET", f"/runs/{run_id}")
        if code != 200 or state is None:
            time.sleep(1)
            continue
        if state["status"] in TERMINAL:
            break
        if state["status"] == "awaiting_approval":
            parked = next((n for n in state["nodes"] if n["status"] == "awaiting_approval"), None)
            if parked is not None:
                client.call(
                    "POST",
                    f"/runs/{run_id}/nodes/{parked['node_id']}/approve",
                    {"decision": "approve", "note": "reliability campaign auto-approve"},
                )
                approvals += 1
        time.sleep(1.5)
    else:
        progress.report("timed_out")
        return RunResult(
            run_id=run_id,
            workflow_id=workflow["id"],
            workflow_name=workflow["name"],
            final_status=None,
            approvals_made=approvals,
            elapsed_s=time.monotonic() - start,
            error=f"exceeded {timeout}s per-run timeout",
        )
    final = state["status"] if state else "unknown"
    progress.report(final)
    return RunResult(
        run_id=run_id,
        workflow_id=workflow["id"],
        workflow_name=workflow["name"],
        final_status=final,
        approvals_made=approvals,
        elapsed_s=time.monotonic() - start,
    )


def cmd_run(args: argparse.Namespace) -> None:
    client = Client(args.api)
    _wait_for(lambda: client.call("GET", "/health")[0] == 200, "the API", timeout=90)
    status_code, token = client.call("POST", "/auth/dev-login", {"email": args.email})
    if status_code != 200:
        raise SystemExit(f"dev-login returned {status_code}: {token}")
    token = token["access_token"]

    auth = Client(args.api, token)
    _, workflows = auth.call("GET", "/workflows")
    if not workflows:
        raise SystemExit(f"{args.email} has no workflows to run — is the stack seeded (`make migrate`)?")
    workflows = sorted(workflows, key=lambda w: w["name"])
    print(f"Driving {args.runs} runs across {len(workflows)} template workflow(s), concurrency={args.concurrency}:")
    for w in workflows:
        print(f"  - {w['name']} ({w['id']})")

    # Round-robin assignment so a 60-run campaign against 3 templates gives each exactly 20, not
    # a random skew — the per-template table in the report is only meaningful if runs are spread.
    assignments = [workflows[i % len(workflows)] for i in range(args.runs)]

    campaign_start = datetime.now(UTC)
    results: list[RunResult] = []
    progress = _Progress(total=args.runs)
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [pool.submit(_drive_one, args.api, token, wf, args.run_timeout, progress) for wf in assignments]
        for future in as_completed(futures):
            results.append(future.result())
    campaign_end = datetime.now(UTC)

    ok = sum(1 for r in results if r.final_status == "succeeded")
    print(f"\nDone: {ok}/{len(results)} succeeded in {(campaign_end - campaign_start).total_seconds():.0f}s.")
    failed = [r for r in results if r.final_status != "succeeded"]
    if failed:
        print(f"{len(failed)} did not succeed:")
        for r in failed[:20]:
            print(f"  - {r.workflow_name} run={r.run_id or '(none)'} status={r.final_status} error={r.error}")

    window = {
        "label": args.label,
        "api": args.api,
        "email": args.email,
        "requested_runs": args.runs,
        "concurrency": args.concurrency,
        "run_timeout_s": args.run_timeout,
        # A half-second of slack on each side absorbs clock skew between this process and the
        # database server without risking pulling in a run from outside the campaign.
        "campaign_start": campaign_start.isoformat(),
        "campaign_end": campaign_end.isoformat(),
        "workflow_ids": [w["id"] for w in workflows],
        "workflow_names": {w["id"]: w["name"] for w in workflows},
        "run_ids": [r.run_id for r in results if r.run_id],
    }
    args.window.parent.mkdir(parents=True, exist_ok=True)
    args.window.write_text(json.dumps(window, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote campaign window to {args.window}")
    print(f"Next: python scripts/reliability_campaign.py report --window {args.window}")


# ---------------------------------------------------------------------------- phase 2: aggregate


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    k = (len(values) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(values) - 1)
    if lo == hi:
        return values[lo]
    return values[lo] + (values[hi] - values[lo]) * (k - lo)


def _write_csv(path: Path, rows: list[dict]) -> None:
    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def cmd_report(args: argparse.Namespace) -> None:
    import psycopg
    from psycopg.rows import dict_row

    if args.window and args.window.exists():
        window = json.loads(args.window.read_text(encoding="utf-8"))
        since, until = window["campaign_start"], window["campaign_end"]
        workflow_ids = window["workflow_ids"]
        workflow_names = window["workflow_names"]
        label = window["label"]
    else:
        if not (args.since and args.until and args.workflow_ids):
            raise SystemExit("No window file found — pass --since, --until and --workflow-ids explicitly.")
        since, until = args.since, args.until
        workflow_ids = args.workflow_ids
        workflow_names = {}
        label = args.label

    with psycopg.connect(args.database_url, row_factory=dict_row) as conn:
        if not workflow_names:
            rows = conn.execute("SELECT id, name FROM workflows WHERE id = ANY(%s)", (workflow_ids,)).fetchall()
            workflow_names = {str(r["id"]): r["name"] for r in rows}

        runs = conn.execute(
            """
            SELECT id, workflow_id, status, total_nodes, failed_nodes, created_at, started_at, completed_at
            FROM execution_runs
            WHERE workflow_id = ANY(%s) AND created_at >= %s AND created_at <= %s
            ORDER BY created_at
            """,
            (workflow_ids, since, until),
        ).fetchall()
        run_ids = [r["id"] for r in runs]

        logs = (
            conn.execute(
                """
                SELECT id, run_id, node_id, agent_type, status, retry_count, duration_ms, error_message
                FROM execution_logs
                WHERE run_id = ANY(%s)
                ORDER BY run_id, position_order
                """,
                (run_ids,),
            ).fetchall()
            if run_ids
            else []
        )

        approvals = (
            conn.execute(
                """
                SELECT a.id, a.log_id, el.run_id, el.node_id, el.agent_type, a.decision,
                       u.email AS decided_by_email, a.decided_at, a.note
                FROM approvals a
                JOIN execution_logs el ON el.id = a.log_id
                LEFT JOIN users u ON u.id = a.decided_by
                WHERE el.run_id = ANY(%s)
                ORDER BY a.decided_at
                """,
                (run_ids,),
            ).fetchall()
            if run_ids
            else []
        )

    report = _build_report(label, since, until, workflow_names, runs, logs, approvals)
    _emit(report, args.out_md, args.csv_dir, label)


@dataclass
class Report:
    label: str
    since: str
    until: str
    text: str
    csv_runs: list[dict]
    csv_logs: list[dict]
    csv_approvals: list[dict]


def _build_report(
    label: str, since: str, until: str, workflow_names: dict, runs: list[dict], logs: list[dict], approvals: list[dict]
) -> Report:
    lines: list[str] = []

    total_runs = len(runs)
    by_status = Counter(r["status"] for r in runs)
    succeeded = by_status.get("succeeded", 0)
    run_success_rate = (succeeded / total_runs * 100) if total_runs else None

    # ---- handoffs (NFR-02): one handoff = the orchestrator handing control to one node, i.e. an
    # execution_log row that actually started. `pending` never started; `skipped` never started
    # either — it means an *upstream* node failed or the run was cancelled first, so the
    # orchestrator never reached this node at all.
    handoff_logs = [log for log in logs if log["status"] not in ("pending", "skipped")]
    total_handoffs = len(handoff_logs)
    successful_handoffs = sum(1 for log in handoff_logs if log["status"] == "success")
    handoff_rate = (successful_handoffs / total_handoffs * 100) if total_handoffs else None

    logs_by_run: dict = defaultdict(list)
    for log in logs:
        logs_by_run[log["run_id"]].append(log)
    runs_no_retry = sum(1 for rid, ls in logs_by_run.items() if all(log["retry_count"] == 0 for log in ls))
    runs_halted_after_max = sum(
        1 for rid, ls in logs_by_run.items() if any(log["retry_count"] >= 3 and log["status"] == "failed" for log in ls)
    )

    # ---- per-template
    per_template = defaultdict(lambda: Counter())
    for r in runs:
        per_template[workflow_names.get(str(r["workflow_id"]), str(r["workflow_id"]))][r["status"]] += 1

    # ---- per-agent
    per_agent_status = defaultdict(lambda: Counter())
    per_agent_durations = defaultdict(list)
    per_agent_retries = defaultdict(int)
    for log in logs:
        per_agent_status[log["agent_type"]][log["status"]] += 1
        if log["duration_ms"] is not None and log["status"] == "success":
            per_agent_durations[log["agent_type"]].append(log["duration_ms"] / 1000.0)
        if log["retry_count"]:
            per_agent_retries[log["agent_type"]] += 1

    # ---- retry-then-success
    retried_logs = [log for log in logs if log["retry_count"] > 0]
    retried_then_success = sum(1 for log in retried_logs if log["status"] == "success")
    retry_then_success_rate = (retried_then_success / len(retried_logs) * 100) if retried_logs else None

    # ---- failure causes
    failure_causes = Counter(
        (log["error_message"] or "(no message)").strip().splitlines()[0][:160]
        for log in logs
        if log["status"] == "failed"
    )

    # ---- run duration p50/p95 (finished runs only)
    run_durations = [
        (r["completed_at"] - r["started_at"]).total_seconds() for r in runs if r["started_at"] and r["completed_at"]
    ]

    # ---- approvals vs gates hit: a gate is "hit" if its log row is currently parked, or has a
    # recorded decision (it can't have left `awaiting_approval` any other way). Dedup by the
    # execution_logs row id, not node_id — node_id comes from the template's graph_snapshot and
    # is the SAME uuid across every run of that template, so it would collapse separate runs.
    approved_log_ids = {a["log_id"] for a in approvals}
    parked_log_ids = {log["id"] for log in logs if log["status"] == "awaiting_approval"}
    gates_hit = len(approved_log_ids | parked_log_ids)
    approvals_recorded = len(approvals)

    lines.append(f"# Reliability campaign — {label}")
    lines.append("")
    lines.append(f"Window: `{since}` to `{until}` (UTC). See **Method** below for how to reproduce.")
    lines.append("")
    lines.append("## NFR-02 — handoff success rate")
    lines.append("")
    lines.append("| Metric | Target | Measured |")
    lines.append("|---|---|---|")
    lines.append(f"| Total runs | ≥ 50 | {total_runs} |")
    lines.append(f"| Total node handoffs | — | {total_handoffs} |")
    lines.append(f"| Successful handoffs | — | {successful_handoffs} |")
    lines.append(
        f"| **Handoff success rate** | **≥ 99%** | **{handoff_rate:.2f}%**"
        if handoff_rate is not None
        else "| **Handoff success rate** | **≥ 99%** | n/a (no handoffs) |"
    )
    lines.append(f"| Runs completing without retry | — | {runs_no_retry} / {total_runs} |")
    lines.append(f"| Runs halted after 3 retries | — | {runs_halted_after_max} |")
    lines.append("")
    lines.append(
        f"Run success rate (terminal status `succeeded` ÷ total runs): "
        f"**{run_success_rate:.2f}%** ({succeeded}/{total_runs})."
        if total_runs
        else "No runs in this window."
    )
    lines.append("")

    lines.append("## Per-template")
    lines.append("")
    lines.append("| Template | Runs | Succeeded | Failed | Cancelled | Other |")
    lines.append("|---|---|---|---|---|---|")
    for name, counts in sorted(per_template.items()):
        total = sum(counts.values())
        other = total - counts.get("succeeded", 0) - counts.get("failed", 0) - counts.get("cancelled", 0)
        lines.append(
            f"| {name} | {total} | {counts.get('succeeded', 0)} | {counts.get('failed', 0)} | "
            f"{counts.get('cancelled', 0)} | {other} |"
        )
    lines.append("")

    lines.append("## Per-agent latency and outcomes")
    lines.append("")
    lines.append("| Agent | Handoffs | Success | Failed | Retried | Median (s) | p95 (s) |")
    lines.append("|---|---|---|---|---|---|---|")
    for agent in sorted(per_agent_status):
        counts = per_agent_status[agent]
        durations = per_agent_durations[agent]
        median = statistics.median(durations) if durations else None
        p95 = _percentile(durations, 0.95)
        total = sum(counts.values())
        lines.append(
            f"| {agent} | {total} | {counts.get('success', 0)} | {counts.get('failed', 0)} | "
            f"{per_agent_retries[agent]} | {f'{median:.2f}' if median is not None else '—'} | "
            f"{f'{p95:.2f}' if p95 is not None else '—'} |"
        )
    lines.append("")

    lines.append("## Retries")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    lines.append(f"| Handoffs retried at least once | {len(retried_logs)} |")
    lines.append(
        f"| Retry-then-success rate | "
        f"{f'{retry_then_success_rate:.2f}%' if retry_then_success_rate is not None else 'n/a (no retries)'} |"
    )
    lines.append("")

    lines.append("## Failure causes")
    lines.append("")
    if failure_causes:
        lines.append("| Error message (first line, truncated) | Count |")
        lines.append("|---|---|")
        for msg, count in failure_causes.most_common(20):
            lines.append(f"| {msg.replace('|', chr(0x7C))} | {count} |")
    else:
        lines.append("No failed node handoffs in this window.")
    lines.append("")

    lines.append("## Total run duration")
    lines.append("")
    p50 = _percentile(run_durations, 0.50)
    p95 = _percentile(run_durations, 0.95)
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    lines.append(f"| Runs with a measured duration | {len(run_durations)} |")
    lines.append(f"| p50 | {f'{p50:.2f}s' if p50 is not None else '—'} |")
    lines.append(f"| p95 | {f'{p95:.2f}s' if p95 is not None else '—'} |")
    lines.append("")

    lines.append("## Approvals audit trail (UC-04 evidence)")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    lines.append(f"| Approval gates hit (node parked `awaiting_approval` or later decided) | {gates_hit} |")
    lines.append(f"| Approvals recorded (`approvals` table rows) | {approvals_recorded} |")
    lines.append(
        f"| Gates hit with no recorded decision | {max(gates_hit - approvals_recorded, 0)} "
        "(should be 0 — every parked node in this campaign was auto-approved) |"
    )
    decisions = Counter(a["decision"] for a in approvals)
    lines.append(f"| Decisions: approve / reject | {decisions.get('approve', 0)} / {decisions.get('reject', 0)} |")
    lines.append("")

    lines.append("## Caveat")
    lines.append("")
    lines.append(
        "This campaign ran with `FAKE_ADAPTERS=true` (the worker's own default — see "
        "`worker/settings.py`): every agent call is a canned, deterministic fake response "
        "(`adapters/*/fake.py`), except that the video agent still renders a real file with "
        "ffmpeg (`exporters/video.py`), so video-step timing and any resource-exhaustion "
        "failures under concurrency are real. The real Google/YouTube/Gmail adapters "
        "(`adapters/_google.py`, D-09) are not implemented yet, so **no external-API failure, "
        "rate limit, or auth error is represented here** — retries and failures measured above "
        "come only from internal orchestration, validation and resource limits, not from a "
        "third-party API. Treat this number as a floor on real-world reliability, not a ceiling."
    )
    lines.append("")

    lines.append("## Method")
    lines.append("")
    lines.append("```")
    lines.append("docker compose up -d --build db redis migrate api worker")
    lines.append(f"python scripts/reliability_campaign.py both --runs 60 --concurrency 2 --label {label}")
    lines.append("```")
    lines.append("")
    lines.append(
        "`run` drives the real HTTP API — no shortcuts through the orchestrator — spreading runs "
        "evenly across the seeded template workflows, polling `GET /runs/{id}` and "
        "auto-approving every parked gate via `POST /runs/{id}/nodes/{node}/approve`. It records "
        "the campaign's start/end timestamps and the seeded workflow ids to a window file; "
        "`report` (or the second half of `both`) aggregates directly from PostgreSQL "
        "(`execution_runs`, `execution_logs`, `agent_outputs`, `approvals`) filtered to that "
        "window, so runs from any other user of the same database are excluded. Rerun the report "
        "alone with `python scripts/reliability_campaign.py report --window "
        f"{DEFAULT_WINDOW_FILE.relative_to(REPO_ROOT).as_posix()}`."
    )
    lines.append("")
    lines.append("## Machine")
    lines.append("")
    lines.append(
        "Measured on a single Windows 11 development machine, Docker Desktop (WSL2 backend), "
        "PostgreSQL 15 and Redis 7 via `docker-compose.yml`, worker `--concurrency 2` (Celery "
        "prefork), campaign driver concurrency as shown above. Not a dedicated benchmarking "
        "environment — absolute latencies are indicative, not a performance claim."
    )
    lines.append("")
    lines.append("## Operational notes (read before rerunning on Windows)")
    lines.append("")
    lines.append(
        "Two infrastructure issues came up while building this campaign on Windows — neither is "
        "an orchestrator handoff failure, so neither run is counted in the numbers above, but "
        "both would otherwise waste a rerun:"
    )
    lines.append("")
    lines.append(
        "1. **The worker's `dev` Docker target (file-watching auto-reload) can crash mid-run** on "
        "Windows/WSL2 Docker Desktop: `watchfiles` (used by `worker/Dockerfile`'s `dev` stage / "
        "`scripts/worker-entrypoint.sh` to reload on source changes) can raise "
        "`WatchfilesRustInternalError: ... Cannot allocate memory (os error 12)` and exit, "
        "silently stranding queued runs — they surface as this script's own `timed_out` outcome, "
        "not an orchestrator failure, since the tasks were never picked up. If `make reliability` "
        "(which uses `docker compose up ... worker`, the `dev` target) hits this, build and run "
        "the `prod` target instead for the measurement: `docker build --target prod -f "
        "worker/Dockerfile -t isnad-worker-prod .` then `docker run -d --name isnad-worker-1 "
        "--network isnad_default --network-alias worker -e DATABASE_URL=... -e REDIS_URL=... "
        "-e STORAGE_ROOT=/data/artifacts -e PUBLIC_FILES_URL=... -v isnad_artifacts:/data/artifacts "
        "isnad-worker-prod` (it has no file watcher, so nothing to crash)."
    )
    lines.append(
        "2. **Git Bash mangles a leading-slash env var.** Passing `-e STORAGE_ROOT=/data/artifacts` "
        "to a raw `docker run` from Git Bash on Windows silently rewrites it to a host path "
        "(e.g. `C:/Program Files/Git/data/artifacts`), which then fails inside the Linux container "
        "with `PermissionError: 'C:'` on the first file write — a genuine node failure, but an "
        "environment bug, not an orchestrator one. Prefix the command with `MSYS_NO_PATHCONV=1`, "
        "or run it from PowerShell/cmd instead. `docker-compose.yml`'s own `environment:` blocks "
        "are not affected — this only bites a raw `docker run -e ...` from Git Bash."
    )
    lines.append("")

    csv_runs = [
        {
            "run_id": r["id"],
            "workflow_id": r["workflow_id"],
            "workflow_name": workflow_names.get(str(r["workflow_id"]), ""),
            "status": r["status"],
            "total_nodes": r["total_nodes"],
            "failed_nodes": r["failed_nodes"],
            "created_at": r["created_at"],
            "started_at": r["started_at"],
            "completed_at": r["completed_at"],
        }
        for r in runs
    ]
    csv_logs = [
        {
            "log_id": log["id"],
            "run_id": log["run_id"],
            "node_id": log["node_id"],
            "agent_type": log["agent_type"],
            "status": log["status"],
            "retry_count": log["retry_count"],
            "duration_ms": log["duration_ms"],
            "error_message": log["error_message"],
        }
        for log in logs
    ]
    csv_approvals = [
        {
            "approval_id": a["id"],
            "log_id": a["log_id"],
            "run_id": a["run_id"],
            "node_id": a["node_id"],
            "agent_type": a["agent_type"],
            "decision": a["decision"],
            "decided_by_email": a["decided_by_email"],
            "decided_at": a["decided_at"],
            "note": a["note"],
        }
        for a in approvals
    ]

    return Report(
        label=label,
        since=since,
        until=until,
        text="\n".join(lines) + "\n",
        csv_runs=csv_runs,
        csv_logs=csv_logs,
        csv_approvals=csv_approvals,
    )


def _emit(report: Report, out_md: Path, csv_dir: Path, label: str) -> None:
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(report.text, encoding="utf-8")
    print(f"Wrote {out_md}")
    _write_csv(csv_dir / f"reliability-{label}-runs.csv", report.csv_runs)
    _write_csv(csv_dir / f"reliability-{label}-logs.csv", report.csv_logs)
    _write_csv(csv_dir / f"reliability-{label}-approvals.csv", report.csv_approvals)
    print(f"Wrote CSVs to {csv_dir}/reliability-{label}-*.csv")


# ---------------------------------------------------------------------------- CLI


def _default_label() -> str:
    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--label", default=None, help="Campaign tag, also used in CSV filenames (default: timestamp).")

    run_p = sub.add_parser("run", help="Drive runs through the real HTTP API.")
    add_common(run_p)
    run_p.add_argument("--api", default="http://localhost:8000")
    run_p.add_argument("--email", default="demo@gp.local")
    run_p.add_argument("--runs", type=int, default=60)
    run_p.add_argument("--concurrency", type=int, default=2)
    run_p.add_argument("--run-timeout", type=float, default=240.0, help="Seconds to wait for one run to finish.")
    run_p.add_argument("--window", type=Path, default=None, help="Where to write the campaign window JSON.")
    run_p.set_defaults(func=cmd_run)

    report_p = sub.add_parser("report", help="Aggregate a campaign window straight from PostgreSQL.")
    add_common(report_p)
    report_p.add_argument("--database-url", default=None, help="Defaults to $DATABASE_URL or the compose default.")
    report_p.add_argument("--window", type=Path, default=None, help="Campaign window JSON written by `run`.")
    report_p.add_argument("--since", default=None, help="ISO timestamp; used only without --window.")
    report_p.add_argument("--until", default=None, help="ISO timestamp; used only without --window.")
    report_p.add_argument("--workflow-ids", nargs="*", default=None, help="Used only without --window.")
    report_p.add_argument("--out-md", type=Path, default=DEFAULT_REPORT_MD)
    report_p.add_argument("--csv-dir", type=Path, default=DEFAULT_CSV_DIR)
    report_p.set_defaults(func=cmd_report)

    both_p = sub.add_parser("both", help="Run, then report (the common case).")
    add_common(both_p)
    both_p.add_argument("--api", default="http://localhost:8000")
    both_p.add_argument("--email", default="demo@gp.local")
    both_p.add_argument("--runs", type=int, default=60)
    both_p.add_argument("--concurrency", type=int, default=2)
    both_p.add_argument("--run-timeout", type=float, default=240.0)
    both_p.add_argument("--window", type=Path, default=None)
    both_p.add_argument("--database-url", default=None)
    both_p.add_argument("--out-md", type=Path, default=DEFAULT_REPORT_MD)
    both_p.add_argument("--csv-dir", type=Path, default=DEFAULT_CSV_DIR)

    def _run_then_report(args: argparse.Namespace) -> None:
        cmd_run(args)
        cmd_report(args)

    both_p.set_defaults(func=_run_then_report)
    return parser


def main(argv: list[str] | None = None) -> int:
    import os

    parser = build_parser()
    args = parser.parse_args(argv)
    if args.label is None:
        args.label = _default_label()
    if getattr(args, "window", None) is None:
        args.window = DEFAULT_CSV_DIR / f"reliability-{args.label}-window.json"
    if hasattr(args, "database_url") and not args.database_url:
        args.database_url = (
            os.environ.get("DATABASE_URL_HOST") or os.environ.get("DATABASE_URL") or DEFAULT_DATABASE_URL
        )
        # A DATABASE_URL of postgresql://...@db:5432/... (the in-container hostname) is useless
        # from the host running this script — fall back to the documented host-side default.
        if "@db:" in args.database_url:
            args.database_url = DEFAULT_DATABASE_URL

    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
