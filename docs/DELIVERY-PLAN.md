# Isnad — delivery plan and working agreement

**Status:** for review · 20 Sep 2026 · covers the work from here to submission on 5 December 2026
**Read with:** [GP-plan.md](GP-plan.md) (requirements, weekly plan, acceptance tests) ·
[FRONTEND-PAGES-PLAN.md](FRONTEND-PAGES-PLAN.md) (the twelve pages) ·
[UX-SPEC.md](UX-SPEC.md) (how the product teaches) · [DESIGN-SYSTEM.md](DESIGN-SYSTEM.md) (how it looks) ·
[DECISIONS.md](DECISIONS.md) (what is still undecided)

This is the plan two agents work from: a **build agent** that implements one part at a time, and a
**review agent** that checks the result before a human merges it. It says what to build, in what
order, what "finished" means, and the rules neither agent may break.

Nothing in this document is started until Hassan has approved the plan.

---

## 1. Who does what

| | Build agent | Review agent |
|---|---|---|
| **Takes** | The next unstarted part in §5 | An open pull request |
| **Does** | Designs (if the part is user-visible), implements, verifies, opens the PR | Reads the diff against §7, runs the checks itself, reports findings |
| **Never** | Starts a second part, merges anything, pushes to `main` | Pushes fixes, merges, or approves work it did not verify |
| **Ends with** | A PR with the template filled in and evidence, then stops and reports | An approval or a list of findings, each with file, line and why |

**A human merges.** Both agents stop at the boundary of one part. The build agent does not begin
the next part until its PR is merged, because every part is built on the one before it.

**Design before building.** For anything a person looks at, the build agent shows a short written
spec and something clickable *before* writing product code. The canvas was rejected once for being
built before it was designed. [UX-SPEC.md](UX-SPEC.md) and the approved prototype are the design for
everything in Parts 0–4; a part that goes beyond them needs its own design step first.

---

## 2. Rules that are never broken

These are the ones that cost the most to get wrong. The review agent checks every one on every PR.

1. **No per-agent code in the frontend (AT-12).** Every form, label, summary, handover and
   destination is read from `/agents/catalog`. A seventh agent must appear with a working form and
   **zero files changed under `frontend/`**. Agent names may appear only in tests and in the test
   catalog fixture.
2. **The form never writes a default, and a cleared field is removed.** `setValue` in
   `frontend/src/lib/schema.ts` is the only write path into a step's `configuration`. The
   orchestrator lays `configuration` over what earlier steps produced, so a stored empty value
   silently overwrites real work — opening a drawer to look would break the chain behind it.
3. **The server owns validation wording.** `/validate` messages are rendered exactly as they
   arrive. If a message reads badly, fix it in the API, never in the frontend.
4. **`main` is protected.** No direct pushes. A pull request, a green `CI passed`, and a branch up
   to date with `main`. Force-push and deletion are blocked.
5. **Component boundaries hold.** Work only inside the component the part is about. `import-linter`
   and CODEOWNERS enforce this. `db/` belongs to Mohammed, `agents/`, `adapters/` and `exporters/`
   to Zain; a fix that seems to need their files is a conversation, not a commit.
6. **This repository is public.** No secrets, tokens, `.env` contents or customer-shaped data in
   commits, tests, fixtures or PR descriptions.
7. **A rejection is not a failure.** A step the user rejected reads "Rejected by you" and never
   shares the failure's red styling or wording.

---

## 3. Where things stand (20 Sep 2026)

**In `main`:** foundation, sign-in and register, workflow list, the canvas (build experience: the
teaching node, handover connections, schema-driven settings drawer, the chain-building palette),
the agent handover data in `contracts`, the UX spec, CI, and Mohammed's async DB session.

