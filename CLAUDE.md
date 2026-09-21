# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Git Safety Rule
Before making any code changes, always run `git branch --show-current`.
If the result is "main" or "master", STOP and ask me to create/switch to a feature branch first. Never make changes directly on main.
Branch names follow `<component>/<short-description>` (e.g. `worker/retry-backoff`) — see [CONTRIBUTING.md](CONTRIBUTING.md).

## What this is
A visual AI-agent workflow platform: drag agents onto a canvas, chain them, press Run — nothing is published until a human approves it. Full narrative: [README.md](README.md). Environment/DB setup and troubleshooting: [SETUP.md](SETUP.md). Team workflow and PR process: [CONTRIBUTING.md](CONTRIBUTING.md).

## Architecture: seven components, one import rule
Each component (`contracts`, `frontend`, `api`, `worker`, `agents/*`, `adapters`, `exporters`, `db`) is a separately installable package, tested in isolation, talking to the others only through `contracts`. Allowed/forbidden import edges are enforced in CI by [`.importlinter`](.importlinter) — read it before adding a cross-component import. If it blocks you, the fix is almost always moving a type into `contracts`, not editing `.importlinter`.

Edges worth knowing without opening the file:
- `agents/*` never imports `worker`, `api`, `db`, `adapters` implementations, or another agent — only `contracts` and `ports`.
- `worker` never imports an agent by name (see below).
- `api` never imports `agents`, `adapters`, `exporters`, or `worker`.
- `exporters` is pure: no network clients, no other component.

`contracts` changes need two approvals (CODEOWNERS-enforced) and should prefer additive changes (new optional field/model) over renames — it's the one package that can break more than one component at once.

## Agent plugin discovery (spans three files, not obvious from any one)
Agents are never imported by name. Each `agents/<name>/pyproject.toml` declares an entry point under `[project.entry-points."gp.agents"]`; `worker/src/worker/registry.py`'s `Registry.from_entry_points()` loads whatever is installed. On startup the worker publishes the resulting catalog (manifests + JSON-Schema config forms) to the Redis key `gp:agents:catalog`; the API reads it from there instead of importing agents, because the `api → agents` edge is forbidden. Consequences:
- The catalog is empty until a worker has started once; `/health/ready` and `/validate` degrade gracefully rather than failing when it's missing.
- Adding an agent should touch nothing outside `agents/<name>/` ([docs/ADDING_AN_AGENT.md](docs/ADDING_AN_AGENT.md)) — if a change bleeds into another component, the boundary is probably wrong.
- The entry point **name** must equal both the folder name and the agent's own `manifest.name`, or the registry silently skips it (logged, not raised — one broken agent must not take the worker down).

## Run execution (worker/src/worker/orchestrator.py)
Before a node runs, the worker merges the outputs of *every* upstream agent (oldest ancestor first), then applies the node's saved config, then validates against the agent's input model — not just the direct parent's output. Agents accept upstream fields under a different name via `validation_alias=AliasChoices(...)` (e.g. Video reads Writer's `article_md` as `script`). Retries are the worker's job (`2^attempt + jitter`, max 3) — agents must not write their own retry loops; raise `contracts.errors.AgentError` (retryable) or `NonRetryableAgentError` (not) instead.

Runs snapshot the graph at press-Run time (`execution_runs.graph_snapshot`); `execution_logs.node_id` is not a foreign key into the live graph, so editing or deleting a node afterward doesn't change history. `agent_type` columns are validated text (`^[a-z][a-z0-9_]*$`), not a Postgres enum, so a new agent never needs a schema migration.

## Commands
```bash
scripts/bootstrap.sh                   # .venv + every Python component installed editable
                                        # (--config-settings editable_mode=compat is required for the
                                        # `agents` namespace package to resolve — docs/DECISIONS.md INF-01)
cd frontend && npm ci

make test                              # every component's own suite, run in isolation (scripts/test_all.sh)
cd worker && python -m pytest          # one Python component
cd worker && python -m pytest tests/test_orchestrator.py::test_name -q    # one test
cd frontend && npm test -- <pattern>   # vitest, one file/pattern
cd frontend && npm run test:e2e        # Playwright (first run: npx playwright install chromium)

make lint                              # ruff + format check + import boundaries + agent manifest shape + eslint + tsc
make check                             # lint + test — what CI runs on a PR

make openapi                           # after any API change: regenerate contracts/openapi.json +
                                        # frontend/src/lib/api-types.ts; commit both, CI checks drift
make revision m="describe the change"  # new Alembic migration after changing db/src/db/models.py —
                                        # read the generated file before committing

python3 scripts/smoke_test.py          # full stack against a running `docker compose up`, expects three ✓ lines
```

## Gotchas worth knowing before you touch things
- `FAKE_ADAPTERS=true` is the default everywhere, including CI: every external service (OpenAI, search, TTS, YouTube, Drive, Gmail) runs against a fake. Look in `adapters/src/adapters/*/fake.py` next to the real implementation when working on a port.
- Migrations are the only way the schema changes — never hand-edit a table; `alembic upgrade head` must reproduce it from scratch.
- Running components outside Docker: `.env` is read from the directory each process is started in, not the repo root.
- Adding a run or node status requires updating three places together or CI fails: `db/src/db/models.py` + a migration, `frontend/src/design-system/status/statusMeta.ts`, and DESIGN-SYSTEM.md §16.
