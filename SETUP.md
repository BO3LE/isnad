# Setup

This is the environment and database how-to required on the CD/DVD (GPC guide). Keep it true: if you change how the project starts, change this file in the same pull request. W11's clean-machine test follows it word for word.

---

## 1. Prerequisites

| Tool | Version | Needed for | Check |
|---|---|---|---|
| Git | any recent | everything | `git --version` |
| Docker Desktop (or Docker Engine + Compose v2) | 24+ | running the stack | `docker compose version` |
| Python | 3.11 or newer | tests and linters outside Docker | `python3 --version` (Windows: `python --version`, see Windows notes) |
| Node.js | 20 LTS | frontend tests and linters outside Docker | `node --version` |
| Make | any | shortcuts (optional) | `make --version` |

Windows: Docker Desktop with the WSL 2 backend works directly from Git Bash — you do **not** have to clone
into the WSL filesystem to run `docker compose up`. If you additionally do local (non-Docker) development,
cloning inside the Linux filesystem (not under `/mnt/c`) makes file watching and hot reload faster, but
it is not required to complete this guide. See **Windows notes** below for the gotchas this test actually hit.

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
# Windows (Git Bash, native Python — not WSL): python -X utf8 scripts/smoke_test.py
# (plain "python3" is usually a Microsoft Store stub, and plain "python" defaults to the
# legacy cp1252 console encoding, which crashes on the script's ✓/✗ output — see Windows notes)
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
                                                # Windows (Git Bash): python -X utf8 scripts/smoke_test.py
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

### Supabase production database

Migrations also cover the Supabase-specific setup (RLS in `0002`, Realtime + the private `artifacts` Storage bucket in `0005`) — see docs/DECISIONS.md INF-12 and INF-13. To apply them to the live project:

1. Get the project's connection string for the **session pooler** (Supabase dashboard → Project Settings → Database → Connection string → "Session pooler", port `5432` — not the transaction pooler on `6543`; Alembic needs a stable session for DDL, see `db/src/db/session.py`).
2. Apply migrations:

   ```bash
   cd db
   DATABASE_URL="postgresql://postgres.<project-ref>:<password>@<pooler-host>:5432/postgres" alembic upgrade head
   ```

3. Verify, read-only, from the repo root:

   ```bash
   DATABASE_URL="postgresql://postgres.<project-ref>:<password>@<pooler-host>:5432/postgres" python -X utf8 scripts/check_supabase.py
   ```

   Every line should print `✓`. A `✗` means something drifted from what the migrations expect; the line names which check failed. The script never prints the connection string.

## 6. Environment variables

Every variable is listed, with a comment, in [`.env.example`](.env.example). The important ones:

