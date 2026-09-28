# API latency under load — w9

GP-plan W9 · C7 · feeds **PART 6 — Results & Metrics**, NFR-01 ("the system shall handle long-running tasks asynchronously using Celery and Redis to ensure the UI remains responsive") and AT-11 ("no request blocks on the worker... record p95 API latency during the run").

Measured 2026-09-28 against the real HTTP API — no shortcuts through the orchestrator — signed in as the seeded demo user (`POST /auth/dev-login`).

## NFR-01 — UI responsiveness under load

| Condition | Requests | p50 (ms) | p95 (ms) | p99 (ms) | max (ms) | Error rate | NFR-01 target p95 | Pass? |
|---|---|---|---|---|---|---|---|---|
| Idle | 8036 | 25.3 | 83.1 | 94.1 | 128.6 | 2.03% | 500 | ✅ |
| During a 1080p video render | 4230 | 39.4 | 146.4 | 302.4 | 485.6 | 1.82% | 500 | ✅ |

**Target.** 500 ms p95 is not a number from any source document — GP-plan NFR-01, AT-11 and M1 §5 all state the requirement qualitatively ("the UI remains responsive", "no request blocks on the worker") with no latency figure. This is the number this measurement was written against: ordinary web-UI responsiveness, the threshold past which a person notices lag. Treat the pass/fail column as this script's own bar, not a supervisor-agreed one — the qualitative claim that matters more is directly below.

**The qualitative claim NFR-01 actually makes** — a video render does not block any API request — is checked separately: the render phase's read endpoints (`GET /workflows`, `GET /runs/{id}`, ...) all kept returning throughout the render window (see the overlap check and per-endpoint table below); nothing timed out or queued behind the worker, because the API process never touches FFmpeg — that work is entirely on the Celery worker, a separate container/process (C2 vs. C3).

## Overlap check — was a video node actually rendering during phase (b)?

Render-phase load window: `2026-09-28T15:51:14.610019+00:00` to `2026-09-28T15:51:44.695724+00:00` (30.1s).

