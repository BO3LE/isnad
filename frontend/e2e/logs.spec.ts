import { expect, test, type Page } from "@playwright/test";

// P-08 in a real browser, against a mocked API (no backend running).
//
// The retried step here is FABRICATED. Nothing can produce a real retry yet: the mock agents never
// fail retryably, and fault injection is an unstarted backend task (GP-plan W9). So this proves
// the page renders what the worker *would* write — the `[attempt N]` history it already appends in
// worker/store.py — and not that the orchestrator retries. AT-06 still needs a real run.

const RUN = "00000000-0000-4000-8000-0000000000aa";

const run = {
  id: RUN,
  workflow_id: "00000000-0000-4000-8000-000000000001",
  status: "failed",
  created_at: "2026-09-20T16:05:00Z",
  started_at: "2026-09-20T16:05:00Z",
  completed_at: "2026-09-20T16:11:02Z",
  total_nodes: 4,
  failed_nodes: 1,
  nodes: [],
};

const log = (over: Record<string, unknown>) => ({
  id: `00000000-0000-4000-8000-00000000000${over.n as string}`,
  run_id: RUN,
  retry_count: 0,
  started_at: "2026-09-20T16:05:02Z",
  completed_at: "2026-09-20T16:05:20Z",
  duration_ms: 18400,
  error_message: null,
  ...over,
});

const logs = [
  log({ n: "1", node_id: "11111111-1111-4111-8111-111111111111", agent_type: "researcher", status: "success" }),
  log({ n: "2", node_id: "22222222-2222-4222-8222-222222222222", agent_type: "writer", status: "success", duration_ms: 42100 }),
  log({
    n: "3",
    node_id: "33333333-3333-4333-8333-333333333333",
    agent_type: "publisher",
    status: "failed",
    retry_count: 3,
    duration_ms: 92000,
    started_at: "2026-09-20T16:09:40Z",
    completed_at: "2026-09-20T16:11:02Z",
    error_message:
      "[attempt 1] invalid_grant: Token has been revoked.\n" +
      "[attempt 2] invalid_grant: Token has been revoked.\n" +
      "[attempt 3] invalid_grant: Token has been revoked.\n" +
      "[attempt 4] invalid_grant: Token has been revoked.",
  }),
  log({
    n: "4",
    node_id: "44444444-4444-4444-8444-444444444444",
    agent_type: "email",
    status: "skipped",
    started_at: null,
    completed_at: null,
    duration_ms: null,
  }),
];

async function openLogs(page: Page, rows: unknown[] = logs) {
  await page.route("http://api.mock/auth/dev-login", (r) => r.fulfill({ json: { access_token: "t", token_type: "bearer" } }));
  await page.route("http://api.mock/workflows", (r) => r.fulfill({ json: [] }));
  await page.route("http://api.mock/agents/catalog", (r) => r.fulfill({ json: [] }));
  await page.route(`http://api.mock/runs/${RUN}`, (r) => r.fulfill({ json: run }));
  await page.route(`http://api.mock/runs/${RUN}/logs`, (r) => r.fulfill({ json: rows }));

  await page.goto("/login");
  await page.getByLabel("Email").fill("demo@gp.local");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Workflows" })).toBeVisible();
  await page.goto(`/runs/${RUN}/logs`);
  await expect(page.getByRole("heading", { name: "Logs" })).toBeVisible();
}

/**
 * Whether the page scrolls sideways at the current viewport.
 *
 * `document` is typed through a shim because e2e compiles without the DOM lib
 * (tsconfig.node.json), so only the two properties this needs are declared.
 */
async function scrollsSideways(page: Page): Promise<boolean> {
  return page.evaluate(() => {
    const { documentElement } = (globalThis as unknown as {
      document: { documentElement: { scrollWidth: number; clientWidth: number } };
    }).document;
    return documentElement.scrollWidth > documentElement.clientWidth;
  });
}

