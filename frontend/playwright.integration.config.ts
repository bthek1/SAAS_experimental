import { defineConfig, devices } from "@playwright/test";
import {
  API_PORT,
  API_URL,
  CATALOG_PORT,
  INSTANCES_PORT,
  WEB_PORT,
  WEB_URL,
} from "./e2e/integration/ports";

// Full-stack suite: both real services (catalog on FastAPI, instances on Django) behind the
// gateway's dev router, each with a fresh SQLite database per run.

function catalog(port: number) {
  return {
    command:
      "rm -f catalog/e2e.sqlite3 && uv run python -m catalog migrate" +
      ` && uv run uvicorn catalog.app:app --port ${port} --no-access-log`,
    cwd: "../backend",
    env: { SETTINGS: "e2e" },
    url: `http://localhost:${port}/internal/health/`,
    reuseExistingServer: false,
  };
}

function service(name: string, port: number) {
  return {
    command:
      `rm -f ${name}/e2e.sqlite3 && uv run python ${name}/manage.py migrate --noinput` +
      ` && uv run python ${name}/manage.py runserver ${port} --noreload`,
    cwd: "../backend",
    env: { DJANGO_SETTINGS_MODULE: "core.settings.e2e" },
    url: `http://localhost:${port}/internal/health/`,
    reuseExistingServer: false,
  };
}

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
    catalog(CATALOG_PORT),
    service("instances", INSTANCES_PORT),
    {
      // The gateway, from the same route table as nginx.
      command:
        `python3 ../infra/gateway/dev_router.py --port ${API_PORT}` +
        ` --service catalog=http://localhost:${CATALOG_PORT}` +
        ` --service instances=http://localhost:${INSTANCES_PORT}`,
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
