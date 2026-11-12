import { describe, expect, it } from "vitest"
import * as charts from "./loadtestCharts"
import {
  barsHeight,
  barsOption,
  cacheReadOption,
  cellNumber,
  changesOption,
  changesTable,
  fixesOption,
  hitRatioOption,
  lineChartOption,
  postgresRowsOption,
  rampTable,
  readsMissOption,
  soakDroppedOption,
  splitMemoryOption,
  splitSoakCpuOption,
  splitSoakLatencyOption,
  splitStressP95Option,
  type SeriesPalette,
} from "./loadtestCharts"
import * as results from "./loadtestResults"
import { CACHE_PAIRS, CHANGES, RAMP, RUNS, type ResultTableData } from "./loadtestResults"

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

type OptionBuilder = (palette: SeriesPalette) => { series: { data: unknown[] }[] }
const allCharts = Object.entries(charts)
  .filter(([name]) => name.endsWith("Option") && !["lineChartOption", "barsOption"].includes(name))
  .map(([name, build]) => [name, build as unknown as OptionBuilder] as const)

const valuesOf = (item: unknown): unknown[] => {
  if (Array.isArray(item)) return [item[1]]
  if (typeof item === "object" && item !== null) return [(item as { value: unknown }).value]
  return [item]
}

describe("every chart", () => {
  it("is found by this test", () => {
    expect(allCharts.length).toBeGreaterThanOrEqual(30)
  })

  it.each(allCharts)("%s has data and no unreadable figure", (_name, build) => {
    const { series } = build(palette)
    expect(series.length).toBeGreaterThan(0)
    for (const s of series) {
      expect(s.data.length).toBeGreaterThan(0)
      for (const item of s.data) {
        for (const value of valuesOf(item)) {
          if (value !== null) expect(Number.isFinite(value)).toBe(true)
        }
      }
    }
  })

  it.each(allCharts)("%s describes itself to screen readers", (_name, build) => {
    const { aria } = build(palette) as unknown as { aria: { label: { description: string } } }
    expect(aria.label.description.length).toBeGreaterThan(20)
  })
})

describe("barsOption", () => {
  const spec = {
    label: "Bars",
    categories: ["a"],
    format: (value: number) => `${value} ms`,
    series: [{ name: "One", color: "#1", data: [5] }],
  }

  it("shows a legend only for more than one series", () => {
    expect(barsOption(spec, palette).legend).toBeUndefined()
    const two = { ...spec, series: [...spec.series, { name: "Two", color: "#2", data: [6] }] }
    expect(barsOption(two, palette).legend).toBeDefined()
  })

  it("formats both the bar label and the tooltip", () => {
    const option = barsOption(spec, palette) as unknown as {
      series: { label: { formatter: (params: { value: number }) => string } }[]
      tooltip: { valueFormatter: (value: number) => string }
    }
    expect(option.series[0].label.formatter({ value: 5 })).toBe("5 ms")
    expect(option.tooltip.valueFormatter(5)).toBe("5 ms")
  })

  it("grows with its bars, down to a minimum", () => {
    expect(barsHeight(1, 1)).toBe(200)
    expect(barsHeight(7, 2)).toBeGreaterThan(barsHeight(7, 1))
  })
})

describe("line chart legend", () => {
  const manySeries = Array.from({ length: 7 }, (_, i) => ({ ...spec.series[0], name: `Run ${i}` }))
  const gridTop = (option: object) => (option as { grid: { top: number } }).grid.top

  it("leaves room for a long legend to wrap over the plot", () => {
    expect(gridTop(lineChartOption({ ...spec, series: manySeries }, palette))).toBeGreaterThan(
      gridTop(lineChartOption(spec, palette)),
    )
  })
})

