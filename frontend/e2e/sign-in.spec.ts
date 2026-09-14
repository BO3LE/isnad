import { expect, test } from "@playwright/test";

// Runs with the whole backend stopped: every API call is answered by page.route.
test("signing in shows the workflow list", async ({ page }) => {
  await page.route("http://api.mock/auth/dev-login", (route) => route.fulfill({ json: { access_token: "t", token_type: "bearer" } }));
  await page.route("http://api.mock/workflows", (route) =>
    route.fulfill({
      json: [
        {
          id: "00000000-0000-4000-8000-000000000001",
          name: "Blog post",
          status: "draft",
          agent_types: ["researcher", "writer"],
          updated_at: "2026-09-14T10:00:00Z",
          last_run: { id: "00000000-0000-4000-8000-000000000002", status: "succeeded", created_at: "2026-09-14T10:00:00Z" },
        },
      ],
    }),
  );

  await page.goto("/login");
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page.getByRole("heading", { name: "Workflows" })).toBeVisible();
  await expect(page.getByText("Blog post")).toBeVisible();
  await expect(page.getByText("Succeeded")).toBeVisible();
});
