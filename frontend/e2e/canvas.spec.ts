import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";

// Runs with the whole backend stopped: every API call is answered by page.route. The catalog is
// the real one, captured from GET /agents/catalog, so the canvas is tested against what the
// agents actually publish.

const WORKFLOW_ID = "00000000-0000-4000-8000-000000000001";
const catalog = JSON.parse(readFileSync(new URL("../src/test/catalog.json", import.meta.url), "utf-8")) as unknown[];

interface SavedGraph {
  graph: { nodes: { id: string; position: { x: number; y: number }; configuration: Record<string, unknown> }[] };
}

// The seeded "Blog → Video → YouTube" chain. Seeds place steps at y=120, which is off the
// canvas's 16 px grid (120 / 16 = 7.5).
const node = (id: string, agent_type: string, x: number, configuration: Record<string, unknown> = {}) => ({
  id,
  agent_type,
  position: { x, y: 120 },
  configuration,
  requires_approval: agent_type === "publisher",
});
const workflow = {
  id: WORKFLOW_ID,
  name: "Blog → Video → YouTube",
  status: "draft",
  created_at: "2026-09-14T10:00:00Z",
  updated_at: "2026-09-14T10:00:00Z",
  graph: {
    nodes: [
      node("research", "researcher", 0, { topic: "The future of solar energy", num_sources: 5 }),
      node("write", "writer", 320, { length: "short", style: "conversational", format: "video_script" }),
      node("video", "video", 640),
      node("publish", "publisher", 960, { platform: "youtube", privacy: "unlisted" }),
    ],
    edges: [
      { id: "research-write", source: "research", target: "write" },
      { id: "write-video", source: "write", target: "video" },
      { id: "video-publish", source: "video", target: "publish" },
    ],
  },
};

interface Validation {
  valid: boolean;
  issues: { code: string; message: string; severity?: string; node_id?: string; edge_id?: string }[];
}

async function openSeededWorkflow(page: Page, puts: SavedGraph[], validation: Validation = { valid: true, issues: [] }) {
  await page.route("http://api.mock/auth/dev-login", (route) => route.fulfill({ json: { access_token: "t", token_type: "bearer" } }));
  await page.route("http://api.mock/workflows", (route) => route.fulfill({ json: [] }));
  await page.route("http://api.mock/agents/catalog", (route) => route.fulfill({ json: catalog }));
  await page.route(`http://api.mock/workflows/${WORKFLOW_ID}`, (route) => {
    if (route.request().method() === "PUT") puts.push(route.request().postDataJSON() as SavedGraph);
    return route.fulfill({ json: workflow });
  });
  await page.route(`http://api.mock/workflows/${WORKFLOW_ID}/runs`, (route) => route.fulfill({ json: [] }));
  await page.route(`http://api.mock/workflows/${WORKFLOW_ID}/validate`, (route) => route.fulfill({ json: validation }));

  await page.goto("/login");
  await page.getByLabel("Email").fill("demo@gp.local");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Workflows" })).toBeVisible();
  await page.goto(`/workflows/${WORKFLOW_ID}`);

  // Seeded steps by id; a step added during the test by its title.
  const step = (key: string) =>
    SEEDED.includes(key) ? page.getByTestId(`rf__node-${key}`) : page.locator(".react-flow__node").filter({ hasText: key });
  await expect(step("research")).toBeVisible();
  return step;
}

const SEEDED = ["research", "write", "video", "publish"];
const configOf = (put: SavedGraph, id: string) => put.graph.nodes.find((n) => n.id === id)?.configuration;

