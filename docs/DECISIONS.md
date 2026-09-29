# Infrastructure decisions

Decisions made while setting up the repository in W1. Each one should also get a row in the Notion **🔑 Decisions Log**; rows marked *Deviates from plan* belong in the M3 report's "Deviations from M2" section.

Project-level decisions still open (D-01 Supabase, host, image provider, product name) are tracked in Notion and in `GP-plan.md` / `DESIGN-SYSTEM.md` §32 — nothing here pre-empts them.

---

## Proposed project decisions

Awaiting team approval. Each is implemented so it can be reviewed working; if it is rejected, the
branch that implemented it is reworked before merge.

### D-09 · How credentials are stored — PROPOSED

**Proposal.** Google OAuth tokens live only in `credentials.encrypted_payload`, encrypted with
**Fernet** (AES-128-CBC + HMAC-SHA256, from `cryptography`) under a key from the environment,
`CREDENTIALS_ENCRYPTION_KEY`. Several comma-separated keys are accepted (MultiFernet): the first
encrypts, all decrypt — that is the rotation path. A workflow step holds only the connection's id
(`credential_id`, a UUID — `contracts.run.CREDENTIAL_CONFIG_KEY`), never a token.

- **Where the code lives.** `db/crypto.py`. The `db` component owns the table and so the format of
  its one secret column; the api (writes on connect) and the worker (re-writes on refresh) both
  already depend on `db` and may not import each other. `db` stays a leaf (`cryptography` is external).
- **Schema (migration `0003`).** Adds `account_email`, `scopes` (JSON list of granted scopes),
  `invalid_at` (Google said `invalid_grant`) and `updated_at`; one row per (user, provider, account).
  Reconnecting the same Google account updates the row in place, so workflows that point at it keep
  working. `expires_at` is when the *connection* ends (Google's `refresh_token_expires_in`, 7 days
  for an app in Testing; empty otherwise) — the hourly access-token expiry is inside the payload.
- **Connect (api, `/connections`).** `POST /connections/google/start` returns Google's consent URL
  (`access_type=offline`, `prompt=consent`; scopes `openid`, `userinfo.email`, `youtube.upload`,
  `drive.file`, `gmail.send`). `state` is a 10-minute HS256 JWT naming the user and a nonce; the
  nonce is also set as an HttpOnly SameSite=Lax cookie, and the callback requires both to match,
  so a consent link sent to someone else can't connect *their* Google account to *your* Isnad
  account. The callback exchanges the code, reads the account email from the ID token, encrypts,
  stores, and returns to `{FRONTEND_URL}/settings/connections?connected=google` (or, with
  `?mode=popup`, a page that `postMessage`s the opener and closes). `GET /connections` lists
  id, account, scopes in plain words, status (connected / expiring < 7 days / expired), expiry
  and how many workflows use it — never a token. `DELETE /connections/{id}` revokes at Google
  (best effort) and deletes. Someone else's id is 404.
- **Use (worker).** In real mode, just before a node runs, `worker.credentials` checks the id belongs
  to the workflow's owner, decrypts, refreshes the access token if it expires within 5 minutes,
  writes the refreshed token back encrypted, and swaps Google adapters into that node's `Ports`.
  The agent never sees where the token came from. `invalid_grant` marks the row `invalid_at` and
  fails the step without retrying: "Your Google connection has expired or was removed. Reconnect
  Google, then run again." With `FAKE_ADAPTERS=true` none of this runs.
- **Guard rails.** Saving a workflow whose step settings contain a Google token, a client secret or
  a key named like one (`refresh_token`, `password`, …), or a `credential_id` that isn't a UUID, is
  refused with 422. `/validate` reports `missing_credential` / `expired_credential` on every
  `x-widget: credential` field — errors with real adapters, warnings with fakes.

**Why.** The graph JSON is copied into every run snapshot, returned to the browser and exported, so
Invariant 4 can only hold if the graph carries a reference. Fernet is authenticated, needs no
infrastructure, and one env var is the same operational cost as `JWT_SECRET`; Supabase Vault or a
KMS would tie credentials to one host before the host is chosen. Tokens are per person, not a server
key, because FR-05 publishes to *the user's* channel and Drive.

**Rejected alternatives.** Supabase Vault / pgsodium (Supabase-only; local Docker and CI would need
a second code path). Storing tokens in the graph or in `agent_nodes.configuration` (violates
Invariant 4). One server-wide Google account in env (every user would publish to the team's
channel).

**Consequences.** Losing `CREDENTIALS_ENCRYPTION_KEY` makes every stored connection unreadable
(people reconnect; nothing else is lost). The key must be set identically on api and worker.
While the Google app is in Testing, connections last 7 days. Email's config gains a
`credential_id` field (C0 change, needs the two-approval review). The start call must be made with
`fetch(..., {credentials: "include"})` so the browser keeps the binding cookie.

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

