import { screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { http, HttpResponse } from "msw"
import { describe, expect, it } from "vitest"
import { API } from "@/test/handlers"
import { publicQuestionnaire } from "@/test/questionnaireFixtures"
import { renderRoute } from "@/test/renderRoute"
import { server } from "@/test/server"

const TOKEN = "11111111-1111-1111-1111-111111111111"

describe("/take/$shareToken", () => {
  it("renders the questionnaire for an anonymous visitor, without the app shell", async () => {
    renderRoute(`/take/${TOKEN}`, { authed: false })
    expect(await screen.findByRole("heading", { name: "Wellbeing" })).toBeInTheDocument()
    expect(screen.getByText("Anything else?")).toBeInTheDocument()
    expect(screen.queryByRole("link", { name: /dashboard/i })).not.toBeInTheDocument()
  })

  it("submits answers with metrics and thanks the respondent", async () => {
    let body: Record<string, unknown> | null = null
    server.use(
      http.patch(`${API}/api/questionnaires/by-token/:token/submit/`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ ...publicQuestionnaire, submittedAt: "2026-01-05T00:00:00Z" })
      }),
    )
    const user = userEvent.setup()
    renderRoute(`/take/${TOKEN}`, { authed: false })
    await user.type(await screen.findByRole("textbox"), "Feeling fine")
    await user.click(screen.getByRole("button", { name: /complete/i }))

    expect(await screen.findByRole("heading", { name: "Thank you!" })).toBeInTheDocument()
    expect(body).toMatchObject({ answers: { q2: "Feeling fine" } })
    expect(body).toHaveProperty("metrics.totalScore")
  })

  it("shows already-submitted for a used link", async () => {
    server.use(
      http.get(`${API}/api/questionnaires/by-token/:token/`, () =>
        HttpResponse.json({ ...publicQuestionnaire, submittedAt: "2026-01-05T00:00:00Z" }),
      ),
    )
    renderRoute(`/take/${TOKEN}`, { authed: false })
    expect(await screen.findByRole("heading", { name: "Already submitted" })).toBeInTheDocument()
  })

  it("treats a 409 on submit as already submitted", async () => {
    server.use(
      http.patch(`${API}/api/questionnaires/by-token/:token/submit/`, () =>
        HttpResponse.json({ detail: "Already submitted." }, { status: 409 }),
      ),
    )
    const user = userEvent.setup()
    renderRoute(`/take/${TOKEN}`, { authed: false })
    await user.click(await screen.findByRole("button", { name: /complete/i }))
    expect(await screen.findByRole("heading", { name: "Already submitted" })).toBeInTheDocument()
  })

  it("lets the respondent retry after a network failure", async () => {
    let calls = 0
    server.use(
      http.patch(`${API}/api/questionnaires/by-token/:token/submit/`, () => {
        calls += 1
        return calls === 1
          ? new HttpResponse(null, { status: 500 })
          : HttpResponse.json({ ...publicQuestionnaire, submittedAt: "2026-01-05T00:00:00Z" })
      }),
    )
    const user = userEvent.setup()
    renderRoute(`/take/${TOKEN}`, { authed: false })
    await user.click(await screen.findByRole("button", { name: /complete/i }))
    await user.click(await screen.findByRole("button", { name: "Try again" }))
    expect(await screen.findByRole("heading", { name: "Thank you!" })).toBeInTheDocument()
    expect(calls).toBe(2)
  })

  it("shows not-found for an unknown link", async () => {
    server.use(
      http.get(`${API}/api/questionnaires/by-token/:token/`, () =>
        HttpResponse.json({ detail: "Not found." }, { status: 404 }),
      ),
    )
    renderRoute(`/take/${TOKEN}`, { authed: false })
    expect(await screen.findByRole("heading", { name: "Questionnaire not found" })).toBeInTheDocument()
  })

  it("works for a visitor who still has an old login token stored", async () => {
    // The client attaches the token; the public endpoint ignores credentials.
    renderRoute(`/take/${TOKEN}`, { authed: true })
    await waitFor(() => expect(screen.getByRole("heading", { name: "Wellbeing" })).toBeInTheDocument())
  })
})