test("opening, touching a step and validating never saves", async ({ page }) => {
  const puts: SavedGraph[] = [];
  const step = await openSeededWorkflow(page, puts);
  const researcher = step("research");

  // A click with a pixel of hand jitter: React Flow treats it as a drag and snaps the step. On an
  // off-grid y of 120 that moved it to 112 and autosaved a change nobody made.
  const box = (await researcher.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + 20);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2, box.y + 19);
  await page.mouse.up();

  // Opening a step's settings must not write its defaults either (UX-SPEC §4.5).
  await step("publish").click();
  await expect(page.getByRole("complementary", { name: "Publisher settings" })).toBeVisible();

  await page.getByRole("button", { name: "Validate" }).click();
  // §15.5 — the panel reports the result; it used to be a toast as well, which said it twice.
  await expect(page.getByRole("region", { name: "Validation" }).getByRole("heading")).toHaveText("Ready to run");

  // Longer than the 800 ms autosave debounce.
  await page.waitForTimeout(1500);
  expect(puts).toEqual([]);
});

test("moving a step still saves it, on the grid", async ({ page }) => {
  const puts: SavedGraph[] = [];
  const researcher = (await openSeededWorkflow(page, puts))("research");

  const box = (await researcher.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + 20);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + 60, box.y + 80, { steps: 5 });
  await page.mouse.up();

  await expect.poll(() => puts.length).toBe(1);
  for (const saved of puts[0]!.graph.nodes) {
    expect(saved.position.x % 16).toBe(0);
    expect(saved.position.y % 16).toBe(0);
  }
});

test("the canvas says what each step is set to do and what crosses each connection", async ({ page }) => {
  const step = await openSeededWorkflow(page, []);

  // Labels from the schema, not raw values — and the topic stays off the canvas.
  await expect(step("research")).toContainText("5 sources");
  await expect(step("write")).toContainText("Short · Conversational · Video script");
  await expect(step("publish")).toContainText("YouTube · Unlisted");
  await expect(step("write")).toContainText("Step 2");

  // Hovering a step names what its connections hand on.
  await step("video").hover();
  await expect(page.getByText("title · article")).toBeVisible();
  await expect(page.getByText("video", { exact: true })).toBeVisible();
});

test("a field left empty says where its value comes from; taking it over and giving it back never stores an empty value", async ({ page }) => {
  const puts: SavedGraph[] = [];
  const step = await openSeededWorkflow(page, puts);
  await step("publish").click();
  const drawer = page.getByRole("complementary", { name: "Publisher settings" });

  // Only an earlier step can supply the file; the title is inherited until the user takes it over.
  await expect(drawer).toContainText("From Video · video");
  await expect(drawer.getByText("From Writer · title")).toBeVisible();

  await drawer.getByRole("button", { name: "Use my own" }).first().click();
  await page.keyboard.type("Solar in Saudi Arabia");
  await expect.poll(() => puts.length).toBeGreaterThan(0);
  expect(configOf(puts.at(-1)!, "publish")).toEqual({ platform: "youtube", privacy: "unlisted", title: "Solar in Saudi Arabia" });

  // Giving control back removes the key; it is never saved as "".
  const before = puts.length;
  await drawer.getByRole("button", { name: "Use Writer's instead" }).click();
  await expect(drawer.getByText("From Writer · title")).toBeVisible();
  await expect.poll(() => puts.length).toBeGreaterThan(before);
  expect(configOf(puts.at(-1)!, "publish")).toEqual({ platform: "youtube", privacy: "unlisted" });
});

test("the palette suggests what fits next, and a click adds it already connected", async ({ page }) => {
  const step = await openSeededWorkflow(page, []);
  const palette = page.getByRole("complementary", { name: "Agents" });

  await expect(palette).toContainText("Click to add after Publisher");
  const suggested = palette.getByRole("region", { name: "Suggested next" });
  await expect(suggested).toContainText("Takes link from Publisher");
  await suggested.getByRole("button", { name: /^Email/ }).click();

  const email = step("Email");
  await expect(email).toContainText("Step 5");
  await expect(email).toContainText("Missing: recipients");
  const drawer = page.getByRole("complementary", { name: "Email settings" });
  await expect(drawer).toContainText("From Publisher · link");
  await expect(drawer.getByText("From Writer · title")).toBeVisible();

  await drawer.getByRole("button", { name: "Send it to me (demo@gp.local)" }).click();
  await expect(email).not.toContainText("Missing");
});

