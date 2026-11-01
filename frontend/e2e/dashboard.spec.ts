import { expect, test, type Page } from "@playwright/test";

// No backend: /api/ is answered here. The dashboard endpoints return fixed data and
// record their query strings so the tests can check what the page asked for.
const TYPE = { id: "qt-1", title: "PHQ-9", questionnaireJson: {}, createdAt: "", updatedAt: "" };

const SUMMARY = {
  range: { days: 30, from: "2026-10-01T00:00:00Z", to: "2026-10-30T12:00:00Z" },
  kpis: {
    questionnairesSent: 12,
    questionnairesSubmitted: 9,
    questionnairesPending: 3,
    completionRate: 0.75,
    medianHoursToComplete: 5.5,
    batteriesTotal: 4,
    batteriesComplete: 2,
    batteriesInProgress: 1,
    batteriesNotStarted: 1,
  },
  submissionsByDay: [
    { date: "2026-10-28", count: 2 },
    { date: "2026-10-29", count: 0 },
    { date: "2026-10-30", count: 1 },
  ],
  byQuestionnaireType: [{ id: "qt-1", title: "PHQ-9", sent: 12, submitted: 9, pending: 3 }],
  byBatteryType: [{ id: "bt-1", title: "Intake", complete: 2, inProgress: 1, notStarted: 1 }],
  recentSubmissions: [],
  stalePending: [],
};

const SCORES = {
  questionnaireTypeId: "qt-1",
  metrics: [
    {
      name: "phq9_total",
      label: "PHQ-9 total",
      kind: "numeric",
      mean: 8,
      points: [
        { questionnaireId: "q-1", name: "Alex", submittedAt: "2026-10-28T10:00:00Z", value: 6 },
        { questionnaireId: "q-2", name: "Sam", submittedAt: "2026-10-30T10:00:00Z", value: 10 },
      ],
    },
  ],
};

async function mockApi(page: Page) {
  const dashboardQueries: URLSearchParams[] = [];
  await page.route(
    (url) => url.pathname.startsWith("/api/"),
    (route) => {
      const url = new URL(route.request().url());
      switch (url.pathname) {
        case "/api/health/":
          return route.fulfill({ json: { status: "ok" } });
        case "/api/token/":
          return route.fulfill({ json: { access: "test-access", refresh: "test-refresh" } });
        case "/api/accounts/me/":
          return route.fulfill({
            json: { id: "u-1", email: "owner@example.com", first_name: "", last_name: "" },
          });
        case "/api/questionnaire-types/":
          return route.fulfill({ json: [TYPE] });
        case "/api/dashboard/":
          dashboardQueries.push(url.searchParams);
          return route.fulfill({ json: SUMMARY });
        case "/api/dashboard/scores/":
          return route.fulfill({ json: SCORES });
        default:
          return route.fulfill({ status: 404, json: { detail: "Not found" } });
      }
    },
  );
  return dashboardQueries;
}

async function signIn(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill("owner@example.com");
  await page.getByLabel("Password").fill("whatever");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
}

test("login lands on the dashboard with KPIs and sized charts", async ({ page }) => {
  await mockApi(page);
  await signIn(page);

  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  const kpis = page.getByRole("list", { name: "Key figures" });
  await expect(kpis).toContainText("75%");
  await expect(kpis).toContainText("2 / 4");

  // The chart must fill its 240px plot area, not collapse (see #1).
  const canvas = page
    .getByRole("region", { name: "Submissions over time" })
    .locator("canvas")
    .first();
  await expect(canvas).toBeVisible();
  expect((await canvas.boundingBox())?.height).toBeGreaterThanOrEqual(235);
});

test("filters update the URL and the request", async ({ page }) => {
  const queries = await mockApi(page);
  await signIn(page);

  await page.getByRole("button", { name: "7 days" }).click();
  await expect(page).toHaveURL(/\/dashboard\?range=7$/);
  await expect.poll(() => queries.at(-1)?.get("days")).toBe("7");

  await page.getByRole("button", { name: "All time" }).click();
  await expect(page).toHaveURL(/range=all/);
  await expect.poll(() => queries.at(-1)?.has("days")).toBe(false);
});

test("selecting a questionnaire type shows its score charts", async ({ page }) => {
  await mockApi(page);
  await signIn(page);
  await expect(page.getByRole("region", { name: "Scores" })).toHaveCount(0);

  await page.getByLabel("Questionnaire type").selectOption({ label: "PHQ-9" });
  await expect(page).toHaveURL(/type=qt-1/);
  const total = page.getByRole("region", { name: "Scores" }).getByRole("region", {
    name: "PHQ-9 total",
  });
  await expect(total).toContainText("Average 8 across 2 responses");
  await expect(total.locator("canvas").first()).toBeVisible();
});
