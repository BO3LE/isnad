import { expect, test, type Page } from "@playwright/test";

// A step's result reviewed on the run page, in a real browser: the article shows, the person edits
// it or sends it back with a note, and exactly that reaches the API.

const RUN = "00000000-0000-4000-8000-0000000000ee";

const catalog = ["researcher", "writer", "video"].map((name) => ({
  name,
  version: "0.1.0",
  title: name.charAt(0).toUpperCase() + name.slice(1),
  description: "d",
  family: "create",
  icon: null,
  input_type: "X",
  output_type: "Y",
  requires_approval: false,
  config_schema: { properties: {} },
  inputs: [],
  outputs: [],
}));

const node = (node_id: string, agent_type: string, status: string, revision = 0) => ({
  node_id,
  agent_type,
  status,
  retry_count: 0,
  revision,
  started_at: "2026-10-19T10:00:00Z",
  completed_at: status === "pending" ? null : "2026-10-19T10:00:40Z",
  duration_ms: null,
  error_message: null,
});

const run = (writerRevision = 0) => ({
  id: RUN,
  workflow_id: "00000000-0000-4000-8000-000000000001",
  status: "awaiting_approval",
  created_at: "2026-10-19T10:00:00Z",
  started_at: "2026-10-19T10:00:00Z",
  completed_at: null,
  total_nodes: 3,
  failed_nodes: 0,
  nodes: [node("r", "researcher", "success"), node("w", "writer", "awaiting_approval", writerRevision), node("v", "video", "pending")],
});

const ARTICLE = "# Solar in Riyadh\n\nThe sun is strong all year, so panels make a lot of power.";

async function openRun(page: Page) {
  const decisions: unknown[] = [];
  await page.route("http://api.mock/auth/dev-login", (r) => r.fulfill({ json: { access_token: "t", token_type: "bearer" } }));
  await page.route("http://api.mock/workflows", (r) => r.fulfill({ json: [] }));
  await page.route("http://api.mock/agents/catalog", (r) => r.fulfill({ json: catalog }));
  await page.route(`http://api.mock/runs/${RUN}`, (r) => r.fulfill({ json: run() }));
  await page.route(`http://api.mock/runs/${RUN}/outputs`, (r) =>
    r.fulfill({
      json: [
        { id: "article", node_id: "w", agent_type: "writer", kind: "text", filename: null, mime_type: null, bytes: null, created_at: "2026-10-19T10:00:40Z" },
        { id: "pdf", node_id: "w", agent_type: "writer", kind: "file", filename: "solar-in-riyadh.pdf", mime_type: "application/pdf", bytes: 21000, created_at: "2026-10-19T10:00:40Z" },
      ],
    }),
  );
  await page.route("http://api.mock/outputs/article", (r) =>
    r.fulfill({ json: { id: "article", text: `title: Solar in Riyadh\n\narticle:\n${ARTICLE}`, expires_in: 0 } }),
  );
  await page.route("http://api.mock/outputs/pdf", (r) => r.fulfill({ json: { id: "pdf", url: "http://files.test/a.pdf", expires_in: 3600 } }));
  await page.route(`http://api.mock/runs/${RUN}/nodes/w/result`, (r) =>
    r.fulfill({
      json: {
        node_id: "w",
        agent_type: "writer",
        revision: 0,
        editable: [
          { name: "title", title: "title", kind: "text", value: "Solar in Riyadh" },
          { name: "article_md", title: "article", kind: "text", value: ARTICLE },
        ],
      },
    }),
  );
  await page.route(`http://api.mock/runs/${RUN}/nodes/w/approve`, (r) => {
    decisions.push(r.request().postDataJSON());
    return r.fulfill({ status: 202, json: { run_id: RUN, status: "queued" } });
  });

  await page.goto("/login");
  await page.getByLabel("Email").fill("demo@gp.local");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Workflows" })).toBeVisible();
  await page.goto(`/runs/${RUN}`);
  return decisions;
}

test("a step's result is shown on the run page, and the person's own version is what's approved", async ({ page }) => {
  const decisions = await openRun(page);
  const review = page.getByRole("region", { name: "Writer's result" });

  await expect(page.getByText("Writer has finished. Check its result below before the run goes on.")).toBeVisible();
  await expect(review).toContainText("The sun is strong all year");
  await expect(review.getByRole("link", { name: "Open solar-in-riyadh.pdf" })).toBeVisible();
  await expect(review).toContainText("Video runs only after you approve this.");

  await review.getByRole("button", { name: "Edit" }).click();
  const article = review.getByLabel("Article");
  await article.fill("# Solar in Riyadh\n\nMy own words.");
  await review.getByRole("button", { name: "Approve my version and run Video" }).click();

  await expect.poll(() => decisions).toEqual([
    { decision: "approve", edits: { article_md: "# Solar in Riyadh\n\nMy own words." } },
  ]);
});

test("a result sent back carries the person's note", async ({ page }) => {
  const decisions = await openRun(page);
  const review = page.getByRole("region", { name: "Writer's result" });

  await review.getByRole("button", { name: "Redo with a note…" }).click();
  await review.getByLabel("What should change?").fill("Explain what the panels cost.");
  await review.getByRole("button", { name: "Redo Writer" }).click();

  await expect.poll(() => decisions).toEqual([{ decision: "redo", note: "Explain what the panels cost." }]);
});
