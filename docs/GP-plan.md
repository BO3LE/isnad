# GP — Visual AI-Agent Workflow Platform
## Complete Notion Workspace Export

**Milestone 3 — Implementation and Testing**
King Faisal University · College of Computer Sciences and Information Technology · Department of Computer Science

**Team:** Ahmed Saleh Almutairi (222417022) · Hasan Ahmed Almutawa (222417572) · Zain Shehab Albandari (222423410) · Mohammed Abdullah Bajaba (222448149)
**Supervisor:** Dr. Hasan Alkahtani · **Committee:** Dr. Asrar Alhaque
**Exported:** 13 September 2026

---

## What is in this file

Everything built in the Notion workspace, in the order it appears there.

| Part | Notion page or database | What it holds |
|---|---|---|
| 1 | Home (root page) | Quick reference, component ownership, scope, open questions |
| 2 | 🧩 Components | The seven components and their boundaries — **the core of the design** |
| 3 | ⚙️ Technologies | Full stack, Docker, file layout, schema, dependencies |
| 4 | 🗓️ Week by Week | W1–W12, tasks grouped by component, every one with a "done when" |
| 5 | 🏗️ Technical Docs | Architecture · Database Schema · API Reference · Agent Specifications · Deployment & Setup · Deviations from M2 |
| 6 | 📊 Results & Metrics | Empty measurement tables ready to fill |
| 7 | 📝 M3 Report | Chapter-by-chapter drafting plan and submission checklist |
| 8 | Databases | Requirements (16) · Tasks (70) · Test Cases (18) · Timeline (12) · Risks (10) · Screenshots (10) · Decisions (1) · Meetings (1) |

---
---

# PART 1 — HOME

*Notion root page: GP — Visual AI-Agent Workflow Platform*

A Visual AI-Agent Workflow Platform for End-to-End Content Automation | Milestone 3 — Implementation & Testing

## 📌 Quick Reference

| | |
|---|---|
| **Milestone** | M3 — Implementation and Testing |
| **Weeks** | 13 September – 5 December 2026 (W1–W12) |
| **Team** | 4 people |
| **Goal** | A deployed, tested platform where five AI agents run one workflow end to end |
| **Stack** | React + FastAPI + Celery/Redis + PostgreSQL (Supabase) + Docker |
| **Architecture** | 7 components, one repo, separate deployables, contract-first |
| **University** | King Faisal University — CCSIT, Computer Science |
| **Supervisor** | Dr. Hasan Alkahtani · Committee: Dr. Asrar Alhaque |

## 🧩 Component Ownership

Each person owns whole components, not slices of a shared codebase. This is the point: two people should almost never need to edit the same file.

| # | Component | Owner | Deploys as |
|---|---|---|---|
| C0 | `contracts` — every type that crosses a boundary | All (2 approvals to change) | Library |
| C1 | `frontend` — canvas, forms, screens | **Ahmed** | Static site |
| C2 | `api` — HTTP, auth, validation, enqueue | **Hasan** | Container |
| C3 | `worker` — DAG execution, retries, logs | **Hasan** | Container |
| C4 | `agents/*` — six plug-ins | **Zain** | Into the worker image |
| C5 | `adapters/*` — OpenAI, search, TTS, YouTube, Drive, Gmail | **Zain** | Library |
| C6 | `exporters` — PDF, DOCX, MP4 | **Zain** | Library |
| C7 | `db` — schema, migrations, RLS, storage | **Mohammed** | Migrations |

Mohammed also owns the things that hold it together: Docker, CI, the import contract, keys, deployment and the test harness.

**The one rule:** if changing an agent forces you to edit the orchestrator, the boundary is wrong. Fix the boundary.

## 🎯 Feature Scope (Frozen after W8 — no additions)

| Requirement | Feature | Component that owns it |
|---|---|---|
| FR-01 | Drag-and-drop workflow canvas | C1 |
| FR-02 | Five pre-configured agents: Research, Write, Video, Publish, Email | C4 |
| FR-03 | Multi-modal output: article, image, video | C4 |
| FR-04 | Export to PDF, DOCX, MP4 | C6 |
| FR-05 | Publish to YouTube and Drive, distribute by Gmail/SMTP | C5 |
| FR-06 | Automated retry with backoff, plus execution logs | C3 |
| UC-04 | Human approval before anything is published | C2 + C3 |

## 🚫 Out of Scope (declared in M1 §3.2 — do not drift into these)

- Real-time chat or voice workflow creation
- Multi-user permissions, roles, teams, sharing — per-user isolation via RLS only
- Advanced video editing inside the Video agent
- ERP or HRMS integration
- Mobile app, Arabic localisation

## ❓ Still Unknown

Absent from M1, M2 and the GPC guide. Settle each one and record it in the Decisions Log.

1. **The M3 submission date.** This workspace assumes W12 ends 5 December 2026 — confirm and shift if wrong.
2. **What the M2 prototype actually runs** — audited in W1.
3. **Budget** for OpenAI, search, TTS and hosting.
4. **Deployment host** — chosen in W1.
5. **Usability participant count** — agree with the supervisor.
6. **D-01: Supabase vs. the M2 stack** — proposed, awaiting sign-off.

---
---

# PART 2 — COMPONENTS

*Notion page: 🧩 Components*

Seven components. One repository, seven independently buildable pieces. Every piece talks to the others through **`contracts`** and nothing else.

> **The one rule.** If changing an agent forces you to edit the orchestrator, or changing the orchestrator forces you to edit the frontend, the boundary is in the wrong place. Fix the boundary, not the caller.

## Component Map

| # | Component | Owner | Deploys as | Language |
|---|---|---|---|---|
| C0 | `contracts` | All — changes need two approvals | Library, never deployed alone | Python + generated TS |
| C1 | `frontend` | Ahmed | Static site (nginx) | TypeScript / React |
| C2 | `api` | Hasan | Container (uvicorn) | Python |
| C3 | `worker` | Hasan | Container (celery) | Python |
| C4 | `agents/*` | Zain | Installed into the worker image | Python |
| C5 | `adapters/*` | Zain builds, Mohammed owns the port shapes | Library | Python |
| C6 | `exporters` | Zain | Library | Python |
| C7 | `db` | Mohammed | Migrations + managed Postgres | SQL / Alembic |

## Dependency Direction

Arrows point one way. Nothing imports upward, ever.

```
contracts          <- depends on nothing at all
   ^  ^  ^  ^
   |  |  |  +----------------------------+
   |  |  +------------------+            |
   |  +-------+             |            |
   |          |             |            |
frontend --> api --------> db <------- worker
  (HTTP)      |                           |
              | enqueue job by name       | resolve agent by manifest
              v                           v
            redis  --------------------> agents/*
                                            |
                                            v
                                   adapters/*   exporters
                                        |
                                        v
                        OpenAI, Search, TTS, YouTube, Drive, Gmail
```

**Read it as four independent halves:**

1. `frontend` knows only the HTTP contract. It could be replaced with a mobile app tomorrow.
2. `api` knows how to store a workflow and how to enqueue a job. It does not know what an agent does.
3. `worker` knows how to walk a DAG and retry. It does not know what any specific agent does.
4. `agents` know how to do one job each. They do not know they are in a workflow.

## C0 · `contracts` — the shared language

**Owner:** everyone. A change here needs two approvals, because it is the only file that can break more than one component.

This is what makes the decoupling real. Every type that crosses a boundary is defined here once, and both sides import it. Neither side imports the other.

| File | Holds |
|---|---|
| `agent_io.py` | Input and output model for each agent — `ResearchInput`, `ResearchOutput`, `WriteInput`, and so on |
| `manifest.py` | The `AgentManifest` shape every agent must publish |
| `run.py` | `RunState`, `NodeState`, `LogEntry`, `WorkflowGraph` |
| `ports.py` | The adapter interfaces — `LLMPort`, `SearchPort`, `TTSPort`, `PublishPort`, `StoragePort` |
| `openapi.json` | Generated from the API at build time; the frontend generates its TypeScript types from this |

**Depends on:** nothing. Pydantic and the standard library only. If `contracts` ever needs to import something from another component, the model belongs somewhere else.

**Done when:** `pip install ./contracts` works in a container that has none of the other components present.

## C1 · `frontend` — what the user sees

**Owner:** Ahmed

| | |
|---|---|
| **Purpose** | The canvas, the configuration drawer, the run monitor, the approval screen, the logs |
| **Deploys as** | Static files behind nginx |
| **Depends on** | The generated OpenAPI types. Nothing else. |
| **Must not know** | Celery, Redis, the database, agent internals, any external API key |
| **Interface in** | — |
| **Interface out** | REST to `api`, plus one Realtime subscription for live run status |
| **Tested alone by** | Vitest for components; Playwright against a mocked API. No backend needs to be running. |

**The decoupling test:** run `npm run test:e2e` with the entire backend stopped. If it passes, the frontend is properly separated.

## C2 · `api` — the front door

**Owner:** Hasan

| | |
|---|---|
| **Purpose** | Authenticate, validate a workflow graph, store it, enqueue a run, serve status and logs |
| **Deploys as** | Its own container |
| **Depends on** | `contracts`, `db` |
| **Must not know** | What an agent does, how a video is rendered, what FFmpeg is, any external content API |
| **Interface in** | REST, documented automatically at `/docs` |
| **Interface out** | Writes to `db`; pushes a job onto Redis carrying only `run_id`. Nothing else. |
| **Tested alone by** | pytest + TestClient with **no worker running at all** |

**The decoupling test:** stop the worker, call `POST /workflows/{id}/run`, and get a 202 with a `run_id`. The API's job is done at that point.

> Grep test: `grep -r "from agents" api/` must return nothing.

## C3 · `worker` — the orchestrator

**Owner:** Hasan

| | |
|---|---|
| **Purpose** | Topological sort, execute nodes in order, retry with backoff, park for approval, write logs |
| **Deploys as** | Its own container, scaled separately from the API |
| **Depends on** | `contracts`, `db`, and the agent **registry** — never an agent by name |
| **Must not know** | What any specific agent does. It resolves `agent_type` to a manifest at runtime. |
| **Interface in** | A Celery job carrying a `run_id` |
| **Interface out** | `registry.get(agent_type).execute(input)` and log rows |
| **Tested alone by** | Running a full DAG with only fake manifest agents registered — no OpenAI, no FFmpeg, no network |

**The decoupling test:** delete the entire `agents/` folder, register two fake agents in the test fixture, and the orchestrator test suite still passes in full.

> Grep test: `grep -r "from agents" worker/` must return nothing. The registry loads by entry point, not by import.

## C4 · `agents/*` — plug-ins

**Owner:** Zain

Six folders, six independent packages: `researcher`, `writer`, `image`, `video`, `publisher`, `email`. Each one is a self-contained unit that happens to be discovered by the worker.

