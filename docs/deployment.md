# Deployment (C7 · W11)

**Done when:** the app opens from a phone on mobile data at an `https://` URL.

This page has three parts: [where to host](#1-where-to-host), [how to deploy](#2-how-to-deploy) and
[what has been verified](#3-what-has-been-verified). The short version of the steps is in
[SETUP.md §10](../SETUP.md#10-deployment).

---

## 1. Where to host

Status: **recommended, awaiting team decision** (see `docs/DECISIONS.md` D-10).

### What the host has to run

Supabase already provides Postgres, Auth and Storage, so the host only runs the stateless part:

| Service | Needs |
|---|---|
| `caddy` | ports 80 + 443 open to the internet, a persistent volume for certificates |
| `web` (nginx + built SPA) | ~20 MB RAM |
| `api` (FastAPI, 2 uvicorn workers) | ~200–300 MB RAM |
| `worker` (Celery + FFmpeg, concurrency 2) | **2 CPU / 4 GiB limit** — measured peak 2.2 GiB for two parallel 1080p renders (`docs/metrics/video-worker.md`) |
| `redis` | ~50 MB, long-running, persistent |

So: **one always-on Linux machine with ≥ 2 vCPU and ≥ 4 GB RAM running Docker Compose**
(4 GB is tight with everything else on it — plan for 4 GB + swap, or 8 GB+). A long-running
Celery worker and a Redis instance are the two things that rule out most "free" PaaS tiers.

### Options compared

Prices checked on **2026-09-29** from the linked pages; anything not confirmed on a primary source
is marked *(unverified)*.

| Option | Spec for this stack | Cost | Runs worker + Redis? | Sleeps? | Notes |
|---|---|---|---|---|---|
| **Oracle Cloud Always Free, Ampere A1 (ARM)** | 2 OCPU / 12 GB, up to 200 GB disk | **$0** | Yes (it's a VM) | No, but *idle reclamation* | Limit was halved from 4 OCPU/24 GB on 2026-06-15 [1][2]. Idle instances (CPU p95, network and memory all < 20 % over 7 days) may be reclaimed [1]. "Out of host capacity" when creating A1 VMs is common in busy regions [3]. Home region is chosen at sign-up and Always Free resources live only there. Needs a card for identity verification *(unverified for 2026)*. ARM64 — every image in this stack is multi-arch. |
| Hetzner Cloud CX33 (x86) / CAX21 (ARM) | 4 vCPU / 8 GB | €8.49 / €10.49 per month + €0.50 IPv4 (from 2026-06-15) [4] | Yes | No | Best value *if you can buy it*: every shared-vCPU (CX/CAX) plan was marked "not available" from 2026-09-07; cheapest orderable was reported as CPX12 at €11.99 [5] *(secondary source)*. EU/US/Singapore only — far from Saudi Arabia. Hourly billing. |
| DigitalOcean Basic droplet | 2 vCPU / 4 GB / 80 GB | $24/month [6][7] | Yes | No | Simple, hourly billing. The GitHub Student Pack $200 credit **ended 2026-07-31**, credits expired 2026-08-01 [8]. |
| AWS Lightsail | 2 vCPU / 4 GB / 80 GB, IPv4 included | $24/month [9] | Yes | No | Has a Bahrain region (me-south-1) *(unverified for Lightsail)*. Free-tier months exist for small bundles only [9]. |
| Azure for Students | B2ats v2 / B2pts v2 (2 vCPU / 1 GB) free 750 h/month; $100 credit / 12 months, no card [10] | $0 → ~$30+/month for a 4 GB B-series *(unverified)* | Yes | No | The free VM sizes have 1 GB RAM — too small for the worker. The $100 credit would cover a 4 GB VM for ~3 months. |
| Render | Worker needs "Pro" 2 CPU / 4 GB *(unverified: Starter $7 = 512 MB/0.5 CPU, Standard $25 = 2 GB/1 CPU)* [11] | $0 only for web services; background workers are **not** free [12] | Worker: paid only. Key Value (Redis): free tier exists [12] | Free web services spin down after 15 min idle, ~1 min cold start [12] | Would need 4 separate services (web, api, worker, Redis) and no Compose file. |
| Railway | Usage-based: ~$20 per vCPU-month, ~$10 per GB-month [13] | Hobby $5/month incl. $5 usage; Free plan $1/month credit, 0.5 GB per service [13] | Yes | No | An idle worker is cheap, but a 4 GB-capped worker plus api/web/Redis will exceed $5 during rendering — expect $10–20/month *(estimate)*. No Compose support; each service configured separately. |
| Fly.io | shared-cpu-2x with 4 GB ≈ $13/month; performance-2x ≈ $62 [14] | No free allowance for new orgs; card required [14] | Yes (Machines) | Optional auto-stop | Dedicated IPv4 $2/month. Needs `fly.toml` per app, Redis via Upstash or a self-run Machine. |
| KFU hosting | — | — | — | — | *Unknown.* Nothing public found. Worth one email to the department / Deanship of IT asking for a VM with a public IP; if they offer one, the same `scripts/deploy.sh` works on it. |
| GitHub Student Pack | Azure $100, Heroku $13/month × 24 months [15] | — | Heroku: yes, but as separate dynos, 512 MB each on Eco/Basic *(unverified)* | Eco dynos sleep *(unverified)* | Also: free domains for a year (Namecheap `.me`, name.com, `.tech`) [15] — useful for a real domain name. |

### Recommendation

**Primary — Oracle Cloud Always Free, one Ampere A1 VM (2 OCPU / 12 GB, Ubuntu 24.04 ARM), $0/month.**
It is the only option that meets the 2 CPU / 4 GiB worker sizing *and* costs nothing, it keeps
the Compose stack unchanged (`scripts/deploy.sh` runs as-is), and it doesn't sleep. Pick the home
region carefully because it cannot be changed: **Mumbai (`ap-mumbai-1`)** puts the VM next to the
Supabase project (ap-south-1 = Mumbai), which matters more than user latency because every API
request makes several database round trips; Jeddah (`me-jeddah-1`) or Riyadh (`me-riyadh-1`) are
fine second choices [16].

Risks and how to handle them:

- *Capacity* — if "Out of host capacity" persists, try another availability domain or retry over a
  few days; start **now** (October), not in December.
- *Idle reclamation* — a demo box sits idle most of the week. Upgrading the tenancy to
  Pay-As-You-Go (still $0 while inside the Always Free limits) is widely reported to exempt it
  *(unverified — confirm in the console when upgrading)*. Set a $1 budget alert if you do.
- *Oracle changed the limits once already (June 2026).* Keep the fallback ready.

**Fallback — a 2 vCPU / 4 GB x86 VPS for the demo weeks only:** DigitalOcean Basic or AWS
Lightsail at **$24/month**, or Hetzner CX33 (**~€9/month**, 4 vCPU / 8 GB) if it is back in stock.
All bill hourly: running Nov 15 → Dec 15 costs ~$24. Same `deploy.sh`, same `.env.production`,
same DNS steps — only the IP changes.

Both options leave Postgres, Auth and Storage on Supabase, so moving between hosts is just
"run `deploy.sh` on the new VM, point DNS at it".

**Domain.** HTTPS needs a hostname. Without buying one, use `<ip-with-dashes>.sslip.io` (e.g.
`203-0-113-10.sslip.io`): it resolves to the IP inside the name and works with Let's Encrypt
HTTP-01 certificates [17]. A free `.me`/`.tech` domain from the Student Pack [15] looks better in a
demo; DuckDNS is another free option.

### Sources (all accessed 2026-09-29)

1. Oracle, *Always Free Resources* — https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm
2. InfoQ, *Oracle Quietly Halves Free Tier Ampere A1 Compute Limits* (July 2026) — https://www.infoq.com/news/2026/07/oracle-cloud-free-tier-limits/
3. hitrov/oci-arm-host-capacity (community tool for the "Out of host capacity" error) — https://github.com/hitrov/oci-arm-host-capacity
4. Hetzner, *Price Adjustment 15 June 2026* — https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/
5. Vincent Schmalbach, *Hetzner's cheap cloud tier is unavailable* / StackValueLab, *Hetzner CX and CAX unavailable* — https://www.vincentschmalbach.com/hetzner-cheap-cloud-unavailable-price-increases/ , https://stackvaluelab.com/hetzner-cx-cax-unavailable/
6. DigitalOcean, *Droplet Pricing* — https://www.digitalocean.com/pricing/droplets
7. DigitalOcean docs, *Droplet pricing* — https://docs.digitalocean.com/products/droplets/details/pricing/
8. GitHub Community, *DigitalOcean leaving the Student Developer Pack* — https://github.com/orgs/community/discussions/201240
9. AWS, *Lightsail pricing* — https://aws.amazon.com/lightsail/pricing/
10. Microsoft, *Azure for Students* — https://azure.microsoft.com/en-us/free/students
11. Render pricing summaries (secondary) — https://northflank.com/blog/railway-vs-render , https://render.com/pricing
12. Render, *Deploy for Free* — https://render.com/docs/free
13. Railway, *Pricing* — https://railway.com/pricing
14. Fly.io, *Pricing* — https://docs.fly.io/about/pricing/
15. GitHub Student Developer Pack — https://education.github.com/pack
16. Oracle, *Regions and Availability Domains* — https://docs.oracle.com/en-us/iaas/Content/General/Concepts/regions.htm
17. nip.io / sslip.io — https://nip.io/

---

## 2. How to deploy

### The production stack

```
phone ──https──▶ caddy :80/:443 ──▶ web (nginx) ──┬─ /           built SPA (VITE_API_URL=/api)
                 Let's Encrypt                    └─ /api/* ──▶ api :8000   (prefix stripped)
                                                                 │
                                   redis ◀──────────────────────┤
                                     ▲                           ▼
                                   worker (2 CPU / 4 GiB) ──▶ Supabase: Postgres · Auth · Storage
migrate (one-shot, every deploy): alembic upgrade head [+ seed]  ──▶ Supabase Postgres
```

Files: [`docker-compose.prod.yml`](../docker-compose.prod.yml),
[`deploy/Caddyfile`](../deploy/Caddyfile), [`deploy/cloud-init.yaml`](../deploy/cloud-init.yaml),
[`scripts/deploy.sh`](../scripts/deploy.sh), [`.env.production.example`](../.env.production.example).

Because `/api` is on the same origin as the SPA, the browser never makes a cross-origin call;
`CORS_ORIGINS`, `FRONTEND_URL` and `GOOGLE_REDIRECT_URI` are still derived from `PUBLIC_URL` so
they are right by default. `ENVIRONMENT=production` is forced, which turns dev sign-in off — so the
frontend is built with `VITE_AUTH_MODE=supabase` (real Supabase Auth accounts).

### Step by step (first deploy)

**1. Create the VM.** Ubuntu 24.04, ≥ 2 vCPU / 4 GB RAM (see §1), a public IPv4, your SSH key.
Paste `deploy/cloud-init.yaml` into the "user data" / "initialization script" field (optional —
`deploy.sh` also installs Docker and opens the OS firewall; cloud-init adds swap).

- *Oracle (primary):* Compute → Instances → Create → Image **Canonical Ubuntu 24.04** (the
  aarch64 build is picked automatically) → Shape **Ampere · VM.Standard.A1.Flex, 2 OCPU, 12 GB** →
  the default VCN with "Assign a public IPv4 address" → upload your SSH public key → Show advanced
  options → Management → paste the cloud-init. Then **Networking → Virtual cloud networks → your VCN
  → Security Lists → Default → Add Ingress Rules**: source `0.0.0.0/0`, TCP, destination port `80`;
  again for `443`; and UDP `443` (HTTP/3, optional). SSH user is `ubuntu`.
- *DigitalOcean / Lightsail / Hetzner (fallback):* same image, 2 vCPU / 4 GB (or more), same
  cloud-init; open 80 and 443 in the provider firewall (Lightsail: Networking → IPv4 firewall; DO
  and Hetzner have no firewall unless you add one).

**2. Pick the hostname** and set `DOMAIN` / `PUBLIC_URL` accordingly:

| You have | DNS | `DOMAIN` | `PUBLIC_URL` |
|---|---|---|---|
| A domain | `A` record `isnad.example.com → <VM IP>` (TTL 300) | `isnad.example.com` | `https://isnad.example.com` |
| No domain | nothing — sslip.io answers for you | `203-0-113-10.sslip.io` | `https://203-0-113-10.sslip.io` |
| Only an IP, just to smoke-test | nothing | `http://203.0.113.10` | `http://203.0.113.10` |

The third row has no HTTPS: Google connections won't work (Google requires an `https://` redirect
URI) and some phone browsers warn. Use it only to check the stack before DNS is ready.

**3. Supabase dashboard** (project `isnad`) — once, and again whenever the URL changes:

- *Authentication → URL Configuration*: **Site URL** = `PUBLIC_URL` (confirmation emails link here);
  **Redirect URLs** → add `PUBLIC_URL/**`. Keep `http://localhost:5173/**` for development.
- *Connect → Session pooler*: copy the URI (port **5432**) into `DATABASE_URL`. The direct
  `db.<ref>.supabase.co` host is IPv6-only on the free plan, and the transaction pooler (6543)
  breaks Alembic and long worker sessions (`db/src/db/session.py`).
- *Storage*: a **private** bucket named `artifacts` (or `STORAGE_BUCKET`) must exist.
- *Project Settings → API keys*: `service_role` → `SUPABASE_SERVICE_KEY`; `anon` → `SUPABASE_ANON_KEY`.
- Free Supabase projects are **paused after about a week of inactivity** *(check the current rule
  on the dashboard)* — open the site at least weekly in the run-up to the demo, and check the
  project is active the day before.

**4. On the VM:**

```bash
git clone https://github.com/<org>/isnad.git && cd isnad    # private repo: use a deploy key or a PAT
cp .env.production.example .env.production && chmod 600 .env.production
nano .env.production        # fill in; comments say which are secrets
scripts/deploy.sh --check-only   # validates the file without starting anything
scripts/deploy.sh                # ~10–15 min the first time (builds 3 images on the VM)
```

`deploy.sh` ends with `Live at https://…` once `/api/health/ready` answers through Caddy with the
database reachable and the worker's agent catalog published. Migrations ran in the `migrate` service
before `api`/`worker` started (`docker compose -p isnad-prod -f docker-compose.prod.yml logs migrate`).

**5. Google connections (optional).** In Google Cloud Console → Credentials → the OAuth client →
add the redirect URI `PUBLIC_URL/api/connections/google/callback` exactly (SETUP.md "Connect
Google"). If Google asks for the domain under *Branding → Authorised domains*, add it; if it
refuses an `sslip.io` name, use a real domain. Put `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` and a
**new** `CREDENTIALS_ENCRYPTION_KEY` in `.env.production`, then `scripts/deploy.sh` again.

**6. The W11 check.** On a phone with Wi-Fi **off**: open `PUBLIC_URL`, register, confirm the email,
sign in, run a template workflow, open its output. Screenshot it for the report.

### Day-to-day

| Task | Command (on the VM, in the repo) |
|---|---|
| Deploy the latest `main` | `scripts/deploy.sh` |
| Deploy the working tree as is | `scripts/deploy.sh --no-pull` |
| Logs | `docker compose -p isnad-prod -f docker-compose.prod.yml logs -f api worker` |
| Status | `docker compose -p isnad-prod -f docker-compose.prod.yml ps` |
| Restart one service | `docker compose -p isnad-prod -f docker-compose.prod.yml --env-file .env.production restart worker` |
| Roll back | `git checkout <good-sha> && scripts/deploy.sh --no-pull` (migrations are not downgraded automatically) |
| Stop everything | `docker compose -p isnad-prod -f docker-compose.prod.yml down` (keep `-v` off: it deletes the certificates) |
| Free disk | `docker system prune -f` (deploy.sh already prunes dangling images) |

Switching hosts: run steps 1, 2 and 4 on the new VM, point DNS at it, update Supabase URL
configuration and the Google redirect URI if the hostname changed.

### Troubleshooting

- **`deploy.sh` times out, caddy log shows ACME/`challenge` errors** — port 80 or 443 is closed
  (provider firewall / Oracle security list) or DNS doesn't point at the VM yet. Test from
  outside: `curl -I http://<DOMAIN>`. After too many failures Let's Encrypt rate-limits the name
  for an hour; Caddy retries on its own.
- **`migrate` failed** — `docker compose … logs migrate`. `connection refused` / `Network is
  unreachable` usually means the direct (IPv6) DB host; use the session pooler URI.
- **502 from `/api`** — `api` is restarting; `logs api`. An empty `FAKE_ADAPTERS=` or other empty
  boolean in `.env.production` stops it at startup.
- **Sign-in fails on the deployed site** — the frontend was built with the wrong Supabase URL/key
  (they're baked in at build time: fix `.env.production`, run `deploy.sh` again), or the Site URL /
  Redirect URLs in Supabase don't include `PUBLIC_URL`.
- **Worker killed (OOM)** — `docker stats`; on a 4 GB VM make sure swap exists (`swapon --show`).

---

## 3. What has been verified

Locally on 2026-09-29 — Windows 11, Docker Desktop 29.7.2 / Compose v5.5.0 (x86_64) — with the real
`docker-compose.prod.yml`, `deploy/Caddyfile` and `scripts/deploy.sh`, plus a throwaway override
file adding a local `postgres:15` in place of Supabase (project `isnad-prodtest`, ports 18080/18443):

| Check | Result |
|---|---|
| `docker compose -f docker-compose.prod.yml config` with the example env filled in | valid; `CORS_ORIGINS`, `FRONTEND_URL`, `GOOGLE_REDIRECT_URI` derived from `PUBLIC_URL` as intended |
| `scripts/deploy.sh --no-pull` end to end (`DOMAIN=http://localhost`, `FAKE_ADAPTERS=true`, `STORAGE_BACKEND=local`, `SEED_DEMO_DATA=true`) | builds the 3 production images, `migrate` applies migrations to head (`0004`) and seeds, all services healthy (incl. the worker's `celery inspect ping` check), exits with "Live at …" |
| `GET /` through Caddy | 200, the built SPA; client-side routes (e.g. `/workflows`) fall back to `index.html`; `/assets/*.js` served |
| `GET /api/health/ready` through Caddy → nginx → api | `{"database":"ok","worker_catalog":"6 agents"}` |
| Mock workflow runs through Caddy | all 3 seeded templates **succeeded** (2 approval gates approved): Blog post; Blog → Video → YouTube (in the prod worker image, fake adapters); Research → PDF → Email |
| `POST /api/auth/dev-login` | 404 — dev sign-in is off in production |
| Frontend bundle | built with `VITE_AUTH_MODE=supabase` and the Supabase URL from the env file |
| `api` recreated on a **different IP** without restarting `web` | `/api` kept working (nginx re-resolves through Docker DNS) |
| HTTPS path: `DOMAIN=localhost` (Caddy's internal CA instead of Let's Encrypt) | `https://…/` 200, `/api/health/ready` ok, `http://` → **308** redirect to `https://`, `Alt-Svc: h3` advertised |
| `deploy.sh --check-only` with a deliberately broken env file | catches empty `FAKE_ADAPTERS`, short `JWT_SECRET`, trailing slash / mismatched `PUBLIC_URL`, transaction pooler port 6543, missing service key, half-configured Google |
| ARM64 (Oracle A1) readiness | all 87 pinned Python dependencies in `constraints.txt` have `linux/aarch64` wheels (checked with `pip download --platform manylinux…_aarch64`); `package-lock.json` has the arm64 rollup/esbuild binaries; every base image (`python:3.11-slim`, `node:20-alpine`, `nginx:1.27-alpine`, `redis:7-alpine`, `caddy:2-alpine`) is multi-arch |
| `scripts/deploy.sh` | `shellcheck` clean, `bash -n` ok |
| Memory at idle | api ~180 MiB, worker ~160 MiB, web/caddy ~15 MiB each, redis ~5 MiB |

**Not verified** (needs the real server / accounts):

- A real Let's Encrypt certificate (needs a public IP with 80/443 reachable and DNS) — only Caddy's
  internal-CA HTTPS was exercised.
- Supabase: the session-pooler connection, migrations against the Supabase database, Supabase Auth
  sign-in from the built frontend, Storage uploads and signed downloads (`STORAGE_BACKEND=supabase`).
  Locally, files were written to the worker container's disk.
- The ARM64 images actually being built and run (only dependency availability was checked), and
  the first-build time on a 2-OCPU VM.
- `deploy.sh` steps 1–2 on a fresh Ubuntu VM (Docker install via get.docker.com, ufw / Oracle
  iptables rules) and `deploy/cloud-init.yaml` — they only ran on Windows, where they are skipped.
- Google OAuth against the production redirect URI; real adapters (`FAKE_ADAPTERS=false`).
- The W11 "done when": opening the URL from a phone on mobile data.