test("a loose step says what it needs, and drawing a connection shows what it would take", async ({ page }) => {
  const step = await openSeededWorkflow(page, []);

  // Nothing Publisher makes is useful to Image, so it is added but left unconnected.
  const palette = page.getByRole("complementary", { name: "Agents" });
  await palette.getByRole("region", { name: "Create" }).getByRole("button", { name: /^Image/ }).click();
  const image = step("Image");
  await expect(image).toContainText("Missing: prompt — or add a Writer before it");
  await expect(image).not.toContainText("Step");

  await expect(image).toBeInViewport({ ratio: 1 });
  await page.waitForTimeout(300);
  await page.getByRole("button", { name: "Close settings" }).click();
  await page.getByRole("button", { name: "Fit View" }).click();
  await page.waitForTimeout(300);

  const from = (await step("write").locator(".react-flow__handle-right").boundingBox())!;
  const to = (await image.locator(".react-flow__handle-left").boundingBox())!;
  await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2);
  await page.mouse.down();
  await page.mouse.move(to.x + to.width / 2, to.y + to.height / 2, { steps: 10 });
  // While dragging, each possible target says what it would take.
  await expect(image).toContainText("Takes title");
  await expect(step("research")).toContainText("Can't use anything from Writer");
  await page.mouse.up();

  await expect(image).toContainText("Step 3");
  await expect(image).not.toContainText("Missing");
});

// ---------------------------------------------------------------- validation panel (§15.5)

// Three problems of three different kinds, worded exactly as api/services/validation.py words them.
const ISSUES = [
  {
    code: "cycle_detected",
    severity: "error",
    node_id: "write",
    message: "These steps form a loop: Writer → Video. Remove one connection.",
  },
  { code: "orphan_node", severity: "error", node_id: "research", message: "Researcher isn't connected to anything." },
  { code: "missing_config", severity: "error", node_id: "video", message: "Video is missing narration voice." },
];

test("validation reports the server's words, and each one takes you to its step", async ({ page }) => {
  const step = await openSeededWorkflow(page, [], { valid: false, issues: ISSUES });
  await page.getByRole("button", { name: "Validate" }).click();

  const panel = page.getByRole("region", { name: "Validation" });
  await expect(panel.getByRole("heading")).toHaveText("3 issues to fix before running");

  // Verbatim: an exact, whole-string match, so a prefix, a trim or a reworded ending fails here.
  for (const issue of ISSUES) await expect(panel.getByText(issue.message, { exact: true })).toBeVisible();

  // Each issue carries its own step's action, named from the catalog.
  await expect(panel.getByRole("button", { name: "Go to Writer" })).toBeVisible();
  await expect(panel.getByRole("button", { name: "Go to Researcher" })).toBeVisible();

  // Go to step selects it, brings it into view, and opens its settings.
  await panel.getByRole("button", { name: "Go to Video" }).click();
  await expect(page.getByRole("complementary", { name: "Video settings" })).toBeVisible();
  await expect(step("video")).toBeInViewport({ ratio: 1 });

  // Each of the three lands on its own step, not merely the first.
  await panel.getByRole("button", { name: "Go to Researcher" }).click();
  await expect(page.getByRole("complementary", { name: "Researcher settings" })).toBeVisible();
  await panel.getByRole("button", { name: "Go to Writer" }).click();
  await expect(page.getByRole("complementary", { name: "Writer settings" })).toBeVisible();
});

test("the issue count opens the report it is counting, and closing it keeps the count", async ({ page }) => {
  await openSeededWorkflow(page, [], { valid: false, issues: ISSUES });
  await page.getByRole("button", { name: "Validate" }).click();

  const panel = page.getByRole("region", { name: "Validation" });
  await expect(panel).toBeVisible();
  await panel.getByRole("button", { name: "Close validation" }).click();
  await expect(panel).toBeHidden();

  // §15.6 — the status bar keeps the count, and it is the way back in.
  await page.getByRole("button", { name: "3 issues" }).click();
  await expect(panel).toBeVisible();
});

