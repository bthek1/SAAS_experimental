import { useEffect, useState } from "react"
import type { ChartPalette } from "@/lib/dashboard"
import { getCSSVar } from "@/lib/theme"

function readPalette(): ChartPalette {
  return {
    strong: getCSSVar("chart4"),
    mid: getCSSVar("chart2"),
    light: getCSSVar("chart1"),
    text: getCSSVar("mutedForeground"),
    border: getCSSVar("border"),
  }
}

/**
 * Theme colours for ECharts, re-read whenever the `dark` class on <html> changes
 * (ECharts draws on a canvas, so it cannot follow CSS variables by itself).
 */
export function useChartPalette(): ChartPalette {
  const [palette, setPalette] = useState(readPalette)

  useEffect(() => {
    const observer = new MutationObserver(() => setPalette(readPalette()))
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] })
    return () => observer.disconnect()
  }, [])

  return palette
}
