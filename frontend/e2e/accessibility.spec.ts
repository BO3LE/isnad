import { readFileSync } from "node:fs";
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

// DESIGN-SYSTEM.md §13 — Isnad targets WCAG 2.1 AA on every screen, and §13's own testing table
// asks for "@axe-core/playwright inside the Playwright E2E suite — fail on serious/critical".
// This is that check. It runs against the production build, like the rest of the suite.
//
// Automated rules cannot see everything — focus order, sensible labels and whether a live region
// says anything useful are all still manual — but they catch the whole class of defect that is
// invisible until someone tries to use the product with a keyboard or a screen reader.

const WORKFLOW = "00000000-0000-4000-8000-000000000001";
const RUN = "00000000-0000-4000-8000-000000000002";
const catalog = JSON.parse(readFileSync(new URL("../src/test/catalog.json", import.meta.url), "utf-8")) as unknown[];

const node = (id: string, agent_type: string, x: number, configuration: Record<string, unknown> = {}) => ({
  id,
  agent_type,
  position: { x, y: 120 },
  configuration,
  requires_approval: agent_type === "publisher",
});

const workflow = {
  id: WORKFLOW,
  name: "Blog → Video → YouTube",
  status: "draft",
  created_at: "2026-09-14T10:00:00Z",
  updated_at: "2026-09-14T10:00:00Z",
  graph: {
    nodes: [
      node("research", "researcher", 0, { topic: "Solar energy", num_sources: 5 }),
      node("write", "writer", 320, { length: "short", style: "conversational", format: "video_script" }),
      node("publish", "publisher", 640, { platform: "youtube", privacy: "unlisted" }),
    ],
    edges: [
      { id: "research-write", source: "research", target: "write" },
      { id: "write-publish", source: "write", target: "publish" },
    ],
  },
};

const nodeState = (node_id: string, agent_type: string, status: string, over: Record<string, unknown> = {}) => ({
  node_id,
  agent_type,
  status,
  retry_count: 0,
  started_at: "2026-09-20T16:05:02Z",
  completed_at: "2026-09-20T16:05:20Z",
  duration_ms: 18400,
  error_message: null,
  ...over,
});

// A run with something of everything on it: a success, a failure carrying retries, and a skip.
const runState = {
  id: RUN,
  workflow_id: WORKFLOW,
  status: "failed",
  created_at: "2026-09-20T16:05:00Z",
  started_at: "2026-09-20T16:05:00Z",
  completed_at: "2026-09-20T16:11:02Z",
  total_nodes: 3,
  failed_nodes: 1,
  nodes: [
    nodeState("research", "researcher", "success"),
    nodeState("write", "writer", "success", { duration_ms: 42100 }),
    nodeState("publish", "publisher", "failed", {
      retry_count: 3,
      error_message: "[attempt 1] Token revoked.\n[attempt 2] Token revoked.\n[attempt 3] Token revoked.\n[attempt 4] Token revoked.",
    }),
  ],
};

const logs = runState.nodes.map((n, i) => ({ ...n, id: `00000000-0000-4000-8000-00000000000${i}`, run_id: RUN }));

const outputs = [
  { id: "article", node_id: "write", agent_type: "writer", kind: "text", filename: null, mime_type: null, bytes: null, created_at: "2026-09-20T16:05:20Z" },
  { id: "clip", node_id: "write", agent_type: "writer", kind: "file", filename: "video.mp4", mime_type: "video/mp4", bytes: 4036, created_at: "2026-09-20T16:05:21Z" },
];

