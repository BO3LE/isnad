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

test("a new step says what it still needs, and connecting it fills that in", async ({ page }) => {
  const step = await openSeededWorkflow(page, []);

  await page.getByRole("button", { name: /^Email/ }).click();
  const email = step("Email");
  await expect(email).toContainText("Missing: recipients");
  await expect(email).toContainText("Missing: subject — or add a Writer before it");
  await expect(email).not.toContainText("Step");

  const drawer = page.getByRole("complementary", { name: "Email settings" });
  await drawer.getByRole("button", { name: "Send it to me (demo@gp.local)" }).click();
  await expect(email).not.toContainText("Missing: recipients");

  // Connect Publisher → Email by dragging between their handles, once the view has settled on
  // the new step.
  await expect(email).toBeInViewport({ ratio: 1 });
  await page.waitForTimeout(300);
  const from = (await step("publish").locator(".react-flow__handle-right").boundingBox())!;
  const to = (await email.locator(".react-flow__handle-left").boundingBox())!;
  await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2);
  await page.mouse.down();
  await page.mouse.move(to.x + to.width / 2, to.y + to.height / 2, { steps: 10 });
  // While dragging, the target says what it would take.
  await expect(email).toContainText("Takes link");
  await page.mouse.up();

  await expect(email).toContainText("Step 5");
  await expect(email).not.toContainText("Missing");
  await expect(drawer).toContainText("From Publisher · link");
  await expect(drawer.getByText("From Writer · title")).toBeVisible();
});
