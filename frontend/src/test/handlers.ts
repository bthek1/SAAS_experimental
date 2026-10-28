import { http, HttpResponse } from "msw"
import {
  battery,
  batteryType,
  publicBattery,
  publicQuestionnaire,
  questionnaire,
  questionnaireType,
  submittedQuestionnaire,
} from "./questionnaireFixtures"

export const API = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8005"

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

  http.get(`${API}/api/questionnaire-types/`, () => HttpResponse.json([questionnaireType])),
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

  http.get(`${API}/api/questionnaires/`, () =>
    HttpResponse.json([questionnaire, submittedQuestionnaire]),
  ),
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

  http.get(`${API}/api/battery-types/`, () => HttpResponse.json([batteryType])),
  http.get(`${API}/api/battery-types/:id/`, () => HttpResponse.json(batteryType)),
  http.post(`${API}/api/battery-types/`, () => HttpResponse.json(batteryType, { status: 201 })),
  http.patch(`${API}/api/battery-types/:id/`, async ({ request }) =>
    HttpResponse.json({ ...batteryType, ...((await request.json()) as object) }),
  ),
  http.delete(`${API}/api/battery-types/:id/`, () => new HttpResponse(null, { status: 204 })),

  http.get(`${API}/api/batteries/`, () => HttpResponse.json([battery])),
  http.get(`${API}/api/batteries/by-token/:token/`, () => HttpResponse.json(publicBattery)),
  http.get(`${API}/api/batteries/:id/`, () => HttpResponse.json(battery)),
  http.post(`${API}/api/batteries/`, () => HttpResponse.json(battery, { status: 201 })),
  http.delete(`${API}/api/batteries/:id/`, () => new HttpResponse(null, { status: 204 })),
]
