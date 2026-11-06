import { act, renderHook, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { useChartPalette, useSeriesPalette } from "./useChartPalette"

// The value says which token was read, and in which theme.
vi.mock("@/lib/theme", () => ({
  getCSSVar: (token: string) =>
    `${document.documentElement.classList.contains("dark") ? "dark" : "light"}:${token}`,
}))

afterEach(() => document.documentElement.classList.remove("dark"))

describe("useChartPalette", () => {
  it("maps the dashboard's meanings onto chart tokens", () => {
    const { result } = renderHook(() => useChartPalette())
    expect(result.current).toEqual({
      strong: "light:chart4",
      mid: "light:chart2",
      light: "light:chart1",
      text: "light:mutedForeground",
      border: "light:border",
    })
  })

  it("re-reads when the theme changes", async () => {
    const { result } = renderHook(() => useChartPalette())
    act(() => document.documentElement.classList.add("dark"))
    await waitFor(() => expect(result.current.strong).toBe("dark:chart4"))
  })
})

describe("useSeriesPalette", () => {
  it("reads the series slots in their fixed order", () => {
    const { result } = renderHook(() => useSeriesPalette())
    expect(result.current.series).toEqual(
      [1, 2, 3, 4, 5, 6, 7].map((slot) => `light:series${slot}`),
    )
    expect(result.current.off).toBe("light:seriesOff")
    expect(result.current.surface).toBe("light:card")
  })

  it("re-reads when the theme changes", async () => {
    const { result } = renderHook(() => useSeriesPalette())
    act(() => document.documentElement.classList.add("dark"))
    await waitFor(() => expect(result.current.series[0]).toBe("dark:series1"))
  })

  it("stops watching the theme after unmount", () => {
    const disconnect = vi.spyOn(MutationObserver.prototype, "disconnect")
    const { unmount } = renderHook(() => useSeriesPalette())
    unmount()
    expect(disconnect).toHaveBeenCalled()
    disconnect.mockRestore()
  })
})
