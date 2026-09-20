import { expect, test, type Page } from "@playwright/test";

// P-09 in a real browser. Two things jsdom cannot answer by construction: whether a download that
// has no URL is still reachable by keyboard, and whether the one that does opens away from the app
// rather than navigating it away. Both were real defects found in review.

const RUN = "00000000-0000-4000-8000-0000000000dd";

const run = {
  id: RUN,
  workflow_id: "00000000-0000-4000-8000-000000000001",
  status: "succeeded",
  created_at: "2026-09-20T10:00:00Z",
  started_at: "2026-09-20T10:00:00Z",
  completed_at: "2026-09-20T10:06:12Z",
  total_nodes: 2,
  failed_nodes: 0,
  nodes: [],
};

const outputs = [
  { id: "ready", node_id: "v", agent_type: "video", kind: "file", filename: "video.mp4", mime_type: "video/mp4", bytes: 4036, created_at: "2026-09-20T10:00:00Z" },
  { id: "gone", node_id: "d", agent_type: "writer", kind: "file", filename: "article.pdf", mime_type: "application/pdf", bytes: 180000, created_at: "2026-09-20T10:00:01Z" },
];

async function openFiles(page: Page) {
  await page.route("http://api.mock/auth/dev-login", (r) => r.fulfill({ json: { access_token: "t", token_type: "bearer" } }));
  await page.route("http://api.mock/workflows", (r) => r.fulfill({ json: [] }));
  await page.route("http://api.mock/agents/catalog", (r) => r.fulfill({ json: [] }));
  await page.route(`http://api.mock/runs/${RUN}`, (r) => r.fulfill({ json: run }));
  await page.route(`http://api.mock/runs/${RUN}/outputs`, (r) => r.fulfill({ json: outputs }));
  await page.route("http://api.mock/outputs/ready", (r) =>
    r.fulfill({ json: { id: "ready", url: "http://files.test/video.mp4", expires_in: 3600 } }),
  );
  // This one has no file behind it, so the page must offer nothing rather than a dead control.
  await page.route("http://api.mock/outputs/gone", (r) => r.fulfill({ status: 404, json: { detail: "This output has no file." } }));

  await page.goto("/login");
  await page.getByLabel("Email").fill("demo@gp.local");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Workflows" })).toBeVisible();
  await page.goto(`/runs/${RUN}/outputs`);
}

test("a download opens the file instead of navigating the app away", async ({ page }) => {
  await openFiles(page);
  const download = page.getByRole("link", { name: /Download/ });
  await expect(download).toHaveAttribute("href", "http://files.test/video.mp4");
  // Files are served from another origin, where the `download` attribute is ignored: without this
  // the click replaces the app with the file.
  await expect(download).toHaveAttribute("target", "_blank");
});

test("a file with nothing behind it says so, and cannot be reached by keyboard", async ({ page }) => {
  await openFiles(page);
  await expect(page.getByText("Couldn't prepare this download.")).toBeVisible();

  // Only the file that has a URL offers a Download, and it is a real link. A dead one rendered as
  // <a href="#"> would still take focus and still activate on Enter, however disabled it looked.
  const downloads = page.locator("a").filter({ hasText: "Download" });
  await expect(downloads).toHaveCount(1);
  await expect(downloads.first()).toHaveAttribute("href", "http://files.test/video.mp4");
});
