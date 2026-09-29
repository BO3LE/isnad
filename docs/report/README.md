# docs/report/

Source for the **Testing Process and Results** chapter (GP-plan W12, C7, Mohammed).

- `testing-process-and-results.md` — the chapter itself, ready to paste into the M3 report
  document (§1 strategy, §2 environment, §3 automated test inventory, §4 CI, §5 the 18-row
  acceptance table, §6 non-functional results, §7 defects, §8 limitations).
- `testing-tables.csv` — the same acceptance table and the automated-test-inventory table, as CSV,
  for pasting straight into a Word table (two tables in one file, each preceded by a `TABLE,` row —
  split on that row before pasting).

Every number in both files was either read from a file already committed to this repository
(`docs/metrics/*.md` and `docs/metrics/data/*`, `docs/fresh-machine-test.md`) or produced by
actually running the named test suite on 2026-09-29 (see the chapter's §3 for exactly how). Nothing
is invented.

## Placeholders the team still needs to fill

Every one of these is marked `[[TO FILL: …]]` in the chapter and/or the CSV. There are **5**:

| # | Where | What's needed | Suggested owner (per GP-plan) |
|---|---|---|---|
| 1 | AT-05 (§5) | Run a real workflow through the real YouTube/Drive/Gmail publish path once live Google OAuth credentials and a YouTube test channel exist. `adapters/src/adapters/publish/youtube.py` still has an open `TODO(W6, Zain)` for the real upload flow. | Zain (W6/W10) |
| 2 | AT-12 / NFR-04 file count (§5, §6.4) | Re-run the seventh-agent exercise in `docs/ADDING_AN_AGENT.md` §7 (add `agents/<name>/`, restart the worker, `git diff --stat main`) and paste the actual output — this repository's own automated `frontend/e2e/seventh-agent.spec.ts` already proves the frontend mechanism, but the file-count artifact itself needs a fresh run. | Zain (W8) |
| 3 | US-01 / NFR-03 (§5, §6.3) | Moderated usability sessions — task, time-on-task, completion rate, SUS per participant. Participant count is not specified anywhere in M1/M2/GP-plan; agree it with the supervisor first. | Ahmed (W11) |
| 4 | NFR-02 external-API slice (§6.2, RT-01 in §5) | The measured 100% handoff success rate ran entirely with `FAKE_ADAPTERS=true`; it says nothing about real external-API failure/retry rates. Once real adapters are live, either re-run `scripts/reliability_campaign.py` against them, or explicitly note in the final report that this slice remains unmeasured. | Whoever owns the live-adapter rollout |
| 5 | AT-11's 500 ms target (§6.1) | This team set 500 ms p95 itself — no source document (GP-plan, M1) gives a number for NFR-01. Confirm with the supervisor whether 500 ms is acceptable to state as the agreed bar, or whether a different figure (or no figure, keeping the requirement qualitative) should appear in the final report. | Supervisor confirmation |

## Partial-coverage notes (not blocking, but worth reading before finalizing)

Seven acceptance/robustness cases are marked **Partial** rather than a flat Pass or a placeholder,
each with a specific named gap: AT-01 (no single test builds-saves-reloads a fresh graph), AT-03
(structure proven, real researched content not), AT-04 (local storage backend only, not the
Supabase signed-URL path), RB-01 (resume works; one crash window is an open, tracked bug — see the
chapter's §7 defects table, item 4), RB-03 (adapter-level classification proven; UI-level error
display not separately tested), and AT-12/RT-01 as covered above. These are not missing evidence so
much as evidence with an honestly stated boundary — see §5 of the chapter for the exact wording used
for each.

## Known, open defects (§7 of the chapter)

Four orchestrator bugs around run cancellation are deliberately pinned down by
`xfail(strict=True)` tests in `tests/integration/test_run_reliability.py` (cancel overwritten by the
last step; cancel ignored during retry backoff; cancelled runs missing `completed_at`; duplicate
output on a specific crash window) plus three more found through load/E2E testing rather than
dedicated bug-hunting (an autosave race causing intermittent 500s, an N+1 query in
`list_workflows`, and a broken "Duplicate workflow" action) — all seven are **open** at the time of
writing. Two earlier Windows setup issues (CRLF entrypoint crash; `python3`/console-encoding
friction) are **fixed**. None of this needs the team's attention before submission unless the
Challenges and Resolutions chapter wants to reference them — they are documented here for
traceability, not as new action items.
