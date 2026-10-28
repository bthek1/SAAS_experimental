import { screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { http, HttpResponse } from "msw"
import { describe, expect, it } from "vitest"
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
})
