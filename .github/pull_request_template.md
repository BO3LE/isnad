## What this changes

<!-- One or two sentences. Link the Notion task: -->
Task:

## Component(s)

- [ ] C0 `contracts` — **needs two approvals**
- [ ] C1 `frontend`
- [ ] C2 `api`
- [ ] C3 `worker`
- [ ] C4 `agents/*`
- [ ] C5 `adapters/*`
- [ ] C6 `exporters`
- [ ] C7 `db` (includes a migration?)
- [ ] Infrastructure (Docker, CI, scripts, docs)

## The one rule

- [ ] This PR does not edit a component outside the one it is about. If it had to, I explained why below — the boundary may be in the wrong place.

## How I tested it

- [ ] `make check` passes locally (or the component's own tests + `make lint`)
- [ ] If the API changed: ran `make openapi` and committed `contracts/openapi.json` and `frontend/src/lib/api-types.ts`
- [ ] If the schema changed: added an Alembic migration and ran `make migrate`
- [ ] If a screen changed: went through the Design QA checklist (docs/DESIGN-SYSTEM.md §29)

## Evidence for the report

<!-- Screenshot, log excerpt or number worth keeping? Add it to the Screenshots / Results databases in Notion. -->
- [ ] Nothing report-worthy
- [ ] Added to Notion:
