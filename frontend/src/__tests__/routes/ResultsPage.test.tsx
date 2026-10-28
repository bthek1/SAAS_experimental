import { screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { http, HttpResponse } from "msw"
import { afterEach, describe, expect, it, vi } from "vitest"
import { API } from "@/test/handlers"
import { questionnaireType, submittedQuestionnaire } from "@/test/questionnaireFixtures"
import { renderRoute } from "@/test/renderRoute"
import { server } from "@/test/server"

describe("/questionnaires/$id/results", () => {
  it("shows stored metrics and answers", async () => {
    renderRoute("/questionnaires/q-2/results")
    expect(await screen.findByText("Total Score")).toBeInTheDocument()
    expect(screen.getByText("8")).toBeInTheDocument()
    expect(within(screen.getByRole("region", { name: "Anything else?" })).getByText("All good"))
      .toBeInTheDocument()
  })

  it("reads the response against its snapshot, not the edited type", async () => {
    server.use(
      http.get(`${API}/api/questionnaires/:id/`, () =>
        HttpResponse.json({
          ...submittedQuestionnaire,
          // The type was edited after submission and lost its questions.
          questionnaireType: { ...questionnaireType, questionnaireJson: { pages: [] } },
        }),
      ),
    )
    renderRoute("/questionnaires/q-2/results")
    expect(await screen.findByRole("region", { name: "Anything else?" })).toBeInTheDocument()
  })

  it("expands the raw responses", async () => {
    const user = userEvent.setup()
    renderRoute("/questionnaires/q-2/results")
    await user.click(await screen.findByRole("button", { name: /raw responses \(1\)/i }))
    expect(screen.getByText(/"q2":"All good"/)).toBeInTheDocument()
  })

  it("explains when there is no response yet", async () => {
    renderRoute("/questionnaires/q-1/results")
    expect(await screen.findByText("No response yet.")).toBeInTheDocument()
  })

  describe("Download PDF", () => {
    afterEach(() => vi.restoreAllMocks())

    it("downloads the PDF through the API client", async () => {
      server.use(
        http.get(`${API}/api/questionnaires/:id/pdf/`, () =>
          new HttpResponse("%PDF-1.7", {
            headers: {
              "Content-Type": "application/pdf",
              "Content-Disposition": 'attachment; filename="Wellbeing-2026-01-05.pdf"',
            },
          }),
        ),
      )
      const createUrl = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:pdf")
      vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {})
      const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {})

      const user = userEvent.setup()
      renderRoute("/questionnaires/q-2/results")
      await user.click(await screen.findByRole("button", { name: /download pdf/i }))

      await vi.waitFor(() => expect(click).toHaveBeenCalled())
      expect(createUrl).toHaveBeenCalledWith(expect.any(Blob))
      const link = click.mock.contexts[0] as HTMLAnchorElement
      expect(link.download).toBe("Wellbeing-2026-01-05.pdf")
    })

    it("shows an error when the PDF fails", async () => {
      server.use(
        http.get(`${API}/api/questionnaires/:id/pdf/`, () => new HttpResponse(null, { status: 500 })),
      )
      const user = userEvent.setup()
      renderRoute("/questionnaires/q-2/results")
      await user.click(await screen.findByRole("button", { name: /download pdf/i }))
      expect(await screen.findByRole("alert")).toHaveTextContent(/could not be created/i)
    })

    it("is not offered before submission", async () => {
      renderRoute("/questionnaires/q-1/results")
      await screen.findByText("No response yet.")
      expect(screen.queryByRole("button", { name: /download pdf/i })).not.toBeInTheDocument()
    })
  })
})
