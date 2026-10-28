import { expect, type APIRequestContext, type Page } from "@playwright/test";
import { API_URL } from "./ports";

export const PASSWORD = "e2e-password-123";

export function uniqueEmail(prefix = "e2e") {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.com`;
}

/** Register a fresh user through the API and return a JWT access token for them. */
export async function registerUser(request: APIRequestContext, email = uniqueEmail()) {
  const register = await request.post(`${API_URL}/api/accounts/register/`, {
    data: { email, password: PASSWORD },
  });
  expect(register.status()).toBe(201);
  const token = await request.post(`${API_URL}/api/token/`, {
    data: { email, password: PASSWORD },
  });
  const { access } = (await token.json()) as { access: string };
  return { email, access };
}

/** Register a user and log the page in by storing their token (skips the login form). */
export async function loginAs(page: Page, request: APIRequestContext) {
  const user = await registerUser(request);
  await page.goto("/login");
  await page.evaluate((access) => localStorage.setItem("access_token", access), user.access);
  return user;
}

/** Owner-side API call with a user's token. */
export function api(request: APIRequestContext, access: string) {
  const headers = { Authorization: `Bearer ${access}` };
  return {
    get: (path: string) => request.get(`${API_URL}/api${path}`, { headers }),
    post: (path: string, data: unknown) =>
      request.post(`${API_URL}/api${path}`, { headers, data }),
  };
}

/** A survey with a recipient page, two ratings and a calculated total. */
export const SCORED_SURVEY = {
  pages: [
    {
      name: "recipient_page",
      elements: [{ type: "text", name: "recipient__name", title: "Who is filling this in?" }],
    },
    {
      name: "page1",
      elements: [
        { type: "rating", name: "mood", title: "Mood today", rateMax: 5 },
        { type: "rating", name: "energy", title: "Energy today", rateMax: 5 },
      ],
    },
  ],
  calculatedValues: [
    { name: "totalScore", expression: "{mood} + {energy}", includeIntoResult: true },
  ],
};

/** Answer SCORED_SURVEY: name "Pat", mood 4, energy 3 (totalScore 7). */
export async function answerScoredSurvey(page: Page) {
  await page.getByRole("textbox").fill("Pat");
  await page.getByRole("button", { name: "Next" }).click();
  for (const [title, value] of [
    ["Mood today", "4"],
    ["Energy today", "3"],
  ]) {
    await page
      .locator(".sd-question", { hasText: title })
      .locator(".sd-rating__item-text", { hasText: new RegExp(`^${value}$`) })
      .first()
      .click();
  }
  await page.getByRole("button", { name: "Complete" }).click();
}
