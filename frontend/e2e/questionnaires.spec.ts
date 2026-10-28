import { expect, test } from "@playwright/test";

// No backend: the public share-link endpoints are answered here, everything
// else under /api/ is 401 (anonymous visitor).
const TOKEN = "11111111-1111-1111-1111-111111111111";
const QUESTIONNAIRE = {
  id: "q-1",
  name: "",
  questionnaireTypeTitle: "Wellbeing",
  questionnaireJson: {
    pages: [{ name: "p1", elements: [{ type: "text", name: "q1", title: "How are you?" }] }],
  },
  submittedAt: null,
};

test.beforeEach(async ({ page }) => {
  await page.route(
    (url) => url.pathname.startsWith("/api/"),
    (route) => {
      const { pathname } = new URL(route.request().url());
      if (pathname === "/api/health/") return route.fulfill({ json: { status: "ok" } });
      if (pathname === `/api/questionnaires/by-token/${TOKEN}/`) {
        return route.fulfill({ json: QUESTIONNAIRE });
      }
      if (pathname === `/api/questionnaires/by-token/${TOKEN}/submit/`) {
        return route.fulfill({ json: { ...QUESTIONNAIRE, submittedAt: "2026-01-01T00:00:00Z" } });
      }
      return route.fulfill({ status: 401, json: { detail: "Not authenticated" } });
    },
  );
});

for (const path of ["/questionnaire-types", "/questionnaires", "/batteries", "/battery-types"]) {
  test(`anonymous visit to ${path} redirects to login`, async ({ page }) => {
    await page.goto(path);
    await expect(page).toHaveURL(new RegExp(`/login\\?redirect=${encodeURIComponent(path)}$`));
    await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
  });
}

test("share link renders without the app shell and submits", async ({ page }) => {
  await page.goto(`/take/${TOKEN}`);
  await expect(page.getByRole("heading", { name: "Wellbeing" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Questionnaires" })).toHaveCount(0);

  await page.getByRole("textbox").fill("Great");
  await page.getByRole("button", { name: "Complete" }).click();
  await expect(page.getByRole("heading", { name: "Thank you!" })).toBeVisible();
});

test("unknown share link shows not found", async ({ page }) => {
  await page.goto("/take/22222222-2222-2222-2222-222222222222");
  await expect(page.getByRole("heading", { name: "Questionnaire not found" })).toBeVisible();
});