test("a retried step tells the whole story: every attempt, the waits, and what it cost", async ({ page }) => {
  await openLogs(page);

  const failed = page.getByRole("row").filter({ hasText: "publisher" });
  // The Retries cell specifically, not the row: the step number is also 3, so a whole-row match
  // would hold even with the Retries column deleted.
  await expect(failed.getByRole("cell").nth(5)).toHaveText("3");
  await failed.getByRole("button", { name: /Show details/ }).click();

  const detail = page.locator('[id^="log-detail-"]');
  // Four attempts, not three: `retry_count` counts retries, and the first try is not a retry.
  // Anchored, because the closing "Out of attempts…" line also contains the word.
  await expect(detail.getByRole("listitem").filter({ hasText: /^Attempt \d/ })).toHaveCount(4);
  await expect(detail).toContainText("Attempt 1");
  await expect(detail).toContainText("Attempt 4");

  // §16.5's backoff, narrated as "about" because the orchestrator adds jitter.
  await expect(detail).toContainText("Retry 1 of 3, about 2s later.");
  await expect(detail).toContainText("Retry 2 of 3, about 4s later.");
  await expect(detail).toContainText("Retry 3 of 3, about 8s later.");
  // The last attempt is the end of the road, not another wait.
  await expect(detail).not.toContainText("Retry 4 of 3");
  await expect(detail).toContainText("Out of attempts");
});

test("a step that never ran reports nothing, rather than zero of everything", async ({ page }) => {
  await openLogs(page);
  // §21 S-07's own mock: the skipped Email row is "— — — —" across the board. Counting zero
  // retries for a step that never made a first attempt states something that did not happen.
  const skipped = page.getByRole("row").filter({ hasText: "email" });
  await expect(skipped.getByRole("cell").nth(2)).toHaveText("—"); // started
  await expect(skipped.getByRole("cell").nth(4)).toHaveText("—"); // duration
  await expect(skipped.getByRole("cell").nth(5)).toHaveText("—"); // retries
});

test("the CSV holds the rows on screen, in UTC, whatever the table is showing", async ({ page }) => {
  await openLogs(page);

  // Read the table in UTC so the comparison below is about the *file*, not about zones.
  await page.getByRole("radio", { name: "UTC" }).click();
  await expect(page.getByRole("row").filter({ hasText: "Researcher" })).toContainText("16:05:02");

  const download = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "Export CSV" }).click(),
  ]).then(([d]) => d);

  const stream = await download.createReadStream();
  const csv = await new Promise<string>((resolve, reject) => {
    let text = "";
    stream.on("data", (chunk) => (text += String(chunk)));
    stream.on("end", () => resolve(text));
    stream.on("error", reject);
  });

  const lines = csv.trimEnd().split("\n");
  expect(lines[0]).toBe("run_id,node_id,agent_type,status,started_at,completed_at,duration_ms,retry_count,error_message");
  // Four steps, but the retried one's error spans four physical lines inside one quoted field.
  expect(csv).toContain('"[attempt 1] invalid_grant: Token has been revoked.');
  expect(csv).toContain("2026-09-20T16:05:02.000Z");
  // A skipped step has no timings, and empty is how a spreadsheet reads "nothing", not "0".
  expect(csv).toContain("email,skipped,,,,0,");
  // Records, not physical lines: the retried step's error is one quoted field spanning four lines.
  expect(csv.split("\n").filter((l) => l.startsWith(RUN))).toHaveLength(4);
});

test("the CSV shrinks with the filter, so the file matches what was being read", async ({ page }) => {
  await openLogs(page);
  await page.getByRole("searchbox", { name: /Search the log/ }).fill("revoked");
  await expect(page.getByRole("row")).toHaveCount(2);

  const download = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "Export CSV" }).click(),
  ]).then(([d]) => d);
  const stream = await download.createReadStream();
  const csv = await new Promise<string>((resolve, reject) => {
    let text = "";
    stream.on("data", (chunk) => (text += String(chunk)));
    stream.on("end", () => resolve(text));
    stream.on("error", reject);
  });

  // Exactly the one visible step. Exporting the whole run here would hand someone a file that
  // disagrees with the screen they exported it from.
  expect(csv).toContain("publisher,failed");
  expect(csv).not.toContain("researcher");
  expect(csv).not.toContain("email,skipped");
  // Header plus one step; the error field's newlines live inside quotes, so count records by
  // counting the rows that start with the run id.
  expect(csv.split("\n").filter((l) => l.startsWith(RUN))).toHaveLength(1);
});