| | |
|---|---|
| **Purpose** | Do exactly one job and return a validated result |
| **Deploys as** | Installed into the worker image; each declares its own dependencies |
| **Depends on** | `contracts` and the `adapters` ports |
| **Must not know** | The database, the API, Celery, the run, or any other agent |
| **Interface in** | `execute(input_data) -> output_data`, both typed from `contracts` |
| **Interface out** | `manifest.json` — name, config JSON schema, input type, output type, version |
| **Tested alone by** | `pytest agents/writer/` with a fixture input. No database, no queue, no worker. |

**Every agent folder looks the same:**

```
agents/writer/
├── manifest.json      # name, version, config schema, input type, output type
├── agent.py           # execute() and nothing else public
├── prompts/           # its own prompt templates
├── requirements.txt   # its own dependencies
└── tests/
    ├── fixtures/      # a sample input and the expected output shape
    └── test_agent.py
```

**The decoupling test — this is also acceptance test AT-12 and the proof of NFR-04:** create a seventh agent that reverses a string. Drop the folder in. Restart the worker. It appears in the palette with a working configuration form. **Files edited outside that folder: zero.**

## C5 · `adapters/*` — the outside world, behind a door

**Owner:** Zain builds them; Mohammed owns the port shapes in `contracts/ports.py`

Every external service is reached through a narrow interface, never called directly from an agent.

| Adapter | Port | Swapping it costs |
|---|---|---|
| `adapters/llm/openai.py` | `LLMPort.complete(prompt) -> str` | One file |
| `adapters/search/tavily.py` | `SearchPort.search(query, n) -> Source[]` | One file |
| `adapters/tts/gtts.py` | `TTSPort.speak(text) -> audio` | One file |
| `adapters/publish/youtube.py` | `PublishPort.publish(file, meta) -> url` | One file |
| `adapters/publish/drive.py` | `PublishPort.publish(file, meta) -> url` | One file |
| `adapters/email/gmail.py` | `EmailPort.send(to, subject, body) -> id` | One file |
| `adapters/storage/supabase.py` | `StoragePort.put(path, bytes) -> url` | One file |

**Must not know:** agents, the orchestrator, the database.

**Why this matters for the report:** M1 §4.2 promised the platform could integrate external APIs. This is the structure that makes it a claim you can demonstrate rather than assert — the Publisher agent calls `PublishPort`, so YouTube and Drive are the same agent with a different adapter injected.

**Every port ships with a fake:** `adapters/llm/fake.py` returns canned text. That is what makes the whole system testable without spending a riyal.

## C6 · `exporters` — pure functions

**Owner:** Zain

| | |
|---|---|
| **Purpose** | markdown to PDF, markdown to DOCX, assets to MP4 |
| **Depends on** | Nothing of ours. WeasyPrint, python-docx, FFmpeg. |
| **Must not know** | The database, the run, the agents, the network |
| **Interface** | `to_pdf(markdown) -> bytes`. Input in, bytes out. |
| **Tested alone by** | Golden-file tests — same input, same output, every time |

The easiest component in the system and the easiest coverage in W10. Keep it pure and it stays that way.

## C7 · `db` — one owner for the schema

**Owner:** Mohammed

| | |
|---|---|
| **Purpose** | Migrations, the eight tables, Row Level Security, the storage bucket, seed data |
| **Depends on** | Nothing |
| **Must not know** | Anything about agents or workflows as concepts — it stores rows |
| **Interface** | The schema itself, plus Alembic migrations |
| **Rule** | Only `api` and `worker` connect. No agent, no adapter, no exporter ever opens a connection. |
| **Tested alone by** | `alembic upgrade head` then `alembic downgrade base` on an empty database |

## Enforcing all of this

Rules written on a page decay. These are checked by CI on every pull request:

| Check | Tool | Fails the build when |
|---|---|---|
| Forbidden imports | `import-linter` with a contract file | `api` or `worker` imports from `agents`; an agent imports from `worker`; an adapter imports from `agents` |
| Isolated tests | pytest markers | Any component's own test suite needs another component running |
| Contract drift | Generated types diff | `openapi.json` changed but the frontend types were not regenerated |
| Agent shape | Manifest validation | An agent folder has no valid `manifest.json` |

Set `import-linter` up in **W1**, not later. Once a forbidden import exists, removing it is a refactor; preventing it costs nothing.

## What this buys you in the report

| Requirement | The component that proves it |
|---|---|
| **NFR-04 Maintainability** | C4 — the seventh-agent test, with a file-count of zero outside the new folder |
| **NFR-01 Performance** | C2 and C3 being separate deployables is *why* a video render cannot block the API |
| **FR-05 API Integration** | C5 — one port, several adapters |
| **FR-06 Fault Tolerance** | C3 owns retry in one place, so every agent gets it without writing any retry code |
| **M2 §6.1 three-layer design** | C1 is layer 1, C2 and C3 are layer 2, C4 is layer 3 — the same architecture, now with enforced edges |

---
---

# PART 3 — TECHNOLOGIES

*Notion page: ⚙️ Technologies*

Full stack for the M3 implementation. Every choice optimises for **a 4-person team on a 12-week deadline**, and for keeping the seven components separable.

## Full Stack Table

| Layer | Technology | Version | Why This Choice |
|---|---|---|---|
| Frontend framework | React | v18 | Named in M2 §6.1.1; the team already used it on the prototype |
| Canvas | React Flow | v11 | Named in M2; custom node rendering and edge logic for free |
| Build tool | Vite | v5 | Far faster dev server than CRA; simple TypeScript setup |
| Styling | Tailwind CSS | v3 | No CSS files to maintain across four people |
| Server state | TanStack Query | v5 | Caching and refetch on the run monitor without hand-rolled state |
| Backend API | FastAPI (Python) | 3.11+ | Named in M2 §7.1; async support and auto docs at `/docs` |
| Validation | Pydantic | v2 | Every boundary in `contracts` is a Pydantic model |
| Task queue | Celery | v5 | Named in M2; mature retry policies and task chaining |
| Broker | Redis | v7 | Named in M2; broker plus result backend |
| Database | PostgreSQL | v15 | Named in M2; relational integrity for runs and logs |
| Auth + DB host + storage | Supabase | Latest | Postgres, auth, storage and realtime in one service — see D-01 |
| Migrations | Alembic | Latest | Versioned schema; reproducible on the CD/DVD |
| LLM | OpenAI GPT-4 | API | Named in M2 §7.1 for tool-calling accuracy |
| Search | Tavily *or* SerpAPI | API | Researcher agent; behind `SearchPort` so either works |
| Narration | gTTS | Latest | Deterministic, free, good enough for a demo video |
| Video assembly | FFmpeg | v6 | Named in M2 Table 6 — deterministic output, no generative model needed |
| PDF | WeasyPrint | Latest | HTML to PDF; keeps the exporter a pure function |
| DOCX | python-docx | Latest | Standard choice; simple golden-file testing |
| Publishing | YouTube Data API v3, Google Drive API, Gmail API | v3 | Named in M1 §3.1 |
| Containerisation | **Docker + Docker Compose** | Latest | Identical environment for four people; each component its own image |
| Boundary enforcement | **import-linter** | Latest | Fails CI when a component imports across a forbidden edge |
| Testing | pytest, Vitest, Playwright, Schemathesis | Latest | One tool per level; see the testing plan |
| Version control | GitHub | — | Branch protection, PR review, ties into CI |
| CI | GitHub Actions | — | Lint, tests and the import contract on every PR |

## Docker — why it is mandatory here

### The problem without it

- Four people, four machines, four Python versions. FFmpeg in particular behaves differently on macOS and Linux, and the video pipeline is already the riskiest week.
- The GPC guide requires setup instructions on the CD/DVD that a future student can follow. "Install these fourteen things in the right order" is not that.
- "Works on my machine" surfaces in W11 during the deployment test, when there is no time left to fix it.

### What it gives us

- `docker compose up` starts the whole stack on any machine in about a minute.
- **Each component is its own image**, which is what makes C2 and C3 genuinely separate deployables rather than two folders in one process.
- The worker can be scaled or restarted without touching the API — the practical proof of NFR-01.
- The W11 clean-machine test becomes a formality instead of a crisis.

## Docker Compose Setup

### Services in `docker-compose.yml`

| Service | Image | Purpose |
|---|---|---|
| `frontend` | Custom Dockerfile (Node 20) | Vite dev server on port 5173 |
| `api` | Custom Dockerfile (Python 3.11) | FastAPI on port 8000 |
| `worker` | Custom Dockerfile (Python 3.11 + FFmpeg) | Celery worker — no ports exposed |
| `redis` | redis:7-alpine | Broker and result backend |
| `db` | postgres:15 | Local Postgres for development only; production uses Supabase |

`docker-compose.prod.yml` drops the `db` service and points at Supabase.

Note that `api` and `worker` are built from **different Dockerfiles**. The worker image carries FFmpeg and the agent dependencies; the API image carries neither. If you ever find yourself adding FFmpeg to the API image, a boundary has been crossed.

### Project file structure

```
gp-platform/
├── contracts/               # C0 — imported by everyone, imports nothing
│   ├── pyproject.toml
│   ├── agent_io.py
│   ├── manifest.py
│   ├── run.py
│   └── ports.py
├── frontend/                # C1
│   ├── Dockerfile
│   └── src/
│       ├── pages/
│       ├── components/
│       └── lib/api.ts       # generated from openapi.json
├── api/                     # C2
│   ├── Dockerfile
│   └── app/
│       ├── main.py
│       ├── routers/
│       └── deps.py
├── worker/                  # C3
│   ├── Dockerfile           # this one has FFmpeg
│   └── app/
│       ├── orchestrator.py  # topological sort, state machine
│       ├── retry.py         # backoff, max 3
│       └── registry.py      # discovers agents by manifest
├── agents/                  # C4 — one folder per agent
│   ├── researcher/
│   ├── writer/
│   ├── image/
│   ├── video/
│   ├── publisher/
│   └── email/
├── adapters/                # C5 — one file per external service
│   ├── llm/
│   ├── search/
│   ├── tts/
│   ├── publish/
│   └── storage/
├── exporters/               # C6 — pure functions
├── db/                      # C7
│   ├── migrations/
│   └── seed.py
├── .importlinter            # the boundary rules, enforced by CI
├── docker-compose.yml
├── docker-compose.prod.yml
└── .env.example
```

### Environment variables (`.env.example`)

```bash
# Database and storage
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_KEY=...
DATABASE_URL=postgresql://postgres:password@db:5432/gp
STORAGE_BUCKET=artifacts

# Queue
REDIS_URL=redis://redis:6379/0

# Adapters — set FAKE_ADAPTERS=true to run the whole system with no API spend
FAKE_ADAPTERS=false
OPENAI_API_KEY=...
SEARCH_API_KEY=...
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...

ENVIRONMENT=development
```

