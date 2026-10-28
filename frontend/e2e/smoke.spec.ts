import { expect, test } from "@playwright/test";

// Smoke tests run without a backend: every /api/ request is answered here.
// Health is up and the visitor is anonymous, so /api/ calls other than health get a 401.
test.beforeEach(async ({ page }) => {
  await page.route(
    (url) => url.pathname.startsWith("/api/"),
    (route) => {
      const { pathname } = new URL(route.request().url());
      if (pathname === "/api/health/") {
        return route.fulfill({ json: { status: "ok" } });
      }
      return route.fulfill({
        status: 401,
        json: { detail: "No active account found with the given credentials" },
      });
    },
  );
});

test("landing page renders", async ({ page }) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: /welcome to my app/i }),
  ).toBeVisible();
});

test("login page links to signup", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();

  await page.getByRole("link", { name: /sign up/i }).click();
  await expect(page).toHaveURL(/\/signup$/);
  await expect(page.getByRole("button", { name: "Create account" })).toBeVisible();
});

test("login form validates input before submitting", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page.getByText("Please enter a valid email address")).toBeVisible();
  await expect(page.getByText("Password is required")).toBeVisible();
});

test("login shows an error for rejected credentials", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("nobody@example.com");
  await page.getByLabel("Password").fill("wrong-password");
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page.getByText("Invalid credentials. Please try again.")).toBeVisible();
  await expect(page).toHaveURL(/\/login$/);
});