describe("charts read from the tables", () => {
  const dataOf = (option: object, i: number) => seriesOf(option)[i].data

  it("parses a table cell", () => {
    expect(cellNumber("1,120 MB")).toBe(1120)
    expect(cellNumber("39 %")).toBe(39)
    expect(cellNumber("3.1 M")).toBe(3.1)
    expect(cellNumber(12)).toBe(12)
  })

  it("Postgres rows read, cache off and on", () => {
    const option = postgresRowsOption(palette)
    expect(dataOf(option, 0)).toEqual([3.1, 3.5])
    expect(dataOf(option, 1)).toEqual([0.45, 0.25])
  })

  it("hit ratios, split out of one cell per traffic mix", () => {
    const option = hitRatioOption(palette)
    expect(dataOf(option, 0)).toEqual([91, 77])
    expect(dataOf(option, 1)).toEqual([96, 89])
  })

  it("cache misses, before and after", () => {
    const option = readsMissOption(palette)
    expect(dataOf(option, 0)).toEqual([275, 239, 97])
    expect(dataOf(option, 1)).toEqual([172, 141, 48])
  })

  it("split memory, for each traffic mix", () => {
    const option = splitMemoryOption(palette)
    expect(dataOf(option, 0)).toEqual([605, 619])
    expect(dataOf(option, 1)).toEqual([1120, 1264])
  })

  it("split stress, with each deploy on its own rates", () => {
    const option = splitStressP95Option(palette)
    expect(dataOf(option, 0)[0]).toEqual([350, 25])
    expect(dataOf(option, 1)[0]).toEqual([358, 23])
    expect(dataOf(option, 1)[4]).toEqual([581, 108])
  })

  it("dropped iterations leave out the first minutes, as the other soak charts do", () => {
    const [before] = seriesOf(soakDroppedOption(palette))
    expect(before.data[0]).toEqual([3, 0])
    expect(before.data[before.data.length - 1]).toEqual([35, 2260])
  })
})

describe("split soak", () => {
  const split = RUNS["soak-20261106T080534Z"]

  it("labels the last minute with its own value", () => {
    const last = split[split.length - 1]
    expect(last[1]).toBe(9.8)
    expect(last[2]).toBe(50)
    expect(JSON.stringify(splitSoakLatencyOption(palette))).toContain("9.8 ms")
    expect(JSON.stringify(splitSoakCpuOption(palette))).toContain("50 %")
  })

  it("puts the re-login drops at minute 45, where the chart marks them", () => {
    expect(split.findIndex((minute) => minute[4] > 0) + 1).toBe(45)
    expect(seriesOf(splitSoakLatencyOption(palette))[0].markLine?.data[0].xAxis).toBe(45)
  })
})

describe("changesTable", () => {
  it("has a row for every change, with its effect", () => {
    expect(changesTable.rows).toHaveLength(CHANGES.length)
    expect(changesTable.rows[3][1]).toContain("+121 %")
  })
})

