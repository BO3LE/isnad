import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";

// DESIGN-SYSTEM.md §22 — the canvas is a desktop tool, but everything after pressing Run has to
// work on a phone ("a URL works from a phone on mobile data", W11).
//
// This checks the two things that break first and are invisible from a desktop: a page that
// scrolls sideways, and controls too small to hit with a thumb (§13 asks for 44 px on coarse
// pointers). The layout choices in §22's table — read-only canvas, bottom-sheet drawer — are
// features rather than a pass, and are not claimed here.

const WORKFLOW = "00000000-0000-4000-8000-000000000001";
const RUN = "00000000-0000-4000-8000-000000000002";
const catalog = JSON.parse(readFileSync(new URL("../src/test/catalog.json", import.meta.url), "utf-8")) as unknown[];

const WIDTHS = [
  { name: "small phone", width: 320, height: 568 },
  { name: "phone", width: 390, height: 844 },
  { name: "md", width: 820, height: 1024 },
  { name: "lg", width: 1100, height: 900 },
  { name: "xl", width: 1440, height: 900 },
];

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
    nodes: [node("research", "researcher", 0, { topic: "Solar", num_sources: 5 }), node("write", "writer", 320)],
    edges: [{ id: "research-write", source: "research", target: "write" }],
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

const runState = {
  id: RUN,
  workflow_id: WORKFLOW,
  status: "failed",
  created_at: "2026-09-20T16:05:00Z",
  started_at: "2026-09-20T16:05:00Z",
  completed_at: "2026-09-20T16:11:02Z",
  total_nodes: 2,
  failed_nodes: 1,
  nodes: [
    nodeState("research", "researcher", "success"),
    nodeState("write", "writer", "failed", { retry_count: 3, error_message: "[attempt 1] Token revoked.\n[attempt 4] Token revoked." }),
  ],
};

async function mockApi(page: Page) {
  await page.route("http://api.mock/auth/dev-login", (r) => r.fulfill({ json: { access_token: "t", token_type: "bearer" } }));
  await page.route("http://api.mock/agents/catalog", (r) => r.fulfill({ json: catalog }));
  await page.route("http://api.mock/workflows", (r) =>
    r.fulfill({
      json: [
        {
          id: WORKFLOW,
          name: "Blog → Video → YouTube",
          status: "draft",
          agent_types: ["researcher", "writer"],
          updated_at: "2026-09-14T10:00:00Z",
          last_run: { id: RUN, status: "failed", created_at: "2026-09-20T16:05:00Z" },
        },
      ],
    }),
  );
  await page.route(`http://api.mock/workflows/${WORKFLOW}`, (r) => r.fulfill({ json: workflow }));
  await page.route(`http://api.mock/workflows/${WORKFLOW}/runs`, (r) => r.fulfill({ json: [] }));
  await page.route(`http://api.mock/runs/${RUN}`, (r) => r.fulfill({ json: runState }));
  await page.route(`http://api.mock/runs/${RUN}/logs`, (r) =>
    r.fulfill({ json: runState.nodes.map((n, i) => ({ ...n, id: `00000000-0000-4000-8000-00000000000${i}`, run_id: RUN })) }),
  );
  await page.route(`http://api.mock/runs/${RUN}/outputs`, (r) =>
    r.fulfill({ json: [{ id: "a", node_id: "write", agent_type: "writer", kind: "text", filename: null, mime_type: null, bytes: null, created_at: "2026-09-20T16:05:20Z" }] }),
  );
  await page.route("http://api.mock/outputs/a", (r) => r.fulfill({ json: { id: "a", text: "The Future of Solar Energy", expires_in: 0 } }));
}

/** How far the document overflows its own viewport, in CSS pixels. */
async function sidewaysOverflow(page: Page): Promise<number> {
  return page.evaluate(() => {
    const { documentElement } = (globalThis as unknown as {
      document: { documentElement: { scrollWidth: number; clientWidth: number } };
    }).document;
    return documentElement.scrollWidth - documentElement.clientWidth;
  });
}

const SCREENS = [
  { name: "P-01 sign in", go: async (page: Page) => page.goto("/login"), ready: (page: Page) => page.getByRole("button", { name: "Sign in" }) },
  { name: "P-03 workflows", go: async (page: Page) => page.goto("/workflows"), ready: (page: Page) => page.getByRole("heading", { name: "Workflows" }) },
  { name: "P-04 canvas", go: async (page: Page) => page.goto(`/workflows/${WORKFLOW}`), ready: (page: Page) => page.getByTestId("rf__node-research") },
  { name: "P-06 run monitor", go: async (page: Page) => page.goto(`/runs/${RUN}`), ready: (page: Page) => page.getByRole("heading", { name: "Run" }) },
  { name: "P-08 logs", go: async (page: Page) => page.goto(`/runs/${RUN}/logs`), ready: (page: Page) => page.getByRole("heading", { name: "Logs" }) },
  { name: "P-09 outputs", go: async (page: Page) => page.goto(`/runs/${RUN}/outputs`), ready: (page: Page) => page.getByRole("heading", { name: "Files" }) },
];

