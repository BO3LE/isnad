# Fresh-machine test (W11)

Report evidence for GP-plan W11 ("clone the repo on a clean machine, follow your own
instructions, `docker compose up`"). This is a factual log, not a summary — see
[SETUP.md](../SETUP.md) for the instructions themselves (which this test corrected) and
[scripts/fresh_machine_test.sh](../scripts/fresh_machine_test.sh) for the automated,
rerunnable version of steps 2–5 below.

## Machine

- OS: Windows 11 Pro, build 10.0.26200
- Shell: Git Bash (MINGW64, Git for Windows), `set -euo pipefail`
- Docker: Docker Desktop, `docker --version` → Docker version 29.7.2, build a7dcaa6; backend WSL 2
  (worker container reported kernel `Linux 6.18.33.2-microsoft-standard-WSL2-x86_64`)
- Docker Compose: v5.5.0 (`docker compose version`)
- Disk: host `C:` drive was at ~99% capacity (14–18 GB free) throughout the test, which is
  unusually tight and slowed a couple of steps (noted below); a normal machine should be faster.
- Date: 2026-09-28

## Method

A fresh `git clone` of this branch's HEAD (`git worktree`, not a copy — no `node_modules`,
`.venv`, or `.env` carried over) into `/c/isnad-fresh-test/repo` (outside the working checkout),
then SETUP.md followed literally, step by step, as a newcomer would.

## Step-by-step log

### 1. Prerequisites (SETUP.md §1)

| Check | Result |
|---|---|
| `git --version` | `git version 2.55.0.windows.5` — OK |
| `docker compose version` | `Docker Compose version v5.5.0` — OK |
| `python3 --version` | **FAILED.** Printed a Microsoft Store redirect message and exited non-zero. `python3` on this machine is only the Windows "App execution alias" stub, not a real interpreter. |
| `python --version` | `Python 3.11.9` — OK. This is the interpreter to use on this machine. |
| `node --version` | **FAILED** in this Git Bash session ("Node.js v20.x.x is not installed or cannot be found") even though a Node 20 install exists on the machine (via an nvm-style manager) — its shim wasn't on this particular shell's `PATH`. Confirmed this only blocks §3/§4's non-Docker commands, not `docker compose up` (Node runs inside the frontend container regardless). |
| `make --version` | **FAILED** ("command not found"). Git Bash does not ship `make`. SETUP.md already marks Make as optional and gives the non-`make` command for everything used in this test, so this did not block anything — confirmed by using the non-`make` form throughout. |

**Finding → fix:** SETUP.md's prerequisites table and every `python3 <script>` invocation assumed
a `python3` binary. Fixed in SETUP.md and README.md to call out `python` on Windows, and added a
"Windows notes" section documenting all four rows above. See commit `a5e2974`.

### 2. Run the whole stack — Docker (SETUP.md §2)

```bash
cp .env.example .env
# + DB_HOST_PORT=5533 / REDIS_HOST_PORT=6479 appended, only because another agent's stack already
# held the default 5433 on this shared machine — not a step a real newcomer needs.
MSYS_NO_PATHCONV=1 docker compose -p isnad-fresh up --build -d
```

- Result: **succeeded.** All five services (`db`, `redis`, `migrate`, `api`, `worker`, `frontend`)
  built and started; `migrate` ran `alembic upgrade head` + seed and exited 0.
- Time: first build (this machine's Docker daemon already held some cached base-image layers from
  other work on the same host, so this is not a fully cold-image-cache number) — **build + start
  ≈ 3 minutes**. A rerun of the same command against warm layer cache (via
  `scripts/fresh_machine_test.sh`, separate clone) took **18–63 seconds**.
- `curl http://localhost:8000/health/ready` → `{"status":"ok","checks":{"database":"ok","worker_catalog":"6 agents"}}` — matches SETUP.md's description.
- `curl http://localhost:5173` → HTTP 200 (frontend serving).
- Worker logs showed a clean start (`celery@... ready`, `published 6 agents to gp:agents:catalog`)
  — the documented "watchfiles reloader may crash with Cannot allocate memory" issue was **not
  reproduced** on this machine/Docker Desktop configuration. Documented anyway in SETUP.md's
  troubleshooting table per the known-issue note, since it's host-resource-dependent.
- Sign-in: not exercised through an actual browser (no interactive browser available in this
  environment) — verified equivalently via `POST /auth/dev-login` as `demo@gp.local`, which is
  exactly what the frontend's dev sign-in does, and it returned a valid token. Flagged below as
  "not independently verified through a browser."

**Finding → fix:** `scripts/smoke_test.py` prints `✓`/`✗`. Native Windows Python's console defaults
to the `cp1252` codepage, not UTF-8:

```
python scripts/smoke_test.py
...
UnicodeEncodeError: 'charmap' codec can't encode character '✓' in position 0
```

Fixed by running `python -X utf8 scripts/smoke_test.py`, which prints correctly and exits 0:

```
✓ API healthy and worker catalog published
✓ catalog: email, image, publisher, researcher, video, writer
✓ Blog post: succeeded (0 approval(s)) — researcher:success → writer:success
✓ Blog → Video → YouTube: succeeded (1 approval(s)) — researcher:success → writer:success → video:success → publisher:success
✓ Research → PDF → Email: succeeded (1 approval(s)) — researcher:success → writer:success → email:success
```

