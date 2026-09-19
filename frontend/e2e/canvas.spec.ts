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

async function openSeededWorkflow(page: Page, puts: SavedGraph[]) {
  await page.route("http://api.mock/auth/dev-login", (route) => route.fulfill({ json: { access_token: "t", token_type: "bearer" } }));
  await page.route("http://api.mock/workflows", (route) => route.fulfill({ json: [] }));
  await page.route("http://api.mock/agents/catalog", (route) => route.fulfill({ json: catalog }));
  await page.route(`http://api.mock/workflows/${WORKFLOW_ID}`, (route) => {
    if (route.request().method() === "PUT") puts.push(route.request().postDataJSON() as SavedGraph);
    return route.fulfill({ json: workflow });
  });
  await page.route(`http://api.mock/workflows/${WORKFLOW_ID}/runs`, (route) => route.fulfill({ json: [] }));
  await page.route(`http://api.mock/workflows/${WORKFLOW_ID}/validate`, (route) =>
    route.fulfill({ json: { valid: true, issues: [] } }),
  );

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
  await expect(page.getByText("Ready to run.")).toBeVisible();

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
