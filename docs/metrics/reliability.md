# Reliability campaign — w10

Window: `2026-09-28T14:21:51.435785+00:00` to `2026-09-28T14:23:08.285883+00:00` (UTC). See **Method** below for how to reproduce.

## NFR-02 — handoff success rate

| Metric | Target | Measured |
|---|---|---|
| Total runs | ≥ 50 | 60 |
| Total node handoffs | — | 180 |
| Successful handoffs | — | 180 |
| **Handoff success rate** | **≥ 99%** | **100.00%**
| Runs completing without retry | — | 60 / 60 |
| Runs halted after 3 retries | — | 0 |

Run success rate (terminal status `succeeded` ÷ total runs): **100.00%** (60/60).

## Per-template

| Template | Runs | Succeeded | Failed | Cancelled | Other |
|---|---|---|---|---|---|
| Blog post | 20 | 20 | 0 | 0 | 0 |
| Blog → Video → YouTube | 20 | 20 | 0 | 0 | 0 |
| Research → PDF → Email | 20 | 20 | 0 | 0 | 0 |

## Per-agent latency and outcomes

| Agent | Handoffs | Success | Failed | Retried | Median (s) | p95 (s) |
|---|---|---|---|---|---|---|
| email | 20 | 20 | 0 | 0 | 0.01 | 0.01 |
| publisher | 20 | 20 | 0 | 0 | 0.01 | 0.01 |
| researcher | 60 | 60 | 0 | 0 | 0.01 | 0.01 |
| video | 20 | 20 | 0 | 0 | 0.19 | 0.22 |
| writer | 60 | 60 | 0 | 0 | 0.01 | 0.01 |

## Retries

| Metric | Value |
|---|---|
| Handoffs retried at least once | 0 |
| Retry-then-success rate | n/a (no retries) |

## Failure causes

No failed node handoffs in this window.

## Total run duration

| Metric | Value |
|---|---|
| Runs with a measured duration | 60 |
| p50 | 1.55s |
| p95 | 1.58s |

## Approvals audit trail (UC-04 evidence)

| Metric | Value |
|---|---|
| Approval gates hit (node parked `awaiting_approval` or later decided) | 40 |
| Approvals recorded (`approvals` table rows) | 40 |
| Gates hit with no recorded decision | 0 (should be 0 — every parked node in this campaign was auto-approved) |
| Decisions: approve / reject | 40 / 0 |

## Caveat

This campaign ran with `FAKE_ADAPTERS=true` (the worker's own default — see `worker/settings.py`): every agent call is a canned, deterministic fake response (`adapters/*/fake.py`), except that the video agent still renders a real file with ffmpeg (`exporters/video.py`), so video-step timing and any resource-exhaustion failures under concurrency are real. The real Google/YouTube/Gmail adapters (`adapters/_google.py`, D-09) are not implemented yet, so **no external-API failure, rate limit, or auth error is represented here** — retries and failures measured above come only from internal orchestration, validation and resource limits, not from a third-party API. Treat this number as a floor on real-world reliability, not a ceiling.

## Method

```
docker compose up -d --build db redis migrate api worker
python scripts/reliability_campaign.py both --runs 60 --concurrency 2 --label w10
```

`run` drives the real HTTP API — no shortcuts through the orchestrator — spreading runs evenly across the seeded template workflows, polling `GET /runs/{id}` and auto-approving every parked gate via `POST /runs/{id}/nodes/{node}/approve`. It records the campaign's start/end timestamps and the seeded workflow ids to a window file; `report` (or the second half of `both`) aggregates directly from PostgreSQL (`execution_runs`, `execution_logs`, `agent_outputs`, `approvals`) filtered to that window, so runs from any other user of the same database are excluded. Rerun the report alone with `python scripts/reliability_campaign.py report --window docs/metrics/data/reliability-window.json`.

## Machine

Measured on a single Windows 11 development machine, Docker Desktop (WSL2 backend), PostgreSQL 15 and Redis 7 via `docker-compose.yml`, worker `--concurrency 2` (Celery prefork), campaign driver concurrency as shown above. Not a dedicated benchmarking environment — absolute latencies are indicative, not a performance claim.

## Operational notes (read before rerunning on Windows)

Two infrastructure issues came up while building this campaign on Windows — neither is an orchestrator handoff failure, so neither run is counted in the numbers above, but both would otherwise waste a rerun:

1. **The worker's `dev` Docker target (file-watching auto-reload) can crash mid-run** on Windows/WSL2 Docker Desktop: `watchfiles` (used by `worker/Dockerfile`'s `dev` stage / `scripts/worker-entrypoint.sh` to reload on source changes) can raise `WatchfilesRustInternalError: ... Cannot allocate memory (os error 12)` and exit, silently stranding queued runs — they surface as this script's own `timed_out` outcome, not an orchestrator failure, since the tasks were never picked up. If `make reliability` (which uses `docker compose up ... worker`, the `dev` target) hits this, build and run the `prod` target instead for the measurement: `docker build --target prod -f worker/Dockerfile -t isnad-worker-prod .` then `docker run -d --name isnad-worker-1 --network isnad_default --network-alias worker -e DATABASE_URL=... -e REDIS_URL=... -e STORAGE_ROOT=/data/artifacts -e PUBLIC_FILES_URL=... -v isnad_artifacts:/data/artifacts isnad-worker-prod` (it has no file watcher, so nothing to crash).
2. **Git Bash mangles a leading-slash env var.** Passing `-e STORAGE_ROOT=/data/artifacts` to a raw `docker run` from Git Bash on Windows silently rewrites it to a host path (e.g. `C:/Program Files/Git/data/artifacts`), which then fails inside the Linux container with `PermissionError: 'C:'` on the first file write — a genuine node failure, but an environment bug, not an orchestrator one. Prefix the command with `MSYS_NO_PATHCONV=1`, or run it from PowerShell/cmd instead. `docker-compose.yml`'s own `environment:` blocks are not affected — this only bites a raw `docker run -e ...` from Git Bash.

