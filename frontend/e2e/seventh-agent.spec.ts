import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";

// AT-12 — a seventh agent must appear with a working form and **zero files changed under
// frontend/**. This file is that test at the frontend boundary: the app is handed a catalog it has
// never seen, containing an agent nothing in the codebase mentions, and has to build the palette
// entry, the node, the settings form, the handover labels and the run's step list from the
// manifest alone.
//
// The other half of AT-12 — registering the agent for real, restarting the worker and checking
// `git status` — is a stack procedure, recorded in docs; this is the part that runs on every PR.

const WORKFLOW_ID = "00000000-0000-4000-8000-000000000002";
const RUN_ID = "00000000-0000-4000-8000-0000000000bb";
const real = JSON.parse(readFileSync(new URL("../src/test/catalog.json", import.meta.url), "utf-8")) as unknown[];

// Nothing in src/ knows this name, this icon or these fields.
const TRANSLATOR = {
  name: "translator",
  title: "Translator",
  description: "Turns an article into another language.",
  icon: "languages",
  family: "create",
  version: "1.0.0",
  requires_approval: false,
  config_schema: {
    type: "object",
    title: "Translator",
    additionalProperties: false,
    required: ["target_language"],
    properties: {
      target_language: {
        type: "string",
        title: "Target language",
        description: "Which language to translate into.",
        enum: ["ar", "fr", "ja"],
        "x-enum-labels": { ar: "Arabic", fr: "French", ja: "Japanese" },
      },
      formal: { type: "boolean", title: "Formal register", default: true },
    },
  },
  inputs: [
    { name: "article", accepts: ["article"], required: true, settable: false },
    { name: "target_language", accepts: ["target_language"], required: true, settable: true },
  ],
  outputs: [{ name: "translation", title: "translation" }],
};

const catalog = [...real, TRANSLATOR];

const workflow = {
  id: WORKFLOW_ID,
  name: "Write → Translate",
  status: "draft",
  created_at: "2026-09-14T10:00:00Z",
  updated_at: "2026-09-14T10:00:00Z",
  graph: {
    nodes: [
      { id: "write", agent_type: "writer", position: { x: 0, y: 128 }, configuration: {}, requires_approval: false },
      { id: "translate", agent_type: "translator", position: { x: 320, y: 128 }, configuration: {}, requires_approval: false },
    ],
    edges: [{ id: "write-translate", source: "write", target: "translate" }],
  },
};

const runState = (status: string, statuses: string[]) => ({
  id: RUN_ID,
  workflow_id: WORKFLOW_ID,
  status,
  created_at: new Date().toISOString(),
  started_at: new Date().toISOString(),
  completed_at: null,
  total_nodes: 2,
  failed_nodes: 0,
  nodes: ["write", "translate"].map((id, i) => ({
    node_id: id,
    agent_type: id === "write" ? "writer" : "translator",
    status: statuses[i],
    retry_count: 0,
    started_at: new Date().toISOString(),
    completed_at: null,
    duration_ms: statuses[i] === "success" ? 1200 : null,
    error_message: null,
  })),
});

async function signIn(page: Page) {
  await page.route("http://api.mock/auth/dev-login", (route) => route.fulfill({ json: { access_token: "t", token_type: "bearer" } }));
  await page.route("http://api.mock/agents/catalog", (route) => route.fulfill({ json: catalog }));
  await page.route("http://api.mock/workflows", (route) => route.fulfill({ json: [] }));
  await page.goto("/login");
  await page.getByLabel("Email").fill("demo@gp.local");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Workflows" })).toBeVisible();
}

test("a seventh agent builds its own palette entry, node and settings form", async ({ page }) => {
  const puts: { graph: { nodes: { id: string; configuration: Record<string, unknown> }[] } }[] = [];
  await signIn(page);
  await page.route(`http://api.mock/workflows/${WORKFLOW_ID}`, (route) => {
    if (route.request().method() === "PUT") puts.push(route.request().postDataJSON());
    return route.fulfill({ json: workflow });
  });
  await page.route(`http://api.mock/workflows/${WORKFLOW_ID}/runs`, (route) => route.fulfill({ json: [] }));
  await page.route(`http://api.mock/workflows/${WORKFLOW_ID}/validate`, (route) => route.fulfill({ json: { valid: true, issues: [] } }));
  await page.goto(`/workflows/${WORKFLOW_ID}`);

  // It is in the palette, under the family its manifest claims, with its own description.
  const palette = page.getByRole("complementary", { name: "Agents" });
  await expect(palette.getByRole("region", { name: "CREATE" }).getByRole("button", { name: /Translator/ })).toBeVisible();
  await expect(palette.getByText("Turns an article into another language.")).toBeVisible();

  // It is on the canvas, titled from the manifest.
  const step = page.locator(".react-flow__node").filter({ hasText: "Translator" });
  await expect(step).toContainText("translator · Step 2");
  // Its required setting is unset, so the node says so — from the schema, not from a rule about it.
  await expect(step).toContainText("Missing: target language");

  // Its form is built from its own schema: the three-option enum became a choice carrying the
  // labels the manifest published, and the boolean a switch showing its default.
  await step.click();
  const drawer = page.getByRole("complementary", { name: "Translator settings" });
  await expect(drawer.getByText("Which language to translate into.")).toBeVisible();
  const choice = drawer.getByRole("radiogroup", { name: "Target language" });
  await expect(choice.getByRole("radio", { name: "Arabic" })).toBeVisible();
  await expect(choice.getByRole("radio", { name: "Japanese" })).toBeVisible();
  await expect(drawer.getByRole("switch", { name: "Formal register" })).toBeChecked();

  await choice.getByRole("radio", { name: "Arabic" }).click();
  await expect.poll(() => puts.length).toBeGreaterThan(0);
  expect(puts.at(-1)!.graph.nodes.find((n) => n.id === "translate")!.configuration).toEqual({ target_language: "ar" });

  // Its unsettable input is reported as coming from an earlier step, from its own `inputs`.
  await expect(drawer.getByText("Needs article from an earlier step")).toBeVisible();
});

test("a seventh agent lists itself on the run monitor", async ({ page }) => {
  await signIn(page);
  let state = runState("running", ["success", "running"]);
  await page.route(`http://api.mock/runs/${RUN_ID}`, (route) => route.fulfill({ json: state }));
  await page.goto(`/runs/${RUN_ID}`);

  await expect(page.getByText("Step 2: Translator")).toBeVisible();
  await expect(page.getByText("1 of 2 steps")).toBeVisible();
  // The bar has to agree with the count: ProgressBar takes 0-1, and 100 would read as full.
  await expect(page.getByRole("progressbar", { name: "Steps finished" })).toHaveAttribute("aria-valuenow", "50");

  // AT-07 on this page: the step moves on without a refresh.
  state = runState("succeeded", ["success", "success"]);
  await expect(page.getByText("Every step finished.")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText("2 of 2 steps")).toBeVisible();
  await expect(page.getByRole("progressbar", { name: "Steps finished" })).toHaveAttribute("aria-valuenow", "100");
});
