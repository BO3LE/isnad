# Testing Process and Results

*Milestone 3 report chapter — GP: A Visual AI-Agent Workflow Platform for End-to-End Content
Automation. Drafted W12 (C7, Mohammed Abdullah Bajaba), from `docs/GP-plan.md` §8.1–§8.3, the
automated test suites in this repository, `docs/metrics/*.md`, and `docs/fresh-machine-test.md`.
Every count and figure below was either read from a committed evidence file or produced by running
the named test suite; nothing is estimated. Places where a number can only come from a live team
session (the acceptance walkthrough, usability participants, production credentials) are marked
`[[TO FILL: …]]` rather than guessed — see `docs/report/README.md` for the consolidated list.*

## 1. Testing strategy

The platform is built as seven independently deployable components (`contracts`, `frontend`, `api`,
`worker`, `agents/*`, `adapters/*`, `exporters`, `db` — GP-plan Part 2), and the test strategy
mirrors that boundary structure rather than testing the system as one monolith. Each level exists to
catch a different class of defect, and each is automated and runs in CI so it cannot silently rot.

| Level | What it proves | Tool |
|---|---|---|
| Unit / component-in-isolation | Each component behaves correctly with every other component absent — the architectural claim in GP-plan Part 2 ("tested alone by…") | pytest (Python components), Vitest (frontend) |
| Integration on real PostgreSQL | The orchestrator, `SqlRunStore` and the installed agents behave correctly against a real relational database, not a mock | pytest + PostgreSQL 15 (`tests/integration`, `db/tests/test_rls.py`) |
| End-to-end, mocked API | The frontend alone — canvas, forms, run monitor, logs, outputs — behaves correctly with the entire backend stopped (GP-plan C1's "decoupling test") | Playwright (`frontend/e2e`) |
| End-to-end, full stack | The same user journeys work through the real UI against the real API, worker, Redis and PostgreSQL, with `FAKE_ADAPTERS=true` so no external API spend is required | Playwright (`frontend/e2e-fullstack`) |
| Acceptance | The 18 test cases in GP-plan §8.3, tracing back to the FR/NFR/UC requirements in §8.1 | Manual walkthrough plus, where an automated test demonstrably reproduces the same behaviour, that test |
| Non-functional / performance / reliability | NFR-01 (latency under load), NFR-02 (handoff success rate over many runs), NFR-04 (a seventh agent needs no core-code change) | Purpose-built measurement scripts (`scripts/measure_api_latency.py`, `scripts/reliability_campaign.py`, `scripts/measure_video_worker.py`) driving the real HTTP API |
| Usability | NFR-03 — the interface is usable by non-technical people with no coding | Moderated sessions (not yet run — see §6.3) |
| Static / structural checks | The component boundaries themselves are never violated, and every agent folder has a valid manifest | `import-linter`, a grep contract, `ruff`, `scripts/validate_manifests.py`, Alembic migration round-trip |

**Why component-in-isolation testing matters here.** GP-plan Part 2's "decoupling test" for each
component is not a slogan — it is enforced structurally: the `api` test matrix entry installs no
worker, Redis or PostgreSQL; the `worker` entry installs no agents at all (Section 4 confirms this
was reproduced: `worker`'s 39 tests pass with zero packages under `agents/` on the Python path); each
agent is installed and tested completely alone, one at a time, uninstalled before the next. This is
what makes "changing an agent forces you to edit the orchestrator" a build-time-checkable violation
rather than a design aspiration.

**The fake-adapter strategy.** Every external port (`LLMPort`, `SearchPort`, `TTSPort`,
`PublishPort`, `StoragePort`) ships a `fake.py` implementation returning canned, deterministic
output (GP-plan C5). `FAKE_ADAPTERS=true` is the default in every component's own settings and in
CI, and it is what makes the entire test pyramid above the unit level runnable for free, offline and
deterministically — including the Video agent's real FFmpeg render, which is exercised with a fake
(but real-audio-signal) TTS input rather than a real network call. The one place this strategy is
deliberately *not* used, and consequently is not automated, is anything that needs a genuine external
response — the real YouTube/Drive/Gmail publish path (`adapters/src/adapters/publish/youtube.py`,
`drive.py`, `adapters/src/adapters/email/gmail.py`) still carries a `TODO(W6, Zain)` for the
production upload flow at the time of writing, so AT-05's "real YouTube test channel" outcome cannot
be produced by an automated test and is left for the team (§5).

## 2. Test environment

### 2.1 Local measurement machine

The counts in §3 and the performance/reliability figures in §6 were measured on the same
development machine described in `docs/metrics/*.md` and `docs/fresh-machine-test.md`:

| | |
|---|---|
| OS | Windows 11 Pro, build 10.0.26200 |
| CPU / RAM | Intel Core i5-14600KF (14 cores / 20 threads), 15.8 GiB RAM |
| Docker | Docker Desktop 29.7.2 (build a7dcaa6), WSL2 backend, Linux 6.18.33.2-microsoft-standard-WSL2 |
| Docker Compose | v5.5.0 |
| Python | 3.11.9 (host), 3.11-slim (container images) |
| Node.js | 20.x (container images; matches CI's `NODE_VERSION: "20"`) |
| PostgreSQL | 15 (`postgres:15`, `docker-compose.yml`'s `db` service) |
| Redis | 7-alpine |
| FFmpeg | 7.1.5 (inside the worker/exporters Docker images only — **not installed on this Windows host**, so any test gated on a local FFmpeg binary is skipped outside Docker; see the skip counts in §3) |

This is a desktop development machine, not a dedicated benchmarking rig or the eventual production
host — every absolute timing figure in this chapter should be read as indicative, not a hosted-
production claim (flagged again in each metrics document and in §8).

### 2.2 Continuous Integration runners

GitHub Actions, `ubuntu-latest` runners, one job per row of `.github/workflows/ci.yml`'s matrix.
`PYTHON_VERSION: "3.11"`, `NODE_VERSION: "20"`. PostgreSQL 15 and Redis (where a job needs them) are
brought up as GitHub Actions service containers, not Docker Compose, except for the two jobs that
explicitly build and run the full `docker-compose.yml` stack (`e2e-fullstack`, `integration`).

## 3. Automated test inventory

Every count below was produced by actually running the suite on 2026-09-29, not estimated. Python
suites were run with this worktree's own `contracts/src`, `db/src`, `adapters/src`, `exporters/src`,
`worker/src`, `api/src` and each `agents/<name>/src` placed first on `PYTHONPATH`, against the
already-installed test toolchain (`pytest 9.1.1`), exactly reproducing how `.github/workflows/ci.yml`
installs and isolates each component. PostgreSQL-backed suites ran against a purpose-created
database `c7_report` on the existing `isnad-db-1` container (`localhost:5433`), which was dropped
immediately afterwards; the shared `gp` database was never touched. Frontend suites were run from
the already-`npm ci`'d checkout at the same commit (`c7/final` @ `091ecf7`, i.e. before this
branch's own doc-only changes), since this worktree has no `frontend/node_modules` of its own.

### 3.1 Unit / component-in-isolation (pytest, one component's dependencies only)

| Component | Passed | Skipped | Failed | Notes |
|---|---|---|---|---|
| `contracts` | 14 | 0 | 0 | |
| `db` (unit, no live database) | 12 | 0 | 0 | `db/tests/test_rls.py` excluded here — it needs PostgreSQL, counted in §3.2 |
| `adapters` | 43 | 0 | 0 | |
| `exporters` | 2 | 1 | 0 | Skipped: `tests/test_exporters.py` — "ffmpeg not installed" (this Windows host; present in the Docker image, see §2.1) |
| `worker` | 39 | 0 | 0 | Run with **zero** `agents/*` packages on the path — the C3 decoupling test reproduced directly |
| `api` | 81 | 0 | 0 | Run with no worker, Redis or PostgreSQL present — the C2 decoupling test reproduced directly |
| `agents/researcher` | 2 | 0 | 0 | Installed and run alone, as CI's matrix does |
| `agents/writer` | 2 | 0 | 0 | Includes the malformed-JSON reformat-retry test (RB-02 evidence, §5) |
| `agents/image` | 1 | 0 | 0 | |
| `agents/video` | 1 | 1 | 0 | Skipped: real render test needs local FFmpeg |
| `agents/publisher` | 2 | 0 | 0 | |
| `agents/email` | 2 | 0 | 0 | |
| **Subtotal** | **199** | **2** | **0** | |

### 3.2 Integration, real PostgreSQL 15

| Suite | Passed | Skipped | xfailed (known bug) | Failed | Notes |
|---|---|---|---|---|---|
| `db/tests/test_rls.py` | 2 | 0 | 0 | 0 | Row Level Security, plain-Postgres and simulated-Supabase modes |
| `tests/integration` (`test_run_lifecycle.py` + `test_run_reliability.py`) | 16 | 1 | 4 | 0 | Skipped: the video-template lifecycle test (needs FFmpeg). The 4 `xfail(strict=True)` cases pin down known worker bugs — see §7; they are not counted as failures because the suite is designed to fail the build if any of them starts passing *silently without the marker being updated*, and to fail it if any of them ever starts truly passing (`strict=True`) |
| **Subtotal** | **18** | **1** | **4** | **0** | |

CI's `run-lifecycle` job runs the same `tests/integration` suite with `REQUIRE_INTEGRATION_DB=1`, so
a missing database is a hard failure there, not a skip — this reproduction used the equivalent real
database, so the counts above are what CI would also report (modulo the FFmpeg skip, which is not
skipped in CI because the job installs FFmpeg first).

### 3.3 Frontend

| Suite | Files | Tests | Passed | Failed | Notes |
|---|---|---|---|---|---|
| Vitest (unit / component) | 23 | 193 | 193 | 0 | `npm run test` equivalent; includes `StepDrawer.test.tsx` (13 tests, agent-configuration-form generation — AT-08 evidence) |
| Playwright, mocked API (`frontend/e2e`) | 7 spec files | 41 | 41 | 0 | Entire backend stopped — reproduces C1's own decoupling test. Includes `seventh-agent.spec.ts` (2 tests, NFR-04/AT-12 frontend-side evidence, §5, §6.4) |
| Playwright, real stack (`frontend/e2e-fullstack`) | 3 spec files | 3 | 3 | 0 | See caveat below |
| **Subtotal** | | **237** | **237** | **0** | |

**Caveat on the full-stack run.** `frontend/e2e-fullstack` needs a real `docker compose` stack
(`db`, `redis`, `migrate`, `api`, `worker`, `frontend`) with three settings that CI's job sets
implicitly by having no `.env` file at all, but that this machine's own local `.env` overrides for
day-to-day development: `VITE_AUTH_MODE` (must be `dev`, not `supabase`, for the dev sign-in bypass
the specs use), `FAKE_ADAPTERS` (must be `true` on both `api` and `worker`, or the Publisher node's
missing-Google-connection warning becomes a hard validation error and no run can start), and
`CORS_ORIGINS` (must include whatever host port the frontend container is actually reachable on).
Running the isolated stack under this repository's default ports also collided with another stack
already running on this shared machine, so the run used remapped ports
(`DB_HOST_PORT=5443 REDIS_HOST_PORT=6389 API_HOST_PORT=8010 FRONTEND_HOST_PORT=5183`) plus a
throwaway Compose override supplying the three settings above — this is exactly the class of
environment-drift issue `docs/fresh-machine-test.md` documents elsewhere, applied here to the CI job
rather than `SETUP.md`. With those three corrected, all three specs (blog post; blog → video →
YouTube with a real MP4 render and an approval gate; research → PDF → email with a second approval
gate) passed against the real stack. No application code was touched to make this pass — only the
test environment's own settings.

### 3.4 Static / structural checks (reproduced locally, not "tests" in the pytest sense)

| Check | Result |
|---|---|
| `ruff check .` | All checks passed |
| `ruff format --check .` | 146 files already formatted |
| `lint-imports` (`.importlinter`, the seven component-boundary contracts) | 8 kept, 0 broken (167 files, 496 dependencies analysed) |
| Forbidden-import grep (`api`/`worker` must never import `agents`) | Passed — no match |
| `scripts/validate_manifests.py` | 6/6 agent folders valid |

### 3.5 Grand total

**456 automated test cases exercised, 456 passed, 3 skipped (all for the same reason: no local
FFmpeg binary outside Docker on this host), 4 `xfail(strict=True)` (deliberately, pinning known
worker bugs — §7), 0 unexplained failures.**

## 4. Continuous integration

`.github/workflows/ci.yml` runs on every pull request and on push to `main`. Jobs:

| Job | Checks | In `ci-ok` (required)? |
|---|---|---|
| `boundaries` | ruff, `lint-imports`, the forbidden-import grep, `scripts/validate_manifests.py`, `landing/site/index.html` freshness | Yes |
| `python-tests` (matrix) | `contracts`, `db`, `adapters`, `exporters`, `worker`, `api`, `agents/*` — each installed with only its own declared dependencies, exactly as reproduced in §3.1 | Yes |
| `db-migrations` | `alembic upgrade head` → `downgrade base` → `upgrade head` → `alembic check` (no model drift) against PostgreSQL 15; `db/tests/test_rls.py`; `db.seed` run twice (idempotency) | Yes |
| `run-lifecycle` | `tests/integration` against PostgreSQL 15, `REQUIRE_INTEGRATION_DB=1` | Yes |
| `api-contract` | `contracts/openapi.json` matches the live API; `frontend/src/lib/api-types.ts` matches `openapi.json` | Yes |
| `frontend` | ESLint, `tsc` typecheck, Vitest, production build | Yes |
| `e2e` | Playwright against the mocked API, no backend | Yes |
| `e2e-fullstack` | Playwright against the real Docker Compose stack, `FAKE_ADAPTERS=true` | **No** — informational. Building the FFmpeg worker image and driving three real runs (one rendering video) is slower and newer than the rest of the pipeline; it runs on every PR so regressions are visible, but does not block merging, pending a track record |
| `integration` | `docker compose up` the whole stack, `scripts/smoke_test.py` | **No** — only runs on `main` (after merge), to save CI minutes |

**`ci-ok`** depends on the seven required jobs above and is the single check named in the branch
protection rule, so adding or renaming a required job never needs a rule edit — and, by the same
token, `main` itself can never be pushed to directly (GP-plan W1). `e2e-fullstack` and `integration`
are deliberately excluded from the gate for the reasons in their rows, not because they are
considered less important; §3.3's caveat is exactly the kind of drift `e2e-fullstack` exists to
surface once it does run.

## 5. Acceptance test cases

The table below is GP-plan §8.3's *Report table* view (`In report = checked`), 18 rows. **Actual**
and **Result** are filled only where an automated test in this repository demonstrably reproduces
the case's own steps; the citation names the exact test. Where the case needs something the
automated suite cannot produce — a real external API response, or a live moderated session — the
cell is left as an explicit placeholder rather than a guess, per the brief for this chapter.

| ID | Level | Requirement | Expected | Actual | Result | Evidence |
|---|---|---|---|---|---|---|
| AT-01 | Acceptance | FR-01, UC-01 | Three connected nodes render; Save succeeds; reloading the page restores the same graph. | Partially automated. Dragging a palette agent onto the canvas already connected, and a moved node's position persisting through a reload, are both covered; no single automated test builds a fresh 3-node graph from an empty canvas, saves, reloads and asserts the identical graph. | **Partial — automated coverage exists but does not match the case exactly** | `frontend/e2e/canvas.spec.ts::"the palette suggests what fits next, and a click adds it already connected"`; `frontend/e2e/canvas.spec.ts::"moving a step still saves it, on the grid"` |
| AT-02 | Acceptance | FR-02 | Researcher, Writer, Video, Publisher and Email all available and draggable, each with its own configuration schema. | The worker-published catalog (6 agents, a superset including Image) is served and rendered into a schema-driven palette and settings form. | **Pass (automated)** | `api/tests/test_api.py::test_catalog_is_served_from_the_worker_published_source`; `frontend/src/components/canvas/StepDrawer.test.tsx` (13 tests) |
| AT-03 | Acceptance | FR-03 | A text article, at least one image/thumbnail and a playable MP4 are produced and stored against the run. | Structurally automated with fake adapters: a Researcher → Writer → Video run produces an article, a thumbnail and a real, playable MP4 (real FFmpeg encode; canned research/narration content). Genuine researched content on a topic chosen live needs real LLM/search credentials. | **Partial — structure proven, content authenticity not** | `frontend/e2e-fullstack/blog-video-youtube.spec.ts` | 
| AT-04 | Acceptance | FR-04 | All three files download via signed URL and open correctly in their native applications. | Automated for the local storage backend (`storage_backend=local`, the default): downloads work and a missing file is reported rather than silently failing. The Supabase signed-URL path (`storage_backend=supabase`) is not exercised by this run. | **Partial — local backend only** | `frontend/e2e/outputs.spec.ts::"a download opens the file instead of navigating the app away"`; `frontend/e2e/outputs.spec.ts::"a file with nothing behind it says so, and cannot be reached by keyboard"`; `frontend/e2e-fullstack` fixtures' `openOutputsFromCanvas` (Files tab) |
| AT-05 | Acceptance | FR-05, UC-05 | Video on the YouTube test channel; file in Drive; email arrives with working links. Remote URLs recorded in agent_outputs. | Cannot be produced automatically: `adapters/src/adapters/publish/youtube.py` still carries `TODO(W6, Zain): resumable upload with title, description, tags and privacy` at the time of writing, so no automated or manual run has gone through the real Google APIs yet. | [[TO FILL: run once real Google OAuth credentials and a YouTube test channel are wired up — W6/W10 owner, Zain]] | — |
| AT-06 | Acceptance | FR-06 | Node retries exactly three times with exponential backoff, retry_count reaches 3, run halts, downstream nodes skipped, error visible in the log viewer. | Automated end to end: the orchestrator retries exactly 3 times with backoff, then halts the run and marks downstream nodes skipped. | **Pass (automated)** | `worker/tests/test_orchestrator.py::test_retry_exhaustion_halts_run_and_skips_downstream`; `tests/integration/test_run_reliability.py::test_retries_run_out_then_the_step_fails_and_the_rest_are_skipped` |
| AT-07 | Acceptance | UC-02 | Each node moves pending → running → success in order; UI updates without a manual refresh. | Automated, both mocked and against the real stack: the canvas advances one handover at a time with no manual refresh. | **Pass (automated)** | `frontend/e2e/canvas.spec.ts::"a run plays on the canvas one handover at a time, then waits for approval"`; `frontend/e2e-fullstack/blog-post.spec.ts` |
| AT-08 | Acceptance | UC-03 | Form matches each agent's schema, validates input, values persist in agent_nodes.configuration after save. | Automated: the settings form is generated from each agent's config schema, validates, and an empty required field is visibly flagged rather than silently saved empty. | **Pass (automated)** | `frontend/src/components/canvas/StepDrawer.test.tsx` (13 tests); `frontend/e2e/canvas.spec.ts::"a field left empty says where its value comes from; taking it over and giving it back never stores an empty value"` |
| AT-09 | Acceptance | UC-04 | Run parks at awaiting_approval and publishes nothing until approval. Approve resumes it; reject halts it. Both recorded in approvals. | Automated on both the backend (park/resume/reject, `approvals` table rows) and the frontend (the real approval dialog, and a rejection requiring a reason). | **Pass (automated)** | `tests/integration/test_run_lifecycle.py::test_email_template_parks_for_approval_then_resumes`; `tests/integration/test_run_lifecycle.py::test_a_rejection_halts_the_run_and_skips_what_follows`; `frontend/e2e/canvas.spec.ts::"the approval window shows the thing itself, not a promise of it"`; `frontend/e2e/canvas.spec.ts::"rejecting needs a reason and never reads as a failure"` |
| AT-10 | Acceptance | UC-06 | Per-node timestamps, status, retry count, duration and error message all shown; log exports as CSV. | Automated: the log viewer's per-attempt detail and CSV export (matching the on-screen filter, in UTC) are both covered. | **Pass (automated)** | `frontend/e2e/logs.spec.ts::"a retried step tells the whole story: every attempt, the waits, and what it cost"`; `frontend/e2e/logs.spec.ts::"the CSV holds the rows on screen, in UTC, whatever the table is showing"`; `frontend/e2e/logs.spec.ts::"the CSV shrinks with the filter, so the file matches what was being read"` |
| AT-11 | Performance | NFR-01 | No request blocks on the worker. Record p95 API latency during the run. | Measured directly against the real HTTP API (not simulated): idle p95 83.1 ms; during a 1080p video render p95 146.4 ms, both under this team's own 500 ms bar (see §6.1 — no source document gives a number). All read endpoints kept responding throughout a render window with confirmed real render overlap (56% of the window). | **Pass, against a target the team set itself — flag for supervisor confirmation** | `docs/metrics/api-latency.md` (measured 2026-09-28) |
| AT-12 | Acceptance | NFR-04 | Appears in the palette with a working configuration form, no frontend and no orchestrator change. Record the file count as NFR-04 evidence. | The frontend-boundary half is automated: an agent catalog entry the codebase has never seen builds a working palette entry, node and settings form with zero `frontend/src` files touched, by construction (the spec only injects a JSON fixture). The full evidence — actually adding `agents/<name>/`, restarting the worker, and running `git diff --stat main` to show zero files changed outside that folder — is a one-time team exercise (GP-plan W8) that has not been re-run for this report. | **Partial — frontend mechanism proven automatically; the file-count artifact itself is a placeholder** | `frontend/e2e/seventh-agent.spec.ts` (2 tests); mechanism documented in `docs/ADDING_AN_AGENT.md`. File count: [[TO FILL: re-run the W8 seventh-agent exercise and paste `git diff --stat main` — Zain]] |
| RT-01 | Reliability | NFR-02 | Handoff success rate reported against the 99% target, with retry frequency broken down by external API. | Measured directly against the real HTTP API: 60 runs, 180/180 node handoffs succeeded (100.00%), 0 retries, 0 runs halted. Ran entirely with `FAKE_ADAPTERS=true` — no external-API failure, rate limit or auth error is represented, so this is a floor on real-world reliability, not a ceiling (see §6.2). | **Pass against the internal-orchestration slice of NFR-02; the external-API slice is untested** | `docs/metrics/reliability.md` (measured 2026-09-28, `scripts/reliability_campaign.py`) |
| RB-01 | Robustness | FR-06 | No silent failure and no data loss. Run state accurate after restart — resumed or clearly marked failed. | Mostly automated and passing: a redelivered run resumes at the interrupted step with its retry budget intact. One specific crash window is a known, marked bug (§7): a worker lost between saving a step's output and marking it successful causes the redelivery to save a second copy of that output. | **Partial — resume works; one crash window has a known defect (open)** | `tests/integration/test_run_reliability.py::test_a_redelivered_run_resumes_at_the_interrupted_step`; `tests/integration/test_run_reliability.py::test_a_redelivered_run_keeps_the_retry_budget_it_had_used`; defect: `tests/integration/test_run_reliability.py::test_a_crash_between_saving_output_and_marking_success_leaves_one_output` (`xfail`, §7) |
| RB-02 | Robustness | FR-06 | Pydantic rejects it; agent makes one reformat attempt; only then does the orchestrator retry counter advance. Error names the schema violation. | Automated exactly as specified, for the Writer agent (the case names it explicitly). | **Pass (automated)** | `agents/writer/tests/test_agent.py::test_one_reformat_attempt_then_a_readable_error` |
| RB-03 | Robustness | FR-05 | Both fail gracefully with an accurate log entry and a readable UI error, not a stack trace. | Automated at the adapter level: an oversized file and a network failure during upload are both classified correctly (permanent vs. retryable) by the storage adapter. The UI-level "readable error, not a stack trace" half of this case is not separately end-to-end tested for these two specific triggers. | **Partial — adapter classification proven; UI-level readable-error display not separately E2E-tested for these triggers** | `adapters/tests/test_supabase_storage.py::test_too_large_is_permanent`; `adapters/tests/test_supabase_storage.py::test_network_failure_is_retryable` |
| US-01 | Usability | NFR-03 | Completed without writing code and without moderator help. Record time-on-task, completion rate and SUS. Participant count to be agreed with the supervisor. | No moderated session has been run yet; nothing in the repository can substitute for a live human-subjects session. | [[TO FILL: run the moderated usability sessions per GP-plan W11 — Ahmed, participant count to be agreed with the supervisor]] | — |
| IT-01 | Integration | UC-02 | All nodes reach success in topological order; one execution_logs row per node; run marked complete. | Automated against real PostgreSQL. Note the case's own wording says "ephemeral Postgres and Redis"; the actual suite calls the orchestrator directly the way the Celery task does, without Redis/Celery in the loop (documented in `ci.yml`'s own comment on this job) — cheaper and still a faithful test of the orchestration logic, but not a Celery-dispatch test. | **Pass (automated), with the Redis/Celery layer itself out of scope for this specific suite** | `tests/integration/test_run_lifecycle.py::test_blog_template_runs_queued_to_succeeded` |

**Summary.** Of 18 cases: 8 fully automated and passing (AT-02, AT-06, AT-07, AT-08, AT-09, AT-10,
RB-02, IT-01); 6 partially automated, each with a named, specific gap (AT-01, AT-03, AT-04, AT-12,
RT-01, RB-01, RB-03 — 7, see table); 1 measured directly and passing against a team-set target
(AT-11); 2 requiring a live external dependency or human subjects that no automated test can
substitute for (AT-05, US-01).

## 6. Non-functional results

### 6.1 NFR-01 — performance (UI responsiveness under load)

Measured 2026-09-28 against the real HTTP API (`docs/metrics/api-latency.md`), not simulated:

| Condition | Requests | p50 | p95 | p99 | max | Error rate |
|---|---|---|---|---|---|---|
| Idle | 8036 | 25.3 ms | 83.1 ms | 94.1 ms | 128.6 ms | 2.03% |
| During a 1080p video render | 4230 | 39.4 ms | 146.4 ms | 302.4 ms | 485.6 ms | 1.82% |

**On the 500 ms target.** Neither GP-plan's NFR-01 nor AT-11 nor M1 §5 state a latency figure — the
requirement is written qualitatively ("the UI remains responsive", "no request blocks on the
worker"). 500 ms p95 is a bar this team chose itself, as the point past which a person notices lag,
purely so the measurement script had something to compare against; **this number should be
confirmed with the supervisor before being presented as an agreed requirement, not just this team's
own bar.** The qualitative claim NFR-01 actually makes — that a render never blocks any API
request — was checked separately and holds: every read endpoint kept responding throughout a
render window in which real FFmpeg rendering was confirmed active for 56% of the window (49 renders
driven through a 30.1 s window), because the API process never touches FFmpeg — only the Celery
worker does, in a separate container.

**A defect this measurement surfaced.** `PUT /workflows/{id}` (the autosave endpoint) returned 5xx
on 16.7–18.6% of concurrent-write requests in this load test, from a `psycopg.errors.UniqueViolation`
on `pk_agent_nodes` — see §7.

### 6.2 NFR-02 — reliability (handoff success rate)

Measured 2026-09-28 (`docs/metrics/reliability.md`), 60 runs across the three seeded templates:

| Metric | Target | Measured |
|---|---|---|
| Total runs | ≥ 50 | 60 |
| Total node handoffs | — | 180 |
| Successful handoffs | — | 180 |
| **Handoff success rate** | **≥ 99%** | **100.00%** |
| Runs completing without retry | — | 60 / 60 |
| Runs halted after 3 retries | — | 0 |

**Caveat, stated plainly because it materially changes what this number means.** This campaign ran
with `FAKE_ADAPTERS=true` — every agent call except the Video agent's real FFmpeg render is a canned
response. The real Google/YouTube/Gmail publish adapters are not fully implemented yet (§1, §5), so
**no external-API failure, rate limit or authentication error is represented in this number.** Treat
100.00% as a floor on the internal orchestration path's reliability, not a ceiling on the whole
system's reliability once real external APIs are in the loop.

### 6.3 NFR-03 — usability

No moderated usability session has been run. GP-plan W11 assigns this to Ahmed, with a participant
count "to be agreed with the supervisor" — no source document specifies one. This entire section is
a placeholder.

[[TO FILL: NFR-03 usability table — participant count, background, time-on-task, completion rate,
SUS per participant and mean. Owner: Ahmed, per GP-plan W11.]]

### 6.4 NFR-04 — extensibility (the seventh-agent test)

The frontend-side half of this proof is automated and passing (`frontend/e2e/seventh-agent.spec.ts`,
2 tests, §3.3, §5/AT-12): handed a manifest for an agent ("Translator") that nothing in
`frontend/src` mentions by name, the app builds a correct palette entry, node, and settings form,
and lists the step on the run monitor — by construction, since the test only ever injects a JSON
fixture and never edits application source.

The full claim from GP-plan W8/§2.6 ("create a seventh agent, restart the worker, `git diff --stat`
shows changes in that folder and nowhere else") is a one-time manual exercise, documented precisely
in `docs/ADDING_AN_AGENT.md`, that produces its own evidence (`git diff --stat main`) each time it is
run. That evidence has not been regenerated for this report; the W8 file-count figure referenced
elsewhere in the project's own notes is a placeholder, not a number verified by this pass.

[[TO FILL: re-run the seventh-agent exercise per `docs/ADDING_AN_AGENT.md` §7 and paste the
`git diff --stat main` output — owner Zain, GP-plan W8/AT-12.]]

### 6.5 Video worker sizing

Measured 2026-09-27 (`docs/metrics/video-worker.md`), under the production worker limits
(`--cpus 2 --memory 4g`, matching `docker-compose.prod.yml`), one render at a time:

| Resolution | Render s / video-minute | × real time | Peak RSS |
|---|---|---|---|
| 720p | ≈ 4.2–4.8 | ≈ 13–14× | ≈ 0.5 GiB |
| 1080p | ≈ 9.5–11.6 | ≈ 5–6× | ≈ 1.1 GiB |

At `--concurrency=2` (two simultaneous 1080p renders, matching the prod worker's Celery
concurrency), measured peak memory is ≈ 2.2 GiB out of the 4 GiB limit, leaving ~45% headroom for
slides and the other agents sharing the container. The measurement document also records that
FFmpeg over-threads inside a 2-CPU cgroup (libx264 sees all 20 host CPUs and starts ~30 threads),
which makes two parallel renders *slower per video* than one at a time — a `-threads` cap is
recommended there as a follow-up, not applied in this pass.

## 7. Defects found through testing

| # | Defect | Found by | Status |
|---|---|---|---|
| 1 | **Cancel overwritten by a run's last step.** A cancel that lands while the final node is executing is overwritten: the orchestrator's main loop ends and sets the run to `SUCCEEDED` without re-reading the run's status, and `SqlRunStore.set_run_status` allows a terminal status to be replaced. | `tests/integration/test_run_reliability.py::test_cancel_during_the_last_step_leaves_the_run_cancelled` (`xfail(strict=True)`) | **Open** — `worker/src/worker/orchestrator.py:126` |
| 2 | **Cancel during retry backoff is ignored.** The retry loop never checks for a cancel signal; it keeps retrying through every backoff window, and `_finish_failed` then overwrites a `CANCELLED` status with `FAILED`. | `tests/integration/test_run_reliability.py::test_cancel_during_a_retry_backoff_stops_retrying` (`xfail(strict=True)`) | **Open** — `worker/src/worker/orchestrator.py:129-157` |
| 3 | **A cancelled run never gets `completed_at`.** The API's cancel endpoint only sets status; the orchestrator's cancel branch returns without calling the one store method that writes `completed_at`. | `tests/integration/test_run_reliability.py::test_a_cancelled_run_records_when_it_ended` (`xfail(strict=True)`) | **Open** — `api/src/api/routers/runs.py:144`, `worker/src/worker/orchestrator.py:89-91` |
| 4 | **Duplicate output on a crash between saving output and marking success.** `save_output` and setting the `SUCCESS` status are two separate commits, and `SqlRunStore.save_output` only inserts (never upserts). A worker process lost between the two commits leaves the step `running` with its output already saved; redelivery re-runs the step and saves a second copy of the output. | `tests/integration/test_run_reliability.py::test_a_crash_between_saving_output_and_marking_success_leaves_one_output` (`xfail(strict=True)`) | **Open** — `worker/src/worker/orchestrator.py:158-159`, `worker/src/worker/store.py:138` |
| 5 | **Autosave race: concurrent `PUT /workflows/{id}` can 500.** `save_graph` deletes and re-inserts a workflow's `agent_nodes` rows without locking the workflow row between the two steps, so two concurrent saves to the same workflow can both see the old rows deleted and then race to insert the same node ids, raising `psycopg.errors.UniqueViolation` on `pk_agent_nodes`. Reproduced under load (16.7–18.6% of concurrent autosave requests failed); unlikely in the shipped single-tab UI, but real. | `docs/metrics/api-latency.md` (load test, 2026-09-28) | **Open** — `api/src/api/services/workflows.py`'s `save_graph` |
| 6 | **`GET /workflows` is N+1.** `list_workflows` runs one extra query per workflow to find that workflow's latest run; with ~100 accumulated workflows on one account, `p50` rose from ~10–50 ms to ~200–370 ms. Scales with a user's own workflow count, independent of concurrent load. | `docs/metrics/api-latency.md` (load test, 2026-09-28) | **Open** — `api/src/api/routers/workflows.py`'s `list_workflows` |
| 7 | **"Duplicate workflow" is broken for any workflow with saved steps.** `duplicateWorkflow` copies the source graph verbatim, node ids included, into `PUT /workflows/{copyId}`; since `agent_nodes.id` is a primary key not scoped to a workflow, the insert collides with the original workflow's own rows and the request 500s (`duplicate key value violates unique constraint pk_agent_nodes`). | `frontend/e2e-fullstack/fixtures.ts` (documented inline; the fullstack specs route around it rather than exercising the broken path) | **Open** — `frontend/src/lib/api.ts`'s `duplicateWorkflow`, backed by the same `save_graph` insert path as defect 5 |
| 8 | **CRLF line endings crashed the worker entrypoint on Windows.** | `docs/fresh-machine-test.md` / earlier W11 work (referenced; not reproduced in this pass) | **Fixed** |
| 9 | **Windows setup friction:** `python3` not resolving (Microsoft Store stub, not a real interpreter); `scripts/smoke_test.py`'s `✓`/`✗` output crashing under the native `cp1252` console codepage; no documented Windows notes for Git Bash lacking `make`, `MSYS_NO_PATHCONV`, nvm-style Node shims. | `docs/fresh-machine-test.md` (W11 fresh-machine test, 2026-09-28) | **Fixed** — `SETUP.md`, `README.md` (commit `a5e2974`) |

Defects 1–4 share a root cause worth stating plainly: **the orchestrator's cancel path was built and
tested for the happy path (cancel while a step is merely pending or mid-flight) but never for the
three specific races around a run's terminal transition** — last step, retry backoff, and the
save/success commit boundary. All four are pinned down by `xfail(strict=True)` tests specifically so
that (a) they cannot be "fixed" by accident without the test suite noticing and demanding the marker
be removed, and (b) a regression that makes any of them fail differently is caught immediately. None
of the four is exercised by `docs/metrics/reliability.md`'s 100% handoff figure, because that
campaign used auto-approval and no injected cancels or crashes — RT-01's 100% and defects 1–4 are
not in tension with each other; they describe different, non-overlapping code paths.

## 8. Limitations and threats to validity

- **Fake adapters dominate the automated evidence.** Every reliability, latency and most acceptance
  results above ran with `FAKE_ADAPTERS=true`. This is the correct and necessary choice for a
  repeatable, free, offline test suite, but it means the numbers in §6.1–§6.2 and most of §5's
  "Pass" rows say nothing about latency, error rates or retry behaviour once real OpenAI, search,
  TTS, YouTube, Drive or Gmail calls are in the loop. The real Google publish adapters in particular
  are still marked `TODO` at the time of writing.
- **Single development machine, not the production host.** Every timing figure in this chapter (API
  latency, video render cost, build/start time) was measured on one Windows 11 desktop under Docker
  Desktop/WSL2. A desktop CPU is faster per core than a typical cloud vCPU; every source document
  cited above says explicitly to re-measure on the chosen deployment host before quoting these
  numbers as production figures (GP-plan W11).
- **Short measurement windows.** The reliability campaign covers 60 runs over roughly 77 seconds of
  wall-clock window; the latency campaign covers two 30-second windows. Both comfortably clear their
  stated minimums (≥ 50 runs; enough requests for a stable p95), but neither approaches the volume or
  duration a production deployment would see over days or weeks, and neither can surface failure
  modes that only appear under sustained load or over longer time horizons (memory leaks, connection
  pool exhaustion, clock drift).
- **No FFmpeg on the measurement host outside Docker.** All Windows-host-only test runs (§3.1's
  `exporters` and `agents/video` suites) skip their one real-encode test for this reason; the actual
  encode path is fully exercised inside the Docker images used by every other suite and by the
  fullstack and reliability campaigns, so this is a coverage gap only for the narrow "runs directly
  on bare Windows" case, not for the shipped system.
- **The four `xfail` bugs (§7) mean run-cancellation is not yet trustworthy in every case.** A user
  who cancels a run during its last step, during a retry backoff, or who is unlucky enough to hit the
  exact worker-crash window in defect 4, will see incorrect state (wrong terminal status, missing
  `completed_at`, or a duplicated output). This is a known, tracked gap, not a silent one — but it is
  real and unresolved at the time of writing.
- **AT-01, AT-03, AT-04, AT-12, RT-01, RB-01 and RB-03 are each only partially demonstrated by
  automation**, as detailed in their own rows in §5; each has a specific, named remaining gap rather
  than being fully proven.
- **Usability (NFR-03) and the real-publish acceptance case (AT-05) have no automated substitute at
  all** and depend entirely on future human sessions and live credentials respectively.
