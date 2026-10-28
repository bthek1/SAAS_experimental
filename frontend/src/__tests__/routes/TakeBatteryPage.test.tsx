import { screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { http, HttpResponse } from "msw"
import { describe, expect, it } from "vitest"
import { API } from "@/test/handlers"
import { publicBattery, publicQuestionnaire } from "@/test/questionnaireFixtures"
import { renderRoute } from "@/test/renderRoute"
import { server } from "@/test/server"
import type { PublicBattery } from "@/types/questionnaires"

const BATTERY_TOKEN = "33333333-3333-3333-3333-333333333333"

/** A tiny fake backend: submitting a slot marks it submitted in the battery. */
function useFakeBattery() {
  let battery: PublicBattery = structuredClone(publicBattery)
  const submitted: string[] = []
  server.use(
    http.get(`${API}/api/batteries/by-token/:token/`, () => HttpResponse.json(battery)),
    http.get(`${API}/api/questionnaires/by-token/:token/`, ({ params }) => {
      const slot = battery.questionnaires.find((s) => s.shareToken === params.token)
      return HttpResponse.json({
        ...publicQuestionnaire,
        questionnaireTypeTitle: slot?.questionnaireTypeName ?? "?",
        submittedAt: slot?.submittedAt ?? null,
      })
    }),
    http.patch(`${API}/api/questionnaires/by-token/:token/submit/`, ({ params }) => {
      submitted.push(String(params.token))
      battery = {
        ...battery,
        questionnaires: battery.questionnaires.map((s) =>
          s.shareToken === params.token ? { ...s, submittedAt: "2026-01-05T00:00:00Z" } : s,
        ),
      }
      battery.isComplete = battery.questionnaires.every((s) => s.submittedAt)
      return HttpResponse.json({ ...publicQuestionnaire, submittedAt: "2026-01-05T00:00:00Z" })
    }),
  )
  return submitted
}

describe("/take-battery/$shareToken", () => {
  it("steps through the slots in order and finishes", async () => {
    const submitted = useFakeBattery()
    const user = userEvent.setup()
    renderRoute(`/take-battery/${BATTERY_TOKEN}`, { authed: false })

    expect(await screen.findByText("Questionnaire 1 of 2")).toBeInTheDocument()
    expect(await screen.findByRole("heading", { name: "Wellbeing" })).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: /complete/i }))

    expect(await screen.findByText("Questionnaire 2 of 2")).toBeInTheDocument()
    expect(await screen.findByRole("heading", { name: "Sleep" })).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: /complete/i }))

    expect(await screen.findByRole("heading", { name: "All done!" })).toBeInTheDocument()
    expect(submitted).toEqual(publicBattery.questionnaires.map((s) => s.shareToken))
  })

  it("resumes at the first unsubmitted slot", async () => {
    server.use(
      http.get(`${API}/api/batteries/by-token/:token/`, () =>
        HttpResponse.json({
          ...publicBattery,
          questionnaires: [
            { ...publicBattery.questionnaires[0], submittedAt: "2026-01-05T00:00:00Z" },
            publicBattery.questionnaires[1],
          ],
        }),
      ),
    )
    renderRoute(`/take-battery/${BATTERY_TOKEN}`, { authed: false })
    expect(await screen.findByText("Questionnaire 2 of 2")).toBeInTheDocument()
  })

  it("shows not-found for an unknown link", async () => {
    server.use(
      http.get(`${API}/api/batteries/by-token/:token/`, () => new HttpResponse(null, { status: 404 })),
    )
    renderRoute(`/take-battery/${BATTERY_TOKEN}`, { authed: false })
    expect(await screen.findByRole("heading", { name: "Battery not found" })).toBeInTheDocument()
  })
})
