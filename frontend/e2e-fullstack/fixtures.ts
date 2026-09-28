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
 * Duplicates the named template through the real "Duplicate" action (the card's "Actions for …"
 * menu — WorkflowCard) and opens the copy's canvas. A fresh workflow per test, so two runs of the
 * suite never share run history and a rerun is always independent (GP-plan W10 point 3).
 *
 * The POST /workflows response from the duplicate is read only to get the new workflow's id
 * reliably — clicking the new card by name would be ambiguous once the suite has run more than
 * once, since every run leaves another "<name> (copy)" card behind.
 */
export async function openFreshCopy(page: Page, templateName: string): Promise<string> {
  await expect(page.getByRole("link", { name: templateName, exact: true })).toBeVisible({ timeout: 20_000 });
  await page.getByRole("button", { name: `Actions for ${templateName}` }).click();
  const [response] = await Promise.all([
    page.waitForResponse((r) => r.request().method() === "POST" && new URL(r.url()).pathname === "/workflows"),
    page.getByRole("menuitem", { name: "Duplicate" }).click(),
  ]);
  const created = (await response.json()) as { id: string };

  await page.goto(`/workflows/${created.id}`);
  await expect(page.getByRole("button", { name: "Run", exact: true })).toBeVisible({ timeout: 20_000 });
  return created.id;
}

/** Presses Run and watches the canvas RunBar to a terminal state, approving the run's one gate
 *  through the real ApprovalDialog when the template has one. */
export async function runToCompletion(page: Page, { approve }: { approve: boolean }) {
  await page.getByRole("button", { name: "Run", exact: true }).click();

  const runBar = page.getByRole("region", { name: "Run progress" });
  await expect(runBar).toBeVisible({ timeout: 20_000 });

  if (approve) {
    // Generous: research + write run for real before the gate opens.
    await expect(page.getByRole("button", { name: "Review" })).toBeVisible({ timeout: 90_000 });
    await page.getByRole("button", { name: "Review" }).click();

    const dialog = page.getByRole("dialog", { name: "Review before it goes out" });
    await expect(dialog).toBeVisible();
    // The label is dynamic ("Approve and send to youtube", "…to 1 recipient" — ApprovalDialog.approveLabel).
    await dialog.getByRole("button", { name: /^Approve/ }).click();
    await expect(dialog).toBeHidden({ timeout: 10_000 });
  }

  // The RunBar only swaps "Cancel run" for "Back to editing" once the run has reached a terminal
  // status (RunBar.tsx `finished`). Video rendering is the slow step even in fake mode.
  await expect(page.getByRole("button", { name: "Back to editing" })).toBeVisible({ timeout: 120_000 });
  await expect(runBar.getByText("Succeeded")).toBeVisible();
}

/** The real path from a finished canvas to that run's Outputs page: exit run mode, follow the
 *  status bar's "View run" link (CanvasStatusBar), then the "Files" tab (RunTabs) — there is no
 *  shortcut link straight from the canvas to Outputs (see the W10 report for this gap). */
export async function openOutputsFromCanvas(page: Page) {
  await page.getByRole("button", { name: "Back to editing" }).click();
  await page.getByRole("link", { name: "View run" }).click();
  await expect(page.getByRole("heading", { name: "Run" })).toBeVisible({ timeout: 20_000 });
  await page.getByRole("link", { name: /^Files/ }).click();
  await expect(page.getByRole("heading", { name: "Files" })).toBeVisible({ timeout: 20_000 });
}
