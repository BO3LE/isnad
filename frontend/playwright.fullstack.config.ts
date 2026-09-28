import { defineConfig, devices } from "@playwright/test";

// A second, separate Playwright project (GP-plan W10, C7). frontend/playwright.config.ts (the
// default `npm run test:e2e`) runs against page.route mocks with no backend at all — that stays
// exactly as it is. These specs instead run against a REAL stack: frontend, api, worker, redis and
// postgres, with FAKE_ADAPTERS=true (canned agent responses, no API spend, no network). They exercise
// all three seeded template workflows end to end through the real UI: sign in, run, approve the
// gate where the template has one, and check what the run actually produced.
//
// This config does not start the stack — bring it up first with docker compose, then point
// E2E_BASE_URL / E2E_API_URL at it:
//
//   docker compose -p isnad-e2e up --build -d db redis migrate api worker frontend
//   E2E_BASE_URL=http://localhost:5173 npm run test:e2e:fullstack
//
// (see .github/workflows/ci.yml's `e2e-fullstack` job for the CI version, which uses
// API_HOST_PORT/FRONTEND_HOST_PORT so it can run alongside another stack without colliding.)
export default defineConfig({
  testDir: "./e2e-fullstack",
  // One worker container behind a single Celery process in fake mode — keep the three runs
  // sequential rather than racing them for the same worker.
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  // A full run (research → write → video encode → publish, with an approval in between) is
  // legitimately slow in CI, not flaky — give it room rather than chasing a tight timeout.
  timeout: 150_000,
  expect: { timeout: 15_000 },
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:5173",
    trace: "retain-on-failure",
    video: "retain-on-failure",
    timezoneId: "Asia/Riyadh",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
