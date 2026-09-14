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
- Branch from `main`, named `<component>/<short-description>`:
  `frontend/canvas-palette`, `worker/retry-backoff`, `agents/writer-prompt`, `db/credentials-index`, `infra/ci-cache`, `contracts/email-port`.
- Keep branches short-lived: open a pull request within two days, even as a draft.
- Rebase on `main` (or merge `main` in) before asking for review.

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
| OpenAPI drift | `contracts/openapi.json` or the frontend types weren't regenerated |
| Migration round-trip | a migration doesn't upgrade, downgrade and upgrade cleanly, or models and migrations disagree |

If the import contract blocks you, don't edit `.importlinter` to get through — talk to the owners of both components.

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
   - Require status checks to pass: `Lint · import boundaries · agent shape`, `Tests · *`, `Migrations round-trip on PostgreSQL 15`, `OpenAPI and frontend types are up to date`, `Frontend · lint · typecheck · unit tests · build`, `Frontend end-to-end (mocked API, no backend)`
   - Require branches to be up to date before merging
   - Do not allow bypassing the above settings
5. **Settings → Actions → General**: allow GitHub Actions.
6. Open a test PR with a deliberate bad import (e.g. `from agents.writer.agent import WriterAgent` in `api/src/api/main.py`) and confirm CI goes red — that is the W1 "done when" for the import contract. Close it without merging.
