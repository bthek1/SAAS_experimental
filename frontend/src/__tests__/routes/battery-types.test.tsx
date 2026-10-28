import { screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { http, HttpResponse } from "msw"
import { describe, expect, it } from "vitest"
import { API } from "@/test/handlers"
import { batteryType, questionnaireType } from "@/test/questionnaireFixtures"
import { renderRoute } from "@/test/renderRoute"
import { server } from "@/test/server"

const sleep = { ...questionnaireType, id: "qt-2", title: "Sleep" }

describe("/battery-types", () => {
  it("lists battery types with their size", async () => {
    renderRoute("/battery-types")
    expect(await screen.findByText("Intake")).toBeInTheDocument()
    expect(screen.getByText("First visit")).toBeInTheDocument()
  })
})

describe("/battery-types/new", () => {
  it("requires at least one questionnaire type", async () => {
    const user = userEvent.setup()
    renderRoute("/battery-types/new")
    await user.type(await screen.findByLabelText("Title"), "Intake")
    await user.click(screen.getByRole("button", { name: "Create" }))
    expect(await screen.findByText("Add at least one questionnaire type")).toBeInTheDocument()
  })

  it("creates a battery type with types in the chosen order", async () => {
    server.use(
      http.get(`${API}/api/questionnaire-types/`, () => HttpResponse.json([questionnaireType, sleep])),
    )
    let body: Record<string, unknown> | null = null
    server.use(
      http.post(`${API}/api/battery-types/`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(batteryType, { status: 201 })
      }),
    )
    const user = userEvent.setup()
    const { router } = renderRoute("/battery-types/new")
    await user.type(await screen.findByLabelText("Title"), "Intake")
    const add = screen.getByRole("combobox", { name: /add a questionnaire type/i })
    await user.selectOptions(add, "qt-1")
    await user.selectOptions(add, "qt-2")
    await user.click(screen.getByRole("button", { name: "Move Sleep up" }))
    await user.click(screen.getByRole("button", { name: "Create" }))

    await waitFor(() => expect(router.state.location.pathname).toBe("/battery-types"))
    expect(body).toEqual({ title: "Intake", description: "", questionnaireTypeIds: ["qt-2", "qt-1"] })
  })
})

describe("/battery-types/$id", () => {
  it("prefills and saves edits", async () => {
    server.use(
      http.get(`${API}/api/questionnaire-types/`, () => HttpResponse.json([questionnaireType, sleep])),
    )
    let body: Record<string, unknown> | null = null
    server.use(
      http.patch(`${API}/api/battery-types/:id/`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json({ ...batteryType, ...body })
      }),
    )
    const user = userEvent.setup()
    renderRoute("/battery-types/bt-1")
    expect(await screen.findByDisplayValue("Intake")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Remove Wellbeing" }))
    await user.selectOptions(screen.getByRole("combobox", { name: /add a questionnaire type/i }), "qt-2")
    await user.click(screen.getByRole("button", { name: "Save" }))
    await waitFor(() => expect(body).toMatchObject({ questionnaireTypeIds: ["qt-2"] }))
  })
})
