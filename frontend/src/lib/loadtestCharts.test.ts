import { describe, expect, it } from "vitest"
import {
  cacheReadOption,
  changesOption,
  fixesOption,
  lineChartOption,
  rampTable,
  type SeriesPalette,
} from "./loadtestCharts"
import { CACHE_PAIRS, CHANGES, RAMP, RUNS } from "./loadtestResults"

const palette: SeriesPalette = {
  series: ["#1", "#2", "#3", "#4", "#5", "#6", "#7"],
  off: "#off",
  surface: "#surface",
  text: "#text",
  border: "#border",
}

type AnySeries = {
  data: unknown[]
  symbol: (value: unknown, params: { dataIndex: number }) => string
  markLine?: { data: { xAxis: number }[] }
}
const seriesOf = (option: object) => (option as { series: AnySeries[] }).series

const spec = {
  label: "A chart",
  xMin: 0,
  xMax: 10,
  xStep: 1,
  yMax: 50,
  xLabel: "x",
  format: (y: number) => `${y} ms`,
  series: [
    {
      name: "Run",
      color: "#1",
      points: [
        { x: 1, y: 5 },
        { x: 2, y: 99 },
        { x: 3, y: 7 },
      ],
    },
  ],
}

describe("lineChartOption", () => {
  it("leaves a gap for a point above the scale, rather than squashing the axis", () => {
    const option = lineChartOption(spec, palette)
    expect(seriesOf(option)[0].data).toEqual([
      [1, 5],
      [2, null],
      [3, 7],
    ])
    expect((option.yAxis as { max: number }).max).toBe(50)
  })

  it("marks only the last point of a run", () => {
    const { symbol } = seriesOf(lineChartOption(spec, palette))[0]
    expect(symbol(null, { dataIndex: 0 })).toBe("none")
    expect(symbol(null, { dataIndex: 2 })).toBe("circle")
  })

  it("describes the chart for screen readers", () => {
    const option = lineChartOption(spec, palette) as { aria: { label: { description: string } } }
    expect(option.aria.label.description).toBe("A chart")
  })

  it("lists each series in the tooltip and skips one with no value", () => {
    const option = lineChartOption(
      { ...spec, tipTitle: (x) => `Minute ${x}`, tipAt: (x) => ` at ${x}` },
      palette,
    )
    const { formatter } = option.tooltip as { formatter: (params: unknown) => string }
    const html = formatter([
      { seriesName: "Run", marker: "*", value: [3, 7] },
      { seriesName: "Gap", marker: "*", value: [3, null] },
    ])
    expect(html).toBe("Minute 3<br/>*<b>7 ms</b> Run at 3")
  })
})

describe("charts", () => {
  it("greys the repeated run, the one bar that is not a change", () => {
    const { data } = seriesOf(changesOption(palette))[0]
    const repeatIndex = CHANGES.findIndex((c) => c.repeat)
    expect(data[repeatIndex]).toEqual({
      value: CHANGES[repeatIndex].knee,
      itemStyle: { color: "#off" },
    })
    expect(data[0]).toBe(CHANGES[0].knee)
  })

  it("does not draw the stall that is off the scale of the read-mostly chart", () => {
    const off = seriesOf(cacheReadOption(palette))[0].data as [number, number | null][]
    expect(off.find(([x]) => x === 268.6)?.[1]).toBeNull()
  })

  it("keeps the same run colours across a chart", () => {
    const names = (fixesOption(palette) as { series: { color: string }[] }).series.map((s) => s.color)
    expect(names).toEqual(["#off", "#1", "#3", "#2"])
  })
})

describe("results data", () => {
  it("has per-minute figures for every run a chart reads", () => {
    for (const { run } of RAMP) expect(RUNS[run]).toBeDefined()
    for (const { run } of CHANGES) expect(RUNS[run]).toBeDefined()
    for (const pair of CACHE_PAIRS) {
      expect(RUNS[pair.offRun]).toBeDefined()
      expect(RUNS[pair.onRun]).toBeDefined()
    }
  })

  it("ends each stress run on its recorded knee", () => {
    const lastRate = (run: string) => Math.round(RUNS[run][RUNS[run].length - 1][0])
    for (const c of CHANGES) expect(lastRate(c.run)).toBe(c.knee)
    for (const p of CACHE_PAIRS) {
      expect(lastRate(p.offRun)).toBe(p.off)
      expect(lastRate(p.onRun)).toBe(p.on)
    }
  })

  it("has one table row per minute of every ramp run", () => {
    const minutes = RAMP.reduce((sum, s) => sum + RUNS[s.run].length, 0)
    expect(rampTable.rows).toHaveLength(minutes)
  })
})
