import { expect, test } from "@playwright/test";
import { API_URL } from "./ports";

// Runs against the real backend started by playwright.integration.config.ts.
// Each test registers its own user, so tests stay independent under fullyParallel.
const PASSWORD = "e2e-password-123";

function uniqueEmail() {
  return `e2e-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.com`;
}

test("new user signs up, logs in and sees the dashboard chart", async ({ page }) => {
  const email = uniqueEmail();

  await page.goto("/signup");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByLabel("Confirm password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/login$/);

  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/demo\/chart$/);
  await expect(page.getByRole("heading", { name: "Chart Demo" })).toBeVisible();

  // The chart must get its h-96 (384px) height, not collapse.
  const canvas = page.locator("canvas").first();
  await expect(canvas).toBeVisible();
  const box = await canvas.boundingBox();
  expect(box?.height).toBeGreaterThanOrEqual(380);
});

test("login rejects a wrong password for a real user", async ({ page, request }) => {
  const email = uniqueEmail();
  const register = await request.post(`${API_URL}/api/accounts/register/`, {
    data: { email, password: PASSWORD },
  });
  expect(register.status()).toBe(201);

  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("not-the-password");
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page.getByText("Invalid credentials. Please try again.")).toBeVisible();
  await expect(page).toHaveURL(/\/login$/);
});
