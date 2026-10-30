import { createMemoryHistory, createRootRoute, createRouter, RouterProvider } from "@tanstack/react-router"
import { render, screen, within } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { ScoreCharts } from "@/components/dashboard/ScoreCharts"
import type { ChartPalette } from "@/lib/dashboard"
import { dashboardScores } from "@/test/questionnaireFixtures"
import type { ScoreMetric } from "@/types/dashboard"

// echarts needs a real canvas, so render a plain div instead
vi.mock("echarts-for-react", () => ({
  default: () => <div data-testid="echart" />,
}))

const palette: ChartPalette = { strong: "#111", mid: "#222", light: "#333", text: "#aaa", border: "#bbb" }

/** ScoreCharts renders router Links, so mount it inside a minimal router. */
function renderScores(metrics: ScoreMetric[]) {
  const router = createRouter({
    routeTree: createRootRoute({
      component: () => <ScoreCharts typeTitle="Wellbeing" metrics={metrics} palette={palette} />,
    }),
    history: createMemoryHistory({ initialEntries: ["/"] }),
  })
  return render(<RouterProvider router={router} />)
}

describe("ScoreCharts", () => {
  it("renders one chart per metric kind", async () => {
    renderScores(dashboardScores.metrics)
    const total = await screen.findByRole("region", { name: "Total score" })
    expect(within(total).getByText("Average 7 across 2 responses")).toBeInTheDocument()
    expect(screen.getByRole("region", { name: "Severity" })).toBeInTheDocument()
    expect(await screen.findAllByTestId("echart")).toHaveLength(2)
  })

  it("lists flagged responses", async () => {
    renderScores(dashboardScores.metrics)
    const flag = await screen.findByRole("region", { name: "Needs follow-up" })
    expect(within(flag).getByText("1 of 2 responses")).toBeInTheDocument()
    expect(within(flag).getByRole("link", { name: "Dee" })).toHaveAttribute(
      "href",
      "/questionnaires/q-5/results",
    )
    expect(within(flag).queryByRole("link", { name: "Bob" })).not.toBeInTheDocument()
  })

  it("explains when there are no scores", async () => {
    renderScores([])
    expect(await screen.findByText(/no scored responses in this period/i)).toBeInTheDocument()
  })
})
