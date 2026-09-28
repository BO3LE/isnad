import { expect, test } from "@playwright/test";
import { DEMO_EMAIL, openOutputsFromCanvas, openTemplate, runToCompletion, signIn } from "./fixtures";

// GP-plan W10 (C7) — the "Research → PDF → Email" template (researcher → writer → email) against
// the real stack. The email step requires approval (D-08).
//
// UI gap (documented rather than faked, per the W10 instructions): EmailOutput
// (contracts/agent_io.py) has message_id, sent_at and recipients — none of those keys end in
// "_path"/"_paths" or are named "remote_url", so worker/store.py's save_output never creates a
// "file" or "url" AgentOutput for it. Every node's raw output is still recorded as a "text"
// output regardless (save_output always adds one), so the email step DOES appear on Outputs, but
// only as a generic "Text" card with its raw fields rendered as words — there is no distinct
// "sent to demo@gp.local" link or file card the way the video template gets one for its publish
// step. This test asserts exactly that: the email step shows up under "Text", with the recipient
// readable in it, and nothing under "Published" or "Files".
test("Research → PDF → Email: run, approve the Email step, and it shows up on Outputs as text (no link card — see note above)", async ({
  page,
}) => {
  await signIn(page);
  await openTemplate(page, "Research → PDF → Email");
  await runToCompletion(page, { approve: true });
  await openOutputsFromCanvas(page);

  await expect(page.getByRole("heading", { name: "Text" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Researcher" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Writer" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Email" })).toBeVisible();
  // EmailOutput.recipients, rendered generically by the API's _as_text.
  await expect(page.getByText(new RegExp(DEMO_EMAIL.replace(".", "\\.")))).toBeVisible();

  // The gap: no Published or Files section for this template.
  await expect(page.getByRole("heading", { name: "Published" })).toHaveCount(0);
  await expect(page.locator("h2").filter({ hasText: /^\d+ files?$/ })).toHaveCount(0);
});
