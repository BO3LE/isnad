# Setup

This is the environment and database how-to required on the CD/DVD (GPC guide). Keep it true: if you change how the project starts, change this file in the same pull request. W11's clean-machine test follows it word for word.

---

## 1. Prerequisites

| Tool | Version | Needed for | Check |
|---|---|---|---|
| Git | any recent | everything | `git --version` |
| Docker Desktop (or Docker Engine + Compose v2) | 24+ | running the stack | `docker compose version` |
| Python | 3.11 or newer | tests and linters outside Docker | `python3 --version` |
| Node.js | 20 LTS | frontend tests and linters outside Docker | `node --version` |
| Make | any | shortcuts (optional) | `make --version` |

Windows: use WSL 2 and clone the repository inside the Linux filesystem, not under `/mnt/c`, or file watching and hot reload will be slow.

## 2. Run the whole stack (Docker)

```bash
git clone <repository-url> gp-platform
cd gp-platform
cp .env.example .env
docker compose up --build
```

First build takes a few minutes (the worker image installs FFmpeg). Later starts take seconds.

| Service | Address | Notes |
|---|---|---|
| frontend | http://localhost:5173 | Vite dev server, hot reload |
| api | http://localhost:8000 · docs at `/docs` | Uvicorn with reload |
| worker | — | Celery; restarts itself when Python files change |
| db | `localhost:5433` (user `postgres`, password `postgres`, database `gp`) | Host port 5433 so a local PostgreSQL on 5432 doesn't clash |
| redis | `localhost:6379` | |
| migrate | — | Runs `alembic upgrade head` and the seed script, then exits |

Sign in at http://localhost:5173 with `demo@gp.local`.

Check everything end to end:

```bash
python3 scripts/smoke_test.py
```

Expected output ends with three `✓` lines — one per template workflow.

### Useful Docker commands

```bash
docker compose logs -f api worker     # follow logs
docker compose restart worker         # e.g. after adding an agent folder
docker compose run --rm migrate       # re-run migrations + seed
docker compose down                   # stop
docker compose down -v                # stop and delete the database and generated files
```

## 3. Local development without Docker (tests, linters, editors)

The stack still needs PostgreSQL and Redis; the simplest route is to run only those in Docker:

```bash
docker compose up -d db redis migrate
scripts/bootstrap.sh                   # creates .venv, installs every component in editable mode
source .venv/bin/activate
cd frontend && npm ci && cd ..
```

Run pieces on your machine (each in its own terminal, with `.venv` activated):

```bash
# API
uvicorn api.main:app --reload

# Worker (from the repository root)
celery -A worker.celery_app worker --loglevel=INFO

# Frontend
cd frontend && npm run dev
```

`.env` is read from the directory you start each process in; the defaults in `.env.example` point at `localhost:5433` and `localhost:6379`.

## 4. Tests and checks

```bash
make test     # every Python component's own suite + frontend unit tests
make lint     # ruff, format, import boundaries, agent shape, eslint, tsc
make check    # both — this is what CI runs on a pull request
```

Individual pieces:

```bash
cd worker && python -m pytest                 # one component
cd frontend && npm run test:e2e               # Playwright; first run: npx playwright install chromium
python3 scripts/smoke_test.py                 # full stack, needs docker compose up
```

## 5. Database

| Task | Command |
|---|---|
| Apply migrations | `docker compose run --rm migrate` (or `cd db && alembic upgrade head` with `DATABASE_URL` set) |
| Create a migration after changing `db/src/db/models.py` | `make revision m="add credentials provider index"` — then read the generated file before committing |
| Undo everything | `cd db && alembic downgrade base` |
| Re-seed | `python -m db.seed` (idempotent) |
| Connect with psql | `psql postgresql://postgres:postgres@localhost:5433/gp` |

Migrations are the only way the schema changes. Never edit a table by hand — the CD/DVD copy must be reproducible from `alembic upgrade head`.

## 6. Environment variables

Every variable is listed, with a comment, in [`.env.example`](.env.example). The important ones:

| Variable | Default | Meaning |
|---|---|---|
| `FAKE_ADAPTERS` | `true` | Canned responses for every external service. Set to `false` only for integration runs with real keys. |
| `JWT_SECRET` | placeholder | Token signing secret. Generate a real one for any shared deployment. |
| `ENABLE_DEV_LOGIN` | `true` | Password-less sign-in. Always disabled when `ENVIRONMENT=production`. |
| `OPENAI_API_KEY`, `SEARCH_API_KEY` | empty | Used only when `FAKE_ADAPTERS=false`. |
| `SUPABASE_*` | empty | Filled in once D-01 is approved. |

Never commit `.env`. Share keys through a password manager, not chat.

## 7. Changing the API

The frontend's types are generated from the API, so the two can't drift:

```bash
make openapi    # writes contracts/openapi.json and frontend/src/lib/api-types.ts
```

Commit both files with your API change. CI fails if they are out of date.

## 8. Troubleshooting

| Symptom | Fix |
|---|---|
| `port is already allocated` for 5433 / 6379 / 8000 / 5173 | Something else uses the port. Stop it, or set `DB_HOST_PORT` / `REDIS_HOST_PORT` in `.env`. |
| Palette is empty; `/health/ready` says `worker_catalog: not published` | The worker isn't running or failed to start: `docker compose logs worker`. |
| A run stays `queued` | Worker down or can't reach Redis: `docker compose ps`, `docker compose logs worker`. |
| `relation "workflows" does not exist` | Migrations didn't run: `docker compose run --rm migrate`. |
| New agent folder doesn't appear | `docker compose restart worker`, then check the log for `installing new agent`. Run `python scripts/validate_manifests.py`. |
| Removed an agent folder and the worker logs "failed to load agent entry point" | Rebuild the worker: `docker compose up -d --build worker`. |
| Frontend doesn't hot-reload on Windows/macOS | Already enabled via polling in Docker; outside Docker nothing is needed. |
| `ModuleNotFoundError` locally | Re-run `scripts/bootstrap.sh` and make sure `.venv` is activated. |
| CI fails on "OpenAPI and frontend types are up to date" | Run `make openapi` and commit the two generated files. |

## 9. Deployment

TODO(W1 decision, W11 execution — Mohammed): the host is not chosen yet (GP-plan §5.5). The production stack is [`docker-compose.prod.yml`](docker-compose.prod.yml): it drops the local database in favour of Supabase, builds production image targets, and serves the frontend through nginx with the API behind `/api`. Record the real deployment steps here as they are performed.