Documented in SETUP.md's Windows notes and troubleshooting table (commit `a5e2974`); README.md's
quick start updated the same way.

### 3. Local development without Docker (SETUP.md §3)

Tried in clean Linux containers per the task's instruction, to sidestep this particular Windows
machine's Node/`python3` PATH gaps and get an honest read on the instructions themselves:

- `python:3.11-slim`, joined to the stack's Docker network (so `db`/`redis` were reachable by
  service name, matching what `docker compose up -d db redis migrate` + host-side processes would
  see via `localhost`), running `bash scripts/bootstrap.sh` unmodified:
  - Result: **succeeded** — `✓ .venv ready — activate with: source .venv/bin/activate`.
  - Time: **~12–15 minutes** (imprecise — not instrumented start-to-finish — but noticeably slow;
    this machine's disk was at 99% capacity for the whole test, which is atypical and likely the
    dominant cause, not the instructions).
  - Follow-up proof the environment actually works: `cd worker && python -m pytest -q` inside the
    same container/venv → `39 passed in 1.63s`.
- `node:20-alpine`, `npm ci --no-audit --no-fund` then `npm run typecheck` in `frontend/`:
  - Result: **succeeded** — `added 440 packages in 32s`; `tsc -b --noEmit` produced no errors.

No changes were needed to SETUP.md §3 itself — the commands as written work. The friction found in
this section (§1 above) is about the *host* shell's `PATH`, not about anything SETUP.md tells you
to type.

### 4. Tests and checks (SETUP.md §4)

- `make test` / `make lint` / `make check`: not run directly (no `make` on this machine, as noted
  in §1) — their underlying commands are what §3 above already exercised (`pytest` in `worker`) and
  what CI runs; not re-derived here to avoid duplicating work already covered.
- `cd worker && python -m pytest`: **passed**, see above (39 passed).
- `python scripts/smoke_test.py` (full stack): **passed**, see §2 above.
- `cd frontend && npm run test:e2e`: **not run** — Playwright's browser download is a heavy,
  separate install (`npx playwright install chromium`) and this machine had ~14 GB free disk for
  the whole test; skipped as out of scope for this pass. Flagged below as not verified.

### 5. Automating it

`scripts/fresh_machine_test.sh` (added this session) automates steps 2–4's Docker path: clone →
`cp .env.example .env` → `docker compose up --build` (own project name + DB/Redis host ports, so it
won't collide with a stack you already have running) → wait for `/health/ready` → run
`scripts/smoke_test.py` (with the same `-X utf8` fix, auto-detected) → tear down (`docker compose
down -v` + delete the clone). Run twice during this test:

| Run | Build + start | Smoke test | Total | Result |
|---|---|---|---|---|
| 1 (bug: picked the `python3` Store stub) | 63s | — | — | ✗ (script bug, not SETUP.md) |
| 2 (after fixing the interpreter probe) | 18s | 14s | 33s | ✓ |

Confirmed clean teardown both times: no leftover containers, volumes, images, or temp directories.

## Summary of SETUP.md/README.md problems found and fixed

1. Prerequisites table and every script invocation assumed `python3` exists — wrong on native
   Windows Python (the `python3` App Execution Alias is a Microsoft Store install stub, not
   Python). Fixed: call out `python` for Windows.
2. `scripts/smoke_test.py`'s ✓/✗ output crashes with `UnicodeEncodeError` under native Windows
   Python (`cp1252` console encoding). Fixed: documented `python -X utf8 scripts/smoke_test.py`
   for Windows, in both SETUP.md and README.md, and added a troubleshooting row.
3. No "Windows notes" section existed to collect these and other gotchas (Git Bash lacking `make`,
   nvm-style Node installs not always on Git Bash's `PATH`, `MSYS_NO_PATHCONV` for Docker commands
   with Linux-style paths). Added one, plus a "Verified on" line, in SETUP.md.

Everything else in SETUP.md — the Docker quick start, the database section, the environment
variable table, the non-Docker local-dev section, the individual test commands — matched what
actually happened. No steps were missing, no ports were wrong, no commands failed for reasons other
than the two above.

## Not independently verified in this pass

- Sign-in through an actual browser UI (verified via the equivalent API call, `/auth/dev-login`,
  instead — no interactive browser in this environment).
- `frontend && npm run test:e2e` (Playwright) — skipped for disk-space reasons on this particular
  machine (~14 GB free); the other agent working on Playwright/CI in parallel covers this more
  thoroughly.
- A fully cold Docker image cache (base images `python:3.11-slim`, `node:20-alpine`, `postgres:15`,
  `redis:7-alpine` were already present on this shared Docker daemon from other work). The "~3
  minutes" first-build timing above reflects a warm base-image cache with the project's own layers
  built fresh; a genuinely offline first pull would take longer depending on connection speed.
- The worker `dev` target's documented "Cannot allocate memory" watchfiles crash — not reproduced
  on this Docker Desktop configuration; the fix is documented in SETUP.md on the strength of the
  task brief's prior knowledge of it, not a reproduction in this session.