test("the time zone toggle actually moves the clock", async ({ page }) => {
  await openLogs(page);
  const started = page.getByRole("row").filter({ hasText: "researcher" }).getByRole("cell").nth(2);

  // The suite pins the browser to Asia/Riyadh (playwright.config.ts) so these two differ. On a UTC
  // runner they would be the same string, and this assertion — and the CSV test's use of the
  // toggle — would hold whether or not the control did anything.
  await expect(started).toHaveText("19:05:02");
  await page.getByRole("radio", { name: "UTC" }).click();
  await expect(started).toHaveText("16:05:02");

  // And it is a real piece of page state, not just a paint.
  await expect(page).toHaveURL(/tz=utc/);
  await page.reload();
  await expect(started).toHaveText("16:05:02");
});

test("filtering narrows the table, says so, and survives a reload", async ({ page }) => {
  await openLogs(page);
  await expect(page.getByRole("row")).toHaveCount(5); // header + 4 steps

  await page.getByRole("searchbox", { name: /Search the log/ }).fill("revoked");
  await expect(page.getByRole("row")).toHaveCount(2);
  await expect(page.getByText("Export CSV writes these 1 of 4 steps")).toBeVisible();

  // §21 S-07: the filter is in the URL, so the view can be linked to and survives a refresh.
  await expect(page).toHaveURL(/q=revoked/);
  await page.reload();
  await expect(page.getByRole("searchbox", { name: /Search the log/ })).toHaveValue("revoked");
  await expect(page.getByRole("row")).toHaveCount(2);

  // A filter that matches nothing says so instead of showing an empty table.
  await page.getByRole("searchbox", { name: /Search the log/ }).fill("nothing matches this");
  await expect(page.getByRole("heading", { name: "No steps match" })).toBeVisible();
  await page.getByRole("button", { name: "Clear the filter" }).click();
  await expect(page.getByRole("row")).toHaveCount(5);
});

test("step numbers keep their place in the run when the table is filtered", async ({ page }) => {
  await openLogs(page);
  // Publisher is step 3 of the run. Filtering must not renumber it to 1 — a log that renames the
  // steps is worse than no log, because the number is how it is referred to everywhere else.
  await page.getByRole("searchbox", { name: /Search the log/ }).fill("revoked");
  const row = page.getByRole("row").filter({ hasText: "Publisher" });
  await expect(row).toHaveCount(1);
  await expect(row.getByRole("rowheader")).toContainText("3");
});

test("a run that finishes while you are reading it stops being \"Running\"", async ({ page }) => {
  // The chip above the table is the *run's* status. Review found the run was fetched exactly once,
  // so it froze on whatever it said when the page opened — and because "is it still going" is
  // derived from it, the log below polled a finished run for as long as the tab stayed open.
  let finished = false;
  await page.route("http://api.mock/auth/dev-login", (r) => r.fulfill({ json: { access_token: "t", token_type: "bearer" } }));
  await page.route("http://api.mock/workflows", (r) => r.fulfill({ json: [] }));
  await page.route("http://api.mock/agents/catalog", (r) => r.fulfill({ json: [] }));
  await page.route(`http://api.mock/runs/${RUN}`, (r) =>
    r.fulfill({ json: { ...run, status: finished ? "succeeded" : "running" } }),
  );
  await page.route(`http://api.mock/runs/${RUN}/logs`, (r) => r.fulfill({ json: logs }));

  await page.goto("/login");
  await page.getByLabel("Email").fill("demo@gp.local");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Workflows" })).toBeVisible();
  await page.goto(`/runs/${RUN}/logs`);

  // Scoped to the header: the status filter has a "Running" option too.
  const header = page.locator("header").filter({ has: page.getByRole("heading", { name: "Logs" }) });
  await expect(header.getByText("Running", { exact: true })).toBeVisible();
  finished = true;
  await expect(header.getByText("Succeeded", { exact: true })).toBeVisible({ timeout: 10_000 });
});