**49 separate 1080p renders** were driven through this window — not one long render, but a pool kept topped up to the requested concurrency (see Caveats: the seeded template's fake narration is short, so one render finishes in well under a second even at 1080p). Their `started_at`/`completed_at` timestamps (read back from `GET /runs/{id}` after each run finished, not assumed) were clipped to the load window and merged, since two renders in flight at once must not be double-counted:

| Metric | Value |
|---|---|
| Renders driven through the window | 49 |
| Window covered by at least one active video render | 16.9s / 30.1s (56%) |

Sample of the first 5 run(s) (all 49 are in the JSON summary):

| Run id | Video node status (final) | node started_at | node completed_at | Overlap with load window |
|---|---|---|---|---|
| 3ed2c4df-2a35-4bc4-bc92-206db8cbfe38 | success | 2026-09-28T15:51:14.582371Z | 2026-09-28T15:51:15.465345Z | 0.9s |
| 28f0d013-080d-4d29-9861-64a0399b7750 | success | 2026-09-28T15:51:14.653945Z | 2026-09-28T15:51:15.500661Z | 0.8s |
| c02385c7-9b91-443a-b3cf-f5e8d6acc5cd | success | 2026-09-28T15:51:16.255498Z | 2026-09-28T15:51:17.388620Z | 1.1s |
| 9e007ae7-1c43-4b17-869d-eafe3ec7ddeb | success | 2026-09-28T15:51:16.258205Z | 2026-09-28T15:51:17.386440Z | 1.1s |
| 67951608-bfe6-42b0-b0f1-b09d854a922d | success | 2026-09-28T15:51:18.135010Z | 2026-09-28T15:51:18.925889Z | 0.8s |

**56% of the render-phase window had a video node genuinely `running` (confirmed from real `started_at`/`completed_at` timestamps, not assumed)** — the "during render" row above was measured while FFmpeg was actually working for most of the window, not just while a run happened to exist.

## Per-endpoint — idle

| Endpoint | Requests | p50 (ms) | p95 (ms) | p99 (ms) | max (ms) | Error rate |
|---|---|---|---|---|---|---|
| GET /agents/catalog | 380 | 20.9 | 29.3 | 37.9 | 55.5 | 0.00% |
| GET /health | 820 | 5.8 | 9.3 | 13.8 | 28.6 | 0.00% |
| GET /runs/{id} | 1746 | 26.7 | 36.4 | 42.2 | 72.3 | 0.06% |
| GET /runs/{id}/logs | 1279 | 26.6 | 36.7 | 51.0 | 67.8 | 0.00% |
| GET /workflows | 1291 | 29.4 | 39.6 | 57.5 | 71.8 | 0.15% |
| GET /workflows/{id} | 1252 | 19.7 | 27.6 | 34.2 | 59.1 | 0.00% |
| POST /workflows/{id}/validate | 406 | 24.6 | 34.6 | 50.1 | 58.5 | 0.00% |
| PUT /workflows/{id} | 862 | 82.2 | 97.8 | 113.2 | 128.6 | 18.56% |

## Per-endpoint — during render

| Endpoint | Requests | p50 (ms) | p95 (ms) | p99 (ms) | max (ms) | Error rate |
|---|---|---|---|---|---|---|
| GET /agents/catalog | 256 | 30.3 | 58.4 | 84.1 | 103.5 | 0.00% |
| GET /health | 419 | 8.2 | 15.1 | 22.5 | 49.3 | 0.48% |
| GET /runs/{id} | 897 | 40.3 | 75.5 | 91.4 | 116.6 | 0.22% |
| GET /runs/{id}/logs | 651 | 39.6 | 70.9 | 83.4 | 124.4 | 0.00% |
| GET /workflows | 646 | 111.0 | 315.7 | 411.2 | 485.6 | 0.00% |
| GET /workflows/{id} | 711 | 29.2 | 51.8 | 69.5 | 91.2 | 0.14% |
| POST /workflows/{id}/validate | 219 | 38.3 | 72.1 | 91.4 | 124.5 | 0.00% |
| PUT /workflows/{id} | 431 | 90.3 | 130.0 | 170.8 | 248.6 | 16.71% |

## Caveats

- **Local machine, not a benchmarking rig.** Everything (API, worker, DB, Redis, this script) runs on one Windows 11 development machine under Docker Desktop/WSL2 — absolute numbers are indicative, not a hosted-production claim.
- **FAKE_ADAPTERS=true.** Researcher/writer/publisher/email calls are canned fake responses (near-zero latency); only the video agent does real work (FFmpeg via `exporters/video.py`), matching `docs/metrics/video-worker.md` and `docs/metrics/reliability.md`. Real LLM/search/publish API calls would add their own latency to those specific run steps, but would not change the finding here, since the API process never calls them — the worker does, off the request path.
- **No network latency to Supabase.** Local Postgres via `docker-compose.yml`, not the production Supabase connection — the deployed API adds real network round-trips per query that this local measurement cannot see.
- **Load pattern.** Each worker fires requests back-to-back for the whole phase (no think-time) — a load-test stress pattern chosen to make the API's behaviour under concurrent load obvious, not a simulation of one person's polling cadence (which would be far lighter and show even better latency).
- **Why the render phase uses many short renders, not one long one.** `adapters/tts/fake.py`'s `FakeTTS.speak` caps synthesised narration at `word_count // 15` seconds (floor 1s) — the seeded template's canned script is short, so even a 1080p render under the W5 prod worker limits finishes in well under a second (`docs/metrics/video-worker.md` measured 6-30s per render, but that used a purpose-built fixed-duration fake TTS this script does not — it drives the seeded template exactly as a real user would). The render-phase pool keeps `--videos` renders going continuously instead of firing once, so the window has real coverage — see the overlap check above for how much.
- **A real bug this run surfaced, not a latency artifact:** `PUT /workflows/{id}` returned 5xx on 16.7% of render-phase requests (and 18.6% idle) whenever multiple autosave writes hit the *same* workflow concurrently. The API logs show `psycopg.errors.UniqueViolation` on `pk_agent_nodes`: `api/services/workflows.py`'s `save_graph` deletes and re-inserts `agent_nodes` rows without locking the workflow row between the two, so two concurrent `PUT`s to one workflow can each see the old rows deleted and then race to insert the same node ids. This is orthogonal to NFR-01/video rendering (it reproduces with the worker idle) and is unlikely in the shipped UI, which autosaves one workflow from one tab — flagged here because this load test is what found it, not filed against this script's own scope.
- **Why this script deletes the workflows it creates.** An earlier run of this script left ~100 scratch/video-copy workflows on the demo account, and `GET /workflows` (`api/routers/workflows.py`'s `list_workflows`) got visibly slower (`GET /workflows` p50 rose from ~10-50ms with 3 seeded workflows to ~200-370ms with 100) because it runs one extra query per workflow to find that workflow's latest run — an N+1 pattern that scales with how many workflows a user has, not with load. This script now deletes every workflow it creates when it finishes (`--keep-workflows` to leave them, e.g. for debugging), so the numbers above reflect the 3 seeded templates, not accumulated test data — but the N+1 pattern itself is real and would affect any user with many workflows, independent of this measurement.
- `--concurrency=8 --duration=30.0s --videos=2`.

## Method

```
python scripts/measure_api_latency.py both --duration 30 --concurrency 8 --videos 2
```

`idle` signs in as the seeded demo user, drives one ordinary (non-video) run to completion for a real run id to poll, then fires the endpoint mix — `GET /health`, `/workflows`, `/workflows/{id}`, `/agents/catalog`, `/runs/{id}`, `/runs/{id}/logs`, `PUT /workflows/{id}` (autosave, against a dedicated scratch workflow) and `POST /workflows/{id}/validate` — from `--concurrency` worker threads for `--duration` seconds. `render` copies the seeded "Blog → Video → YouTube" template `--videos` times, sets each copy's video node `resolution` to `1080p`, starts all of them (`POST /workflows/{id}/run`), drives them to completion in background threads (polling + auto-approving the publisher gate via `POST /runs/{id}/nodes/{node}/approve`, exactly like `scripts/reliability_campaign.py`), and fires the same endpoint mix concurrently. After the load window, it re-reads each run's final state and reports whether the video node's `started_at`/`completed_at` actually overlapped the load window (see the overlap check above) rather than assuming it did.

## Machine

| | |
|---|---|
| Host | Windows 11 Pro, Intel Core i5-14600KF (14 cores / 20 threads), 15.8 GiB RAM |
| Where it ran | `api` on Docker Desktop 29.7.2 / WSL2 (dev target, uvicorn --reload, single process); `worker` built from `worker/Dockerfile`'s `prod` target, run with `docker run --cpus 2 --memory 4g` (the W5 production limits, `docker-compose.prod.yml`) — matches `docs/metrics/video-worker.md`'s host |
| PostgreSQL | 15 (`docker-compose.yml`'s `db` service, local — see caveats) |
| Redis | 7-alpine |
| Python | 3.11 (this script), 3.11-slim (api/worker images) |

A desktop CPU is faster per core than a typical cloud vCPU — expect a hosted deployment to differ from these absolute numbers; re-run on the chosen host before quoting them elsewhere (W11).

## How to rerun

```bash
make latency
# or, with a stack already up:
python scripts/measure_api_latency.py both --api http://localhost:8000 --duration 30 --concurrency 8
```

