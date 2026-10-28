import { defineConfig, devices } from "@playwright/test";

const PORT = 5174;
const BASE_URL = `http://localhost:${PORT}`;

// https://playwright.dev/docs/test-configuration
export default defineConfig({
  testDir: "./e2e",
  // Needs a real backend: run with `npm run e2e:integration`.
  testIgnore: "integration/**",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  // Starts Vite for the run, or reuses a dev server already on :5174 locally.
  webServer: {
    command: `npm run dev -- --port ${PORT} --strictPort`,
    url: BASE_URL,
    reuseExistingServer: !process.env.CI,
  },
});