### INF-12 · Row Level Security: the backend bypasses it, policies are defence in depth

**Decision.** Migration `0002` enables RLS on all eight tables and on `alembic_version`. On Supabase (detected by `auth.uid()` and the `authenticated` role existing) it also adds per-user policies for `authenticated`, keyed on `auth.uid()`: own `users` row (read, update); own `workflows` and their `agent_nodes` (full CRUD); runs, logs, outputs and approvals of own workflows (read only — they are created by the API and worker, and an approval must go through the API to resume the run). `credentials` gets no policy at all, and `anon` gets none anywhere. The migration also revokes `EXECUTE` on the hand-made `public.rls_auto_enable()` from `PUBLIC`, `anon` and `authenticated`.

**Why.** The API and worker connect as `postgres`, which owns the tables, so RLS never filters their queries (no `FORCE ROW LEVEL SECURITY`); they keep their own ownership checks (`api.deps.owned`). The policies protect everything that reaches Supabase with a user's JWT instead — PostgREST with the anon key that ships in the frontend, and Realtime subscriptions for run progress. `credentials` holds encrypted OAuth tokens that only the backend reads or writes, so deny-all is the smallest surface. The policy and revoke steps are guarded so the same migration runs on local Docker and CI, which have neither `auth` nor `authenticated`.

**Consequence.** Downgrading `0002` drops the policies everywhere but disables RLS only where `auth.uid()` does not exist; on Supabase RLS stays on (it was enabled by hand before this migration, and turning it off would expose every table to the anon key). `db/tests/test_rls.py` checks both paths against a real PostgreSQL, faking `auth.uid()` for the Supabase one; it runs in CI's `db-migrations` job and skips when `RLS_TEST_DATABASE_URL` is unset.

### D-10 · Production host — RECOMMENDED, awaiting team decision

**Recommendation.** One Oracle Cloud Always Free Ampere A1 VM (2 OCPU / 12 GB, ARM, $0/month),
home region Mumbai (`ap-mumbai-1`, next to the Supabase project) or Jeddah/Riyadh. Fallback: a
2 vCPU / 4 GB x86 VPS (DigitalOcean or Lightsail, $24/month; Hetzner CX33 ~€9 if in stock) for the
demo weeks only. Comparison, prices (checked 2026-09-29) and sources: `docs/deployment.md` §1.

**Why.** Supabase already hosts Postgres, Auth and Storage, so the host only needs one always-on
machine for Docker Compose, big enough for the 2 CPU / 4 GiB video worker. Free PaaS tiers don't run
a long-running Celery worker (Render) or cap services far below 4 GB (Railway free, Azure's free
B-series); Fly.io has no free allowance. A plain VM keeps `docker-compose.prod.yml` unchanged, so
switching between the primary and the fallback is "run `scripts/deploy.sh` on the other VM".

**Risks.** Oracle halved the A1 allowance on 2026-06-15, may reclaim idle instances, and often has
no A1 capacity in busy regions — hence starting in October and keeping the fallback ready.

### INF-13 · Caddy terminates HTTPS in front of the existing nginx

**Decision.** `docker-compose.prod.yml` adds a `caddy` service as the only published container
(80/443). It obtains and renews a Let's Encrypt certificate for `DOMAIN` automatically and proxies
everything to `web` (nginx), which keeps serving the SPA and proxying `/api/*` to the API exactly as
before. With no domain, `DOMAIN` can be `<ip-with-dashes>.sslip.io` (still HTTPS) or `http://<ip>`
(plain HTTP, smoke tests only). `FRONTEND_URL`, `CORS_ORIGINS` and `GOOGLE_REDIRECT_URI` default
from one `PUBLIC_URL`.

**Why.** Caddy needs no certbot container, cron job or certificate volume juggling — a four-line
Caddyfile and one env var — and it is host-agnostic (works the same on Oracle, a VPS, or a KFU VM).
Keeping nginx behind it means the `/api` routing the frontend was built against (`VITE_API_URL=/api`)
is unchanged. Rejected: certbot + nginx (more moving parts, renewal cron), a managed load balancer
(provider-specific, often paid), Cloudflare Tunnel (needs a domain on Cloudflare and an account).

**Also changed for production.** nginx resolves `api` per request through Docker's DNS, so a
redeploy that recreates `api` doesn't leave it pointing at a stale IP (502s), and forwards the
browser's scheme from Caddy. The frontend image takes `VITE_AUTH_MODE` / `VITE_SUPABASE_*` as build
args (production builds use Supabase Auth, since dev sign-in is off when `ENVIRONMENT=production`).
The `artifacts` volume is gone from the production stack: the API never serves `/files` in
production, so `STORAGE_BACKEND=supabase` is the only working option there.
