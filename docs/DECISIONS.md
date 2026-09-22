# Infrastructure decisions

Decisions made while setting up the repository in W1. Each one should also get a row in the Notion **🔑 Decisions Log**; rows marked *Deviates from plan* belong in the M3 report's "Deviations from M2" section.

Project-level decisions still open (D-01 Supabase, host, image provider, product name) are tracked in Notion and in `GP-plan.md` / `DESIGN-SYSTEM.md` §32 — nothing here pre-empts them.

---

### INF-01 · Each component is an installable package with a `src/` layout

**Decision.** `contracts`, `db`, `adapters`, `exporters`, `api`, `worker` and each agent have their own `pyproject.toml` and `src/<package>/`. Agents share the PEP 420 namespace package `agents` (`agents.researcher`, `agents.writer`, …), each installed from its own folder.

**Why.** "Tested alone" and "separate deployables" only mean something if each piece installs on its own. CI installs each component with only its dependencies. The namespace keeps the plan's grep test (`from agents`) meaningful and lets import-linter treat all agents as one layer.

**Consequence.** Local editable installs use `--config-settings editable_mode=compat` (in `scripts/bootstrap.sh` and the dev images) so the namespace resolves correctly from the repository root. The plan's tree showed `api/app/`; the packages are `api/src/api/` and `worker/src/worker/` so the two don't both claim the name `app`.

*Deviates from plan:* folder layout only.

### INF-02 · The agent catalog travels through Redis

**Decision.** On startup the worker publishes the catalog (every manifest plus its configuration JSON Schema) to the Redis key `gp:agents:catalog`. `GET /agents/catalog` reads it.

**Why.** The API must not import agents (C2 rule), yet it must serve the catalog that builds the palette and forms (NFR-04). The worker is the component that discovers agents, so it publishes what it found.

**Consequence.** The catalog is empty until a worker has started; `/health/ready` reports it and `/validate` returns a warning rather than failing.

### INF-03 · Agents are discovered through the `gp.agents` entry point group

**Decision.** Each agent's `pyproject.toml` declares `[project.entry-points."gp.agents"]`. `worker.registry.Registry.from_entry_points()` loads them. In development the worker container installs any new agent folder on start.

**Why.** The worker never names an agent. Adding the seventh agent (AT-12) is: add a folder, restart the worker. Verified during setup — the new agent appeared in the catalog with its form schema and no other file changed.

### INF-04 · Runs snapshot the graph; logs reference the snapshot

**Decision.** `execution_runs.graph_snapshot` stores the graph as it was when Run was pressed. `execution_logs.node_id` references a node in that snapshot (not a foreign key to `agent_nodes`), and the log row carries `agent_type` and `position_order`.

**Why.** Users edit workflows after running them. Without a snapshot, editing or deleting a node would change or destroy the history the NFR-02 numbers are measured from.

*Deviates from plan:* adds three columns; `execution_logs.node_id` is no longer a foreign key.

### INF-05 · `agent_type` is text, not a PostgreSQL enum

**Decision.** `agent_nodes.agent_type` and `execution_logs.agent_type` are `varchar(64)` validated by the contracts model (`^[a-z][a-z0-9_]*$`). Run status, node status, output type and approval decision remain enums.

**Why.** An enum would need a migration for every new agent, which would make AT-12 ("zero files edited outside the new folder") impossible.

*Deviates from plan:* §5.2 specified `agent_type_enum`.

### INF-06 · Authentication: JWT in the Supabase shape, dev sign-in until D-01

**Decision.** The API accepts JWTs with `sub`, `email` and `aud = authenticated` — the same shape Supabase Auth issues — from two sources: `POST /auth/dev-login` (HS256, signed with `JWT_SECRET`, no password, disabled when `ENVIRONMENT=production`) and, when the frontend is switched to `VITE_AUTH_MODE=supabase`, Supabase Auth itself.

**Why.** Nothing about the rest of the system depends on who signs the token, so work isn't blocked on D-01. The frontend opts in per environment (`frontend/src/lib/auth-client.ts`); the API tells the two apart by the token's `alg` header rather than a mode flag, so both can be exercised side by side.

**Verification detail (superseded from the original plan).** Supabase now signs new tokens with a project-specific asymmetric key (ES256/RS256) rather than a single HS256 shared secret — the isnad project has already rotated off the legacy shared secret. So `api/src/api/auth.py` verifies a Supabase-issued token against the project's public JWKS (`{SUPABASE_URL}/auth/v1/.well-known/jwks.json`) instead of a secret; only dev-login's own HS256 tokens use `JWT_SECRET`. `JWT_SECRET` never needs to match anything on Supabase's side.

Uses **PyJWT** rather than python-jose (listed in the plan) because python-jose is no longer maintained; `PyJWKClient` handles the JWKS fetch and caching.

### INF-07 · Run context = outputs of every upstream agent

**Decision.** Before a node runs, the worker merges the outputs of all its ancestors (oldest first), then applies the node's saved configuration, then validates against the agent's input model. Input models use field aliases to accept upstream names (Video reads Writer's `article_md` as `script`).

**Why.** Found during setup: with only the direct parent's output, Publisher (after Video) never received Writer's `title`. The plan describes a run context that accumulates outputs; this implements it.

### INF-08 · An `ImagePort` was added to `contracts.ports`

**Decision.** `ImagePort.generate(prompt, aspect) -> PNG bytes`, with a fake. The real provider is still undecided (risk R1).

**Why.** The plan's port list had no port for the Image agent. *Needs the C0 two-approval review in W1.*

### INF-09 · Dependency versions are pinned in `constraints.txt`

**Decision.** Every `pip install` — bootstrap, CI, Dockerfiles — uses `-c constraints.txt`. Node dependencies are pinned by `package-lock.json`. Major versions follow the stack in GP-plan Part 3 (React 18, React Flow 11, Vite 5, Tailwind 3).

**Why.** "Identical environment for four people" (GP-plan Part 3) and a CI that fails only for real reasons. Regenerate with `scripts/update_constraints.sh` when dependencies change.

### INF-10 · Development database on host port 5433

**Decision.** The Docker PostgreSQL is published on `localhost:5433` (configurable with `DB_HOST_PORT`).

**Why.** Team members may already run PostgreSQL on 5432; a clash silently connects tools to the wrong database.

### INF-11 · CI integration job runs on `main`, not on every pull request

**Decision.** The full `docker compose` + smoke test job runs on pushes to `main` and on demand. Pull requests run lint, boundaries, every component's isolated tests, migrations, contract drift, frontend and Playwright.

**Why.** The integration job builds the FFmpeg worker image and costs several minutes per run; private repositories have a monthly Actions allowance. Run it on a PR manually (Actions → CI → Run workflow) when a change touches several components.
