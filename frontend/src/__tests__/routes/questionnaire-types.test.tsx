import { screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { http, HttpResponse } from "msw"
import { describe, expect, it } from "vitest"
import { API } from "@/test/handlers"
import { questionnaireType } from "@/test/questionnaireFixtures"
import { renderRoute } from "@/test/renderRoute"
import { server } from "@/test/server"

describe("/questionnaire-types", () => {
  it("lists the user's types", async () => {
    renderRoute("/questionnaire-types")
    expect(await screen.findByRole("cell", { name: "Wellbeing" })).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Edit" })).toHaveAttribute(
      "href",
      "/questionnaire-types/qt-1/json",
    )
  })

  it("shows an empty state", async () => {
    server.use(http.get(`${API}/api/questionnaire-types/`, () => HttpResponse.json([])))
    renderRoute("/questionnaire-types")
    expect(await screen.findByText(/no questionnaire types yet/i)).toBeInTheDocument()
  })

  it("shows the API message when delete is blocked", async () => {
    server.use(
      http.delete(`${API}/api/questionnaire-types/:id/`, () =>
        HttpResponse.json({ detail: "This item is used by existing questionnaires." }, { status: 409 }),
      ),
    )
    const user = userEvent.setup()
    renderRoute("/questionnaire-types")
    await user.click(await screen.findByRole("button", { name: "Delete" }))
    const dialog = await screen.findByRole("dialog")
    await user.click(within(dialog).getByRole("button", { name: "Delete" }))
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(/used by existing/)
  })
})

describe("/questionnaire-types/new", () => {
  it("validates the title", async () => {
    const user = userEvent.setup()
    renderRoute("/questionnaire-types/new")
    await user.click(await screen.findByRole("button", { name: /create and open editor/i }))
    expect(await screen.findByText("Title is required")).toBeInTheDocument()
  })

  it("creates from a template and opens the editor", async () => {
    let body: Record<string, unknown> | null = null
    server.use(
      http.post(`${API}/api/questionnaire-types/`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ ...questionnaireType, id: "qt-new" }, { status: 201 })
      }),
    )
    const user = userEvent.setup()
    const { router } = renderRoute("/questionnaire-types/new")
    await user.type(await screen.findByLabelText("Title"), "Check-in")
    await user.click(screen.getByRole("radio", { name: /scored check-in/i }))
    await user.click(screen.getByRole("button", { name: /create and open editor/i }))

    await waitFor(() =>
      expect(router.state.location.pathname).toBe("/questionnaire-types/qt-new/json"),
    )
    expect(body).toMatchObject({ title: "Check-in" })
    expect(JSON.stringify(body)).toContain("totalScore")
  })
})

describe("/questionnaire-types/$id/json", () => {
  it("edits the JSON and saves it", async () => {
    let saved: Record<string, unknown> | null = null
    server.use(
      http.patch(`${API}/api/questionnaire-types/:id/`, async ({ request }) => {
        saved = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ ...questionnaireType, ...saved })
      }),
    )
    const user = userEvent.setup()
    renderRoute("/questionnaire-types/qt-1/json")
    await user.click(await screen.findByRole("tab", { name: "JSON" }))
    const textarea = screen.getByLabelText("Questionnaire JSON")
    await user.clear(textarea)
    await user.click(textarea)
    await user.paste('{"pages":[{"name":"p","elements":[{"type":"text","name":"x","title":"Pasted question"}]}]}')

    // The live preview follows the JSON.
    expect(await screen.findByText("Pasted question")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Save" }))
    await waitFor(() => expect(saved).not.toBeNull())
    expect(saved).toMatchObject({
      title: "Wellbeing",
      questionnaireJson: { pages: [{ name: "p" }] },
    })
  })

  it("blocks saving invalid JSON", async () => {
    const user = userEvent.setup()
    renderRoute("/questionnaire-types/qt-1/json")
    await user.click(await screen.findByRole("tab", { name: "JSON" }))
    const textarea = screen.getByLabelText("Questionnaire JSON")
    await user.clear(textarea)
    await user.type(textarea, "nope")
    expect(screen.getByRole("alert")).toHaveTextContent("Invalid JSON")
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled()
  })
})
