import { screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { http, HttpResponse } from "msw"
import { describe, expect, it, vi } from "vitest"
import { API } from "@/test/handlers"
import { dashboardScores, dashboardSummary } from "@/test/questionnaireFixtures"
import { renderRoute } from "@/test/renderRoute"
import { server } from "@/test/server"

// echarts needs a real canvas, so render a plain div instead
vi.mock("echarts-for-react", () => ({
  default: () => <div data-testid="echart" />,
}))

const last = <T,>(items: T[]): T | undefined => items[items.length - 1]

function recordDashboardRequests() {
  const seen: URLSearchParams[] = []
  server.use(
    http.get(`${API}/api/dashboard/`, ({ request }) => {
      seen.push(new URL(request.url).searchParams)
      return HttpResponse.json(dashboardSummary)
    }),
  )
  return seen
}

describe("/dashboard", () => {
  it("renders KPI cards from the API", async () => {
    renderRoute("/dashboard")
    const kpis = await screen.findByRole("list", { name: "Key figures" })
    expect(within(kpis).getByText("Completion rate").nextElementSibling).toHaveTextContent("75%")
    expect(within(kpis).getByText("Sent").nextElementSibling).toHaveTextContent("12")
    expect(within(kpis).getByText("Median time to complete").nextElementSibling).toHaveTextContent(
      "5.5 h",
    )
    expect(within(kpis).getByText("Batteries complete").nextElementSibling).toHaveTextContent(
      "2 / 4",
    )
    expect(await screen.findAllByTestId("echart")).toHaveLength(3)
  })

  it("asks for the last 30 days by default", async () => {
    const seen = recordDashboardRequests()
    renderRoute("/dashboard")
    await screen.findByRole("list", { name: "Key figures" })
    expect(seen[0].get("days")).toBe("30")
    expect(seen[0].has("questionnaireType")).toBe(false)
  })

  it("shows empty state when there is no data", async () => {
    server.use(http.get(`${API}/api/questionnaire-types/`, () => HttpResponse.json([])))
    renderRoute("/dashboard")
    expect(await screen.findByRole("link", { name: /new questionnaire type/i })).toHaveAttribute(
      "href",
      "/questionnaire-types/new",
    )
    expect(screen.queryByRole("list", { name: "Key figures" })).not.toBeInTheDocument()
  })

  it("changing the date range updates the search params and refetches", async () => {
    const seen = recordDashboardRequests()
    const user = userEvent.setup()
    const { router } = renderRoute("/dashboard")
    await screen.findByRole("list", { name: "Key figures" })

    await user.click(screen.getByRole("button", { name: "7 days" }))
    await waitFor(() => expect(router.state.location.search).toEqual({ range: 7 }))
    await waitFor(() => expect(last(seen)?.get("days")).toBe("7"))
    expect(screen.getByRole("button", { name: "7 days" })).toHaveAttribute("aria-pressed", "true")

    await user.click(screen.getByRole("button", { name: "All time" }))
    await waitFor(() => expect(last(seen)?.has("days")).toBe(false))
  })

  it("filters by questionnaire type", async () => {
    const seen = recordDashboardRequests()
    const user = userEvent.setup()
    const { router } = renderRoute("/dashboard")
    await user.selectOptions(await screen.findByLabelText("Questionnaire type"), "qt-1")
    await waitFor(() => expect(router.state.location.search).toEqual({ type: "qt-1" }))
    await waitFor(() => expect(last(seen)?.get("questionnaireType")).toBe("qt-1"))
  })

  it("shows scores only once a questionnaire type is selected", async () => {
    const user = userEvent.setup()
    renderRoute("/dashboard")
    await screen.findByRole("list", { name: "Key figures" })
    expect(screen.queryByRole("region", { name: "Scores" })).not.toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText("Questionnaire type"), "qt-1")
    const scores = await screen.findByRole("region", { name: "Scores" })
    expect(within(scores).getByRole("region", { name: "Total score" })).toBeInTheDocument()
    expect(within(scores).getByRole("region", { name: "Needs follow-up" })).toBeInTheDocument()
  })

  it("asks for scores of the selected type and range", async () => {
    const seen: URLSearchParams[] = []
    server.use(
      http.get(`${API}/api/dashboard/scores/`, ({ request }) => {
        seen.push(new URL(request.url).searchParams)
        return HttpResponse.json(dashboardScores)
      }),
    )
    renderRoute("/dashboard?range=7&type=qt-1")
    await screen.findByRole("region", { name: "Scores" })
    expect(seen[0].get("questionnaireType")).toBe("qt-1")
    expect(seen[0].get("days")).toBe("7")
  })

  it("recent submission links to the results page", async () => {
    renderRoute("/dashboard")
    const recent = await screen.findByRole("region", { name: "Recent submissions" })
    expect(within(recent).getByRole("link", { name: "Bob" })).toHaveAttribute(
      "href",
      "/questionnaires/q-2/results",
    )
  })

  it("lists stale pending questionnaires with a copy-link action", async () => {
    renderRoute("/dashboard")
    const stale = await screen.findByRole("region", { name: "Awaiting response" })
    expect(within(stale).getByRole("link", { name: "Alice" })).toBeInTheDocument()
    expect(within(stale).getByText("29 days")).toBeInTheDocument()
    expect(within(stale).getByRole("button", { name: /copy link/i })).toBeInTheDocument()
  })

  it("ignores an unknown range in the URL", async () => {
    const seen = recordDashboardRequests()
    renderRoute("/dashboard?range=5")
    await screen.findByRole("list", { name: "Key figures" })
    expect(seen[0].get("days")).toBe("30")
  })

  it("shows an error when the dashboard fails to load", async () => {
    // The router logs loader errors; keep that (and its unprintable Axios error) quiet.
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {})
    server.use(
      http.get(`${API}/api/dashboard/`, () =>
        HttpResponse.json({ detail: "Boom" }, { status: 500 }),
      ),
    )
    renderRoute("/dashboard")
    expect(await screen.findByRole("alert")).toHaveTextContent(/dashboard|boom/i)
    expect(consoleError).toHaveBeenCalled()
    consoleError.mockRestore()
  })
})
