import { expect, test, type Page } from "@playwright/test";

// This page has no API of its own: /api/ is answered here only for the app shell.
// These tests cover what needs a real canvas and layout, which happy-dom can't do.
async function openPage(page: Page, path = "/load-tests") {
  await page.addInitScript(() => localStorage.setItem("access_token", "test-access"));
  await page.route(
    (url) => url.pathname.startsWith("/api/"),
    (route) =>
      route.fulfill({
        json: { id: "u-1", email: "owner@example.com", first_name: "", last_name: "", status: "ok" },
      }),
  );
  await page.goto(path);
  await expect(page.getByRole("heading", { name: "Load test results" })).toBeVisible();
}

test("is a page of the app, marked in the sidebar", async ({ page }) => {
  await openPage(page);
  await expect(page.getByRole("link", { name: "Load tests" })).toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("link", { name: "Back to the app" })).toHaveCount(0);
});

test("draws charts at their full height", async ({ page }) => {
  await openPage(page);
  const canvas = page.getByRole("region", { name: "Mean latency in ms, all requests, by request rate" }).locator("canvas").first();
  await expect(canvas).toBeVisible();
  expect((await canvas.boundingBox())?.height).toBeGreaterThanOrEqual(370);
});

test("describes a chart to screen readers", async ({ page }) => {
  await openPage(page);
  await expect(page.getByLabel(/Latency against request rate for each configuration/)).toBeVisible();
});

test("shows a line chart's values in a tooltip on hover", async ({ page }) => {
  await openPage(page);
  const chart = page.getByRole("region", { name: "Mean latency in ms, all requests, by request rate" });
  await chart.locator("canvas").first().hover();
  await expect(chart).toContainText(/\d+(\.\d+)? ms Dashboards cached at [\d.]+ req\/s/);
});

test("shows a bar chart's formatted values in a tooltip on hover", async ({ page }) => {
  await openPage(page);
  const chart = page.getByRole("region", { name: "CPU at each knee, %" });
  await chart.locator("canvas").first().hover();
  await expect(chart).toContainText(/saas-app CPU\s*\d+ %/);
});

test("has its own series colours in each theme", async ({ page }) => {
  // A token with no CSS reads as an empty string, and ECharts then uses its own colours.
  // A string, because the e2e TypeScript project has no DOM types.
  const read = () =>
    page.evaluate<string[]>(`["1", "2", "3", "4", "5", "6", "7", "off"].map((slot) =>
      getComputedStyle(document.documentElement).getPropertyValue("--series-" + slot).trim())`);
  await page.emulateMedia({ colorScheme: "light" });
  await openPage(page);
  const light = await read();
  await page.emulateMedia({ colorScheme: "dark" });
  await expect(page.locator("html")).toHaveClass(/dark/);
  const dark = await read();
  for (const value of [...light, ...dark]) expect(value).toMatch(/^#[0-9a-f]{6}$/);
  expect(light[0]).not.toBe(dark[0]);
  expect(new Set(light).size).toBe(8);
});

test("keeps the tab across a reload", async ({ page }) => {
  await openPage(page);
  await page.getByRole("tab", { name: "Data growth" }).click();
  await expect(page).toHaveURL(/\?tab=growth$/);
  await page.reload();
  await expect(page.getByRole("heading", { name: "What happens as data grows" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Data growth" })).toHaveAttribute("aria-selected", "true");
});

test("opens a charted table's exact numbers on request", async ({ page }) => {
  await openPage(page, "/load-tests?tab=cache");
  const cell = page.getByRole("cell", { name: "questionnaire-submit" });
  await expect(cell).toBeHidden();
  await page.getByText("Show the table").click();
  await expect(cell).toBeVisible();
});

for (const tab of ["capacity", "cache", "growth", "fixes", "split", "mongo", "method"]) {
  test(`fits a phone without sideways scrolling: ${tab}`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openPage(page, `/load-tests?tab=${tab}`);
    const main = page.locator("main");
    const [scrollWidth, clientWidth] = await main.evaluate((m) => [m.scrollWidth, m.clientWidth]);
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth);
  });
}