test("the column names stay put when a long run is scrolled", async ({ page }) => {
  // §21 S-07 asks for a sticky header. A long log is unreadable without it, and the wrapper around
  // the table must not clip its overflow or the stickiness is captured and silently does nothing.
  const many = Array.from({ length: 40 }, (_, i) => ({
    ...logs[0]!,
    id: `00000000-0000-4000-8000-${String(i).padStart(12, "0")}`,
    node_id: `00000000-0000-4000-9000-${String(i).padStart(12, "0")}`,
  }));
  await openLogs(page, many);

  const head = page.getByRole("columnheader", { name: "Step" });
  const before = (await head.boundingBox())!;
  expect(before.y).toBeGreaterThan(50);

  await page.mouse.wheel(0, 2000);
  await expect.poll(async () => Math.round((await head.boundingBox())!.y)).toBeLessThan(Math.round(before.y));

  // Still on screen after scrolling past where it started, rather than gone with the page.
  await expect(head).toBeInViewport();
});

test("a step retrying right now says which attempt is in flight", async ({ page }) => {
  // Most of a retry cycle is spent `running`, not `retrying`. A bare retry count there reads as
  // "it retried once and is fine now", hiding that a second attempt is under way.
  const midRetry = [
    { ...logs[0]!, agent_type: "publisher", status: "running", retry_count: 1, completed_at: null, duration_ms: null, error_message: "[attempt 1] invalid_grant: Token has been revoked." },
  ];
  await openLogs(page, midRetry);
  const row = page.getByRole("row").filter({ hasText: "publisher" });
  await expect(row.getByRole("cell").nth(5)).toHaveText("Attempt 2");
});

test("a step between attempts says how much rope is left", async ({ page }) => {
  const waiting = [
    { ...logs[0]!, agent_type: "publisher", status: "retrying", retry_count: 2, completed_at: null, duration_ms: null, error_message: "[attempt 1] Token revoked.\n[attempt 2] Token revoked." },
  ];
  await openLogs(page, waiting);
  const row = page.getByRole("row").filter({ hasText: "publisher" });
  await expect(row.getByRole("cell").nth(5)).toHaveText("Retrying 2/3");
});

test("a rejected step's hover says the same thing its cell does", async ({ page }) => {
  const rejected = [
    { ...logs[0]!, agent_type: "publisher", status: "failed", error_message: "[attempt 1] Rejected by reviewer." },
  ];
  await openLogs(page, rejected);
  const cell = page.getByRole("row").filter({ hasText: "publisher" }).getByRole("cell").nth(6);
  await expect(cell).toHaveText("You stopped this step.");
  // The tooltip used to fall back to the worker's own wording and contradict the cell.
  await expect(cell).toHaveAttribute("title", "You stopped this step.");
});

test("a run with nothing logged says so", async ({ page }) => {
  await openLogs(page, []);
  await expect(page.getByRole("heading", { name: "Nothing logged yet" })).toBeVisible();
  await expect(page.getByRole("table")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Export CSV" })).toBeDisabled();
});

test("on a phone the table becomes cards, with no sideways scrolling", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openLogs(page);

  // §22: seven columns do not fit a phone, so the table is replaced rather than squeezed.
  await expect(page.getByRole("table")).toBeHidden();
  const cards = page.getByRole("listitem").filter({ hasText: "Publisher" });
  await expect(cards).toHaveCount(1);

  await cards.locator("button[aria-expanded]").click();
  await expect(page.locator('[id^="log-card-"]')).toContainText("Attempt 4");

  expect(await scrollsSideways(page)).toBe(false);
});