test("a warning is not a pass: the canvas never claims Valid for something the server didn't check", async ({ page }) => {
  // The worker hasn't started, so the server passes the graph but says the settings went unchecked.
  const unchecked = {
    code: "catalog_unavailable",
    severity: "warning",
    message: "Agent settings couldn't be checked because the worker hasn't started yet.",
  };
  await openSeededWorkflow(page, [], { valid: true, issues: [unchecked] });
  await page.getByRole("button", { name: "Validate" }).click();

  const panel = page.getByRole("region", { name: "Validation" });
  await expect(panel.getByRole("heading")).toHaveText("1 warning");
  await expect(panel.getByText(unchecked.message, { exact: true })).toBeVisible();

  // It must not dismiss itself like a pass, and the status bar must not read "✓ Valid".
  await page.waitForTimeout(2500);
  await expect(panel).toBeVisible();
  await page.getByRole("button", { name: "Close validation" }).click();
  await expect(page.getByText("✓ Valid")).toBeHidden();

  // The warning stays reachable.
  await page.getByRole("button", { name: "1 warning" }).click();
  await expect(panel).toBeVisible();
});

test("two unset settings on one step list as two issues", async ({ page }) => {
  // validation.py emits one missing_config per required field, so a step can raise several rows
  // that share a code and a step.
  await openSeededWorkflow(page, [], {
    valid: false,
    issues: [
      { code: "missing_config", severity: "error", node_id: "video", message: "Video is missing narration voice." },
      { code: "missing_config", severity: "error", node_id: "video", message: "Video is missing resolution." },
    ],
  });
  // That they are kept apart rather than colliding is guarded in ValidationPanel.test.tsx: React's
  // duplicate-key warning is development-only, and these specs run against a production build.
  await page.getByRole("button", { name: "Validate" }).click();
  const panel = page.getByRole("region", { name: "Validation" });
  await expect(panel.getByRole("heading")).toHaveText("2 issues to fix before running");
  await expect(panel.getByRole("listitem")).toHaveCount(2);
  await expect(panel.getByRole("button", { name: "Go to Video" })).toHaveCount(2);
});

test("a workflow with nothing wrong says so, then gets out of the way", async ({ page }) => {
  const step = await openSeededWorkflow(page, [], { valid: true, issues: [] });
  await page.getByRole("button", { name: "Validate" }).click();

  const panel = page.getByRole("region", { name: "Validation" });
  await expect(panel.getByRole("heading")).toHaveText("Ready to run");

  // Moving on and off a step re-renders the canvas (onNodeMouseEnter/Leave). The countdown must
  // survive that, or the panel outstays its two seconds for anyone whose hand is on the mouse.
  // The hovering has to outlast the countdown itself, which is what makes this a real test: a
  // countdown restarted by each re-render would still be running when the loop ends.
  const over = (await step("write").boundingBox())!;
  for (let i = 0; i < 12; i++) {
    await page.mouse.move(over.x + over.width / 2, over.y + over.height / 2);
    await page.waitForTimeout(125);
    await page.mouse.move(over.x + over.width / 2, over.y - 60);
    await page.waitForTimeout(125);
  }
  // Already gone: the countdown ran while the hovering did. A restarted one would still owe 2 s.
  await expect(panel).toBeHidden({ timeout: 1_000 });
});

test("pressing Run on a graph the server refuses opens the panel, not a toast", async ({ page }) => {
  await openSeededWorkflow(page, []);
  // The run endpoint answers 422 with the same shape /validate returns.
  await page.route(`http://api.mock/workflows/${WORKFLOW_ID}/run`, (route) =>
    route.fulfill({ status: 422, json: { detail: { valid: false, issues: ISSUES } } }),
  );

  await page.getByRole("button", { name: "Run", exact: true }).click();

  const panel = page.getByRole("region", { name: "Validation" });
  await expect(panel.getByRole("heading")).toHaveText("3 issues to fix before running");
  await expect(panel.getByText(ISSUES[1].message, { exact: true })).toBeVisible();
  // "not a toast" is half the point: an error toast is role="alert", and none should appear.
  await expect(page.getByRole("alert")).toHaveCount(0);
});

// ---------------------------------------------------------------- run mode (UX-SPEC §6, §7)

