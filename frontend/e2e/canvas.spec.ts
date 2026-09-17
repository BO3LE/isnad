import { expect, test, type Page } from "@playwright/test";

// Runs with the whole backend stopped: every API call is answered by page.route.

const WORKFLOW_ID = "00000000-0000-4000-8000-000000000001";

const manifest = (name: string, title: string) => ({
  name,
  title,
  description: `${title} agent`,
  family: "create",
  icon: null,
  input_type: "In",
  output_type: "Out",
  requires_approval: false,
  version: "1.0.0",
  config_schema: null,
});

// The seeds place steps at y=120, which is off the canvas's 16 px grid (120 / 16 = 7.5).
const workflow = {
  id: WORKFLOW_ID,
  name: "Blog post",
  status: "draft",
  created_at: "2026-09-14T10:00:00Z",
  updated_at: "2026-09-14T10:00:00Z",
  graph: {
    nodes: [
      { id: "research", agent_type: "researcher", position: { x: 80, y: 120 }, configuration: { topic: "Solar" }, requires_approval: false },
      { id: "write", agent_type: "writer", position: { x: 400, y: 120 }, configuration: {}, requires_approval: false },
    ],
    edges: [{ id: "research-write", source: "research", target: "write" }],
  },
};

async function openSeededWorkflow(page: Page, puts: string[]) {
  await page.route("http://api.mock/auth/dev-login", (route) => route.fulfill({ json: { access_token: "t", token_type: "bearer" } }));
  await page.route("http://api.mock/workflows", (route) => route.fulfill({ json: [] }));
  await page.route("http://api.mock/agents/catalog", (route) =>
    route.fulfill({ json: [manifest("researcher", "Researcher"), manifest("writer", "Writer")] }),
  );
  await page.route(`http://api.mock/workflows/${WORKFLOW_ID}`, (route) => {
    if (route.request().method() === "PUT") puts.push(route.request().postData() ?? "");
    return route.fulfill({ json: workflow });
  });
  await page.route(`http://api.mock/workflows/${WORKFLOW_ID}/validate`, (route) =>
    route.fulfill({ json: { valid: true, issues: [] } }),
  );

  await page.goto("/login");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Workflows" })).toBeVisible();
  await page.goto(`/workflows/${WORKFLOW_ID}`);

  const researcher = page.locator(".react-flow__node").filter({ hasText: "Researcher" });
  await expect(researcher).toBeVisible();
  return researcher;
}

test("opening, touching a step and validating never saves", async ({ page }) => {
  const puts: string[] = [];
  const researcher = await openSeededWorkflow(page, puts);

  // A click with a pixel of hand jitter: React Flow treats it as a drag and snaps the step. On an
  // off-grid y of 120 that moved it to 112 and autosaved a change nobody made.
  const box = (await researcher.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + 20);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2, box.y + 19);
  await page.mouse.up();
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("ArrowUp");

  await page.getByRole("button", { name: "Validate" }).click();
  await expect(page.getByText("Ready to run.")).toBeVisible();

  // Longer than the 800 ms autosave debounce.
  await page.waitForTimeout(1500);
  expect(puts).toEqual([]);
});

test("moving a step still saves it, on the grid", async ({ page }) => {
  const puts: string[] = [];
  const researcher = await openSeededWorkflow(page, puts);

  const box = (await researcher.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + 20);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + 60, box.y + 80, { steps: 5 });
  await page.mouse.up();

  await expect.poll(() => puts.length).toBe(1);
  const saved = JSON.parse(puts[0]) as { graph: { nodes: { id: string; position: { x: number; y: number } }[] } };
  for (const node of saved.graph.nodes) {
    expect(node.position.x % 16).toBe(0);
    expect(node.position.y % 16).toBe(0);
  }
});
