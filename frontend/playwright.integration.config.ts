import { defineConfig, devices } from "@playwright/test";
import { API_PORT, API_URL, WEB_PORT, WEB_URL } from "./e2e/integration/ports";

// Full-stack suite: a real Django backend with a fresh SQLite database per run.

// https://playwright.dev/docs/test-webserver#multiple-web-servers
export default defineConfig({
  testDir: "./e2e/integration",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: WEB_URL,
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  // Never reuse servers: a reused backend would carry data over from an earlier run.
  webServer: [
    {
      command:
        "rm -f e2e.sqlite3 && uv run python manage.py migrate --noinput" +
        ` && uv run python manage.py runserver ${API_PORT} --noreload`,
      cwd: "../backend",
      env: { DJANGO_SETTINGS_MODULE: "core.settings.e2e" },
      url: `${API_URL}/api/health/`,
      reuseExistingServer: false,
    },
    {
      command: `npm run dev -- --port ${WEB_PORT} --strictPort`,
      env: { VITE_API_BASE_URL: API_URL },
      url: WEB_URL,
      reuseExistingServer: false,
    },
  ],
});