const RUN_ID = "00000000-0000-4000-8000-0000000000aa";
type NodeStatus = "pending" | "running" | "awaiting_approval" | "success" | "failed" | "skipped";
const runState = (status: string, statuses: NodeStatus[], error?: string) => ({
  id: RUN_ID,
  workflow_id: WORKFLOW_ID,
  status,
  created_at: new Date().toISOString(),
  started_at: new Date().toISOString(),
  completed_at: ["succeeded", "failed", "cancelled"].includes(status) ? new Date().toISOString() : null,
  total_nodes: 4,
  failed_nodes: statuses.filter((s) => s === "failed").length,
  nodes: SEEDED.map((id, index) => ({
    node_id: id,
    agent_type: workflow.graph.nodes[index]!.agent_type,
    status: statuses[index],
    retry_count: 0,
    started_at: statuses[index] === "pending" ? null : new Date().toISOString(),
    error_message: statuses[index] === "failed" ? error : null,
  })),
});

/** Opens the seeded workflow with a run the test controls: `server.state` is what GET /runs returns. */
async function withRun(page: Page) {
  const server = { state: runState("awaiting_approval", ["success", "success", "success", "awaiting_approval"]) as unknown };
  const decisions: { decision: string; note?: string }[] = [];
  const step = await openSeededWorkflow(page, []);
  await page.route(`http://api.mock/workflows/${WORKFLOW_ID}/run`, (route) => route.fulfill({ status: 202, json: { run_id: RUN_ID, status: "queued" } }));
  await page.route(`http://api.mock/runs/${RUN_ID}`, (route) => route.fulfill({ json: server.state }));
  await page.route(`http://api.mock/runs/${RUN_ID}/nodes/publish/approve`, (route) => {
    decisions.push(route.request().postDataJSON());
    return route.fulfill({ status: 202, json: { run_id: RUN_ID, status: "queued" } });
  });
  // What the run produced, as Part 3's endpoint serves it.
  await page.route(`http://api.mock/runs/${RUN_ID}/outputs`, (route) =>
    route.fulfill({
      json: [
        { id: "out-article", node_id: "write", agent_type: "writer", kind: "text", filename: null, mime_type: null, bytes: null, created_at: "2026-09-20T10:00:00Z" },
        { id: "out-video", node_id: "video", agent_type: "video", kind: "file", filename: "video.mp4", mime_type: "video/mp4", bytes: 4036, created_at: "2026-09-20T10:00:01Z" },
      ],
    }),
  );
  await page.route("http://api.mock/outputs/out-article", (route) =>
    route.fulfill({ json: { id: "out-article", text: "title: The Future of Solar Energy" } }),
  );
  await page.route("http://api.mock/outputs/out-video", (route) =>
    route.fulfill({ json: { id: "out-video", url: "http://api.mock/files/video.mp4", expires_in: 3600 } }),
  );
  await page.route(`http://api.mock/runs/${RUN_ID}/cancel`, (route) => {
    server.state = runState("cancelled", ["success", "skipped", "skipped", "skipped"]);
    return route.fulfill({ status: 202, json: server.state });
  });
  return { step, server, decisions };
}

test("a run plays on the canvas one handover at a time, then waits for approval", async ({ page }) => {
  const { step, server, decisions } = await withRun(page);
  const bar = page.getByRole("region", { name: "Run progress" });

  await page.getByRole("button", { name: "Run", exact: true }).click();

  // The worker finished three steps between polls; the canvas still shows each one working.
  await expect(step("research")).toContainText("Running");
  await expect(step("research")).toContainText("Done");
  await expect(step("write")).toContainText("Running");
  await expect(step("write")).toContainText("Done");
  await expect(page.getByRole("complementary", { name: "Agents" })).toContainText("Editing is paused while this workflow runs.");

  await expect(step("publish")).toContainText("Needs approval", { timeout: 10_000 });
  await expect(bar).toContainText("Publisher is waiting for your approval. Nothing has been sent yet.");
  await expect(bar).toContainText("3 of 4 steps");
  await expect(page).toHaveTitle(/Needs approval/);

  await bar.getByRole("button", { name: "Review" }).click();
  const dialog = page.getByRole("dialog", { name: "Review before it goes out" });
  await expect(dialog).toContainText("Nothing has been sent yet.");
  await expect(dialog).toContainText("From Video · video");
  await expect(dialog).toContainText("Unlisted");

  server.state = runState("succeeded", ["success", "success", "success", "success"]);
  await dialog.getByRole("button", { name: "Approve and send to YouTube" }).click();
  expect(decisions).toEqual([{ decision: "approve" }]);

  await expect(bar).toContainText("Run finished in", { timeout: 10_000 });
  await expect(bar).toContainText("4 of 4 steps");
  await bar.getByRole("button", { name: "Back to editing" }).click();
  await expect(page.getByRole("complementary", { name: "Agents" })).toContainText("Click to add after Publisher");
});

