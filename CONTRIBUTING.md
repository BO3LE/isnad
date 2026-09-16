# How we work

Four people, twelve weeks, seven components. These rules exist so two people almost never edit the same file.

## Ownership

| Person | Owns | Reviews by default |
|---|---|---|
| Ahmed | C1 `frontend`, `docs/DESIGN-SYSTEM.md` | Hasan |
| Hasan (lead) | C2 `api`, C3 `worker` | Mohammed |
| Zain | C4 `agents/*`, C5 `adapters/*`, C6 `exporters` | Hasan |
| Mohammed | C7 `db`, Docker, CI, scripts, deployment, port shapes in `contracts/ports.py` | Zain |
| Everyone | C0 `contracts` | **Two approvals** |

Every area has a named backup reviewer (risk R9 — exams). No account, key or secret is held by one person only.

## Branches

- `main` is protected: no direct pushes, CI must pass, at least one approval.
  **This is only true once the rule in "Setting up the GitHub repository" below is applied.**
  Until then every line in this file is a convention, not a gate: anyone can push straight to
  `main`, and a pull request can be merged while CI is red.
- Branch from `main`, named `<component>/<short-description>`:
  `frontend/canvas-palette`, `worker/retry-backoff`, `agents/writer-prompt`, `db/credentials-index`, `infra/ci-cache`, `contracts/email-port`.
- Keep branches short-lived: open a pull request within two days, even as a draft.
- Rebase on `main` (or merge `main` in) before asking for review.

## Before you push

`make bootstrap` installs git hooks (or `make hooks` on an existing clone). They are the same
checks CI runs, just earlier:

| When | What runs | Roughly |
|---|---|---|
| On commit | whitespace, YAML/JSON/TOML validity, **no private keys**, ruff lint + format, eslint, landing drift | under a second |
| On push | frontend typecheck, frontend unit tests, import boundaries | ~20 s |

`make hooks-all` runs everything against the whole repo. `git commit --no-verify` skips them — CI
will still fail, so all you have bought yourself is a slower answer.

The hooks are a convenience, not the gate. **CI is the gate, and the branch rule on `main` is what
makes it one.**

## Commits

Short imperative subject, component first:

```
worker: park runs at awaiting_approval before side effects
frontend: build config drawer from catalog schema
contracts: add EmailPort
```

## Pull requests

1. Fill in the template — especially **which component** and **how you tested it**.
2. One component per PR. If you had to touch another component, say why in the description: it may mean the boundary is in the wrong place.
3. CI green before review.
4. Reviewer checks: does it respect the boundaries, is it tested, is the "done when" from the plan met.
5. Squash-merge. Delete the branch.

### Changing `contracts/`

`contracts` is the only package that can break more than one component.

- Needs **two approvals**, from people whose components use the changed type.
- Prefer additive changes (new optional field, new model) over renames.
- If you change an API response, run `make openapi` and commit the regenerated files.
- If you add a run or node status: update `db/src/db/models.py` + a migration, `frontend/src/design-system/status/statusMeta.ts`, and DESIGN-SYSTEM.md §16 — CI will fail until you do.

## The boundaries, and how CI enforces them

| Check | Fails when |
|---|---|
| `lint-imports` | `api` or `worker` imports an agent; an agent imports the worker, database or an adapter implementation; an adapter imports an agent; `contracts` or `db` import anything of ours |
| Component test jobs | a component's tests need another component running (each job installs only what that component depends on) |
| `scripts/validate_manifests.py` | an agent folder has no valid `manifest.json` or entry point |
| `make landing-check` | `landing/index.html` changed without regenerating `landing/site/index.html` |
| OpenAPI drift | `contracts/openapi.json` or the frontend types weren't regenerated |
| Migration round-trip | a migration doesn't upgrade, downgrade and upgrade cleanly, or models and migrations disagree |

If the import contract blocks you, don't edit `.importlinter` to get through — talk to the owners of both components.

**One check gates the merge: `CI passed`.** It is a job that depends on every other one, so the
branch rule names a single check that cannot go stale when a job is added or renamed. If it is red,
open it and look at which job underneath it failed.

`Integration · docker compose + smoke test` is deliberately **not** in that gate: it builds the
FFmpeg worker image, so it is skipped on pull requests to save CI minutes and runs on `main` after
the merge. A red integration run on `main` means fixing forward, fast.

## Definition of done

A task is done when:

- its **"done when"** line in [docs/GP-plan.md](docs/GP-plan.md) Part 4 is true,
- it has tests at the level the component uses (unit for agents/exporters/orchestrator, API tests for endpoints, component or e2e tests for screens),
- CI is green and the PR is merged,
- the Notion task is ticked, and anything report-worthy (a screenshot, a number, an obstacle) is logged in Notion the same week.

## Secrets

- Never commit `.env`, keys, tokens or OAuth client secrets. `.gitignore` covers `.env*` except `.env.example`.
- Every new variable goes into `.env.example` with a comment, in the same PR.
- If a secret is committed by mistake: tell Mohammed, rotate the key immediately — removing it from history is not enough.

## Setting up the GitHub repository (lead, once)

1. Create the repository (private) and push `main`.
2. **Settings → Collaborators**: add the other three.
3. Replace the placeholder handles in [.github/CODEOWNERS](.github/CODEOWNERS) with real GitHub usernames.
4. **Settings → Branches → Add rule for `main`**:
   - Require a pull request before merging — 1 approval (2 for contracts is enforced by CODEOWNERS + reviewers)
   - Require review from Code Owners
   - Require status checks to pass: **`CI passed`** — that one job covers all six (see above). Do
     not list the individual jobs: a required check that is later renamed silently stops being
     required, and one that never runs blocks every pull request for ever.
   - Require branches to be up to date before merging
   - Do not allow bypassing the above settings
5. **Settings → Actions → General**: allow GitHub Actions.
6. Open a test PR with a deliberate bad import (e.g. `from agents.writer.agent import WriterAgent` in `api/src/api/main.py`) and confirm CI goes red — that is the W1 "done when" for the import contract. Close it without merging.