async function mockApi(page: Page) {
  await page.route("http://api.mock/auth/dev-login", (r) => r.fulfill({ json: { access_token: "t", token_type: "bearer" } }));
  await page.route("http://api.mock/auth/register", (r) => r.fulfill({ json: { access_token: "t", token_type: "bearer" } }));
  await page.route("http://api.mock/agents/catalog", (r) => r.fulfill({ json: catalog }));
  await page.route("http://api.mock/workflows", (r) =>
    r.fulfill({
      json: [
        {
          id: WORKFLOW,
          name: "Blog → Video → YouTube",
          status: "draft",
          agent_types: ["researcher", "writer", "publisher"],
          updated_at: "2026-09-14T10:00:00Z",
          last_run: { id: RUN, status: "failed", created_at: "2026-09-20T16:05:00Z" },
        },
      ],
    }),
  );
  await page.route(`http://api.mock/workflows/${WORKFLOW}`, (r) => r.fulfill({ json: workflow }));
  await page.route(`http://api.mock/workflows/${WORKFLOW}/runs`, (r) => r.fulfill({ json: [{ id: RUN, status: "failed", created_at: "2026-09-20T16:05:00Z", completed_at: "2026-09-20T16:11:02Z", reason: null }] }));
  await page.route(`http://api.mock/workflows/${WORKFLOW}/validate`, (r) => r.fulfill({ json: { valid: true, issues: [] } }));
  await page.route(`http://api.mock/runs/${RUN}`, (r) => r.fulfill({ json: runState }));
  await page.route(`http://api.mock/runs/${RUN}/logs`, (r) => r.fulfill({ json: logs }));
  await page.route(`http://api.mock/runs/${RUN}/outputs`, (r) => r.fulfill({ json: outputs }));
  await page.route("http://api.mock/outputs/article", (r) => r.fulfill({ json: { id: "article", text: "The Future of Solar Energy", expires_in: 0 } }));
  await page.route("http://api.mock/outputs/clip", (r) => r.fulfill({ json: { id: "clip", url: "http://api.mock/files/video.mp4", expires_in: 3600 } }));
}

async function signIn(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill("demo@gp.local");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Workflows" })).toBeVisible();
}

/**
 * Serious and critical violations on the page as it currently stands.
 *
 * Only those two levels fail the build, as §13's testing table specifies — "minor" and "moderate"
 * include advisory rules that would make this a nagging gate rather than a trustworthy one.
 */
/**
 * Rules axe could not finish evaluating, and that are known to be unanswerable here rather than
 * unexamined. Each needs a reason: an `incomplete` is a rule that ran and gave up, and the first
 * version of this gate discarded all of them — which is exactly where axe had already put an
 * orphaned `role="tabpanel"` at critical impact.
 */
const ACCEPTED_INCOMPLETE: Record<string, string> = {
  // Two different causes, both measured rather than assumed:
  //
  // On the auth pages the decorative grain overlay (`.grain::after`) sits between axe's sampler
  // and the gradient behind it. Reading the real composited pixels gives 12.57 : 1 for the
  // headline and 11.08 : 1 for the subhead, against 12.74 and 11.18 with the grain removed — the
  // overlay moves contrast by about 0.15 of a ratio point on text already far above the 4.5 : 1
  // threshold, and both elements sit inside an `aria-hidden` decorative aside anyway.
  //
  // On the outputs page the video card "contains an image node" (the poster frame), which axe
  // also cannot sample through. §13's contrast table is measured by hand against the tokens.
  "color-contrast": "axe cannot sample a background through the grain overlay or a video poster",
  // A generated video has no caption track and never will — there is no captioning step in the
  // pipeline. §13 names the narration script as the text alternative instead, and the card now
  // carries it (`aria-describedby` on the video, expandable text below it).
  "video-caption": "no caption track exists; §13's text alternative is the narration script, which the card shows",
};

async function axeRun(page: Page) {
  return new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
}

const describe = (v: { id: string; impact?: string | null; help: string; nodes: { target: unknown[] }[] }) => ({
  id: v.id,
  impact: v.impact,
  help: v.help,
  nodes: v.nodes.map((n) => n.target.join(" ")).slice(0, 4),
});

/**
 * Serious and critical problems on the page as it currently stands — both the ones axe is sure
 * about and the ones it could not finish, minus the handful justified above.
 *
 * Only those two impact levels fail the build, as §13's testing table specifies; "minor" and
 * "moderate" include advisory rules that would make this a nagging gate rather than a trustworthy
 * one. I re-ran axe with no tag filter at all and the serious/critical set was identical.
 */
async function seriousViolations(page: Page) {
  const { violations, incomplete } = await axeRun(page);
  const bad = (v: { impact?: string | null }) => v.impact === "serious" || v.impact === "critical";
  return [
    ...violations.filter(bad).map(describe),
    ...incomplete.filter(bad).filter((v) => !(v.id in ACCEPTED_INCOMPLETE)).map(describe),
  ];
}