> `FAKE_ADAPTERS=true` is the single most useful line in this file. It runs the entire platform end to end with canned responses, which is how three people work while the fourth is still building an agent, and how the Playwright suite runs for free in CI.

## Database Schema (Core Tables)

| Table | Key fields | Purpose |
|---|---|---|
| `users` | id, email, created_at | Accounts — mirrors Supabase `auth.users` |
| `workflows` | id, user_id, name, graph_definition (jsonb), status | Saved canvases |
| `agent_nodes` | id, workflow_id, agent_type, configuration (jsonb), position_order | One row per node on a canvas |
| `execution_runs` | id, workflow_id, triggered_by, status, started_at, completed_at | One row per Run press |
| `execution_logs` | id, run_id, node_id, status, retry_count, duration_ms, error_message | One row per node execution |
| `agent_outputs` | id, log_id, output_type, content, content_json, storage_path | What each agent produced |
| `credentials` | id, user_id, provider, encrypted_payload, expires_at | Google OAuth tokens — never in the graph JSON |
| `approvals` | id, log_id, decision, decided_by, decided_at, note | The UC-04 audit trail |

Eight tables, up from M2's five. `execution_runs` and `approvals` are additions — the reasoning is on the Deviations from M2 page.

## Supabase Features Used

| Feature | Used for |
|---|---|
| PostgreSQL | Every table above |
| Auth | Login, JWT, `get_current_user` in the API |
| Storage | Generated PDFs, DOCX and MP4 files, served by signed URL |
| Realtime | Live node status on the run monitor, without a custom WebSocket |
| Row Level Security | Each user sees only their own workflows |

## Key Dependencies

### `contracts` (C0)

```
pydantic
```

That is the whole list, and it should stay that way.

### `api` (C2)

```
fastapi
uvicorn[standard]
sqlalchemy
alembic
supabase
python-jose[cryptography]
celery              # to enqueue only
contracts           # local package
```

### `worker` (C3)

```
celery[redis]
sqlalchemy
contracts           # local package
```

No OpenAI, no FFmpeg bindings, no Google libraries. Those belong to the agents and adapters the worker loads, not to the worker itself.

### `agents/*` (C4) — each folder declares its own

```
# agents/writer/requirements.txt
openai

# agents/video/requirements.txt
gTTS
ffmpeg-python

# agents/publisher/requirements.txt
google-api-python-client
google-auth-oauthlib
```

### `frontend` (C1)

```
react
react-dom
react-router-dom
reactflow
@tanstack/react-query
zustand
axios
tailwindcss
@supabase/supabase-js
lucide-react
vite
```

---
---

# PART 4 — WEEK BY WEEK

*Notion page: 🗓️ Week by Week — who does what*

**Start here.** Twelve weeks, four people, one list per person per week. Tick things off as you go.

Tasks are grouped by **component**, not by person. Because each person owns whole components the two come to the same thing — but naming the component tells you which folder to open, and makes it obvious when a task is straying across a boundary. Full definitions are in Part 2.

Every task says what "done" looks like, so nobody has to guess whether it is finished.

| Who | Components owned | What that means in the repo |
|---|---|---|
| Ahmed Saleh Almutairi | **C1** `frontend` | Everything the user sees. Talks to the API and nothing else. |
| Hasan Ahmed Almutawa | **C2** `api`, **C3** `worker` | The front door and the engine. Neither knows what an agent does. |
| Zain Shehab Albandari | **C4** `agents/*`, **C5** `adapters/*`, **C6** `exporters` | Six plug-in agents, the ports to external services, the file renderers. |
| Mohammed Abdullah Bajaba | **C7** `db`, plus Docker, CI, keys, deployment | The schema and everything that holds the components together. |
| Everyone | **C0** `contracts` | Every type that crosses a boundary. Two approvals to change it. |

**Report Steward** rotates: Ahmed weeks 1–3, Hasan 4–6, Zain 7–9, Mohammed 10–12. That person spends 30 minutes a week logging problems in *Challenges & Resolutions* and taking screenshots. It is the cheapest marks in the whole project.

---

## W1 · 13–19 September

**Goal:** decide the stack, prove an empty skeleton runs, get every API key.

> This is the heaviest admin week and the most important one. Four decisions here unblock everything else.

### C1 · frontend — Ahmed

- [ ] **Audit the existing prototype.** Open whatever was built for M2 and find out what actually runs. *Done when:* a short written list of "works / half-works / does not exist" is in the W1 supervisor meeting notes.
- [ ] **Scaffold the React app.** Vite + TypeScript + Tailwind, routing, and empty Login, Register and Workflow-list screens. *Done when:* `npm run dev` opens a login page.

### C2 · api + C3 · worker — Hasan

- [ ] **Scaffold FastAPI.** Folder layout, a `/health` endpoint, automatic API docs at `/docs`. *Done when:* `/health` returns 200 from inside Docker.
- [ ] **Audit the backend claims** in M2 §8 with Ahmed — was the Google API authentication really verified? *Done when:* written into the same note.

### C4 · agents + C5 · adapters + C6 · exporters — Zain

- [ ] **Choose the image and video provider.** Named nowhere in M1 or M2, so it must be picked now. Recommended default: FFmpeg slideshow + gTTS narration, which is what M2 Table 6 already argued for. *Done when:* recorded in the Decisions Log.
- [ ] **Write the six agent input/output schemas** as Pydantic models. No logic yet, just the shapes. *Done when:* each model validates a sample dictionary.

### C7 · db + platform — Mohammed

- [ ] **Create the GitHub repo.** Branch protection on `main`, a PR template, `.env.example` with every variable named and no secrets. *Done when:* nobody can push to `main` directly.
- [ ] **Docker Compose skeleton** with four services: api, worker, redis, web. *Done when:* `docker compose up` starts all four without errors.
- [ ] **Write the database schema as a migration** — the 8 tables from the Database Schema page. *Done when:* `alembic upgrade head` builds the whole database from empty.
- [ ] **Get every API key and test it:** OpenAI, Tavily or SerpAPI, TTS, Google OAuth. *Done when:* each one returns a successful test call.
- [ ] **Apply for YouTube Data API quota.** Verification can take weeks. *Done when:* the application is submitted, whatever its status.
- [ ] **Choose where the system will be deployed.** *Done when:* recorded in the Decisions Log.
- [ ] **Set up the seven-folder repo layout** exactly as it appears in Part 3, each with its own Dockerfile where it has one. *Done when:* the tree matches, even where the folders are still empty.
- [ ] **Add `.importlinter` and wire it into CI.** Forbid: `api` and `worker` importing `agents`; agents importing `worker`; adapters importing `agents`. *Done when:* a deliberate bad import makes the build go red. **Do this in week one — later it is a refactor, now it is free.**

### C0 · contracts — all four, together, in one sitting

- [ ] **Agree and write the contracts package.** Sit in one room and define every type that crosses a boundary: the six agent input/output pairs, `AgentManifest`, `RunState`, `NodeState`, `LogEntry`, and the adapter ports. *Done when:* `pip install ./contracts` works in a container with no other component present, and all four people have read it.

> Nothing else in the project is worth starting before this exists. Four people building against four different mental models of "what the Writer returns" is the failure mode this hour prevents.

### All four together

- [ ] **Supervisor meeting — get D-01 signed off.** Supabase or the M2 stack. Do not write code that depends on the answer before you have it.
- [ ] **Agree the Report Steward rota** and put the weekly supervisor slot in everyone's calendar.

---

## W2 · 20–26 September

**Goal:** an empty pipeline works end to end — one fake agent runs from a button click and writes a log entry.

> Nothing here is real yet. That is deliberate: get the plumbing right while the agents are still fake and free.

### C1 · frontend — Ahmed

- [ ] **Build the canvas.** Agent palette down the left, React Flow area filling the rest, drag a node on, draw an arrow between two nodes. *Done when:* a three-node graph saves and is still there after a page reload.
- [ ] **Wire the login and register screens** to the real auth endpoints.

### C2 · api + C3 · worker — Hasan

- [ ] **Auth endpoints** and route protection — no endpoint answers without a valid session.
- [ ] **Workflow CRUD:** list, create, fetch, save, delete.
- [ ] **Graph validation** (`POST /workflows/{id}/validate`). Reject cycles, orphan nodes and missing configuration, each with a message a human can act on — "Writer has no upstream Researcher", not "validation failed".
- [ ] **Topological sort + Celery dispatch** of a single node.
- [ ] **Write the log rows.** Every state change creates or updates exactly one `execution_logs` row. *Done when:* running a one-node workflow leaves a complete, readable trail in the database.

### C4 · agents + C5 · adapters + C6 · exporters — Zain

- [ ] **BaseAgent class** with the abstract `execute` method and a mock-mode environment flag.
- [ ] **Mock versions of all six agents** returning realistic canned output that passes the real schemas. *This is what lets the other three work without spending API credit — do not skip it.*
- [ ] **`GET /agents/catalog`** returning each agent's configuration schema, so the frontend can build its own forms.

### C7 · db + platform — Mohammed

- [ ] **Row Level Security** so each user sees only their own workflows.
- [ ] **Seed script:** one demo user and three ready-made workflows (blog only; blog → video → YouTube; research → PDF → email). *Done when:* anyone can demo the system 30 seconds after a fresh install.
- [ ] **CI runs lint and tests** on every pull request, **plus the import contract**. *Done when:* a PR that crosses a component boundary cannot be merged.
- [ ] **Generate the frontend types from `openapi.json`** as a build step, so the frontend can never drift from the API. *Done when:* changing a response model and forgetting to regenerate makes the frontend build fail.

---

## W3 · 27 September – 3 October

**Goal:** type in a topic and get a real, researched article back.

### C1 · frontend — Ahmed

- [ ] **Configuration drawer** that builds its own form from `/agents/catalog`. Researcher shows topic and number of sources; Writer shows length, style and format. *Done when:* adding a new agent to the catalog makes a working form appear with zero frontend changes.
- [ ] **Run monitor** — node badges change colour as the run progresses.

### C2 · api + C3 · worker — Hasan

- [ ] **Pass output between agents.** The Writer receives what the Researcher produced, through the run context.
- [ ] **Live status** — Realtime subscription, or 2-second polling if that is simpler.

### C4 · agents + C5 · adapters + C6 · exporters — Zain

- [ ] **Researcher agent** against Tavily or SerpAPI. Returns notes plus a source list with titles and URLs.
- [ ] **Writer agent** against GPT-4. Returns the article, a title and a summary.
- [ ] **Prompt templates**, plus one reformat retry inside the agent when the model returns unparsable JSON — so a sloppy model response does not count against the reliability numbers later.

### C7 · db + platform — Mohammed

- [ ] **Store agent outputs** — text in the database, files in the bucket.
- [ ] **First integration test:** a full run lifecycle using mock agents, running in CI.