describe("results data", () => {
  const tables = Object.entries(results).filter(
    (entry): entry is [string, ResultTableData] => entry[0].endsWith("Table"),
  )

  it.each(tables)("%s has a cell for every column in every row", (_name, table) => {
    expect(table.rows.length).toBeGreaterThan(0)
    for (const row of table.rows) expect(row).toHaveLength(table.columns.length)
  })


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

describe("Postgres against MongoDB", () => {
  const ariaOf = (option: object) =>
    (option as { aria: { label: { description: string } } }).aria.label.description

  it("labels each soak line's end with its last row", () => {
    const last = results.mongoSoakTable.rows[results.mongoSoakTable.rows.length - 1]
    expect(last.slice(1)).toEqual(["57 ms", "1,388 ms", "14 %", "76 %"])
    expect(JSON.stringify(charts.mongoSoakLatencyOption(palette))).toContain("1,388 ms")
    expect(ariaOf(charts.mongoSoakLatencyOption(palette))).toContain("from 34 to 1,388")
    expect(ariaOf(charts.mongoSoakCpuOption(palette))).toContain("from 16 to 76")
  })

  it("marks MongoDB's first dropped minute where the chart says", () => {
    expect(seriesOf(charts.mongoSoakLatencyOption(palette))[0].markLine?.data[0].xAxis).toBe(13)
  })

  it("reads every stress knee from the table, coloured by engine", () => {
    const [knees] = seriesOf(charts.mongoKneeOption(palette)) as unknown as {
      data: { value: number; itemStyle: { color: string } }[]
    }[]
    expect(knees.data.map((d) => d.value)).toEqual([575, 579, 614, 332, 322, 495, 526, 509, 404, 419])
    expect(knees.data[3].itemStyle.color).toBe("#1")
    expect(knees.data[0].itemStyle.color).toBe("#off")
    for (const knee of [575, 579, 614, 332, 322, 495, 526, 509, 404, 419]) {
      expect(ariaOf(charts.mongoKneeOption(palette))).toContain(String(knee))
    }
  })

  it("fixed-rate latency, Postgres then MongoDB", () => {
    const [postgres, mongo] = seriesOf(charts.mongoLatencyOption(palette))
    expect(postgres.data).toEqual([3.86, 8.54, 4.06, 8.74])
    expect(mongo.data).toEqual([6.68, 16.12, 4.85, 10.44])
  })
})

describe("catalog on FastAPI against Django", () => {
  const ariaOf = (option: object) =>
    (option as { aria: { label: { description: string } } }).aria.label.description

  it("fixed-rate p95, Django then FastAPI", () => {
    const [django, fastapi] = seriesOf(charts.fastapiHoldOption(palette))
    expect(django.data).toEqual([5.12, 2.56, 5.31, 3.02])
    expect(fastapi.data).toEqual([5.79, 2.3, 5.09, 2.34])
    for (const value of ["5.12", "5.79", "5.31", "5.09", "2.56", "2.30", "3.02", "2.34"]) {
      expect(ariaOf(charts.fastapiHoldOption(palette))).toContain(value)
    }
  })

  it("reads every stress knee from the table, FastAPI in the series colour", () => {
    const [knees] = seriesOf(charts.fastapiKneeOption(palette)) as unknown as {
      data: { value: number; itemStyle: { color: string } }[]
    }[]
    const values = [575, 579, 614, 600, 495, 526, 509, 518]
    expect(knees.data.map((d) => d.value)).toEqual(values)
    expect(knees.data[3].itemStyle.color).toBe("#1")
    expect(knees.data[0].itemStyle.color).toBe("#off")
    for (const knee of values) expect(ariaOf(charts.fastapiKneeOption(palette))).toContain(String(knee))
  })
})

describe("catalog alone (#39)", () => {
  const ariaOf = (option: object) =>
    (option as { aria: { label: { description: string } } }).aria.label.description

  it("reads every knee from the table, the final code in the series colour", () => {
    const [knees] = seriesOf(charts.catalogKneeOption(palette)) as unknown as {
      data: { value: number; itemStyle: { color: string } }[]
    }[]
    const values = [431, 409, 183, 176, 375, 350, 532, 594]
    expect(knees.data.map((d) => d.value)).toEqual(values)
    expect(knees.data[0].itemStyle.color).toBe("#off")
    expect(knees.data[6].itemStyle.color).toBe("#1")
    expect(knees.data[2].itemStyle.color).toBe("#3")
    for (const knee of values) expect(ariaOf(charts.catalogKneeOption(palette))).toContain(String(knee))
  })

  it("group p95, Django then FastAPI, with the label's figures in the table", () => {
    const [django, fastapi] = seriesOf(charts.catalogGroupOption(palette))
    expect(django.data).toEqual([8.52, 7.35, 10.06, 6.5, 7.21, 32.88, 34.46, 43.74])
    expect(fastapi.data).toEqual([4.07, 3.71, 4.95, 2.73, 3.18, 19.2, 19.85, 22.25])
    for (const value of ["8.52", "4.07", "43.74", "22.25"]) {
      expect(ariaOf(charts.catalogGroupOption(palette))).toContain(value)
    }
  })
})