for (const size of WIDTHS) {
  test(`no screen scrolls sideways at ${size.name} (${size.width}px)`, async ({ page }) => {
    await page.setViewportSize({ width: size.width, height: size.height });
    await mockApi(page);
    await page.goto("/login");
    await page.getByLabel("Email").fill("demo@gp.local");
    await page.getByRole("button", { name: "Sign in" }).click();
    await expect(page.getByRole("heading", { name: "Workflows" })).toBeVisible();

    for (const screen of SCREENS) {
      await screen.go(page);
      await expect(screen.ready(page)).toBeVisible();
      // Zero, not "small": measured at every width above on every screen below, the answer is 0
      // everywhere, so a tolerance would only hide the first regression.
      expect(await sidewaysOverflow(page), `${screen.name} at ${size.width}px`).toBe(0);
    }
  });
}

/**
 * Visible controls smaller than `min` on the screens §22 says must work after a run.
 *
 * Returns the count it examined alongside the offenders, because `.all()` does not auto-wait: if
 * the page is a tick behind, it enumerates fewer controls — or none — and an empty result would
 * otherwise read as a pass.
 */
async function undersizedControls(page: Page, min: number): Promise<{ small: string[]; examined: number }> {
  const small: string[] = [];
  let examined = 0;
  for (const path of [`/runs/${RUN}`, `/runs/${RUN}/logs`, `/runs/${RUN}/outputs`]) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    // Something interactive has definitely rendered before anything is counted.
    await expect(page.getByRole("button").first()).toBeVisible();
    for (const control of await page.getByRole("button").all()) {
      examined += 1;
      if (!(await control.isVisible())) continue;
      const box = await control.boundingBox();
      if (!box) continue;
      if (box.height < min || box.width < min) {
        const name = (await control.textContent())?.trim().slice(0, 24) || "(icon)";
        small.push(`${path.split("/").pop()} "${name}" ${Math.round(box.width)}×${Math.round(box.height)}`);
      }
    }
  }
  return { small, examined };
}

async function signedIn(page: Page) {
  await mockApi(page);
  await page.goto("/login");
  await page.getByLabel("Email").fill("demo@gp.local");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Workflows" })).toBeVisible();
}

test("no control is smaller than the design system's own smallest button", async ({ page }) => {
  // §13 asks for 32 px on desktop; §14.1 defines `sm` as 28 px and uses it for table-row actions.
  // The two disagree, so this holds the line at 28 — the smallest size the design system defines —
  // and catches anything that is simply unsized. The 28-vs-32 conflict is Hassan's to settle.
  await page.setViewportSize({ width: 390, height: 844 });
  await signedIn(page);
  const { small, examined } = await undersizedControls(page, 28);
  expect(small).toEqual([]);
  // The sweep actually looked at something. Without this the test passes on an empty page.
  expect(examined).toBeGreaterThanOrEqual(9);
});