---

## W4 · 4–10 October

**Goal:** the article comes out as a PDF and a Word file you can download.

### C1 · frontend — Ahmed

- [ ] **Outputs screen** — every artefact from a run, with download buttons.
- [ ] **Loading, empty and error states** on every screen built so far. Usability testing in W11 punishes their absence, and retrofitting them is miserable.

### C2 · api + C3 · worker — Hasan

- [ ] **Download endpoint** returning a signed URL rather than streaming the file through the API.

### C4 · agents + C5 · adapters + C6 · exporters — Zain

- [ ] **PDF export** (WeasyPrint or ReportLab).
- [ ] **DOCX export** (python-docx).
- [ ] **Unit tests** for both — they are pure functions, so they are easy marks for the coverage target.

### C7 · db + platform — Mohammed

- [ ] **Storage bucket and signed URLs**, paths shaped `artifacts/{user}/{run}/`. M2 never said where generated files live; this settles it.

---

## W5 · 11–17 October

**Goal:** a script becomes a playable MP4. **This is the hardest week — if it slips, W8 slips.**

### C4 · agents + C5 · adapters — Zain *(most of the week is his)*

- [ ] **Text-to-speech narration** from the script.
- [ ] **FFmpeg assembly** — slides plus narration, rendered to MP4. *Done when:* the file plays in VLC and in a browser.
- [ ] **Image / thumbnail agent.**

### C7 · db + platform — Mohammed

- [ ] **Measure what the video worker costs:** CPU, memory, and render seconds per minute of video. Put the numbers straight into Results & Metrics — the report's infrastructure section needs them.

### C1 · frontend — Ahmed

- [ ] **Video preview player** on the Outputs screen.
- [ ] **Progress indication** for long-running nodes, so a five-minute render does not look like a hang.

### C2 · api + C3 · worker — Hasan

- [ ] **Prove the API never blocks** during a render. Start a video run, use the app throughout. *Done when:* every page still responds normally.

---

## W6 · 18–24 October

**Goal:** content leaves the platform — a real YouTube video and a real Drive file.

### C7 · db + platform — Mohammed

- [ ] **Google OAuth flow** plus the encrypted credentials table. No secret ever goes into the workflow graph JSON.

### C4 · agents + C5 · adapters + C6 · exporters — Zain

- [ ] **Publisher → YouTube:** upload with title, description and tags. *Done when:* the video is visible on the test channel and its URL is stored against the run.
- [ ] **Publisher → Google Drive:** upload and return a shareable link.

### C1 · frontend — Ahmed

- [ ] **Credential picker** in the configuration drawer.
- [ ] **Show published links** on the Outputs screen.

### C2 · api + C3 · worker — Hasan

- [ ] **Readable publish failures.** A rejected upload shows what went wrong, not a stack trace.

---

## W7 · 25–31 October

**Goal:** nothing gets published until a human clicks Approve.

### C4 · agents + C5 · adapters + C6 · exporters — Zain

- [ ] **Email agent** — Gmail API, with SMTP as a fallback. Sends the content links to a recipient list.

### C2 · api + C3 · worker — Hasan

- [ ] **Approval gate.** A node marked "requires approval" parks the run in `awaiting_approval` instead of continuing. *Done when:* a Publisher node genuinely cannot publish until someone approves.
- [ ] **Approve / reject endpoint** that resumes the run or halts it, recording who decided and when.

### C1 · frontend — Ahmed

- [ ] **Approval screen** — preview the article, video or PDF, then Approve or Reject with a note.

### C7 · db + platform — Mohammed

- [ ] **Approvals table and audit trail** — evidence that the human-in-the-loop requirement is real.

---

## W8 · 1–7 November

**Goal:** Research → Write → Video → Publish → Email runs start to finish, unattended, on a real topic. **Then the feature list closes.**

> This week is done together, not split up. The failures will be in the seams between people's work, which is exactly why nobody can fix them alone.

### Everyone, in order

- [ ] **Sun–Mon: the first full run.** Expect it to break. Write down precisely where it broke, in Challenges & Resolutions, as it happens.
- [ ] **Tue–Wed: fix the seams.** Schema mismatches, missing fields, wrong assumptions about what the previous agent returned.
- [ ] **Thu: the second full run**, unattended, start to finish, on a topic nobody has tested with.
- [ ] **Thu: declare feature freeze.** From here it is bug fixes, tests, deployment and the report. Every new idea goes to M4 Future Work — write it down there so it is not lost, then leave it.
- [ ] **Fri: the seventh-agent test** (Zain, 1 hour). Write a trivial agent that reverses a string. Drop the folder into `agents/`. Restart the worker. It must appear in the palette with a working configuration form. *Done when:* `git diff --stat` shows changes in that folder and nowhere else. **Record the file count — it is the evidence for NFR-04 and for acceptance test AT-12, and "zero files edited outside the new folder" is one of the strongest sentences you can put in the report.**

### Report Steward (Zain this week)

- [ ] **Capture the headline screenshot:** the canvas with all five agents wired together. This is the picture the report opens with.

---

## W9 · 8–14 November

**Goal:** make it fail well. Every failure visible, logged, and recoverable.

### C2 · api + C3 · worker — Hasan

- [ ] **Fault injection.** Kill the worker mid-run. Revoke a Google token. Force a network timeout. *Done when:* each one retries exactly three times, then halts the run and marks downstream nodes skipped.
- [ ] **Cancel a running workflow** from an endpoint.

### C1 · frontend — Ahmed

- [ ] **Error chips** on failed nodes, showing the real message.
- [ ] **Log viewer:** node, status, retry count, duration, error — plus CSV export. The export is what turns a log into a report table without retyping anything.

### C4 · agents + C5 · adapters + C6 · exporters — Zain

- [ ] **Handle malformed model output** cleanly in every agent, not just the Writer.

### C7 · db + platform — Mohammed

- [ ] **Performance pass:** measure p95 API latency while a video renders. Record it in Results & Metrics.

---

## W10 · 15–21 November

**Goal:** produce the numbers the report needs.

### C2 · api + C3 · worker — Hasan

- [ ] **Unit tests to 70%** on the orchestrator and agent modules.

### C7 · db + platform — Mohammed

- [ ] **Integration suite** — run lifecycle, retry-then-succeed, retry exhaustion, approval park and resume.
- [ ] **Playwright end-to-end** on the three template workflows, using mock agents so it is repeatable and free.
- [ ] **Reliability campaign: 50+ runs.** Aggregate the logs and fill in the NFR-02 table. *Report the number you actually measure, even if it is below 99% — an honest 94% with an explanation reads far better than an unsupported 99%.*

### C4 · agents + C5 · adapters + C6 · exporters — Zain

- [ ] **Time the manual baseline.** Do research → write → video → publish by hand, once, with a stopwatch on each stage. M1 §4.5 asks for exactly this comparison and it cannot be faked.

### All four together

- [ ] **Work through the 12 acceptance test cases** in one sitting. Fill in *Actual*, not just Pass or Fail — the report wants observed behaviour.

---

## W11 · 22–28 November

**Goal:** it is deployed, and real people who did not build it have used it.

### C7 · db + platform — Mohammed

- [ ] **Deploy to the chosen host.** *Done when:* a URL works from a phone on mobile data.
- [ ] **Fresh-machine test.** Clone the repo on a clean machine, follow your own instructions, `docker compose up`. Write `SETUP.md` as you go — it becomes the setup guide required on the CD/DVD.

### C1 · frontend — Ahmed

- [ ] **Usability sessions with non-technical people.** Give them one task — "produce a blog post about a topic you choose and email it to yourself" — and no instructions. Record time taken, whether they finished unaided, and their SUS score. *Do not help them. Watching someone get stuck is the finding.*

### C2 · api + C3 · worker — Hasan

- [ ] **Production architecture diagram** with the real container list and resource sizes — the as-deployed version of M2 Figure 2, not a copy of it.

### C4 · agents + C5 · adapters + C6 · exporters — Zain

- [ ] **Fill in the Results & Metrics tables** from the W10 measurements.

### Report Steward (Mohammed this week)

- [ ] **Sweep the Screenshots database.** Every row captured, every caption written. Use the *Still missing* view — when it is empty, this is done.

---

## W12 · 29 November – 5 December

**Goal:** the report is written, checked and submitted.

> Nothing new gets built this week. If something is broken and not critical, it becomes a documented limitation — that is a legitimate and well-marked thing to have in a report.

### C2 · api + C3 · worker — Hasan

- [ ] **Implementation Details chapter** — deployment steps, screenshots with descriptions, infrastructure setup.
- [ ] **Deviations from M2** section — the table is already drafted in Technical Docs.

### C7 · db + platform — Mohammed

- [ ] **Testing Process and Results chapter** — pull the table straight from the Test Cases *Report table* view.
- [ ] **Assemble the CD/DVD:** report soft copy, complete source code, the free tools used, and the setup instructions.

### C4 · agents + C5 · adapters + C6 · exporters — Zain

- [ ] **Result Analysis chapter** — the updated version of the M2 initial results, built from the Results & Metrics tables.

### Report Steward (Mohammed)

- [ ] **Challenges and Resolutions chapter** — filter Challenges to *Report-worthy* and write it up. If that database is empty this week, the chapter cannot be written honestly, which is why it gets logged from W1.

### All four together

- [ ] **Preliminary sections:** title page, acknowledgment, undertaking, abstract (250–300 words, rewritten for M3 — it is now about what was built, not what was proposed), contents, list of tables, list of figures, references.
- [ ] **Similarity check early in the week**, not on the last day. Above 15% excluding references is not accepted.
- [ ] **Get the checklist form signed** by Dr. Alkahtani. Late submission costs five marks.
- [ ] **Two hard-bound copies, dark green cover** (Computer Science), project title and ID on the spine.

---
---

# PART 5 — TECHNICAL DOCS

*Notion page: 🏗️ Technical Docs, and its six sub-pages*

The living technical reference. Keep these current as you build — in W12 they become the Implementation Details chapter, and the setup page becomes the how-to instructions the GPC guide requires on the CD/DVD.

## 5.1 Architecture

The three layers are exactly those specified in M2 §6.1, made concrete.

### Layer 1 — Client

React 18 + TypeScript + Vite. React Flow for the canvas, TanStack Query for server state, Zustand for canvas state, Tailwind for styling.

Screens: Auth · Workflow list · Canvas · Config drawer · Run monitor · Approval · Logs · Outputs.

Talks to Layer 2 over REST, plus a Realtime subscription for live run status.

### Layer 2 — Orchestration

FastAPI on Python 3.11. Receives the workflow as a directed acyclic graph, validates it, decomposes it into ordered tasks, and dispatches them. A workflow state machine tracks where each run is. Celery with Redis as broker keeps long tasks — video rendering, uploads — off the API server.

