import { http, HttpResponse } from "msw"
import { afterEach, describe, expect, it, vi } from "vitest"
import { getDashboard, getDashboardScores } from "@/api/dashboard"
import { API } from "@/test/handlers"
import { dashboardScores, dashboardSummary } from "@/test/questionnaireFixtures"
import { server } from "@/test/server"

function captureQuery(path: string, body: object) {
  const seen: URLSearchParams[] = []
  server.use(
    http.get(`${API}${path}`, ({ request }) => {
      seen.push(new URL(request.url).searchParams)
      return HttpResponse.json(body)
    }),
  )
  return seen
}

function stubTimeZone(timeZone: string) {
  vi.spyOn(Intl, "DateTimeFormat").mockReturnValue({
    resolvedOptions: () => ({ timeZone }),
  } as Intl.DateTimeFormat)
}

describe("dashboard requests", () => {
  afterEach(() => vi.restoreAllMocks())

  it("sends the browser's time zone with the summary", async () => {
    stubTimeZone("Australia/Sydney")
    const seen = captureQuery("/api/dashboard/", dashboardSummary)
    await getDashboard({ days: 7 })
    expect(seen[0].get("tz")).toBe("Australia/Sydney")
    expect(seen[0].get("days")).toBe("7")
  })

  it("sends the browser's time zone with the scores", async () => {
    stubTimeZone("America/New_York")
    const seen = captureQuery("/api/dashboard/scores/", dashboardScores)
    await getDashboardScores({ questionnaireType: "qt-1" })
    expect(seen[0].get("tz")).toBe("America/New_York")
  })

  it("leaves tz out when the browser has no usable zone", async () => {
    stubTimeZone("Etc/Unknown")
    const seen = captureQuery("/api/dashboard/", dashboardSummary)
    await getDashboard({})
    expect(seen[0].has("tz")).toBe(false)
  })
})