test.describe("on a touch screen", () => {
  test.use({ hasTouch: true, isMobile: true, viewport: { width: 390, height: 844 } });

  test("no control's tappable area covers another control", async ({ page }) => {
    // The assertion that matters, and the one that was missing when a blanket 44 px hit area went
    // in: it is easy to check that a control owns its own space, and the damage is always in the
    // other direction. That rule made the show-password toggle own 6 px of the password field and
    // left every React Flow control overlapping both of its neighbours by 9 px.
    await signedIn(page);
    const overlaps: string[] = [];
    let examined = 0;

    for (const path of ["/login", `/workflows/${WORKFLOW}`, `/runs/${RUN}`, `/runs/${RUN}/logs`, `/runs/${RUN}/outputs`]) {
      await page.goto(path);
      await page.waitForLoadState("networkidle");

      const found = await page.evaluate(() => {
        type Box = { left: number; top: number; right: number; bottom: number };
        type El = {
          getBoundingClientRect(): Box & { width: number; height: number };
          getAttribute(n: string): string | null;
          textContent: string | null;
          tagName: string;
          contains(o: unknown): boolean;
        };
        const doc = (globalThis as unknown as {
          document: {
            querySelectorAll(s: string): ArrayLike<El>;
            defaultView: { getComputedStyle(e: El, pseudo?: string): { getPropertyValue(p: string): string } };
          };
        }).document;

        const controls = Array.from(doc.querySelectorAll('button, [role="button"], a[href], input, textarea, select'));
        const visible = controls.filter((el) => {
          const r = el.getBoundingClientRect();
          return r.width > 0 && r.height > 0;
        });

        const name = (el: El) =>
          `${el.tagName.toLowerCase()}:${el.getAttribute("aria-label") ?? el.getAttribute("type") ?? ((el.textContent ?? "").trim().slice(0, 18) || "?")}`;

        /** The area a press on this control actually claims, including any `::after` overlay. */
        const claimed = (el: El) => {
          const r = el.getBoundingClientRect();
          // The overlay's own box, not the element's: a hit area given by `::after { min-width }`
          // is invisible to `getComputedStyle(el)` and the first version of this read that and so
          // could never see an inflated area at all.
          const after = doc.defaultView.getComputedStyle(el, "::after");
          const hasOverlay = after.getPropertyValue("content") !== "none";
          const minW = hasOverlay ? parseFloat(after.getPropertyValue("min-width")) || 0 : 0;
          const minH = hasOverlay ? parseFloat(after.getPropertyValue("min-height")) || 0 : 0;
          const w = Math.max(r.width, minW);
          const h = Math.max(r.height, minH);
          const cx = (r.left + r.right) / 2;
          const cy = (r.top + r.bottom) / 2;
          return { left: cx - w / 2, right: cx + w / 2, top: cy - h / 2, bottom: cy + h / 2 };
        };

        const out: string[] = [];
        for (const a of visible) {
          const drawn = a.getBoundingClientRect();
          const ab = claimed(a);
          // Only areas that grew past what is drawn. A control deliberately placed on top of
          // another — the show-password toggle sits inside its field — overlaps by design, and
          // whether it steals the field's taps is what the elementFromPoint test below answers.
          const grew = ab.right - ab.left > drawn.width + 1 || ab.bottom - ab.top > drawn.height + 1;
          if (!grew) continue;

          for (const b of visible) {
            if (a === b || a.contains(b) || b.contains(a)) continue;
            const bb = b.getBoundingClientRect();
            const w = Math.min(ab.right, bb.right) - Math.max(ab.left, bb.left);
            const h = Math.min(ab.bottom, bb.bottom) - Math.max(ab.top, bb.top);
            if (w > 1 && h > 1) out.push(`${name(a)} (${Math.round(drawn.width)}x${Math.round(drawn.height)}) covers ${Math.round(w)}x${Math.round(h)}px of ${name(b)}`);
          }
        }
        return out;
      });

      overlaps.push(...found.map((f) => `${path} — ${f}`));
      examined += found.length >= 0 ? await page.getByRole("button").count() : 0;
    }

    expect(overlaps).toEqual([]);
    expect(examined).toBeGreaterThanOrEqual(12);
  });
});

test.describe("controls that sit inside a text field", () => {
  test.use({ hasTouch: true, isMobile: true, viewport: { width: 390, height: 844 } });

  test("never capture a tap meant for the field", async ({ page }) => {
    // §13's 44 px target is NOT met (see index.css). The attempt to meet it with an invisible hit
    // area grew *every* button, including the ones drawn on top of an input: the show-password
    // toggle then captured taps 6 px inside the password field, so aiming at the end of your own
    // password revealed it in plaintext. This pins that exact regression; the sweep above is the
    // general guard.
    await page.goto("/login");
    const field = page.locator('input[type="password"]').first();
    await field.waitFor();
    const fieldBox = (await field.boundingBox())!;
    const toggle = page.getByRole("button", { name: /Show password/ });
    const toggleBox = (await toggle.boundingBox())!;

    const capturesFrom = await page.evaluate(
      ([left, right, y]) => {
        const doc = (globalThis as unknown as {
          document: { elementFromPoint(a: number, b: number): { closest(s: string): unknown } | null };
        }).document;
        for (let x = left; x <= right; x += 1) {
          const el = doc.elementFromPoint(x, y);
          if (el && el.closest('button[aria-label="Show password"]')) return x;
        }
        return null;
      },
      [Math.round(fieldBox.x), Math.round(fieldBox.x + fieldBox.width), Math.round(fieldBox.y + fieldBox.height / 2)],
    );

    // It may own every pixel it is drawn on, and not one pixel more.
    expect(capturesFrom).not.toBeNull();
    expect(capturesFrom!).toBeGreaterThanOrEqual(Math.round(toggleBox.x));
  });
});