test.describe("WCAG 2.1 AA — no serious or critical violations", () => {
  test("P-01 sign in", async ({ page }) => {
    await mockApi(page);
    await page.goto("/login");
    await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
    expect(await seriousViolations(page)).toEqual([]);
  });

  test("P-02 register", async ({ page }) => {
    await mockApi(page);
    await page.goto("/register");
    await expect(page.getByRole("button", { name: /Create/ })).toBeVisible();
    expect(await seriousViolations(page)).toEqual([]);
  });

  test("P-03 workflows", async ({ page }) => {
    await mockApi(page);
    await signIn(page);
    expect(await seriousViolations(page)).toEqual([]);
  });

  test("P-04 canvas", async ({ page }) => {
    await mockApi(page);
    await signIn(page);
    await page.goto(`/workflows/${WORKFLOW}`);
    await expect(page.getByTestId("rf__node-research")).toBeVisible();
    expect(await seriousViolations(page)).toEqual([]);
  });

  test("P-04 canvas with a step's settings open", async ({ page }) => {
    await mockApi(page);
    await signIn(page);
    await page.goto(`/workflows/${WORKFLOW}`);
    await page.getByTestId("rf__node-write").click();
    await expect(page.getByRole("complementary", { name: "Writer settings" })).toBeVisible();
    expect(await seriousViolations(page)).toEqual([]);
  });

  test("P-04 drawer showing a step that made exactly one thing", async ({ page }) => {
    // The single-output case renders no tablist, and the panel attributes have to disappear with
    // it. This was a real orphan `role="tabpanel"` — no name, no owning tablist, a stray tab stop
    // — and axe reported it as `incomplete`, which the first version of this gate threw away.
    await mockApi(page);
    await page.route(`http://api.mock/runs/${RUN}/outputs`, (r) => r.fulfill({ json: [outputs[0]] }));
    await signIn(page);
    await page.goto(`/workflows/${WORKFLOW}`);
    await page.getByTestId("rf__node-write").click();
    await page.getByRole("tab", { name: "Last output" }).click();
    await expect(page.getByText("The Future of Solar Energy")).toBeVisible();
    expect(await seriousViolations(page)).toEqual([]);
  });

  test("P-06 run monitor", async ({ page }) => {
    await mockApi(page);
    await signIn(page);
    await page.goto(`/runs/${RUN}`);
    await expect(page.getByRole("heading", { name: "Run" })).toBeVisible();
    expect(await seriousViolations(page)).toEqual([]);
  });

  test("P-08 logs", async ({ page }) => {
    await mockApi(page);
    await signIn(page);
    await page.goto(`/runs/${RUN}/logs`);
    await expect(page.getByRole("heading", { name: "Logs" })).toBeVisible();
    expect(await seriousViolations(page)).toEqual([]);
  });

  test("P-08 logs with a step expanded", async ({ page }) => {
    await mockApi(page);
    await signIn(page);
    await page.goto(`/runs/${RUN}/logs`);
    await page.getByRole("button", { name: /Show details for Publisher/ }).click();
    await expect(page.locator('[id^="log-detail-"]')).toBeVisible();
    expect(await seriousViolations(page)).toEqual([]);
  });

  test("P-09 outputs", async ({ page }) => {
    await mockApi(page);
    await signIn(page);
    await page.goto(`/runs/${RUN}/outputs`);
    await expect(page.getByRole("heading", { name: "Files" })).toBeVisible();
    expect(await seriousViolations(page)).toEqual([]);
  });

  test("not found", async ({ page }) => {
    await mockApi(page);
    await signIn(page);
    await page.goto("/nothing-here");
    expect(await seriousViolations(page)).toEqual([]);
  });
});

/**
 * Every `aria-controls` / `aria-labelledby` / `aria-describedby` that points at nothing.
 *
 * Stronger than axe here, which reports a missing target only as `incomplete`, and it is the check
 * that would have found the orphaned tabpanel directly instead of by inference. A reference that
 * resolves nowhere tells a screen reader to go somewhere that does not exist.
 */
async function danglingReferences(page: Page): Promise<string[]> {
  return page.evaluate((deferred: string[]) => {
    type El = { tagName: string; getAttribute(n: string): string | null };
    const doc = (globalThis as unknown as {
      document: { querySelectorAll(s: string): ArrayLike<El>; getElementById(id: string): unknown };
    }).document;
    const out: string[] = [];
    for (const attr of ["aria-controls", "aria-labelledby", "aria-describedby"]) {
      for (const el of Array.from(doc.querySelectorAll(`[${attr}]`))) {
        for (const id of (el.getAttribute(attr) ?? "").split(/\s+/).filter(Boolean)) {
          if (doc.getElementById(id)) continue;
          // `aria-controls` pointing at content that has not been rendered yet is deliberate: a
          // closed disclosure and an unselected tab both defer their panel (see Tabs.tsx).
          //
          // `aria-labelledby` and `aria-describedby` get no such allowance. They sit on something
          // that IS on screen and name what it is — an element naming itself after nothing is the
          // orphaned tabpanel this sweep exists to catch, so the allowlist must not cover it.
          if (attr === "aria-controls" && deferred.some((prefix) => id.startsWith(prefix))) continue;
          out.push(`${el.tagName.toLowerCase()}[${attr}="${id}"]`);
        }
      }
    }
    return out;
  }, ["step-detail-", "log-detail-", "log-card-", "step-panels-panel-", "what-this-step-made-panel-", "what-this-run-made-panel-"]);
}

