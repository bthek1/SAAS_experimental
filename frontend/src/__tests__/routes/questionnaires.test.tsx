import { screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { http, HttpResponse } from "msw"
import { describe, expect, it } from "vitest"
import { API } from "@/test/handlers"
import { battery, questionnaire } from "@/test/questionnaireFixtures"
import { renderRoute } from "@/test/renderRoute"
import { server } from "@/test/server"

describe("/questionnaires", () => {
  it("lists questionnaires with their status", async () => {
    renderRoute("/questionnaires")
    expect(await screen.findByRole("link", { name: "Alice" })).toBeInTheDocument()
    expect(screen.getByText("Pending")).toBeInTheDocument()
    expect(screen.getByText(/^Submitted/)).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Results" })).toHaveAttribute(
      "href",
      "/questionnaires/q-2/results",
    )
  })

  it("filtering by type shows a summary of responses", async () => {
    renderRoute("/questionnaires?type=qt-1")
    expect(await screen.findByRole("region", { name: "Summary" })).toBeInTheDocument()
    expect(screen.getByText("Summary of 1 responses")).toBeInTheDocument()
  })
})

describe("/questionnaires/new", () => {
  it("creates a questionnaire and shows its share link", async () => {
    let body: Record<string, unknown> | null = null
    server.use(
      http.post(`${API}/api/questionnaires/`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(questionnaire, { status: 201 })
      }),
    )
    const user = userEvent.setup()
    renderRoute("/questionnaires/new")
    await user.selectOptions(await screen.findByLabelText("Questionnaire type"), "qt-1")
    await user.type(screen.getByLabelText(/respondent name/i), "Alice")
    await user.click(screen.getByRole("button", { name: "Create share link" }))

    expect(await screen.findByText(`${window.location.origin}/take/${questionnaire.shareToken}`))
      .toBeInTheDocument()
    expect(body).toEqual({ questionnaireTypeId: "qt-1", name: "Alice" })
  })

  it("requires a type", async () => {
    const user = userEvent.setup()
    renderRoute("/questionnaires/new")
    await user.click(await screen.findByRole("button", { name: "Create share link" }))
    expect(await screen.findByText("Pick a questionnaire type")).toBeInTheDocument()
  })
})

describe("/batteries", () => {
  it("shows progress and links to the detail page", async () => {
    renderRoute("/batteries")
    expect(await screen.findByRole("link", { name: "Carol" })).toBeInTheDocument()
    expect(screen.getByText("0/2")).toBeInTheDocument()
  })

  it("detail lists slots in order with status", async () => {
    renderRoute(`/batteries/${battery.id}`)
    const list = await screen.findByRole("list", { name: /questionnaires in this battery/i })
    expect(list).toHaveTextContent(/1\.Wellbeing.*2\.Sleep/)
    expect(screen.getByText("0 of 2 done")).toBeInTheDocument()
  })

  it("creates a battery and shows its share link", async () => {
    const user = userEvent.setup()
    renderRoute("/batteries/new")
    await user.selectOptions(await screen.findByLabelText("Battery type"), "bt-1")
    await user.click(screen.getByRole("button", { name: "Create share link" }))
    await waitFor(() =>
      expect(
        screen.getByText(`${window.location.origin}/take-battery/${battery.shareToken}`),
      ).toBeInTheDocument(),
    )
  })
})
