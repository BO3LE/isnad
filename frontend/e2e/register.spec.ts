import { expect, test } from "@playwright/test";

// Runs with the whole backend stopped: every API call is answered by page.route.
// AUTH_MODE is "dev" until D-01 lands, so register goes through /auth/dev-login.
test("creating an account lands on the workflow list", async ({ page }) => {
  await page.route("http://api.mock/auth/dev-login", (route) => route.fulfill({ json: { access_token: "t", token_type: "bearer" } }));
  await page.route("http://api.mock/workflows", (route) => route.fulfill({ json: [] }));

  await page.goto("/login");
  await page.getByRole("link", { name: "Create an account" }).click();
  await expect(page.getByRole("heading", { name: "Create account" })).toBeVisible();

  await page.getByLabel(/Email/).fill("new@kfu.edu.sa");
  await page.getByLabel(/^Password/).fill("a-long-enough-password");
  await page.getByLabel(/Confirm password/).fill("a-long-enough-password");
  await page.getByRole("button", { name: "Create account" }).click();

  await expect(page.getByRole("heading", { name: "Workflows" })).toBeVisible();
});

test("a short password is refused before anything is sent", async ({ page }) => {
  let called = false;
  await page.route("http://api.mock/auth/dev-login", (route) => {
    called = true;
    return route.fulfill({ json: { access_token: "t", token_type: "bearer" } });
  });

  await page.goto("/register");
  await page.getByLabel(/Email/).fill("new@kfu.edu.sa");
  await page.getByLabel(/^Password/).fill("short");
  await page.getByLabel(/Confirm password/).fill("short");
  await page.getByRole("button", { name: "Create account" }).click();

  await expect(page.getByText("Use at least 8 characters.")).toBeVisible();
  expect(called).toBe(false);
});
