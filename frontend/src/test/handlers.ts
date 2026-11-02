import { http, HttpResponse } from "msw"
import {
  battery,
  batteryType,
  dashboardScores,
  dashboardSummary,
  publicBattery,
  publicQuestionnaire,
  questionnaire,
  questionnaireType,
  submittedQuestionnaire,
} from "./questionnaireFixtures"

export const API = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8005"

/**
 * A list endpoint's response, paginated like the server (#10): honours `page`
 * and `page_size` (default 25), and links `next`/`previous`.
 */
export function paginated<T>(items: T[], request: Request) {
  const url = new URL(request.url)
  const page = Number(url.searchParams.get("page") ?? 1)
  const size = Number(url.searchParams.get("page_size") ?? 25)
  const start = (page - 1) * size
  const link = (to: number) => {
    const next = new URL(url)
    next.searchParams.set("page", String(to))
    return next.toString()
  }
  return HttpResponse.json({
    count: items.length,
    next: start + size < items.length ? link(page + 1) : null,
    previous: page > 1 ? link(page - 1) : null,
    results: items.slice(start, start + size),
  })
}

/**
 * Default request handlers used by every test. Override per-test with
 * `server.use(...)` from `@/test/server` to simulate errors or edge cases.
 */
export const handlers = [
  http.get(`${API}/api/health/`, () =>
    HttpResponse.json({ status: "ok" })
  ),
  http.get(`${API}/api/accounts/me/`, () =>
    HttpResponse.json({ id: "u-1", email: "owner@example.com", first_name: "", last_name: "", date_joined: "2026-01-01T00:00:00Z" })
  ),

  http.get(`${API}/api/questionnaire-types/`, ({ request }) => paginated([questionnaireType], request)),
  http.get(`${API}/api/questionnaire-types/:id/`, () => HttpResponse.json(questionnaireType)),
  http.post(`${API}/api/questionnaire-types/`, async ({ request }) =>
    HttpResponse.json(
      { ...questionnaireType, id: "qt-new", ...((await request.json()) as object) },
      { status: 201 },
    ),
  ),
  http.patch(`${API}/api/questionnaire-types/:id/`, async ({ request }) =>
    HttpResponse.json({ ...questionnaireType, ...((await request.json()) as object) }),
  ),
  http.delete(`${API}/api/questionnaire-types/:id/`, () => new HttpResponse(null, { status: 204 })),

  http.get(`${API}/api/questionnaires/`, ({ request }) => {
    const submitted = new URL(request.url).searchParams.get("submitted")
    const rows = [questionnaire, submittedQuestionnaire].filter(
      (q) => submitted === null || Boolean(q.submittedAt) === (submitted === "true"),
    )
    return paginated(rows, request)
  }),
  http.get(`${API}/api/questionnaires/by-token/:token/`, () =>
    HttpResponse.json(publicQuestionnaire),
  ),
  http.patch(`${API}/api/questionnaires/by-token/:token/submit/`, () =>
    HttpResponse.json({ ...publicQuestionnaire, submittedAt: "2026-01-05T00:00:00Z" }),
  ),
  http.get(`${API}/api/questionnaires/:id/`, ({ params }) =>
    HttpResponse.json(params.id === submittedQuestionnaire.id ? submittedQuestionnaire : questionnaire),
  ),
  http.post(`${API}/api/questionnaires/`, () => HttpResponse.json(questionnaire, { status: 201 })),
  http.delete(`${API}/api/questionnaires/:id/`, () => new HttpResponse(null, { status: 204 })),

  http.get(`${API}/api/battery-types/`, ({ request }) => paginated([batteryType], request)),
  http.get(`${API}/api/battery-types/:id/`, () => HttpResponse.json(batteryType)),
  http.post(`${API}/api/battery-types/`, () => HttpResponse.json(batteryType, { status: 201 })),
  http.patch(`${API}/api/battery-types/:id/`, async ({ request }) =>
    HttpResponse.json({ ...batteryType, ...((await request.json()) as object) }),
  ),
  http.delete(`${API}/api/battery-types/:id/`, () => new HttpResponse(null, { status: 204 })),

  http.get(`${API}/api/batteries/`, ({ request }) => paginated([battery], request)),
  http.get(`${API}/api/batteries/by-token/:token/`, () => HttpResponse.json(publicBattery)),
  http.get(`${API}/api/batteries/:id/`, () => HttpResponse.json(battery)),
  http.post(`${API}/api/batteries/`, () => HttpResponse.json(battery, { status: 201 })),
  http.delete(`${API}/api/batteries/:id/`, () => new HttpResponse(null, { status: 204 })),

  http.get(`${API}/api/dashboard/`, () => HttpResponse.json(dashboardSummary)),
  http.get(`${API}/api/dashboard/scores/`, () => HttpResponse.json(dashboardScores)),
]