Responsibilities, in order:

1. Validate the graph. Reject with actionable errors: cycle detected, orphan node, Writer without an upstream Researcher, missing credential.
2. Topological sort. The ordered node list is persisted with the run.
3. Dispatch node *n* as a Celery task. On success, write the output, merge it into the run context, dispatch *n+1*.
4. `retry_with_backoff(max_retries=3, delay=2**attempt + random())`, exactly as M2 §7.3.3 specifies. Each attempt increments `retry_count` and appends to `error_message`.
5. On terminal failure: run status `failed`, downstream nodes `skipped`, workflow halted (M2 §6.3).
6. Nodes flagged `requires_approval` park at `awaiting_approval` and resume on the approve endpoint.
7. Emit a structured log line per state transition. This is the raw material for every results table in the report.

### Layer 3 — Agents

Each agent is an independent module consuming structured input and returning structured output for the next agent. `BaseAgent(ABC).execute(input: dict) -> dict`.

Researcher · Writer · Image/Thumbnail · Video · Publisher · Email, plus an Export service (PDF/DOCX/MP4) that is a service rather than a node.

External: OpenAI · Tavily/SerpAPI · TTS · FFmpeg · YouTube Data v3 · Drive · Gmail/SMTP.

### Why three layers

From M2 §6.1: each layer can be tested and developed independently; compute-heavy agents scale horizontally without touching the frontend; new agents drop into Layer 3 without modifying the orchestrator. That last point is NFR-04, and AT-12 is the test that proves it.

### Non-negotiable invariants

1. The frontend never calls an LLM or an external content API directly.
2. Every agent returns a validated Pydantic model, never free text.
3. Every node execution writes exactly one `execution_logs` row, updated in place through its status transitions.
4. No secret is ever stored in the workflow graph JSON. Credentials live in the `credentials` table, encrypted, or in server environment variables.
5. FastAPI is the only writer to the database. The browser touches Supabase only for Realtime subscriptions and signed-URL downloads.

---

## 5.2 Database Schema

Every entity and field from M2 §6.4 is preserved. Two tables and two node states are added because execution needs them.

> **Why `execution_runs` is new.** M2 logs against `workflow_id` only, which cannot distinguish two runs of the same workflow. NFR-02 is measured per run, so the run has to be a first-class row.

### Tables

| Table | Columns | Notes |
|---|---|---|
| `users` | `id uuid PK`, `email text unique`, `created_at timestamptz` | Supabase `auth.users` mirror. `hashed_password` is handled by Supabase Auth, or kept in-house on the fallback stack. |
| `workflows` | `id uuid PK`, `user_id FK`, `name text`, `graph_definition jsonb`, `status text`, `created_at`, `updated_at` | `graph_definition` holds the React Flow nodes and edges. M2 field names preserved. |
| `agent_nodes` | `id uuid PK`, `workflow_id FK`, `agent_type agent_type_enum`, `configuration jsonb`, `position_order int` | enum: researcher, writer, image, video, publisher, email |
| `execution_runs` | `id uuid PK`, `workflow_id FK`, `triggered_by FK`, `status run_status`, `started_at`, `completed_at`, `total_nodes int`, `failed_nodes int` | **New.** One row per Run press. The unit NFR-02 is measured over. |
| `execution_logs` | `id uuid PK`, `run_id FK`, `workflow_id FK`, `node_id FK`, `status node_status`, `started_at`, `completed_at`, `retry_count int default 0`, `error_message text`, `duration_ms int` | node_status: pending, running, success, failed, retrying — M2's five — plus `awaiting_approval` (UC-04) and `skipped`. |
| `agent_outputs` | `id uuid PK`, `log_id FK`, `output_type output_type_enum`, `content text`, `content_json jsonb`, `storage_path text`, `mime_type text`, `bytes bigint`, `created_at` | enum: text, file, url. `content_json` is what replaces MongoDB; `storage_path` points into the bucket. |
| `credentials` | `id uuid PK`, `user_id FK`, `provider text`, `encrypted_payload bytea`, `expires_at`, `created_at` | Google OAuth tokens. Never in `configuration`. |
| `approvals` | `id uuid PK`, `log_id FK`, `decision text`, `decided_by FK`, `decided_at`, `note text` | **New.** Evidence trail for UC-04. |

### Indexes

`execution_logs(run_id, started_at)` · `execution_logs(status)` · `workflows(user_id)` · `agent_outputs(log_id)`

### Constraints

- `agent_nodes(workflow_id, position_order)` unique
- `retry_count <= 3` check — matches the limit in M2 §6.3

### Row Level Security

If D-01 is approved: every table filtered on `user_id`, or via a join to `workflows.user_id`. The service role bypasses RLS for the FastAPI worker.

This gives per-user isolation for free. It does **not** license roles, teams or sharing — those are out of scope per M1 §3.2.

### Migrations

Alembic, or Supabase migration files, from day one. A hand-clicked schema cannot be reproduced on the CD/DVD, and the GPC guide requires database setup instructions there.

### Seed data

One demo user and three template workflows: blog only; blog → video → YouTube; research → PDF → email. Any team member should be able to demo in thirty seconds without preparation.

---

## 5.3 API Reference

FastAPI. The OpenAPI schema at `/docs` is the source of truth once the code exists; this page is the contract agreed up front so the frontend and backend can be built in parallel.

| Method | Path | Purpose |
|---|---|---|
| POST | `/auth/register`, `/auth/login` | Session. Delegated to Supabase Auth if D-01 is approved. |
| GET, POST | `/workflows` | List / create |
| GET, PUT, DELETE | `/workflows/{id}` | Fetch / save graph / delete |
| POST | `/workflows/{id}/validate` | DAG check: acyclic, connected, type-compatible edges, required config present |
| POST | `/workflows/{id}/run` | Enqueue a run. Returns `run_id` with 202. |
| GET | `/runs/{id}` | Run status + per-node states |
| GET | `/runs/{id}/logs` | Full log with retries and errors |
| POST | `/runs/{id}/nodes/{node_id}/approve` | UC-04 approve / reject |
| POST | `/runs/{id}/cancel` | Halt a running workflow |
| GET | `/outputs/{id}` | Signed download URL (PDF / DOCX / MP4) |
| GET | `/agents/catalog` | Agent types + JSON schema of each config. Drives the config drawer dynamically. |
| GET | `/health` | Liveness. Needed for the deployment section of the report. |

### Conventions

- All validation errors come from `/validate`, never from client-side logic. The client renders what the server says.
- `/agents/catalog` is what makes NFR-04 real: a new agent appears in the palette with a working config form and no frontend change.
- 202 on run enqueue, not 200 — the run has not finished when the response returns. This is the visible face of NFR-01.

---

## 5.4 Agent Specifications

Extends M2 Table 1 with the input and output schemas the orchestrator actually needs.

### Contract

```python
class BaseAgent(ABC):
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]

    @abstractmethod
    async def execute(self, input_data: dict) -> dict: ...
```

Every agent validates in and out with Pydantic. A model that returns prose where a schema was expected is an agent bug, not an orchestrator failure — the agent gets one reformat attempt before the orchestrator's retry counter advances (risk R5).

### The agents

| Agent | Input | Output | External dependency |
|---|---|---|---|
| Researcher | topic, num_sources | notes[], sources[] (title + url) | Tavily / SerpAPI |
| Writer | notes, length, style, format | article_md, title, summary | OpenAI GPT-4 |
| Image | prompt / article title | image files | **Provider not named in M1 or M2 — must be chosen (risk R1)** |
| Video | script, voice, resolution | mp4 path, duration | TTS + FFmpeg (slides / stock + narration) |
| Publisher | file or url, platform, metadata | remote_url, platform_id | YouTube Data v3 / Drive API |
| Email | recipients, subject, body, links | message_id, sent_at | Gmail API / SMTP |
| Export *(service, not a node)* | article_md / assets | pdf, docx, mp4 | WeasyPrint or ReportLab; python-docx; FFmpeg |

### Mock mode

Every agent ships with a mock mode behind an environment flag, returning canned output that satisfies the same schema.

This is not a nicety. It is what lets four people develop in parallel against agents they do not own, what makes the end-to-end suite runnable without burning API credit, and what keeps the W10 reliability campaign affordable. Build it in W2, with the BaseAgent contract, not later.

### Configuration surface

Per M2 §6.5.2, each agent exposes its own fields — Researcher: topic and number of sources; Writer: length, style, output format; Publisher: target platform and credentials. These are published as JSON schema through `/agents/catalog`, so the config drawer builds itself.

---

## 5.5 Deployment & Setup

> Write this page **as you go**, not in W12. It becomes the environment and database how-to that the GPC guide requires on the CD/DVD, and `SETUP.md` in the repo is its twin.

### Services

`docker-compose.yml`:

- `web` — nginx serving the React build
- `api` — FastAPI / uvicorn
- `worker` — Celery
- `beat` — only if scheduling is added
- `redis` — broker and result backend
- Postgres and file storage: managed by Supabase if D-01 is approved, otherwise a `db` container plus MinIO

### Environment

`.env.example` is committed with every variable named and no secrets in it. Nobody should have to guess a variable name to get the project running.

### Host

**Not yet chosen** — decide in W1. Options considered:

| Option | For | Against |
|---|---|---|
| Small cloud VM + Docker Compose | Simplest to explain in a report; full control | Manual TLS, manual updates |
| Container host (Railway / Render / Fly) | Fast to deploy, TLS handled | Less to write about; cost at idle |
| University server | Free; institutionally appropriate | Access and firewall policy unknown |

FFmpeg makes the worker CPU-hungry. 2 vCPU / 4 GB is the practical floor, and the W5 sizing test will give a real number.

### Backups

Nightly Postgres dump; artefacts live in the storage bucket.

### Capture during deployment (W11)

The report's Implementation Details chapter needs all of this, and it is far easier to collect while deploying than to reconstruct afterwards:

- [ ] Architecture-in-production diagram
- [ ] Container list with resource sizing
- [ ] Cost table
- [ ] Terminal screenshot of a clean-machine bring-up
- [ ] Step-by-step deployment procedure, as actually performed
- [ ] Database setup and migration commands

---

## 5.6 Deviations from M2

The M3 report needs this section if anything built differs from the approved M2 Technical Development Plan. A documented, justified change reads as engineering judgement. An undocumented one reads as inconsistency.

Keep this page in step with the **Decisions Log** — every row there with *Deviates from M2* checked belongs here, written out in report prose.

### D-01 — Supabase instead of self-hosted Postgres + MongoDB

**Status: proposed, awaiting supervisor sign-off.** Do not write this up as fact until it is approved.

