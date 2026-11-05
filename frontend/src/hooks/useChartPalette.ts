import { useEffect, useState } from "react"
import type { ChartPalette } from "@/lib/dashboard"
import type { SeriesPalette } from "@/lib/loadtestCharts"
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

function readSeriesPalette(): SeriesPalette {
  return {
    series: [
      getCSSVar("series1"),
      getCSSVar("series2"),
      getCSSVar("series3"),
      getCSSVar("series4"),
      getCSSVar("series5"),
      getCSSVar("series6"),
      getCSSVar("series7"),
    ],
    off: getCSSVar("seriesOff"),
    surface: getCSSVar("card"),
    text: getCSSVar("mutedForeground"),
    border: getCSSVar("border"),
  }
}

/**
 * Re-read theme colours whenever the `dark` class on <html> changes
 * (ECharts draws on a canvas, so it cannot follow CSS variables by itself).
 */
function useThemeColours<T>(read: () => T): T {
  const [colours, setColours] = useState(read)

  useEffect(() => {
    const observer = new MutationObserver(() => setColours(read()))
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] })
    return () => observer.disconnect()
  }, [read])

  return colours
}

/** Theme colours for charts of done / partly done / waiting. */
export function useChartPalette(): ChartPalette {
  return useThemeColours(readPalette)
}

/** Theme colours for charts with many separate series. */
export function useSeriesPalette(): SeriesPalette {
  return useThemeColours(readSeriesPalette)
}
