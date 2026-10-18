import { expect, type Page } from "@playwright/test";

// Shared steps for the fullstack template specs (GP-plan W10, C7). Every call here goes through the
// real UI against the real API — nothing is mocked. Kept out of frontend/e2e/, which is the
// mocked-API suite and must keep running with no backend at all.

export const DEMO_EMAIL = "demo@gp.local";

/** Dev sign-in (VITE_AUTH_MODE=dev, the docker-compose default): any email works, the password is
 *  ignored. Filled explicitly rather than relying on the field's dev-mode default value. */
export async function signIn(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(DEMO_EMAIL);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Workflows" })).toBeVisible({ timeout: 20_000 });
}

/**
 * Opens the named template's canvas from the workflows list.
 *
 * GP-plan W10 point 3 suggests "duplicate the template per test" for run independence — but the
 * real "Duplicate" action (WorkflowCard's "Actions for …" menu, `duplicateWorkflow` in
 * lib/api.ts) is broken against the real API for any workflow that already has saved steps,
 * which every seeded template does: `duplicateWorkflow` copies the source's graph verbatim,
 * node ids included, into `PUT /workflows/{copyId}`; the API inserts those ids as new
 * `agent_nodes` rows without regenerating them, and since `agent_nodes.id` is a primary key (not
 * scoped to a workflow) the insert collides with the original workflow's own rows and the
 * request 500s ("duplicate key value violates unique constraint pk_agent_nodes"). Confirmed
 * directly against the API (see the W10 report) — this is a real backend bug, not a test
 * mistake, and out of scope to fix here per the W10 brief (don't touch app code without a
 * forcing reason, and this one belongs to whoever owns C2/workflows).
 *
 * Independence doesn't actually need duplication, though: every Run press creates its own
 * run_id and its own outputs regardless of how many times the same workflow has run before, and
 * these specs run one at a time (`fullyParallel: false`, `workers: 1`), so two specs never touch
 * the same seeded workflow concurrently. Running the template directly is simpler and sidesteps
 * the bug entirely.
 */
export async function openTemplate(page: Page, templateName: string): Promise<void> {
  const link = page.getByRole("link", { name: templateName, exact: true });
  await expect(link).toBeVisible({ timeout: 20_000 });
  await link.click();
  await expect(page.getByRole("button", { name: "Run", exact: true })).toBeVisible({ timeout: 20_000 });
}

/** Presses Run and watches the canvas RunBar to a terminal state, approving every step that waits
 *  for a person on the way: each result to review (every template step, by default) and what a step
 *  is about to send — through the real dialogs, as a person would. */
export async function runToCompletion(page: Page) {
  await page.getByRole("button", { name: "Run", exact: true }).click();

  const runBar = page.getByRole("region", { name: "Run progress" });
  await expect(runBar).toBeVisible({ timeout: 20_000 });

  // The RunBar only swaps "Cancel run" for "Back to editing" once the run has reached a terminal
  // status (RunBar.tsx `finished`).
  const finished = page.getByRole("button", { name: "Back to editing" });
  const review = runBar.getByRole("button", { name: "Review" });
  const status = runBar.locator("p[aria-live]");
  for (let gates = 0; gates < 10; gates += 1) {
    // Generous: the steps run for real, and video rendering is the slow one even in fake mode.
    await expect(review.or(finished)).toBeVisible({ timeout: 120_000 });
    if (await finished.isVisible()) break;
    const waiting = await status.textContent();
    await review.click();
    // "Review before it goes out" for a step that sends; "Review <step>'s result" for any other.
    // Their approve buttons are worded for what happens next ("Approve and run Writer", "…send to YouTube").
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await dialog.getByRole("button", { name: /^Approve/ }).click();
    await expect(dialog).toBeHidden({ timeout: 10_000 });
    // Until the worker moves on, the bar still shows this step waiting: don't review it twice.
    await expect(status).not.toHaveText(waiting ?? "", { timeout: 120_000 });
  }

  await expect(finished).toBeVisible({ timeout: 120_000 });
  await expect(runBar.getByText("Succeeded")).toBeVisible();
}

/** The real path from a finished canvas to that run's Outputs page: exit run mode, follow the
 *  status bar's "View run" link (CanvasStatusBar), then the "Files" tab (RunTabs) — there is no
 *  shortcut link straight from the canvas to Outputs (see the W10 report for this gap). */
export async function openOutputsFromCanvas(page: Page) {
  await page.getByRole("button", { name: "Back to editing" }).click();
  // "View run" appears once the status bar's run-history query has refetched after exiting run
  // mode (useCanvasRun's `exit`) — a brief, real network round trip, not instant.
  const viewRun = page.getByRole("link", { name: "View run" });
  await expect(viewRun).toBeVisible({ timeout: 20_000 });
  await viewRun.click();
  await expect(page.getByRole("heading", { name: "Run" })).toBeVisible({ timeout: 20_000 });
  const filesTab = page.getByRole("link", { name: /^Files/ });
  await expect(filesTab).toBeVisible({ timeout: 20_000 });
  await filesTab.click();
  // exact: the page's "Files" title, not the "3 files" heading under it (names match as substrings).
  await expect(page.getByRole("heading", { name: "Files", exact: true })).toBeVisible({ timeout: 20_000 });
}
