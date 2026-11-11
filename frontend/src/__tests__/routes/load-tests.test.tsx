import { screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"
import { renderRoute } from "@/test/renderRoute"

// echarts needs a real canvas, so render a plain div instead
vi.mock("echarts-for-react", () => ({
  default: () => <div data-testid="echart" />,
}))

describe("/load-tests", () => {
  it("sends anonymous visitors to the login page", async () => {
    const { router } = renderRoute("/load-tests", { authed: false })
    await waitFor(() => expect(router.state.location.pathname).toBe("/login"))
  })

  it("shows the key figures and the capacity charts by default", async () => {
    renderRoute("/load-tests")
    const kpis = await screen.findByRole("list", { name: "Key figures" })
    expect(within(kpis).getByText("Failed requests").nextElementSibling).toHaveTextContent("1")
    expect(screen.getByRole("heading", { name: "Capacity after each change" })).toBeInTheDocument()
    expect(await screen.findAllByTestId("echart")).toHaveLength(6)
  })

  it.each([
    ["capacity", "Latency as the rate climbs", 6],
    ["cache", "When Redis fails", 8],
    ["growth", "Holding a steady rate", 6],
    ["fixes", "What the dashboard fixes did", 11],
    ["split", "What splitting into two services did", 8],
    ["mongo", "Postgres against MongoDB for instances", 5],
    ["fastapi", "catalog on FastAPI against Django", 2],
  ])("renders the %s tab with its %s section and %i charts", async (tab, heading, charts) => {
    renderRoute(`/load-tests?tab=${tab}`)
    expect(await screen.findByRole("heading", { name: heading })).toBeInTheDocument()
    expect(await screen.findAllByTestId("echart")).toHaveLength(charts)
  })

  it("renders the method tab as text, with both of its cards", async () => {
    renderRoute("/load-tests?tab=method")
    expect(await screen.findByRole("region", { name: "Still open" })).toBeInTheDocument()
    expect(screen.getByRole("region", { name: "How this was measured" })).toBeInTheDocument()
    expect(screen.queryByTestId("echart")).not.toBeInTheDocument()
  })

  it("keeps each charted table available for exact numbers", async () => {
    renderRoute("/load-tests?tab=fixes")
    await screen.findByRole("heading", { name: "What the dashboard fixes did" })
    expect(screen.getAllByText("Show the table")).toHaveLength(3)
  })

  it("links from the capacity notes to the dashboard fixes", async () => {
    const user = userEvent.setup()
    const { router } = renderRoute("/load-tests")
    await user.click(await screen.findByRole("link", { name: "compared separately" }))
    expect(await screen.findByRole("heading", { name: "What the dashboard fixes did" })).toBeInTheDocument()
    expect(router.state.location.search).toEqual({ tab: "fixes" })
  })

  it("keeps the chosen tab in the URL and renders only that tab", async () => {
    const user = userEvent.setup()
    const { router } = renderRoute("/load-tests")
    await user.click(await screen.findByRole("tab", { name: "Cache" }))
    expect(await screen.findByRole("heading", { name: "What the Redis cache did" })).toBeInTheDocument()
    expect(router.state.location.search).toEqual({ tab: "cache" })
    expect(screen.queryByRole("heading", { name: "Capacity after each change" })).not.toBeInTheDocument()
  })

  it("opens a tab from its URL, and ignores an unknown one", async () => {
    renderRoute("/load-tests?tab=split")
    expect(
      await screen.findByRole("heading", { name: "What splitting into two services did" }),
    ).toBeInTheDocument()

    renderRoute("/load-tests?tab=nope")
    expect(await screen.findByRole("heading", { name: "Capacity after each change" })).toBeInTheDocument()
  })

  it("links from the correction note to how this was measured", async () => {
    const user = userEvent.setup()
    renderRoute("/load-tests")
    await user.click(await screen.findByRole("link", { name: "How this was measured." }))
    expect(await screen.findByRole("region", { name: "How this was measured" })).toBeInTheDocument()
  })
})