| Concern | M2 stack of record | Proposed | Why |
|---|---|---|---|
| Relational DB | Self-hosted PostgreSQL (Docker) | Managed PostgreSQL | Same engine — the §6.4 schema is portable unchanged |
| Documents | MongoDB | `jsonb` columns | Removes an entire database from the deployment |
| Auth | Own users table + JWT | Supabase Auth | M2 specified only `hashed_password`; days of work removed |
| File storage | **Unspecified in M2** | Supabase Storage + signed URLs | M2 §6.4 never says where PDF/DOCX/MP4 files live — this closes a real gap |
| Realtime status | Polling or custom WebSocket | Realtime on `execution_logs` | Live run status without extra infrastructure |
| Task queue | Celery + Redis | **Unchanged** | Supabase does not replace this. NFR-01 depends on it |

**Argument for the report:** fewer moving parts for a four-person team on a fixed deadline; storage and authentication were the two least-specified parts of M2; Postgres remains Postgres, so the designed schema survives intact.

**Scope note.** Supabase Auth with Row Level Security makes per-user isolation nearly free. Take it — each user sees only their own workflows. Do not add roles, teams or sharing: M1 §3.2 and M2 §3.2 place multi-user permissions and access control explicitly out of scope, and quietly crossing that line is worse than not having the feature.

**If rejected:** Docker Postgres + MinIO for files + custom JWT auth, MongoDB still dropped in favour of `jsonb`. Nothing else in the plan changes.

### Schema additions

Not a change of technology, but a change from the M2 §6.4 design and worth one paragraph:

- **`execution_runs`** — M2 logs against `workflow_id` only, which cannot distinguish two runs of the same workflow. NFR-02 is measured per run.
- **`approvals`** — UC-04 requires human review before publication, but M2 gave it no storage.
- **`awaiting_approval` and `skipped` node states** — added to M2's five. The first is UC-04; the second is what downstream nodes become when a run halts.

### Further deviations

*Add a section here each time the Decisions Log gains a row with "Deviates from M2" checked.*

---
---

# PART 6 — RESULTS & METRICS

*Notion page: 📊 Results & Metrics*

Empty tables, ready to fill. Everything the M3 **Result Analysis** section needs. Fill them as measurements happen, not in W12.

## Automated vs. manual baseline

M1 §4.5 asks for exactly this comparison. Time the manual pipeline yourselves once (W10) and record it here beside the automated timings.

| Stage | Manual (min) | Automated (min) | Speed-up |
|---|---|---|---|
| Research a topic | | | |
| Write the article | | | |
| Produce the video | | | |
| Publish to YouTube | | | |
| Distribute by email | | | |
| **End-to-end total** | | | |

## Per-agent latency

From `execution_logs.duration_ms`, aggregated over the W10 campaign.

| Agent | Runs | Median (s) | p95 (s) | Failures | Retries |
|---|---|---|---|---|---|
| Researcher | | | | | |
| Writer | | | | | |
| Image | | | | | |
| Video | | | | | |
| Publisher | | | | | |
| Email | | | | | |

## NFR-02 — handoff success rate

The only number M1 quantified: 99%. Report what was actually measured, whatever it turns out to be, and explain any gap.

| Metric | Target | Measured |
|---|---|---|
| Total runs | ≥ 50 | |
| Total node handoffs | — | |
| Successful handoffs | — | |
| **Handoff success rate** | **≥ 99%** | |
| Runs completing without retry | — | |
| Runs halted after 3 retries | — | |

## Retry rate by external API

| API | Calls | Retries | Retry rate | Most common error |
|---|---|---|---|---|
| OpenAI | | | | |
| Search (Tavily / SerpAPI) | | | | |
| TTS | | | | |
| YouTube Data v3 | | | | |
| Google Drive | | | | |
| Gmail / SMTP | | | | |

## NFR-01 — UI responsiveness under load

| Condition | p50 API latency | p95 API latency | UI blocked? |
|---|---|---|---|
| Idle | | | |
| During a video render | | | |
| Three concurrent runs | | | |

## NFR-03 — usability

Participant count is not specified in any source document — agree it with the supervisor.

| Participant | Background | Time on task | Completed unaided | SUS | Notes |
|---|---|---|---|---|---|
| P1 | | | | | |
| P2 | | | | | |
| P3 | | | | | |
| **Mean** | | | | | |

## Test pass rate

| Level | Cases | Pass | Fail | Coverage |
|---|---|---|---|---|
| Unit (backend) | | | | |
| Unit (frontend) | | | | |
| Integration | | | | |
| End-to-end | | | | |
| Acceptance | 12 | | | — |
| Robustness | 3 | | | — |

## Output quality

A rubric agreed by the team, scored blind where possible. Define the scale before scoring, not after.

| Dimension | Scale | Score | Notes |
|---|---|---|---|
| Article factual accuracy | 1–5 | | |
| Article readability | 1–5 | | |
| Video audio clarity | 1–5 | | |
| Video pacing | 1–5 | | |
| Thumbnail relevance | 1–5 | | |

---
---

# PART 7 — M3 REPORT

*Notion page: 📝 M3 Report*

Drafting page for the Milestone 3 report. Structure is taken from the GPC guide, section C.

> **Reminder:** similarity above 15% excluding references is not acceptable, and late submission costs five marks.

## Preliminary sections

| Section | Owner | Status | Notes |
|---|---|---|---|
| Title page | All | Not started | Project title, four names + IDs, supervisor, committee, month/year |
| Acknowledgment | All | Not started | Carry forward from M1/M2 |
| Undertaking | All | Not started | Signed by all four |
| Abstract | All | Not started | 250–300 words. Rewrite for M3 — it is now about what was built, not what was proposed |
| Table of contents | All | Not started | |
| List of tables | All | Not started | |
| List of figures | All | Not started | |

## Milestone 3 chapters

| Chapter | Required content (GPC guide) | Owner | Status |
|---|---|---|---|
| **Implementation Details** | Deployment steps; UI screenshots with functionality descriptions; infrastructure setup — computational resources, cloud servers, databases | Hasan | Not started |
| ↳ *Deviations from the M2 Technical Development Plan* | Not required by the guide, but necessary if D-01 is approved. Table + justification | Hasan | Not started |
| **Testing Process / Results** | Testing methods, evaluation metrics, robustness, unit / integration / acceptance testing; test cases and results | Mohammed | Not started |
| **Result Analysis** | Updated version of the M2 initial results | Zain | Not started |
| **Challenges and Resolutions** | Obstacles faced during implementation and the solutions adopted | Report Steward | Not started |
| **References** | Complete, properly cited | All | Not started |

## Where the content comes from

Nothing in this report should be written from memory. Each chapter has a source in this workspace:

- **Implementation Details** → Technical Docs pages + Screenshots & Evidence (filter: Report section = Implementation Details)
- **Testing Process / Results** → Test Cases database (filter: In report = checked)
- **Result Analysis** → Results & Metrics tables
- **Challenges and Resolutions** → Challenges database (filter: Report-worthy = checked)
- **Deviations from M2** → Decisions Log (filter: Deviates from M2 = checked)

If a chapter's source is empty when W12 arrives, that chapter cannot be written honestly. That is the whole reason the databases exist.

## Submission checklist

- [ ] Signed Graduation Project Checklist form (supervisor-signed)
- [ ] Two hard-bound copies
- [ ] **Dark green cover** — CS students
- [ ] Spine: project title (short form if needed) + project ID
- [ ] CD/DVD: report soft copy
- [ ] CD/DVD: complete source code
- [ ] CD/DVD: free software tools / IDEs used
- [ ] CD/DVD: environment and database setup how-to
- [ ] Similarity check under 15% excluding references

---
---

# PART 8 — DATABASES

The nine tracking databases and every row seeded into them.

## 8.1 📋 Requirements (16 rows)

Traceability matrix: every FR, NFR and UC from M1/M2, its build status and its evidence.
Properties: ID · Type · Description · Build status · Area · Source · Target week · Evidence · Tasks (relation) · Test Cases (relation).
View: *Traceability by status* (board grouped by Build status).

| ID | Name | Type | Area | Source | Target week | Description |
|---|---|---|---|---|---|---|
| FR-01 | Visual Orchestration | Functional | Frontend | M1 §5 | W2 | The system shall provide a drag-and-drop interface allowing users to link task-specific AI agents into a sequential workflow. |
| FR-02 | Multi-Agent Library | Functional | Agents | M1 §5 | W7 | The system shall include pre-configured agents for Research, Writing, Video Creation, Publishing, and Email. |
| FR-03 | Multi-Modal Generation | Functional | Agents | M1 §5 | W5 | The platform shall generate text articles, images/thumbnails, and video content based on user-defined scripts. |
| FR-04 | File Transformation | Functional | Agents | M1 §5 | W4 | The system shall automatically export generated content into PDF, DOCX, and MP4 formats. |
| FR-05 | API Integration | Functional | Agents | M1 §5 | W6 | The system shall facilitate direct uploads to YouTube and Google Drive, and dissemination via Gmail/SMTP. |
| FR-06 | Fault Tolerance | Functional | Backend | M1 §5 | W9 | The system shall implement an automated retry mechanism for failed API operations and maintain execution logs. |
| NFR-01 | Performance | Non-Functional | Backend | M1 §5 | W9 | The system shall handle long-running tasks asynchronously using Celery and Redis to ensure the UI remains responsive. |
| NFR-02 | Reliability | Non-Functional | Backend | M1 §5 | W10 | The platform shall maintain a 99% success rate for task handoffs between agents within the internal orchestrator. Measured over 50+ runs in W10. |
| NFR-03 | Usability | Non-Functional | Frontend | M1 §5 | W11 | The interface shall be designed for non-technical users, requiring no manual coding to execute complex AI pipelines. Verified by moderated usability sessions. |
| NFR-04 | Maintainability | Non-Functional | Cross-cutting | M1 §5 | W8 | The system architecture shall be modular, allowing for the addition of new specialized AI agents with minimal code changes. Demonstrated via the BaseAgent contract. |
| UC-01 | Create Workflow | Use Case | Frontend | M2 §6.2 | W2 | User drags agent nodes onto the canvas, configures parameters, and connects them to define an automation pipeline. |
| UC-02 | Execute Workflow | Use Case | Cross-cutting | M2 §6.2 | W3 | User triggers workflow execution; the orchestrator processes agents sequentially and displays real-time status. |
| UC-03 | Configure Agent | Use Case | Frontend | M2 §6.2 | W3 | User selects an agent node and sets its parameters (topic, format, API credentials, etc.). |
| UC-04 | Review Output | Use Case | Frontend | M2 §6.2 | W7 | User previews generated content before approving publication. Implemented as the awaiting_approval node state. |
| UC-05 | Publish Content | Use Case | Agents | M2 §6.2 | W6 | System uploads approved content to YouTube, Google Drive, or sends via email through API integration. |
| UC-06 | View Execution Logs | Use Case | Frontend | M2 §6.2 | W9 | User accesses detailed logs of workflow runs including timestamps, success/failure status, and retry attempts. |