test.describe("aria references resolve", () => {
  for (const screen of [
    { name: "canvas with settings open", go: async (page: Page) => { await page.goto(`/workflows/${WORKFLOW}`); await page.getByTestId("rf__node-write").click(); await expect(page.getByRole("complementary", { name: "Writer settings" })).toBeVisible(); } },
    {
      // The state the orphaned tabpanel lived in: one output, so no tablist renders. Without this
      // screen the sweep is correct and still sees nothing — the defect is simply not on any of
      // the other pages.
      name: "drawer showing a step that made one thing",
      only: [outputs[0]],
      go: async (page: Page) => {
        await page.goto(`/workflows/${WORKFLOW}`);
        await page.getByTestId("rf__node-write").click();
        await page.getByRole("tab", { name: "Last output" }).click();
        await expect(page.getByText("The Future of Solar Energy")).toBeVisible();
      },
    },
    { name: "logs with a step expanded", go: async (page: Page) => { await page.goto(`/runs/${RUN}/logs`); await page.getByRole("button", { name: /Show details for Publisher/ }).click(); await expect(page.locator('[id^="log-detail-"]')).toBeVisible(); } },
    { name: "outputs", go: async (page: Page) => { await page.goto(`/runs/${RUN}/outputs`); await expect(page.getByRole("heading", { name: "Files" })).toBeVisible(); } },
    { name: "run monitor", go: async (page: Page) => { await page.goto(`/runs/${RUN}`); await expect(page.getByRole("heading", { name: "Run" })).toBeVisible(); } },
  ]) {
    test(screen.name, async ({ page }) => {
      await mockApi(page);
      if ("only" in screen && screen.only) {
        await page.route(`http://api.mock/runs/${RUN}/outputs`, (r) => r.fulfill({ json: screen.only }));
      }
      await signIn(page);
      await screen.go(page);
      expect(await danglingReferences(page)).toEqual([]);
    });
  }
});

test("a viewer who asks for stillness gets it — and there was motion to stop", async ({ page }) => {
  // §12 rule 1: "every looping animation stops". A run in flight spins its status chip forever,
  // which is the thing to silence. The first half of this test exists because the second half is
  // worthless without it: on a finished run there is nothing looping, and "no loops found" would
  // pass against an app with no reduced-motion support at all.
  await mockApi(page);
  await page.route(`http://api.mock/runs/${RUN}`, (r) =>
    r.fulfill({
      json: {
        ...runState,
        status: "running",
        completed_at: null,
        nodes: [nodeState("research", "researcher", "success"), nodeState("write", "writer", "running", { completed_at: null, duration_ms: null })],
      },
    }),
  );
  await signIn(page);

  const loopsOnPage = () =>
    page.evaluate(() => {
      // e2e compiles without the DOM lib (tsconfig.node.json), so the shape is declared inline.
      type El = { tagName: string };
      type Style = { animationName: string; animationIterationCount: string; animationDuration: string };
      const doc = (globalThis as unknown as {
        document: { querySelectorAll(s: string): ArrayLike<El>; defaultView: { getComputedStyle(e: El): Style } };
      }).document;
      const out: string[] = [];
      for (const el of Array.from(doc.querySelectorAll("*"))) {
        const style = doc.defaultView.getComputedStyle(el);
        if (style.animationName === "none") continue;
        const forever = style.animationIterationCount.split(",").some((c) => c.trim() === "infinite");
        const slow = style.animationDuration.split(",").some((d) => parseFloat(d) > 0.05);
        if (forever && slow) out.push(`${el.tagName.toLowerCase()} ${style.animationName}`);
      }
      return out;
    });

  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.goto(`/runs/${RUN}`);
  await expect(page.getByRole("heading", { name: "Run" })).toBeVisible();
  await expect.poll(async () => (await loopsOnPage()).length).toBeGreaterThan(0);

  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto(`/runs/${RUN}`);
  await expect(page.getByRole("heading", { name: "Run" })).toBeVisible();
  expect(await loopsOnPage()).toEqual([]);
});
