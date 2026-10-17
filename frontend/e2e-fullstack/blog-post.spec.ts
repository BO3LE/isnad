import { expect, test } from "@playwright/test";
import { openOutputsFromCanvas, openTemplate, runToCompletion, signIn } from "./fixtures";

// GP-plan W10 (C7) — the "Blog post" template (researcher → writer) against the real stack:
// frontend, api, worker, redis, postgres, FAKE_ADAPTERS=true. No approval gate on this one.
test("Blog post: sign in, run, and the article shows up on Outputs", async ({ page }) => {
  await signIn(page);
  await openTemplate(page, "Blog post");
  await runToCompletion(page, { approve: false });
  await openOutputsFromCanvas(page);

  // Every step's raw output lands as a "Text" card (worker/store.py `save_output`), titled by the
  // agent. The writer's is the article itself — its field is titled "article" in the catalog
  // (contracts/agent_io.py WriteOutput.article_md), so the API's _as_text renders it as "article:".
  await expect(page.getByRole("heading", { name: "Text" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Researcher" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Writer" })).toBeVisible();
  await expect(page.getByText(/article:/i)).toBeVisible();

  // The Writer also saves the article as a PDF and a Word document (FR-04): two file cards.
  await expect(page.locator("h2").filter({ hasText: /^2 files$/ })).toBeVisible();
  await expect(page.getByText("PDF", { exact: true })).toBeVisible();
  await expect(page.getByText("DOCX", { exact: true })).toBeVisible();
  // Nothing is published by this template.
  await expect(page.getByRole("heading", { name: "Published" })).toHaveCount(0);
});