## 8.2 ✅ Tasks (70 rows, 549 estimated hours)

Properties: Name · Status · Owner (person) · Lead (select) · Area · Week · Dates · Priority · Est. hours · Requirement (relation) · Blocked by / Blocks (self-relation) · PR link · Notes.
Views: Board by Status · Board by Lead · Timeline · This week (W1) · Blocked · Critical path.

| Week | Tasks | Hours |
|---|---|---|
| W1 | 13 | 62 |
| W2 | 8 | 74 |
| W3 | 6 | 52 |
| W4 | 5 | 34 |
| W5 | 4 | 36 |
| W6 | 4 | 34 |
| W7 | 4 | 32 |
| W8 | 3 | 29 |
| W9 | 5 | 36 |
| W10 | 6 | 60 |
| W11 | 4 | 40 |
| W12 | 8 | 60 |
| **Total** | **70** | **549** |

### W1 — 13–19 Sep

| Task | Lead | Area | Priority | Hrs |
|---|---|---|---|---|
| Decide Supabase vs. M2 stack — and get supervisor sign-off | All | Admin | P0 | 4 |
| Audit the existing prototype against the M2 §8 claims | Ahmed | Admin | P0 | 6 |
| Create repo, branch protection, PR template, .env.example | Mohammed | Data & DevOps | P0 | 4 |
| Docker Compose skeleton: api, worker, redis, web | Mohammed | Data & DevOps | P0 | 8 |
| Database schema + first migration (8 tables) | Mohammed | Data & DevOps | P0 | 8 |
| CI: lint + tests on every pull request | Mohammed | Data & DevOps | P1 | 4 |
| Obtain and smoke-test every API key | Mohammed | Data & DevOps | P0 | 6 |
| Apply for YouTube Data API quota / app verification | Mohammed | Data & DevOps | P0 | 3 |
| Choose the image / video generation provider | Zain | Agents | P0 | 4 |
| Choose the deployment target | Mohammed | Data & DevOps | P1 | 2 |
| FastAPI skeleton: /health, OpenAPI, project layout | Hasan | Backend | P0 | 6 |
| React + Vite + Tailwind skeleton, routing, auth screen shells | Ahmed | Frontend | P1 | 6 |
| Set the Report Steward rotation and the weekly supervisor slot | All | Report | P1 | 1 |

### W2 — 20–26 Sep

| Task | Lead | Area | Priority | Hrs | Requirement |
|---|---|---|---|---|---|
| Auth: register and login wired to Supabase Auth | Hasan | Backend | P0 | 8 | — |
| /workflows CRUD endpoints | Hasan | Backend | P0 | 8 | UC-01 |
| DAG validation + topological sort | Hasan | Backend | P0 | 10 | UC-02 |
| Celery + Redis wiring — one mock agent runs end-to-end | Hasan | Backend | P0 | 10 | NFR-01 |
| execution_runs / execution_logs writing + state machine | Hasan | Backend | P0 | 8 | FR-06 |
| React Flow canvas: palette, custom nodes, edges, save graph | Ahmed | Frontend | P0 | 16 | FR-01, UC-01 |
| BaseAgent contract, mock mode flag, /agents/catalog | Zain | Agents | P0 | 10 | NFR-04 |
| Seed script: demo user + 3 template workflows | Mohammed | Data & DevOps | P1 | 4 | — |

### W3 — 27 Sep – 3 Oct

| Task | Lead | Area | Priority | Hrs | Requirement |
|---|---|---|---|---|---|
| Researcher agent (Tavily / SerpAPI) | Zain | Agents | P0 | 8 | FR-02 |
| Writer agent (GPT-4) with validated Pydantic output | Zain | Agents | P0 | 10 | FR-02 |
| Schema-driven config drawer from /agents/catalog | Ahmed | Frontend | P0 | 12 | UC-03 |
| Run monitor with live node status | Ahmed | Frontend | P1 | 10 | UC-02 |
| Persist agent outputs (content_json + storage path) | Mohammed | Data & DevOps | P1 | 6 | — |
| Prompt templates + in-agent reformat retry | Zain | Agents | P1 | 6 | — |

### W4 — 4–10 Oct

| Task | Lead | Area | Priority | Hrs | Requirement |
|---|---|---|---|---|---|
| PDF export (WeasyPrint or ReportLab) | Zain | Agents | P0 | 8 | FR-04 |
| DOCX export (python-docx) | Zain | Agents | P1 | 6 | FR-04 |
| Storage bucket + signed-URL download endpoint | Mohammed | Data & DevOps | P0 | 8 | FR-04 |
| Outputs screen with downloads and published links | Ahmed | Frontend | P1 | 8 | FR-04 |
| Unit tests for the export module | Zain | Agents | P2 | 4 | — |

### W5 — 11–17 Oct

| Task | Lead | Area | Priority | Hrs | Requirement |
|---|---|---|---|---|---|
| TTS narration from script | Zain | Agents | P0 | 8 | FR-03 |
| FFmpeg assembly — playable MP4 from a script | Zain | Agents | P0 | 16 | FR-03 |
| Image / thumbnail agent | Zain | Agents | P1 | 8 | FR-03 |
| Worker resource sizing test for the video pipeline | Mohammed | Data & DevOps | P1 | 4 | NFR-01 |

### W6 — 18–24 Oct

| Task | Lead | Area | Priority | Hrs | Requirement |
|---|---|---|---|---|---|
| Google OAuth flow + encrypted credentials table | Mohammed | Data & DevOps | P0 | 12 | FR-05 |
| Publisher agent — YouTube upload | Zain | Agents | P0 | 10 | FR-05, UC-05 |
| Publisher agent — Google Drive upload | Zain | Agents | P1 | 6 | FR-05, UC-05 |
| Credential selection in the config drawer | Ahmed | Frontend | P1 | 6 | UC-03 |

### W7 — 25–31 Oct

| Task | Lead | Area | Priority | Hrs | Requirement |
|---|---|---|---|---|---|
| Email agent (Gmail API / SMTP) | Zain | Agents | P1 | 8 | FR-05, UC-05 |
| Approval gate: awaiting_approval state + resume endpoint | Hasan | Backend | P0 | 10 | UC-04 |
| Approval UI with article / video / PDF preview | Ahmed | Frontend | P0 | 10 | UC-04 |
| approvals table + audit trail | Mohammed | Data & DevOps | P2 | 4 | UC-04 |

### W8 — 1–7 Nov

| Task | Lead | Area | Priority | Hrs | Requirement |
|---|---|---|---|---|---|
| Full pipeline dry run on a real topic | All | Backend | P0 | 12 | NFR-04 |
| Fix handoff and schema mismatches found in the dry run | All | Backend | P0 | 16 | — |
| Declare feature freeze — scope locked | All | Admin | P0 | 1 | — |

### W9 — 8–14 Nov

| Task | Lead | Area | Priority | Hrs | Requirement |
|---|---|---|---|---|---|
| Fault injection — verify retry and exponential backoff | Hasan | Backend | P0 | 10 | FR-06 |
| Run cancel endpoint + UI control | Hasan | Backend | P1 | 6 | UC-02 |
| Error surfacing in the UI (node error chips) | Ahmed | Frontend | P1 | 6 | FR-06 |
| Log viewer with retries, durations and CSV export | Ahmed | Frontend | P1 | 8 | UC-06 |
| Performance pass — p95 API latency under load | Mohammed | Data & DevOps | P1 | 6 | NFR-01 |

### W10 — 15–21 Nov

| Task | Lead | Area | Priority | Hrs | Requirement |
|---|---|---|---|---|---|
| Unit test suite — 70% coverage on orchestrator/ and agents/ | Hasan | Backend | P1 | 12 | — |
| Integration suite — run lifecycle, retry, approval park/resume | Mohammed | Data & DevOps | P1 | 12 | — |
| Playwright end-to-end on the 3 template workflows | Mohammed | Data & DevOps | P1 | 10 | — |
| Acceptance test pass — 12 scripted cases across FR and UC | All | Report | P0 | 10 | — |
| Reliability campaign — 50+ runs, measure NFR-02 | Mohammed | Data & DevOps | P0 | 10 | NFR-02 |
| Time the manual baseline for the automated-vs-manual comparison | Zain | Report | P1 | 6 | — |

### W11 — 22–28 Nov

| Task | Lead | Area | Priority | Hrs | Requirement |
|---|---|---|---|---|---|
| Deploy to the chosen host | Mohammed | Data & DevOps | P0 | 12 | — |
| Clean-machine reproduction test + SETUP.md | Mohammed | Data & DevOps | P0 | 8 | — |
| Usability sessions with non-technical participants + SUS | Ahmed | Frontend | P0 | 12 | NFR-03 |
| Capture every UI screenshot with its report caption | Report Steward | Report | P0 | 8 | — |

### W12 — 29 Nov – 5 Dec

| Task | Lead | Area | Priority | Hrs |
|---|---|---|---|---|
| Draft — Implementation Details chapter | Hasan | Report | P0 | 12 |
| Draft — Testing Process and Results chapter | Mohammed | Report | P0 | 10 |
| Draft — Result Analysis chapter | Zain | Report | P0 | 10 |
| Draft — Challenges and Resolutions chapter | Report Steward | Report | P0 | 6 |
| Assemble the report per GPC structure + preliminary sections | All | Report | P0 | 12 |
| Similarity check — under 15% excluding references | Report Steward | Report | P0 | 4 |
| Signed Graduation Project Checklist form | All | Admin | P0 | 2 |
| Assemble the CD/DVD contents | Mohammed | Admin | P0 | 4 |

## 8.3 🧪 Test Cases (18 rows)

Properties: ID · Level · Requirement (relation) · Steps · Expected · Actual · Result · Run date · Tester · In report.
View: *Report table* (filtered to In report = checked) — this is the table that goes into the M3 report.