test("the approval window shows the thing itself, not a promise of it", async ({ page }) => {
  await withRun(page);
  await page.getByRole("button", { name: "Run", exact: true }).click();
  await page.getByRole("region", { name: "Run progress" }).getByRole("button", { name: "Review" }).click({ timeout: 15_000 });

  const dialog = page.getByRole("dialog", { name: "Review before it goes out" });
  const preview = dialog.getByRole("region", { name: "Preview" });

  // One tab per thing the run made, named from the catalog — never "Preview isn't available yet".
  await expect(dialog).not.toContainText("Preview isn't available yet");
  await expect(preview.getByRole("tab")).toHaveCount(2);
  await expect(preview.getByRole("tab", { name: "Writer · text" })).toBeVisible();
  await expect(preview.getByRole("tab", { name: "Video · video.mp4" })).toBeVisible();

  // The article is shown as words, and marked as made by an agent.
  await expect(preview).toContainText("The Future of Solar Energy");
  await expect(preview).toContainText("Generated");

  // The video is playable in place, with its size in the product's own units (§23.1).
  await preview.getByRole("tab", { name: "Video · video.mp4" }).click();
  await expect(preview.locator("video")).toHaveAttribute("src", "http://api.mock/files/video.mp4");
  await expect(preview).toContainText("4.0 KB");
});

test("rejecting needs a reason and never reads as a failure", async ({ page }) => {
  const { step, server, decisions } = await withRun(page);
  const bar = page.getByRole("region", { name: "Run progress" });
  await page.getByRole("button", { name: "Run", exact: true }).click();
  await bar.getByRole("button", { name: "Review" }).click({ timeout: 15_000 });

  const dialog = page.getByRole("dialog", { name: "Review before it goes out" });
  await dialog.getByRole("button", { name: "Reject…" }).click();
  await dialog.getByRole("button", { name: "Reject and stop the run" }).click();
  await expect(dialog).toContainText("Add a note — it's kept with the run.");
  expect(decisions).toEqual([]);

  server.state = runState("failed", ["success", "success", "success", "failed"], "[attempt 1] Rejected by reviewer.");
  await dialog.getByLabel("Why are you rejecting this?").fill("Wrong thumbnail");
  await dialog.getByRole("button", { name: "Reject and stop the run" }).click();
  expect(decisions).toEqual([{ decision: "reject", note: "Wrong thumbnail" }]);

  await expect(bar).toContainText("Rejected by you at Publisher", { timeout: 10_000 });
  await expect(step("publish")).toContainText("You rejected this step. Nothing was sent.");
  await expect(step("publish")).not.toContainText("Failed");
});

test("cancelling shows at once what was skipped", async ({ page }) => {
  const { step, server } = await withRun(page);
  server.state = runState("running", ["running", "pending", "pending", "pending"]);
  const bar = page.getByRole("region", { name: "Run progress" });
  await page.getByRole("button", { name: "Run", exact: true }).click();
  await expect(step("research")).toContainText("Running");

  await bar.getByRole("button", { name: "Cancel run" }).click();
  await expect(bar).toContainText("Run cancelled. Steps that hadn't started were skipped.");
  await expect(step("video")).toContainText("Skipped");
});