**Not in `main` yet — this is Part 0.** Run mode (#20) was merged into `frontend/canvas-teaching`
rather than into `main`, and `main` was taken from the commit before that merge. The work is
complete and green; it needs its own PR into `main`.

**Untouched so far:** Outputs, Connections, Logs, Run history, templates for new users, and the two
API endpoints those depend on.

---

## 4. The stack, for verification

```bash
docker compose up -d db redis migrate api worker   # API :8000, Postgres :5433, Redis :6379
cd frontend && npm run dev                          # :5173 — the only origin the API's CORS allows
```

Sign in as `demo@gp.local` (dev sign-in: any email, no password). Agents run in mock mode, so a
whole chain finishes in milliseconds.

Checks, all of which CI also runs:

```bash
make lint          # ruff, import boundaries, agent shape, frontend eslint + typecheck
make test          # every component's own suite, then frontend unit tests
cd frontend && npx playwright test   # end-to-end against a mocked API
```

---

## 5. The parts, in order

One pull request per part. Each lists what "done" means; the review agent checks exactly that.

### Part 0 — Land run mode in `main`

Open a PR into `main` from a branch holding the two run-mode commits. No new code.

**Done when:** `main` contains `lib/runPlayback.ts`, `RunBar`, `ApprovalDialog`, `useCanvasRun`,
and the run-mode Playwright tests pass on `main`.

### Part 1 — Validation panel · frontend

The last missing piece of the canvas (DESIGN-SYSTEM §15.5).

- A panel listing every problem `/validate` reports, in the server's words.
- **Go to step** selects the step and opens its settings.
- The issue count in the status bar opens the panel.

**Done when:** a workflow with a loop, an orphan step and a missing setting shows three messages,
each one navigates to the right step, and no message has been reworded by the frontend.

### Part 2 — Run monitor page (P-06) and the AT-12 test · frontend

`/runs/:id` is still a skeleton. Run mode lives on the canvas, but a deep link, a notification, or
returning the next day all need a real page.

- The run bar, step states and handovers, read-only, reusing the canvas components.
- **A steps list** — the accessible equivalent of the diagram. The whole run must be usable without
  seeing the graph.
- **The AT-12 test, automated:** register a throwaway seventh agent, restart the worker, assert it
  appears with a working form and that `git status` shows no change under `frontend/`.
- **Pay off the AT-12 debt in `design-system/agents/agentMeta.ts`**, found while writing this plan:
  `ICONS` hard-codes the six agents *and is consulted before the manifest's own icon*, so an agent
  that changes its icon is ignored by the frontend; and `agentFamily` falls back to naming
  `publisher` and `email`. Let the manifest win, and drop the name-based fallback.

**Done when:** AT-07 and AT-12 pass, and the run is navigable by keyboard alone.

### Part 3 — `GET /runs/{run_id}/outputs` · api + worker

Small, and it unblocks the headline feature.

- Lists what a run produced: step, agent, kind, filename, size, created time, and the id that
  `GET /outputs/{id}` turns into a signed URL.
- The worker already records outputs; this exposes them.
- Same PR: the runs list cannot say **why** a run ended, so a rejected run shows as "Failed" in the
  workflow list. Add the reason to the run summary.
- `make openapi` and commit the regenerated types.

**Done when:** a finished chain returns its article, image and video, and a rejected run is
distinguishable from a failed one without opening it.

### Part 4 — Outputs page (P-09) and the real approval preview · frontend

Needs Part 3 and Mohammed's storage work.

- Files per run, downloads through signed URLs, published links.
- The approval window shows the real article, image and video instead of "preview isn't available
  yet".
- The drawer's **Last output** tab starts working.

**Done when:** AT-04 passes, and AT-09 passes with a real preview of the file that is about to go
out.

### Part 5 — `GET /workflows/templates` and templates on the list · api + frontend

Templates are the only onboarding this product has, and a new account currently opens to nothing.

- Mark the seeded workflows as templates; serve them to any signed-in user.
- The empty state offers **Use a template**; picking one copies it and opens it, already configured
  and runnable.

**Done when:** a brand-new account can run something in two clicks.

### Part 6 — Connections (P-10) and the credential picker · api + frontend

Needs D-09 decided and Google OAuth in place.

- Connect and disconnect a Google account. A token is never rendered, never logged, never stored in
  the graph.
- Publisher's **Connect Google** stops being disabled; the credential field becomes a real picker
  holding a reference.

**Done when:** AT-05 can run for real — a video on the test channel, a file in Drive.

### Part 7 — Logs (P-08) and retry narration · frontend

- Per-attempt table: timestamps, status, retry count, duration, error message; filters; CSV export.
- Retry strips on steps, from what the worker already records.

**Done when:** AT-10 passes and AT-06's three retries are visible end to end.

### Part 8 — Run history (P-05) · frontend

The only page with no specification. **It needs a short spec approved before it is built** — a list
of runs per workflow with status, duration and a link into the monitor is the suggested scope.

### Part 9 — Accessibility, responsive and theme · frontend

- Keyboard-only pass over every screen; screen-reader labels; reduced motion honoured.
- Responsive behaviour per DESIGN-SYSTEM §22.
- Lighthouse ≥ 95.
- D-05: sign off shipping the dark theme, which is built and working.

### Part 10 — Test sweep

- Visual regression over the design-system page.
- Playwright through all three seeded workflows end to end.
- A full acceptance-test run, recorded for the report.

### Part 11 — Usability and the report

- **US-01**: someone non-technical produces a blog post and emails it to themselves, unaided.
  Record time-on-task, completion and SUS.
- Fix only critical findings — W8 was the feature freeze.
- Screenshot sweep and the written report.

---

## 6. Finishing a part — the build agent's checklist

1. Branch as `<component>/<short-description>` from an up-to-date `main`.
2. Commit as `component: imperative subject`, with a body explaining *why*.
3. `make lint`, `make test`, `npm run build`, and Playwright where the behaviour is user-visible.
4. Drive the real stack: the change, in both themes, at 375 px, with the browser console clean.
5. Fill in the PR template, including the evidence: what was run, what was seen, what is still
   missing. Say what was *not* done.
6. Stop. Report. Do not start the next part.

**Never claim a check that was not run.** If a test fails, say so with the output; if a step was
skipped, say which and why.

---

## 7. Reviewing a part — the review agent's checklist

Run the checks; do not take the description's word for them.

**Correctness**
- Does it do what the part says, and nothing else?
- `make lint`, `make test`, the build and Playwright, all run locally on the branch.
- New behaviour has a test that fails without the change.

**The invariants in §2**
- Agent names never decide behaviour. From `frontend/`:

  ```bash
  grep -rnE "['\"](researcher|writer|image|video|publisher|email)['\"]" src \
    --include='*.ts' --include='*.tsx' | grep -vE "\.test\.|/test/"
  ```

  Every surviving hit must be about something other than an agent: the JSON Schema's
  `format: email`, or an HTML `type="email"` input. A hit that compares an agent type is a finding.
  The honest check is the AT-12 test from Part 2 — a seventh agent, zero files changed under
  `frontend/`.
- Every write into a step's `configuration` goes through `setValue`; no default is stored; a
  cleared field is deleted.
- No `/validate` message is reworded, shortened or prefixed in the frontend.
- No file outside the part's component is touched, except regenerated API types.
- No secret, token or `.env` content anywhere in the diff.

**The experience**
- Copy follows UX-SPEC §8: say what happened, then what to do; no blame; specific numbers; the
  words *step*, *run*, *file*, *Google connection* — never *node*, *execution*, *artifact*,
  *credential*.
- Every value a person sees says where it comes from.
- Keyboard reachable; labels on controls; colour never the only signal.
- Both themes; 375 px with no horizontal scroll.

**The report**
- Does the PR description match the diff? Anything claimed but not done is a finding.

Findings are reported with file, line and the failure they would cause. The review agent does not
push fixes.

---

## 8. Things that will bite you

- **Pushing runs the pre-push hook**, which needs the virtualenv on `PATH`:
  `PATH="$PWD/.venv/bin:$PATH" git push`. Without it, `lint-imports` is "not found" and the push fails.
- **`ruff format --check` also formats Python blocks inside Markdown.** A docs-only PR can fail CI
  on a stray space in a code sample.
- **The frontend has no Prettier configuration.** Do not run Prettier over it; it rewraps every file.
- **React Query stops polling in a hidden tab** unless `refetchIntervalInBackground` is set. A run
  being watched from another tab freezes without it.
- **The seeds place steps at `y=120`**, which is off the 16 px grid. The canvas snaps positions on
  load; do not change the seed, which belongs to Mohammed.
- **Worker errors carry an `[attempt N] ` prefix** (`worker/store.py`). Strip it before showing it.
- **Mock agents finish in milliseconds.** Run playback is paced deliberately so handovers are
  visible; that pacing must never hold back a real agent.
- **The catalog fixture** at `frontend/src/test/catalog.json` is a capture of the live
  `/agents/catalog`. Regenerate it when an agent's schema changes, and never hand-edit it.

---

## 9. Schedule

| Week | Dates | Parts | Notes |
|---|---|---|---|
| W2 | 20–26 Sep | 0, 1, 2 | Canvas complete; AT-12 automated |
| W3 | 27 Sep – 3 Oct | 2, 3 | Real Researcher and Writer land (Zain) |
| W4 | 4–10 Oct | 4, 5 | Storage and signed URLs (Mohammed) |
| W5 | 11–17 Oct | 4 | Video pipeline — the highest-risk week |
| W6 | 18–24 Oct | 6 | Google integrations |
| W7 | 25–31 Oct | 6 | Email and the approval gate |
| W8 | 1–7 Nov | polish | **Feature freeze** |
| W9 | 8–14 Nov | 7, 8, 9 | Hardening |
| W10 | 15–21 Nov | 10 | Testing |
| W11 | 22–28 Nov | 11 | Usability sessions |
| W12 | 29 Nov – 5 Dec | 11 | Report and submission |

**Risk worth naming:** Parts 4, 5 and 6 all wait on endpoints that do not exist yet, and three
pages have not been started. If Part 3 slips past W5, the approval preview and templates are
squeezed against the freeze. US-01 at W11 leaves one week to react to what it finds — a dry run
with one person around W8 is cheap insurance.

---

## 10. Open decisions

| | Decision | Blocks | Needed by |
|---|---|---|---|
| D-01 | Supabase Auth or in-house | Sign-in is dev-only: any email, no password | Before the W8 freeze |
| D-03 | Five or six agents | Image is built; nothing consumes its output | Before W8 |
| D-05 | Ship the dark theme | Built and working; needs sign-off | W9 |
| D-09 | How credentials are stored | Part 6 entirely | W6 |

---

## 11. What we are measured on

| Check | Passes at | Meaning |
|---|---|---|
| AT-01, AT-02, AT-08 | now | Build a chain, configure every agent from its schema |
| AT-07 | Part 2 | Steps move pending → running → done without a refresh |
| AT-12 | Part 2 | A seventh agent needs no frontend change |
| AT-04 | Part 4 | Every file downloads and opens |
| AT-09 | Part 4 | A run parks, publishes nothing, resumes only on approval |
| AT-05 | Part 6 | A real upload and a real email |
| AT-06, AT-10 | Part 7 | Retries and the log viewer |
| AT-11 | Part 10 | No request blocks on the worker |
| **US-01** | Part 11 | **Someone non-technical finishes the task unaided — the one that counts** |