| ID | Level | Req | Steps | Expected |
|---|---|---|---|---|
| AT-01 | Acceptance | FR-01, UC-01 | Log in → New workflow → drag Researcher, Writer and Publisher onto the canvas → connect them in order → Save. | Three connected nodes render; Save succeeds; reloading the page restores the same graph. |
| AT-02 | Acceptance | FR-02 | Open the canvas and inspect the agent palette. | Researcher, Writer, Video, Publisher and Email all available and draggable, each with its own configuration schema. |
| AT-03 | Acceptance | FR-03 | Run a workflow with Researcher → Writer → Image → Video on a real topic. | A text article, at least one image/thumbnail and a playable MP4 are produced and stored against the run. |
| AT-04 | Acceptance | FR-04 | From the Outputs screen of a completed run, download each artefact. | All three files download via signed URL and open correctly in their native applications. |
| AT-05 | Acceptance | FR-05, UC-05 | Approve a completed run and let the Publisher and Email agents execute. | Video on the YouTube test channel; file in Drive; email arrives with working links. Remote URLs recorded in agent_outputs. |
| AT-06 | Acceptance | FR-06 | Revoke a credential mid-run so a node fails, and observe the orchestrator. | Node retries exactly three times with exponential backoff, retry_count reaches 3, run halts, downstream nodes skipped, error visible in the log viewer. |
| AT-07 | Acceptance | UC-02 | Press Run on a saved workflow and watch the run monitor. | Each node moves pending → running → success in order; UI updates without a manual refresh. |
| AT-08 | Acceptance | UC-03 | Click a Researcher node, set topic and sources; click a Writer node, set length, style and format. | Form matches each agent's schema, validates input, values persist in agent_nodes.configuration after save. |
| AT-09 | Acceptance | UC-04 | Run a workflow whose Publisher node requires approval; inspect the preview; approve. Repeat and reject. | Run parks at awaiting_approval and publishes nothing until approval. Approve resumes it; reject halts it. Both recorded in approvals. |
| AT-10 | Acceptance | UC-06 | Open the log viewer for a run that included a retry. | Per-node timestamps, status, retry count, duration and error message all shown; log exports as CSV. |
| AT-11 | Performance | NFR-01 | Start a workflow containing video generation; while it runs, navigate the app and load the log viewer. | No request blocks on the worker. Record p95 API latency during the run. |
| AT-12 | Acceptance | NFR-04 | Implement a trivial new agent against BaseAgent and register it. Count the files touched. | Appears in the palette with a working configuration form, no frontend and no orchestrator change. Record the file count as NFR-04 evidence. |
| RT-01 | Reliability | NFR-02 | Script 50+ runs across the three template workflows, mixing mock and live agents. Aggregate execution_logs. | Handoff success rate reported against the 99% target, with retry frequency broken down by external API. |
| RB-01 | Robustness | FR-06 | Terminate the worker container while a node is executing, then restart it. | No silent failure and no data loss. Run state accurate after restart — resumed or clearly marked failed. |
| RB-02 | Robustness | FR-06 | Force the Writer agent to receive unparsable JSON. | Pydantic rejects it; agent makes one reformat attempt; only then does the orchestrator retry counter advance. Error names the schema violation. |
| RB-03 | Robustness | FR-05 | Attempt a publish with a file beyond the platform limit; separately force a network timeout during upload. | Both fail gracefully with an accurate log entry and a readable UI error, not a stack trace. |
| US-01 | Usability | NFR-03 | Moderated session. Task: "produce a blog post about a topic of your choice and email it to yourself", with no instruction on how. | Completed without writing code and without moderator help. Record time-on-task, completion rate and SUS. Participant count to be agreed with the supervisor. |
| IT-01 | Integration | UC-02 | Automated: enqueue a run of mock agents against ephemeral Postgres and Redis; assert every state transition and the final context. | All nodes reach success in topological order; one execution_logs row per node; run marked complete. |

## 8.4 🗓️ Timeline (12 rows)

Properties: Week · Dates · Deliverable · M2 Gantt phase · Status. View: *Gantt* (timeline).

| Week | Dates | Focus | M2 Gantt phase |
|---|---|---|---|
| W1 | 13–19 Sep | Foundations & decisions | Phase 1/2 start |
| W2 | 20–26 Sep | Skeleton end-to-end | Phase 1, Phase 2 |
| W3 | 27 Sep – 3 Oct | Researcher + Writer | Phase 2 |
| W4 | 4–10 Oct | Export module | Phase 3 (FR-04) |
| W5 | 11–17 Oct | Video pipeline (highest risk) | Phase 2/3 |
| W6 | 18–24 Oct | Google integrations | Phase 3 |
| W7 | 25–31 Oct | Email + approval gate | Phase 3 |
| W8 | 1–7 Nov | Full pipeline (feature freeze) | Phase 3 |
| W9 | 8–14 Nov | Hardening | Phase 3/4 (FR-06, NFR-01) |
| W10 | 15–21 Nov | Testing | Phase 4 |
| W11 | 22–28 Nov | Deployment + usability | Phase 4 |
| W12 | 29 Nov – 5 Dec | Report + submission | Phase 4 |

## 8.5 🚨 Risk Register (10 rows)

Properties: ID · Impact · Likelihood · Status · Consequence · Mitigation · Lead · Owner · Watch from. View: *By status* (board).

| ID | Risk | Impact | Likelihood | Lead | Watch from | Mitigation |
|---|---|---|---|---|---|---|
| R1 | Video/image generation provider never chosen | High | High | Zain | W1 — blocks W5 | Decide in W1. Default to deterministic FFmpeg slideshow + TTS, already the rationale in M2 Table 6. |
| R2 | YouTube upload quota / app verification | High | Medium | Mohammed | W1 — blocks W6 | Apply in W1. Fallback: unlisted uploads to a test channel, documented as a limitation. |
| R3 | API cost overrun | High | Medium | Mohammed | W1 — continuous | Mock mode by default; live keys only for integration runs; track spend at every team sync. |
| R4 | Stack switch to Supabase mid-project | High | Medium | All | W1 | Decide once, in W1, with supervisor sign-off. Record in the Decisions Log; write up as a deviation table. |
| R5 | LLM returns unparsable JSON | Medium | High | Zain | W3 | Pydantic validation plus one in-agent reformat retry before the orchestrator's retry counter is touched. |
| R6 | Scope creep into multi-user roles and sharing | Medium | Medium | All | W2 | RLS isolation only. Roles, teams and sharing deferred to Future Work and named as such. |
| R7 | Report written at the last minute | High | High | Report Steward | W1 — continuous | Steward rotates weekly from W1. Screenshots captured the week the feature lands, captions written then. |
| R8 | Long-running video task blocks the API | Medium | Medium | Hasan | W5 | Celery isolation verified by an explicit test in W9: drive a long run while exercising the UI, record p95. |
| R9 | Team member unavailable (exams) | Medium | High | All | W1 — continuous | Every area has a named backup reviewer; no secrets or accounts held by one person only. |
| R10 | Similarity index above 15% | High | Medium | Report Steward | W12 | Original prose for M3 chapters; quote and cite properly; run the check early in W12. |

## 8.6 ⚠️ Challenges & Resolutions (empty — fill continuously)

Properties: Date · Area · Challenge · Root cause · Resolution · Lead · Owner · Report-worthy · Status.
View: *Report-worthy* (filtered) — feeds the M3 Challenges and Resolutions chapter directly.

**This database starts empty on purpose.** Log obstacles the week they happen. If it is still empty in W12, that chapter cannot be written honestly.

## 8.7 📸 Screenshots & Evidence (10 placeholder rows)

Properties: Screen · Feature · Caption for report · Date · Image · Report section · Captured.
View: *Still missing* (filtered to Captured = unchecked) — when it is empty, W11's screenshot sweep is done.

| Screen | Feature | When to capture |
|---|---|---|
| Auth | Supabase Auth email + password sign-in | W2 |
| Workflow list | Saved workflows with last-run status, New / Duplicate / Delete | W2 |
| Canvas | Agent palette, connected nodes, top bar, status bar | W2, retake in W8 with all five agents wired — the headline figure |
| Config drawer | Schema-driven form; Researcher and Writer side by side | W3 |
| Run monitor | Live node status, elapsed time, cancel | W3 — catch it mid-run, one node running and one green |
| Approval | UC-04 human-in-the-loop review before publication | W7 |
| Logs | Per-node status, retry count, duration, error | W9 during fault injection — a log showing a real retry is worth far more than a clean one |
| Outputs | PDF, DOCX, MP4 downloads and published links | W6, after a real YouTube and Drive publish |
| Deployment / terminal | docker compose up on a fresh machine, all services healthy | W11 — evidence for the deployment-steps requirement |
| Diagram | Deployed three-layer architecture with container list and sizing | W11 — the as-deployed version of M2 Figure 2, not a copy |

## 8.8 🔑 Decisions Log (1 row)

Properties: Date · Status · Area · Options considered · Rationale · Approved by · Deviates from M2.
View: *Deviations from M2* (filtered).

### D-01 — Supabase (Postgres + Auth + Storage + Realtime) instead of self-hosted Postgres + MongoDB

- **Date:** 13 September 2026
- **Status:** Proposed — **not yet approved**
- **Area:** Data
- **Deviates from M2:** Yes
- **Approved by:** PENDING — Dr. Hasan Alkahtani sign-off required before any code depends on this

**Options considered:**
A) Keep the M2 stack of record: self-hosted PostgreSQL + MongoDB + custom JWT auth + unspecified file storage.
B) Supabase managed Postgres + Auth + Storage + Realtime, MongoDB dropped in favour of jsonb, Celery + Redis unchanged.
C) Fallback if rejected: Docker Postgres + MinIO for files + custom JWT, MongoDB still dropped.

**Rationale:** Fewer moving parts for a four-person team on a fixed deadline. Storage and auth were the two least-specified parts of M2 — §6.4 never says where PDF/DOCX/MP4 files live. Postgres remains Postgres, so the §6.4 schema survives intact. Supabase does NOT replace Celery + Redis; NFR-01 still depends on them.

Full consequences table is in Part 5.6.

## 8.9 📅 Meetings (1 row)

Properties: Date · Type · Attendees · Present · Decisions · Actions · Week.
Supervisor rows are the evidence of the continuous engagement the GPC guide expects.

### W1 supervisor meeting — stack decision sign-off (16 September 2026)

**Agenda:**

1. **D-01 — Supabase vs. the M2 stack of record.** Present the deviation table; ask for sign-off or rejection. Nothing else on this list matters if this is left open.
2. **Prototype audit.** What actually runs today versus what M2 §8 claimed.
3. **Scope confirmation.** Per-user isolation via Row Level Security is in; roles, teams and sharing stay out, as declared in M1 §3.2.
4. **Usability testing.** How many participants, recruited how? Not specified in any document.
5. **Dates.** Confirm the M3 submission date so the 12-week schedule can be checked against it. Current plan runs W1 = 13 Sep to W12 ending 5 Dec 2026.
6. **Budget.** Is there any funding for API credit and hosting?

---
---

## Source documents this workspace is built from

- `M1v5.docx` — Milestone 1: Project Initiation (Proposal and Planning)
- `Milestone_2_Report 1.docx` — Milestone 2: Design and Development
- `GPC-Milestones-Guide.pdf` — CCSIT Graduation Project Milestone Reports Guidelines, Ver. 01 (2024–2025)

Everything traceable to those files is cited inline by section number. Additions made to render the plan executable — the seven-component split, the `contracts` package, the `execution_runs` and `approvals` tables, the `awaiting_approval` and `skipped` states, the API surface, the Supabase evaluation, role assignments, the week-by-week schedule, test levels and the risk register — are engineering proposals, not claims found in the source documents.

*End of export.*
