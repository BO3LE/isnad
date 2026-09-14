# GP Platform — Visual AI-Agent Workflow Platform

Drag AI agents onto a canvas, connect them into a chain, press Run: research becomes an article, the article becomes a video, the video reaches YouTube and your inbox — and nothing is published until a human approves it.

Graduation project · King Faisal University · CCSIT · Milestone 3 (13 Sep – 5 Dec 2026)
Supervisor: Dr. Hasan Alkahtani · Committee: Dr. Asrar Alhaque

---

## Quick start

```bash
cp .env.example .env
docker compose up --build
```

| Open | What |
|---|---|
| http://localhost:5173 | The app — sign in as `demo@gp.local` (development sign-in, no password) |
| http://localhost:8000/docs | API reference (generated) |
| http://localhost:8000/health/ready | Database and worker status |

Three template workflows are seeded. With `FAKE_ADAPTERS=true` (the default) every agent runs against canned responses — no API keys, no spend — and the Video agent still renders a real MP4 with FFmpeg.

Prove the whole stack works:

```bash
python3 scripts/smoke_test.py
```

Full setup, local development without Docker, and troubleshooting: **[SETUP.md](SETUP.md)**. How we work: **[CONTRIBUTING.md](CONTRIBUTING.md)**.

---

## Seven components, one rule

Each component is its own package, tested alone, talking to the others only through `contracts`.

| # | Component | Folder | Owner | Deploys as |
|---|---|---|---|---|
| C0 | contracts — every type that crosses a boundary | [`contracts/`](contracts) | Everyone · **2 approvals** | Library |
| C1 | frontend — canvas, forms, screens | [`frontend/`](frontend) | Ahmed | Static site |
| C2 | api — auth, validation, enqueue | [`api/`](api) | Hasan | Container |
| C3 | worker — DAG execution, retries, logs | [`worker/`](worker) | Hasan | Container |
| C4 | agents — six plug-ins | [`agents/`](agents) | Zain | Into the worker image |
| C5 | adapters — OpenAI, search, TTS, YouTube, Drive, Gmail, storage | [`adapters/`](adapters) | Zain (ports: Mohammed) | Library |
| C6 | exporters — PDF, DOCX, MP4 | [`exporters/`](exporters) | Zain | Library |
| C7 | db — schema, migrations, seed | [`db/`](db) | Mohammed | Migrations |

> **The one rule.** If changing an agent forces you to edit the orchestrator, the boundary is wrong. Fix the boundary, not the caller.

CI enforces it: [`.importlinter`](.importlinter) fails the build when a component imports across a forbidden edge.

```
contracts  ← depends on nothing
frontend ──HTTP──▶ api ──▶ db ◀── worker
                    │               │ resolves agents by entry point
                    └─ run_id ▶ redis ▶ agents/* ──▶ adapters/* · exporters
```

## What already works (W1 skeleton)

- **API:** development sign-in, workflow CRUD, graph validation with human-readable messages, `POST /workflows/{id}/run` → 202, run state and logs, approve / reject, cancel, agent catalog, health checks.
- **Worker:** topological execution, run context passed between agents, retry with exponential backoff (`2^attempt + jitter`, max 3), approval gate that parks and resumes, cancellation, downstream skipping, acks-late redelivery.
- **Agents:** all six run end to end against fake adapters; Writer has the one-reformat retry; Video renders a real MP4.
- **Adding an agent:** drop a folder into `agents/`, restart the worker — it appears in the catalog with its settings schema. Verified. See [docs/ADDING_AN_AGENT.md](docs/ADDING_AN_AGENT.md).
- **Database:** the eight tables, one migration, seed data; migrations round-trip on PostgreSQL 15.
- **Frontend:** sign in, workflow list, a basic canvas that saves, validates and runs, a polling run monitor with approve/cancel — built on the design-system tokens.
- **CI:** lint, formatting, import boundaries, agent shape, each component's tests in isolation, migration round-trip, OpenAPI/type drift, frontend lint/typecheck/tests/build, Playwright against a mocked API, full-stack smoke test on `main`.

What is deliberately left as TODOs, by week, is marked in the code as `TODO(W<n>, <owner>)`:

```bash
grep -rn "TODO(W" --include=*.py --include=*.ts --include=*.tsx .
```

## Everyday commands

```bash
make help        # everything below, and more
make up          # docker compose up --build
make bootstrap   # local .venv + npm ci (for running tests and linters outside Docker)
make test        # every component's own test suite
make lint        # ruff, format check, import boundaries, agent shape, eslint, tsc
make openapi     # after changing the API: regenerate contracts/openapi.json and frontend types
make revision m="describe the change"   # new Alembic migration
```

## Repository layout

```
contracts/     C0  pydantic models, ports, graph helpers, openapi.json
frontend/      C1  React 18 + React Flow + Vite + Tailwind + TanStack Query
api/           C2  FastAPI
worker/        C3  Celery orchestrator
agents/        C4  one installable package per agent (entry point group gp.agents)
adapters/      C5  one file per external service, each with a fake
exporters/     C6  pure functions
db/            C7  SQLAlchemy models, Alembic migrations, seed
scripts/           bootstrap, tests, smoke test, manifest validation
docs/              GP-plan.md · DESIGN-SYSTEM.md · DECISIONS.md · ADDING_AN_AGENT.md
```

## Documents

- [docs/GP-plan.md](docs/GP-plan.md) — the full M3 plan: components, week-by-week tasks, requirements, tests, risks
- [docs/DESIGN-SYSTEM.md](docs/DESIGN-SYSTEM.md) — brand, tokens, components, screens
- [docs/DECISIONS.md](docs/DECISIONS.md) — infrastructure decisions made while setting up this repository
