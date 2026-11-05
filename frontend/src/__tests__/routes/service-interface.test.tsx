import { screen, waitFor } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { renderRoute } from "@/test/renderRoute"

describe("/service-interface", () => {
  it("explains the interface to a logged-in user", async () => {
    renderRoute("/service-interface")
    expect(await screen.findByRole("heading", { level: 1, name: "Service interface" })).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "When one service is down" })).toBeInTheDocument()
  })

  it("lists every call between the services", async () => {
    renderRoute("/service-interface")
    const paths = [
      "POST /internal/events/",
      "POST /internal/refs/<kind>/<id>/retire/",
      "GET /internal/<types>/<id>/",
      "GET /internal/<types>/?after=<id>",
    ]
    for (const path of paths) {
      expect(await screen.findByText(path)).toBeInTheDocument()
    }
  })

  it("says which service calls which", async () => {
    renderRoute("/service-interface")
    expect(await screen.findAllByRole("img", { name: "catalog calls instances" })).toHaveLength(2)
    expect(screen.getAllByRole("img", { name: "instances calls catalog" })).toHaveLength(2)
  })

  it("lists every event in backend/contracts", async () => {
    renderRoute("/service-interface")
    const events = [
      "questionnaire_type.changed",
      "questionnaire_type.deleted",
      "battery_type.changed",
      "battery_type.deleted",
      "user.deactivated",
      "user.reactivated",
      "user.deleted",
    ]
    for (const event of events) {
      expect(await screen.findByText(event)).toBeInTheDocument()
    }
  })

  it("sends an anonymous visitor to the login page", async () => {
    const { router } = renderRoute("/service-interface", { authed: false })
    await waitFor(() => expect(router.state.location.pathname).toBe("/login"))
  })
})
