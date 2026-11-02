import { screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { http, HttpResponse } from "msw"
import { beforeEach, describe, expect, it } from "vitest"
import { API, paginated } from "@/test/handlers"
import { questionnaireType } from "@/test/questionnaireFixtures"
import { renderRoute } from "@/test/renderRoute"
import { server } from "@/test/server"

// 30 types: 25 on page 1 (the server default), 5 on page 2 (#10).
const types = Array.from({ length: 30 }, (_, i) => ({
  ...questionnaireType,
  id: `qt-${i + 1}`,
  title: `Type ${String(i + 1).padStart(2, "0")}`,
}))

beforeEach(() => {
  server.use(
    http.get(`${API}/api/questionnaire-types/`, ({ request }) => paginated(types, request)),
  )
})

describe("paginated index pages", () => {
  it("shows the first page and how many there are", async () => {
    renderRoute("/questionnaire-types")
    expect(await screen.findByRole("cell", { name: "Type 01" })).toBeInTheDocument()
    expect(screen.queryByRole("cell", { name: "Type 26" })).not.toBeInTheDocument()
    expect(screen.getByText("Page 1 of 2 · 30 total")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /previous/i })).toBeDisabled()
  })

  it("moves to the next page through the URL", async () => {
    const user = userEvent.setup()
    const { router } = renderRoute("/questionnaire-types")
    await user.click(await screen.findByRole("button", { name: /next/i }))
    expect(await screen.findByRole("cell", { name: "Type 26" })).toBeInTheDocument()
    expect(router.state.location.search).toEqual({ page: 2 })
    expect(screen.getByRole("button", { name: /next/i })).toBeDisabled()
  })

  it("opens straight on the page in the URL", async () => {
    renderRoute("/questionnaire-types?page=2")
    expect(await screen.findByRole("cell", { name: "Type 30" })).toBeInTheDocument()
    expect(screen.getByText("Page 2 of 2 · 30 total")).toBeInTheDocument()
  })

  it("hides the pager when everything fits on one page", async () => {
    server.use(
      http.get(`${API}/api/questionnaire-types/`, ({ request }) =>
        paginated(types.slice(0, 3), request),
      ),
    )
    renderRoute("/questionnaire-types")
    expect(await screen.findByRole("cell", { name: "Type 01" })).toBeInTheDocument()
    expect(screen.queryByRole("navigation", { name: "Pagination" })).not.toBeInTheDocument()
  })

  it("steps back a page after deleting the last item on it", async () => {
    let rows = types.slice(0, 26)
    server.use(
      http.get(`${API}/api/questionnaire-types/`, ({ request }) => paginated(rows, request)),
      http.delete(`${API}/api/questionnaire-types/:id/`, ({ params }) => {
        rows = rows.filter((t) => t.id !== params.id)
        return new HttpResponse(null, { status: 204 })
      }),
    )
    const user = userEvent.setup()
    const { router } = renderRoute("/questionnaire-types?page=2")
    const row = (await screen.findByRole("cell", { name: "Type 26" })).closest("tr")!
    await user.click(within(row).getByRole("button", { name: "Delete" }))
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Delete" }))
    await waitFor(() => expect(router.state.location.search).toEqual({}))
    expect(await screen.findByRole("cell", { name: "Type 25" })).toBeInTheDocument()
  })
})

describe("pickers", () => {
  it("offer items from every page", async () => {
    renderRoute("/questionnaires/new")
    const picker = await screen.findByLabelText("Questionnaire type")
    await waitFor(() =>
      expect(within(picker).getByRole("option", { name: "Type 30" })).toBeInTheDocument(),
    )
    expect(within(picker).getAllByRole("option")).toHaveLength(31) // + the placeholder
  })
})
