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

<!-- filled in below -->

---

## 3. What has been verified

<!-- filled in below -->
