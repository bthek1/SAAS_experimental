import { existsSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import { join } from "node:path";
import { defineConfig, devices } from "@playwright/test";
import {
  API_PORT,
  API_URL,
  CATALOG_PORT,
  INSTANCES_DB_PORT,
  INSTANCES_PORT,
  WEB_PORT,
  WEB_URL,
} from "./e2e/integration/ports";

// Full-stack suite: both real services (catalog on FastAPI, instances on .NET) behind the
// gateway's dev router, each on a fresh database per run: catalog on SQLite, instances on a
// throwaway Postgres in Docker (it is Postgres only, #44).

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

const INSTANCES_DB = "e2e-instances-db";
const INSTANCES_DB_URL = `postgres://postgres:e2e@127.0.0.1:${INSTANCES_DB_PORT}/instances`;
const INSTANCES_BUILD = join(tmpdir(), "e2e-instances-dotnet");
// The SDK on PATH, or where README's no-sudo install puts it.
const DOTNET =
  process.env.DOTNET_ROOT ? join(process.env.DOTNET_ROOT, "dotnet")
  : existsSync(join(homedir(), ".dotnet", "dotnet")) ? join(homedir(), ".dotnet", "dotnet")
  : "dotnet";

// Gone when the run ends: SIGTERM reaches `docker run`, which passes it to the container,
// and --rm removes it. Playwright's default, SIGKILL, would leave the container running.
function instancesDatabase() {
  return {
    command:
      `docker rm -f ${INSTANCES_DB} >/dev/null 2>&1; exec docker run --rm --name ${INSTANCES_DB}` +
      ` --tmpfs /var/lib/postgresql/data -e POSTGRES_PASSWORD=e2e -e POSTGRES_DB=instances` +
      ` -p 127.0.0.1:${INSTANCES_DB_PORT}:5432 postgres:16-alpine`,
    port: INSTANCES_DB_PORT,
    reuseExistingServer: false,
    timeout: 120_000,
    gracefulShutdown: { signal: "SIGTERM" as const, timeout: 15_000 },
  };
}

// Built once per run, then migrated as soon as the database answers.
function instances(port: number) {
  const dll = join(INSTANCES_BUILD, "Instances.Api.dll");
  return {
    command:
      `${DOTNET} build instances_NET/src/Instances.Api -c Release -o ${INSTANCES_BUILD} --nologo -v q` +
      ` && until ${DOTNET} ${dll} migrate; do sleep 1; done` +
      ` && exec ${DOTNET} ${dll}`,
    cwd: "../backend",
    env: {
      SETTINGS: "e2e",
      INSTANCES_DATABASE_URL: INSTANCES_DB_URL,
      ASPNETCORE_URLS: `http://localhost:${port}`,
      DOTNET_CLI_TELEMETRY_OPTOUT: "1",
      DOTNET_NOLOGO: "1",
      Logging__LogLevel__Default: "Warning",
    },
    url: `http://localhost:${port}/internal/health/`,
    reuseExistingServer: false,
    timeout: 240_000,
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
    instancesDatabase(),
    instances(INSTANCES_PORT),
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
