import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";
import {
  PASSWORD,
  SCORED_SURVEY,
  answerScoredSurvey,
  api,
  loginAs,
  registerUser,
} from "./helpers";

// Full questionnaire flow against the real backend (issue #5). Each test owns its users.

test("login redirect returns to the page that asked for it", async ({ page, request }) => {
  const { email } = await registerUser(request);
  await page.goto("/questionnaire-types");
  await expect(page).toHaveURL(/\/login\?redirect=%2Fquestionnaire-types$/);

  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/questionnaire-types$/);
  await expect(page.getByRole("heading", { name: "Questionnaire types" })).toBeVisible();
});

test("owner builds a type in the visual and JSON editors", async ({ page, request }) => {
  await loginAs(page, request);
  await page.goto("/questionnaire-types/new");
  await page.getByLabel("Title").fill("Daily check-in");
  await page.getByRole("radio", { name: /scored check-in/i }).click();
  await page.getByRole("button", { name: /create and open editor/i }).click();
  await expect(page).toHaveURL(/\/questionnaire-types\/[0-9a-f-]+\/json$/);

  // A visual edit shows up in the JSON.
  const titleInput = page.locator("input").and(page.locator('[value="How is your mood today?"]'));
  if ((await titleInput.count()) === 0) {
    await page.getByText("How is your mood today?").first().click();
  }
  await titleInput.first().fill("How is your mood right now?");
  await page.getByRole("tab", { name: "JSON" }).click();
  await expect(page.getByLabel("Questionnaire JSON")).toHaveValue(/How is your mood right now\?/);

  // A JSON edit drives the preview, and saving persists it.
  await page.getByLabel("Questionnaire JSON").fill(JSON.stringify(SCORED_SURVEY, null, 2));
  await expect(page.getByLabel("Preview").getByText("Who is filling this in?")).toBeVisible();
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Saved", { exact: true })).toBeVisible();

  await page.reload();
  await page.getByRole("tab", { name: "JSON" }).click();
  await expect(page.getByLabel("Questionnaire JSON")).toHaveValue(/totalScore/);
});

test("respondent completes a share link once and the owner sees the score", async ({
  page,
  browser,
  request,
}) => {
  const owner = await loginAs(page, request);
  const type = await api(request, owner.access).post("/questionnaire-types/", {
    title: "Daily check-in",
    questionnaireJson: SCORED_SURVEY,
  });
  expect(type.status()).toBe(201);

  await page.goto("/questionnaires/new");
  await page.getByLabel("Questionnaire type").selectOption({ label: "Daily check-in" });
  await page.getByLabel(/respondent name/i).fill("Pat");
  await page.getByRole("button", { name: "Create share link" }).click();
  const link = await page.locator("code").first().innerText();
  expect(link).toMatch(/\/take\/[0-9a-f-]{36}$/);

  // Logged-out respondent in a separate browser context.
  const respondent = await (await browser.newContext()).newPage();
  await respondent.goto(link);
  await expect(respondent.getByRole("heading", { name: "Daily check-in" })).toBeVisible();
  await expect(respondent.getByRole("link", { name: "Questionnaires" })).toHaveCount(0);
  await answerScoredSurvey(respondent);
  await expect(respondent.getByRole("heading", { name: "Thank you!" })).toBeVisible();
  await respondent.reload();
  await expect(respondent.getByRole("heading", { name: "Already submitted" })).toBeVisible();

  await page.goto("/questionnaires");
  await page.getByRole("link", { name: "Results" }).click();
  await expect(page.getByText("Total Score")).toBeVisible();
  await expect(page.locator("main")).toContainText(/Total Score\s*7/);
  await expect(page.getByRole("region", { name: "Mood today" })).toContainText("4");

  // The real backend renders the snapshot with WeasyPrint.
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: /download pdf/i }).click(),
  ]);
  expect(download.suggestedFilename()).toMatch(/^Daily-check-in-\d{4}-\d{2}-\d{2}\.pdf$/);
  const pdfPath = await download.path();
  expect(readFileSync(pdfPath).subarray(0, 4).toString()).toBe("%PDF");
});

test("respondent steps through a battery in order", async ({ page, browser, request }) => {
  const owner = await loginAs(page, request);
  const ownerApi = api(request, owner.access);
  const ids: string[] = [];
  for (const title of ["First survey", "Second survey"]) {
    const res = await ownerApi.post("/questionnaire-types/", {
      title,
      questionnaireJson: SCORED_SURVEY,
    });
    ids.push(((await res.json()) as { id: string }).id);
  }

  await page.goto("/battery-types/new");
  await page.getByLabel("Title").fill("Intake pack");
  const add = page.getByRole("combobox", { name: /add a questionnaire type/i });
  await add.selectOption({ label: "Second survey" });
  await add.selectOption({ label: "First survey" });
  await page.getByRole("button", { name: "Move First survey up" }).click();
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page).toHaveURL(/\/battery-types$/);

  await page.goto("/batteries/new");
  await page.getByLabel("Battery type").selectOption({ label: "Intake pack" });
  await page.getByRole("button", { name: "Create share link" }).click();
  const link = await page.locator("code").first().innerText();
  await page.getByRole("link", { name: "Open battery" }).click();
  const batteryUrl = page.url();

  const respondent = await (await browser.newContext()).newPage();
  await respondent.goto(link);
  await expect(respondent.getByText("Questionnaire 1 of 2")).toBeVisible();
  await expect(respondent.getByRole("heading", { name: "First survey" })).toBeVisible();
  await answerScoredSurvey(respondent);
  await expect(respondent.getByText("Questionnaire 2 of 2")).toBeVisible();
  await expect(respondent.getByRole("heading", { name: "Second survey" })).toBeVisible();
  await answerScoredSurvey(respondent);
  await expect(respondent.getByRole("heading", { name: "All done!" })).toBeVisible();

  await page.goto(batteryUrl);
  await expect(page.getByText("Complete", { exact: true })).toBeVisible();
});

test("one user cannot see another user's questionnaires", async ({ page, request }) => {
  const userA = await registerUser(request);
  const created = await api(request, userA.access).post("/questionnaire-types/", {
    title: "Private type",
  });
  const { id } = (await created.json()) as { id: string };

  const userB = await registerUser(request);
  const asB = api(request, userB.access);
  for (const path of ["/questionnaire-types/", "/battery-types/", "/questionnaires/", "/batteries/"]) {
    expect(await (await asB.get(path)).json()).toEqual([]);
  }
  expect((await asB.get(`/questionnaire-types/${id}/`)).status()).toBe(404);

  await page.goto("/login");
  await page.evaluate((access) => localStorage.setItem("access_token", access), userB.access);
  await page.goto("/questionnaire-types");
  await expect(page.getByText("No questionnaire types yet.")).toBeVisible();
  await expect(page.getByText("Private type")).toHaveCount(0);
});
