import { expect, test } from "@playwright/test";
import { openFreshCopy, openOutputsFromCanvas, runToCompletion, signIn } from "./fixtures";

// GP-plan W10 (C7) — the "Blog → Video → YouTube" template (researcher → writer → video →
// publisher) against the real stack. The publisher requires approval (D-08: every Distribute
// agent does), which is where FFmpeg-rendered video meets the approval gate.
test("Blog → Video → YouTube: run, approve the Publisher, and the MP4 + link show up on Outputs", async ({
  page,
}) => {
  await signIn(page);
  await openFreshCopy(page, "Blog → Video → YouTube");
  await runToCompletion(page, { approve: true });
  await openOutputsFromCanvas(page);

  // The video's output (video_path) becomes a "file" output — a FileCard under "Files", with a
  // playable <video> once its download URL resolves.
  await expect(page.getByRole("heading", { name: /^\d+ files?$/ })).toBeVisible();
  await expect(page.getByText("MP4")).toBeVisible();
  const video = page.locator("video").first();
  await expect(video).toBeVisible({ timeout: 20_000 });
  await expect(video).toHaveAttribute("src", /.+/);

  // The publisher's output (remote_url) becomes a "url" output — a Published card with a link.
  // (The card's own agent-title line is a <p>, not a heading — only the section title is.)
  const published = page.getByRole("region", { name: "Published" });
  await expect(published.getByRole("heading", { name: "Published" })).toBeVisible();
  await expect(published.getByText("Publisher")).toBeVisible();
  await expect(published.getByRole("link", { name: "Open" })).toBeVisible({ timeout: 20_000 });
});