| Variable | Default | Meaning |
|---|---|---|
| `FAKE_ADAPTERS` | `true` | Canned responses for every external service. Set to `false` only for integration runs with real keys. |
| `JWT_SECRET` | placeholder | Token signing secret. Generate a real one for any shared deployment. |
| `ENABLE_DEV_LOGIN` | `true` | Password-less sign-in. Always disabled when `ENVIRONMENT=production`. |
| `OPENAI_API_KEY`, `SEARCH_API_KEY` | empty | Used only when `FAKE_ADAPTERS=false`. |
| `STORAGE_BACKEND` | `local` | Where generated files go. `local` = `STORAGE_ROOT` on disk, served at `PUBLIC_FILES_URL` (development only). `supabase` = the private bucket `STORAGE_BUCKET`, downloaded through signed URLs. Set the same value for api and worker. Files are stored at `artifacts/{user_id}/{run_id}/…` either way. |
| `STORAGE_BUCKET` | `artifacts` | Supabase Storage bucket for `STORAGE_BACKEND=supabase`. Must be **private**. |
| `DOWNLOAD_URL_EXPIRES_IN` | `300` | Lifetime of a signed download URL, in seconds. |
| `SUPABASE_URL` | the isnad project | Verifies sign-in tokens (JWKS) and, with `STORAGE_BACKEND=supabase`, is the Storage endpoint. |
| `SUPABASE_SERVICE_KEY` | empty | Needed only for `STORAGE_BACKEND=supabase` (worker uploads, API signs links). A secret that bypasses RLS: server side only, never `VITE_`-prefixed. |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`, `CREDENTIALS_ENCRYPTION_KEY`, `FRONTEND_URL` | empty / local defaults | Settings → Connections (see below). Not needed with `FAKE_ADAPTERS=true`. |

Never commit `.env`. Share keys through a password manager, not chat.

### Connect Google (Settings → Connections, D-09)

Publisher (YouTube, Drive) and Email (Gmail) act as a person's Google account. Each person connects
theirs once; the tokens are stored encrypted in the `credentials` table and a workflow step only
holds the connection's id. With `FAKE_ADAPTERS=true` none of this is needed.

**1. Google Cloud Console** (one project for the team, <https://console.cloud.google.com>)

1. *APIs & Services → Library*: enable **YouTube Data API v3**, **Google Drive API** and **Gmail API**.
2. *APIs & Services → OAuth consent screen* (Google Auth Platform → Branding / Audience / Data access):
   - User type **External**; app name "Isnad", support email, developer contact email.
   - Data access → add scopes: `openid`, `.../auth/userinfo.email`, `.../auth/youtube.upload`,
     `.../auth/drive.file`, `.../auth/gmail.send`. (`youtube.upload` and `gmail.send` are
     *sensitive* scopes: fine unverified in Testing; publishing the app needs Google's verification.)
   - Audience → Publishing status **Testing**, and add every team member's and every tester's Gmail
     address under **Test users** (max 100). Anyone else gets "Access blocked".
   - While in Testing, Google expires refresh tokens after **7 days**: the Connections screen shows
     "expiring", then "expired — Reconnect". That is expected until the app is published.
3. *APIs & Services → Credentials → Create credentials → OAuth client ID*:
   - Application type **Web application**.
   - Authorised redirect URIs (exact match, no trailing slash):
     - local: `http://localhost:8000/connections/google/callback`
     - production: `https://<your-host>/api/connections/google/callback` (the API sits behind `/api`)
   - Authorised JavaScript origins are not needed (the browser never talks to Google's APIs).
   - Copy the client ID and client secret.

**2. `.env`** (and `.env.production` with the production values)

```bash
FAKE_ADAPTERS=false                  # only for real publishing; the connect flow itself works either way
GOOGLE_CLIENT_ID=1234-abc.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-...
GOOGLE_REDIRECT_URI=http://localhost:8000/connections/google/callback
FRONTEND_URL=http://localhost:5173   # where the browser returns: {FRONTEND_URL}/settings/connections
# Generate once per environment and keep it: losing it makes every stored connection unreadable.
CREDENTIALS_ENCRYPTION_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
```

Both the API and the worker read these (the worker needs the client ID/secret to refresh tokens and
the key to decrypt them). To rotate the key: set `CREDENTIALS_ENCRYPTION_KEY=<new>,<old>` — new
first — on both, and later drop the old one once every row has been refreshed or re-encrypted.

**3. Check it:** sign in, open Settings → Connections, press **Connect Google**, choose a test user.
You land back on `/settings/connections?connected=google`; `GET /connections` lists the account with
"YouTube · Drive · Gmail". Errors come back as `?error=google_denied` (Cancel pressed),
`google_state` (link expired, reused or opened in another browser) or `google_failed`.

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
| `UnicodeEncodeError: 'charmap' codec can't encode character '✓'` running a script | Native Windows Python's console defaults to `cp1252`. Run with `python -X utf8 <script>` (or set `PYTHONIOENCODING=utf-8`). |
| Worker container restarts with "Cannot allocate memory" (seen in `docker compose logs worker`) | Known on some memory-constrained Docker Desktop hosts: the `dev` target's `watchfiles` reloader can crash on start. First try raising Docker Desktop's memory limit (Settings → Resources → Advanced). If it still crashes, change the worker service's `build.target` from `dev` to `prod` in `docker-compose.yml` and rebuild (`docker compose up -d --build worker`) — you lose auto-reload on file changes (restart the container manually instead), but the worker no longer runs the reloader. Not reproduced on the W11 test machine; documented per known host issue. |

## 9. Windows notes

Confirmed by the W11 fresh-machine test (`docs/fresh-machine-test.md`) on native Windows + Git Bash
(Docker Desktop, WSL 2 backend) — none of these block `docker compose up`, only the non-Docker paths:

- **`python3` does not exist in Git Bash by default.** It resolves to the Microsoft Store's
  "install Python" stub, which prints a message and exits non-zero instead of running anything.
  Use `python` (or `py -3`) instead — check which one you have with `python --version`.
- **`python`'s console output defaults to `cp1252`, not UTF-8.** Any script that prints `✓`/`✗`
  (e.g. `scripts/smoke_test.py`) raises `UnicodeEncodeError` under plain `python`. Run it as
  `python -X utf8 scripts/smoke_test.py`, or `export PYTHONIOENCODING=utf-8` once per shell.
- **`make` is not installed in Git Bash.** The table in §1 already lists it as optional for this
  reason — every `make <target>` used in this guide has the underlying command spelled out next to
  it (§2–§4), so you never strictly need `make`. To get it anyway: `choco install make`, or run
  inside WSL 2, or use `winget install GnuWin32.Make`.
- **Node installed via nvm-windows (or similar) may not be on Git Bash's `PATH`** even though
  `node --version` works in PowerShell/cmd — the shim directory nvm adds to the Windows `PATH` isn't
  always picked up by Git Bash until you restart the terminal (or reinstall/relink the current
  version). If `node`/`npm` aren't found, this is the first thing to check; it only affects §3 and
  §4's non-Docker commands, not `docker compose up`.
- **Shell scripts stay LF automatically.** `.gitattributes` forces `*.sh` to `eol=lf` on checkout,
  so `scripts/bootstrap.sh` and friends don't need any manual fixing even with
  `core.autocrlf=true` — this was verified, not assumed.
- **Docker commands with Linux-style paths from Git Bash:** if a command embeds a path like
  `/app/...` and Docker complains it can't find it, Git Bash rewrote the path. Prefix the command
  with `MSYS_NO_PATHCONV=1`, e.g. `MSYS_NO_PATHCONV=1 docker compose run --rm api sh -c "..."`.
- **Ports:** if 5433, 6379, 8000 or 5173 are already in use (for example by another checkout of this
  repo, or another project), set `DB_HOST_PORT` / `REDIS_HOST_PORT` in `.env` and, if 8000 or 5173
  themselves collide, edit the `ports:` mapping in `docker-compose.yml` (left side only — the
  frontend's `VITE_API_URL` and the API's `CORS_ORIGINS` assume the defaults).

## 10. Deployment

Full guide, host comparison and troubleshooting: [`docs/deployment.md`](docs/deployment.md). Host:
**recommended, awaiting team decision** — Oracle Cloud Always Free (Ampere A1, $0), fallback a
2 vCPU / 4 GB VPS (~$24/month) for the demo weeks (DECISIONS D-10).

The production stack is [`docker-compose.prod.yml`](docker-compose.prod.yml) on any Linux VM with
Docker: Caddy (HTTPS via Let's Encrypt) → nginx (SPA, `/api` → API) → api / worker / redis, with
Postgres, Auth and Storage on Supabase. There is no local database; migrations run in a one-shot
`migrate` service on every deploy.

1. Create an Ubuntu 24.04 VM (≥ 2 vCPU / 4 GB), optionally with [`deploy/cloud-init.yaml`](deploy/cloud-init.yaml) as user data; open TCP 80 and 443 in the provider's firewall.
2. DNS: an `A` record to the VM's IP — or, with no domain, use `<ip-with-dashes>.sslip.io`.
3. Supabase → Authentication → URL Configuration: Site URL = your `https://` URL, and add `https://<host>/**` to Redirect URLs.
4. On the VM:
   ```bash
   git clone <repo-url> isnad && cd isnad
   cp .env.production.example .env.production && chmod 600 .env.production   # fill it in
   scripts/deploy.sh          # installs Docker if needed, checks the file, builds, migrates, waits for health
   ```
5. Google connections (optional): add `https://<host>/api/connections/google/callback` to the OAuth client's redirect URIs (see *Connect Google* above).
6. Open the URL on a phone on mobile data.

Redeploy after changes: `scripts/deploy.sh` (it `git pull`s first). Logs:
`docker compose -p isnad-prod -f docker-compose.prod.yml logs -f api worker`.

---

**Verified on:** Windows 11 Pro (10.0.26200), Docker Desktop 29.7.2 / Compose v5.5.0, WSL 2 backend — 2026-09-28.
Fresh clone → `docker compose up --build` → `/health/ready` healthy → `scripts/smoke_test.py` (3/3 workflows) in
about 3 minutes end to end (first build, warm image-layer cache; see `docs/fresh-machine-test.md` for the full log
and timings, including a completely cold-cache estimate).
