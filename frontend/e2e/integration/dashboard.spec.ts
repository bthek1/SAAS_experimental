import { expect, test } from "@playwright/test";
import { SCORED_SURVEY, answerScoredSurvey, api, loginAs } from "./helpers";

// Dashboard against the real backend (issue #7): the owner sends one questionnaire and one
// battery, a respondent submits the questionnaire, and the dashboard counts both.

test("dashboard counts what was sent and charts the submitted score", async ({
  page,
  browser,
  request,
}) => {
  const owner = await loginAs(page, request);
  const ownerApi = api(request, owner.access);

  const type = await ownerApi.post("/questionnaire-types/", {
    title: "Daily check-in",
    questionnaireJson: SCORED_SURVEY,
  });
  expect(type.status()).toBe(201);
  const typeId = ((await type.json()) as { id: string }).id;

  const questionnaire = await ownerApi.post("/questionnaires/", {
    questionnaireTypeId: typeId,
    name: "Pat",
  });
  expect(questionnaire.status()).toBe(201);
  const { shareToken } = (await questionnaire.json()) as { shareToken: string };

  const batteryType = await ownerApi.post("/battery-types/", {
    title: "Weekly review",
    questionnaireTypeIds: [typeId],
  });
  expect(batteryType.status()).toBe(201);
  const battery = await ownerApi.post("/batteries/", {
    batteryTypeId: ((await batteryType.json()) as { id: string }).id,
    name: "Robin",
  });
  expect(battery.status()).toBe(201);

  // Logged-out respondent in a separate browser context.
  const respondent = await (await browser.newContext()).newPage();
  await respondent.goto(`/take/${shareToken}`);
  await answerScoredSurvey(respondent);
  await expect(respondent.getByRole("heading", { name: "Thank you!" })).toBeVisible();

  await page.goto("/dashboard");
  const kpis = page.getByRole("list", { name: "Key figures" });
  // The battery added a second, unsubmitted questionnaire.
  await expect(kpis.getByText("Sent", { exact: true }).locator("..")).toContainText("2");
  await expect(kpis.getByText("Submitted", { exact: true }).locator("..")).toContainText("1");
  await expect(kpis).toContainText("50%");
  await expect(kpis).toContainText("0 / 1");
  await expect(kpis).toContainText("1 not started");
  await expect(
    page.getByRole("region", { name: "Recent submissions" }).getByRole("link", { name: "Pat" }),
  ).toBeVisible();

  await page.getByLabel("Questionnaire type").selectOption({ label: "Daily check-in" });
  const score = page.getByRole("region", { name: "Scores" }).getByRole("region", {
    name: "totalScore",
  });
  await expect(score).toContainText("Average 7 across 1 responses");
  await expect(score.locator("canvas").first()).toBeVisible();
});

test.describe("in Sydney", () => {
  test.use({ timezoneId: "Australia/Sydney" });

  test("the window starts at midnight in the browser's time zone", async ({ page, request }) => {
    const summary = page.waitForResponse((r) => new URL(r.url()).pathname === "/api/dashboard/");
    await loginAs(page, request);
    await page.goto("/dashboard");

    const response = await summary;
    expect(new URL(response.url()).searchParams.get("tz")).toBe("Australia/Sydney");
    const { range } = (await response.json()) as { range: { from: string } };
    // Sydney is UTC+10 or +11, depending on daylight saving.
    expect(range.from).toMatch(/T00:00:00\+1[01]:00$/);
  });
});

test("an unknown time zone is refused", async ({ page, request }) => {
  const owner = await loginAs(page, request);
  const response = await api(request, owner.access).get("/dashboard/?tz=Not/AZone");
  expect(response.status()).toBe(400);
});
