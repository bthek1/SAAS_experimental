import type { EChartsOption } from "echarts"
import {
  CACHE_PAIRS,
  CHANGES,
  catalogGroupTable,
  catalogKneeTable,
  fastapiHoldTable,
  fastapiKneeTable,
  matchingTable,
  mongoHoldTable,
  mongoSoakTable,
  mongoStressTable,
  profileTable,
  RAMP,
  readsTable,
  RUNS,
  splitHoldTable,
  splitStressTable,
  trueP95Table,
  type ResultTableData,
} from "@/lib/loadtestResults"

/** Resolved theme colours for these charts (see `useSeriesPalette`). */
export interface SeriesPalette {
  /** Fixed categorical order. A run keeps its slot on every chart. */
  series: string[]
  /** The baseline or "before" run. */
  off: string
  /** Chart background, used to ring the end dots. */
  surface: string
  text: string
  border: string
}

interface LinePoint {
  x: number
  y: number
}

interface LineSeries {
  name: string
  color: string
  points: LinePoint[]
  endLabel?: string
}

interface LineChartSpec {
  /** Read out by screen readers in place of the canvas. */
  label: string
  series: LineSeries[]
  xMin: number
  xMax: number
  xStep: number
  yMax: number
  xLabel: string
  format: (y: number) => string
  /** Shared heading for tooltips where every series has the same x, such as a minute. */
  tipTitle?: (x: number) => string
  /** Suffix for a tooltip row, where each series has its own x, such as a rate. */
  tipAt?: (x: number) => string
  marker?: { x: number; text: string }
}

interface TooltipRow {
  seriesName: string
  marker: string
  value: [number, number | null]
}

export const formatMs = (value: number) => `${value.toLocaleString("en-US")} ms`
const formatPct = (value: number) => `${value} %`
const atRate = (x: number) => ` at ${x.toLocaleString("en-US")} req/s`
const minuteTitle = (x: number) => `Minute ${x}`

function axisStyle(palette: SeriesPalette) {
  return {
    axisLabel: { color: palette.text, hideOverlap: true },
    axisLine: { lineStyle: { color: palette.border } },
    splitLine: { lineStyle: { color: palette.border } },
  }
}

/** One line per run, with a dot on its last point. A point above `yMax` leaves a gap. */
export function lineChartOption(spec: LineChartSpec, palette: SeriesPalette): EChartsOption {
  const hasEndLabels = spec.series.some((s) => s.endLabel)
  // A long legend wraps, to four rows at phone width.
  const top = spec.series.length > 4 ? 104 : spec.marker ? 60 : 40
  return {
    aria: { enabled: true, label: { description: spec.label } },
    grid: { top, right: hasEndLabels ? 64 : 16, bottom: 48, left: 44 },
    legend: { top: 0, textStyle: { color: palette.text } },
    tooltip: {
      trigger: "axis",
      formatter: (params) => {
        const rows = (params as unknown as TooltipRow[]).filter((r) => r.value[1] !== null)
        const title = spec.tipTitle && rows[0] ? `${spec.tipTitle(rows[0].value[0])}<br/>` : ""
        return (
          title +
          rows
            .map((r) => {
              const at = spec.tipAt ? spec.tipAt(r.value[0]) : ""
              return `${r.marker}<b>${spec.format(r.value[1] as number)}</b> ${r.seriesName}${at}`
            })
            .join("<br/>")
        )
      },
    },
    xAxis: {
      type: "value",
      min: spec.xMin,
      max: spec.xMax,
      interval: spec.xStep,
      name: spec.xLabel,
      nameLocation: "middle",
      nameGap: 30,
      nameTextStyle: { color: palette.text },
      ...axisStyle(palette),
      splitLine: { show: false },
    },
    yAxis: { type: "value", min: 0, max: spec.yMax, ...axisStyle(palette) },
    series: spec.series.map((s, i) => {
      const lastIndex = s.points.length - 1
      return {
        name: s.name,
        type: "line" as const,
        color: s.color,
        lineStyle: { width: 2 },
        showAllSymbol: true,
        symbol: (_value: unknown, params: { dataIndex: number }) =>
          params.dataIndex === lastIndex ? "circle" : "none",
        symbolSize: 9,
        itemStyle: { borderColor: palette.surface, borderWidth: 2 },
        // The last point can sit on the plot edge; don't cut its dot in half.
        clip: false,
        data: s.points.map((p) => [p.x, p.y > spec.yMax ? null : p.y]),
        endLabel: s.endLabel
          ? { show: true, formatter: s.endLabel, color: palette.text, fontWeight: 600 }
          : undefined,
        labelLayout: { moveOverlap: "shiftY" as const },
        ...(i === 0 && spec.marker
          ? {
              markLine: {
                silent: true,
                symbol: "none",
                label: {
                  formatter: spec.marker.text,
                  position: "end" as const,
                  color: palette.text,
                },
                lineStyle: { color: palette.text, type: "dashed" as const },
                data: [{ xAxis: spec.marker.x }],
              },
            }
          : {}),
      }
    }),
  } as EChartsOption
}

/** Columns of a `RunMinute`. */
const LATENCY = 1
const APP_CPU = 2
const DB_CPU = 3
const DROPPED = 4
type RunColumn = typeof LATENCY | typeof APP_CPU | typeof DB_CPU | typeof DROPPED

function rateSeries(
  name: string,
  run: string,
  color: string,
  endLabel?: string,
  column: RunColumn = LATENCY,
): LineSeries {
  return { name, color, endLabel, points: RUNS[run].map((r) => ({ x: r[0], y: r[column] })) }
}

function minuteSeries(
  name: string,
  run: string,
  color: string,
  endLabel: string,
  column: RunColumn,
  firstMinute = 1,
): LineSeries {
  return {
    name,
    color,
    endLabel,
    points: RUNS[run].map((r, i) => ({ x: i + 1, y: r[column] })).filter((p) => p.x >= firstMinute),
  }
}

const rateChart = {
  xLabel: "Requests per second",
  format: formatMs,
  tipAt: atRate,
}
const minuteChart = {
  xLabel: "Minute of the run",
  tipTitle: minuteTitle,
}

interface BarSeries {
  name: string
  data: (number | { value: number; itemStyle: { color: string } })[]
  color: string
}

interface BarChartSpec {
  label: string
  categories: string[]
  series: BarSeries[]
  format: (value: number) => string
  tooltip?: EChartsOption["tooltip"]
  /** Room for the category names. Narrow it for a chart in a small card. */
  labelWidth?: number
}

/** Pixel height that fits every bar of every category. */
export function barsHeight(categories: number, series: number): number {
  return Math.max(200, 64 + categories * (series * 24 + 12))
}

/** Horizontal bars with the value at the end of each. */
export function barsOption(spec: BarChartSpec, palette: SeriesPalette): EChartsOption {
  const hasLegend = spec.series.length > 1
  return {
    aria: { enabled: true, label: { description: spec.label } },
    grid: { top: hasLegend ? 32 : 8, right: 64, bottom: 24, left: 8, containLabel: true },
    legend: hasLegend ? { top: 0, textStyle: { color: palette.text } } : undefined,
    tooltip: spec.tooltip ?? {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      valueFormatter: (value) => spec.format(value as number),
    },
    xAxis: { type: "value", ...axisStyle(palette) },
    yAxis: {
      type: "category",
      data: spec.categories,
      inverse: true,
      ...axisStyle(palette),
      axisLabel: { color: palette.text, width: spec.labelWidth ?? 150, overflow: "break" },
    },
    series: spec.series.map(({ color, ...s }) => ({
      ...s,
      type: "bar",
      barMaxWidth: 24,
      barGap: "10%",
      itemStyle: { color, borderRadius: [0, 4, 4, 0] },
      label: {
        show: true,
        position: "right",
        formatter: (params) => spec.format(params.value as number),
        color: palette.text,
        fontWeight: 600,
      },
    })),
  }
}

export function changesOption(palette: SeriesPalette): EChartsOption {
  return barsOption(
    {
      label: `Knee per stress run, from about ${CHANGES[0].knee} to about ${CHANGES[CHANGES.length - 1].knee} requests per second. The table below has the same values.`,
      categories: CHANGES.map((c) => c.label),
      format: (value) => `~${value}`,
      series: [
        {
          name: "Knee",
          color: palette.series[0],
          // The grey bar repeated the settings above it: it is not a change.
          data: CHANGES.map((c) =>
            c.repeat ? { value: c.knee, itemStyle: { color: palette.off } } : c.knee,
          ),
        },
      ],
      tooltip: {
        trigger: "item",
        formatter: (params) => {
          const { dataIndex } = params as unknown as { dataIndex: number }
          const c = CHANGES[dataIndex]
          return [
            c.label,
            `<b>~${c.knee} req/s</b> knee`,
            `<b>${c.p95} ms</b> slowest group p95, since run start`,
            `<b>${c.app} % / ${c.db} %</b> saas-app / saas-db CPU`,
          ].join("<br/>")
        },
      },
    },
    palette,
  )
}

export function kneeLatencyOption(palette: SeriesPalette): EChartsOption {
  return barsOption(
    {
      label: "Slowest group and Django p95 at each knee, since run start. The table below has the same values.",
      categories: CHANGES.map((c) => c.label),
      format: formatMs,
      labelWidth: 130,
      series: [
        { name: "Slowest group p95", color: palette.series[0], data: CHANGES.map((c) => c.p95) },
        { name: "Django p95", color: palette.series[1], data: CHANGES.map((c) => c.django) },
      ],
    },
    palette,
  )
}

export function kneeCpuOption(palette: SeriesPalette): EChartsOption {
  return barsOption(
    {
      label: "saas-app and saas-db CPU at each knee. The table below has the same values.",
      categories: CHANGES.map((c) => c.label),
      format: formatPct,
      labelWidth: 130,
      series: [
        { name: "saas-app CPU", color: palette.series[0], data: CHANGES.map((c) => c.app) },
        { name: "saas-db CPU", color: palette.series[1], data: CHANGES.map((c) => c.db) },
      ],
    },
    palette,
  )
}

export function cacheKneesOption(palette: SeriesPalette): EChartsOption {
  return barsOption(
    {
      label:
        "Knee with the cache off and on: about 375 and 480 requests per second on mixed traffic, about 360 and 459 on read-mostly traffic.",
      categories: CACHE_PAIRS.map((p) => `${p.label} (${p.note})`),
      format: (value) => `~${value}`,
      series: [
        { name: "Cache off", color: palette.off, data: CACHE_PAIRS.map((p) => p.off) },
        { name: "Cache on", color: palette.series[0], data: CACHE_PAIRS.map((p) => p.on) },
      ],
    },
    palette,
  )
}

export function rampOption(palette: SeriesPalette): EChartsOption {
  return lineChartOption(
    {
      ...rateChart,
      label: "Latency against request rate for each configuration. The table below has the same values.",
      series: RAMP.map((s) => rateSeries(s.name, s.run, palette.series[s.series])),
      xMin: 0,
      xMax: 500,
      xStep: 50,
      yMax: 40,
    },
    palette,
  )
}

function rampCpuOption(
  column: typeof APP_CPU | typeof DB_CPU,
  yMax: number,
  label: string,
  palette: SeriesPalette,
): EChartsOption {
  return lineChartOption(
    {
      ...rateChart,
      label,
      format: formatPct,
      series: RAMP.map((s) =>
        rateSeries(s.name, s.run, palette.series[s.series], undefined, column),
      ),
      xMin: 0,
      xMax: 500,
      xStep: 100,
      yMax,
    },
    palette,
  )
}

export function rampAppCpuOption(palette: SeriesPalette): EChartsOption {
  return rampCpuOption(
    APP_CPU,
    100,
    "saas-app CPU against request rate for each configuration. The table below has the same values.",
    palette,
  )
}

export function rampDbCpuOption(palette: SeriesPalette): EChartsOption {
  return rampCpuOption(
    DB_CPU,
    60,
    "saas-db CPU against request rate for each configuration. The table below has the same values.",
    palette,
  )
}

function cachePairOption(
  offRun: string,
  onRun: string,
  offLabel: string,
  onLabel: string,
  label: string,
  palette: SeriesPalette,
): EChartsOption {
  return lineChartOption(
    {
      ...rateChart,
      label,
      series: [
        rateSeries("Cache off", offRun, palette.off, offLabel),
        rateSeries("Cache on", onRun, palette.series[0], onLabel),
      ],
      xMin: 150,
      xMax: 500,
      xStep: 50,
      yMax: 40,
    },
    palette,
  )
}

export function cacheMixedOption(palette: SeriesPalette): EChartsOption {
  return cachePairOption(
    "stress-20261103T114326Z",
    "stress-20261103T115330Z",
    "off ~375",
    "on ~480",
    "Mixed traffic: with the cache on, latency stays lower and the knee moves from about 375 to about 480 requests per second.",
    palette,
  )
}

export function cacheReadOption(palette: SeriesPalette): EChartsOption {
  return cachePairOption(
    "stress-20261103T121030Z",
    "stress-20261103T122641Z",
    "off ~360",
    "on ~459",
    "Read-mostly traffic: with the cache on, latency stays lower and the knee moves from about 360 to about 459 requests per second.",
    palette,
  )
}

const SOAK_BEFORE = "soak-20261103T133342Z"
const SOAK_AFTER = "soak-20261104T055745Z"
const soakChart = {
  ...minuteChart,
  xMin: 0,
  xMax: 45,
  xStep: 5,
  marker: { x: 29, text: "drops begin, before" },
}

export function soakLatencyOption(palette: SeriesPalette): EChartsOption {
  return lineChartOption(
    {
      ...soakChart,
      label:
        "Before the fixes, mean latency reaches 33 milliseconds by minute 28 and 327 by minute 35. After them it is 7.5 at minute 28, 11.5 at minute 41 and 33 at minute 45.",
      series: [
        minuteSeries("Before the fixes", SOAK_BEFORE, palette.off, "327 ms", LATENCY, 3),
        minuteSeries("After the fixes", SOAK_AFTER, palette.series[0], "33 ms", LATENCY, 3),
      ],
      yMax: 350,
      format: formatMs,
    },
    palette,
  )
}

export function soakCpuOption(palette: SeriesPalette): EChartsOption {
  return lineChartOption(
    {
      ...soakChart,
      label:
        "Before the fixes, saas-app CPU reaches 93 percent by minute 35. After them it stays between 48 and 66 percent to minute 41, then reaches 77 percent.",
      series: [
        minuteSeries("Before the fixes", SOAK_BEFORE, palette.off, "93 %", APP_CPU, 3),
        minuteSeries("After the fixes", SOAK_AFTER, palette.series[0], "67 %", APP_CPU, 3),
      ],
      yMax: 100,
      format: formatPct,
    },
    palette,
  )
}

export function fixesOption(palette: SeriesPalette): EChartsOption {
  return lineChartOption(
    {
      ...rateChart,
      label:
        "Mean latency by request rate. Before the fixes it reaches 32 milliseconds at about 480 requests per second. The three later runs end at about 430, 497 and 573 requests per second.",
      series: [
        rateSeries("Before the fixes", "stress-20261103T115330Z", palette.off, "~480"),
        rateSeries("After, run 1", "stress-20261104T052442Z", palette.series[0], "~430"),
        rateSeries("After, run 2", "stress-20261104T053920Z", palette.series[2], "~497"),
        rateSeries("After, run 3", "stress-20261104T080836Z", palette.series[1], "~573"),
      ],
      xMin: 150,
      xMax: 650,
      xStep: 50,
      yMax: 40,
    },
    palette,
  )
}

export function nearPeakOption(palette: SeriesPalette): EChartsOption {
  return lineChartOption(
    {
      ...minuteChart,
      label:
        "Mean latency by minute at about 445 requests per second. Run 1 rises to 129 milliseconds in minute 6, recovers by minute 10 and ends at 24. Run 2 rises steadily from 7 to 16.",
      series: [
        minuteSeries("Run 1", "soak-20261104T074625Z", palette.series[0], "24 ms", LATENCY),
        minuteSeries("Run 2", "soak-20261104T083207Z", palette.series[2], "16 ms", LATENCY),
      ],
      xMin: 1,
      xMax: 14,
      xStep: 1,
      yMax: 140,
      format: formatMs,
    },
    palette,
  )
}

export function holdOption(palette: SeriesPalette): EChartsOption {
  return lineChartOption(
    {
      ...minuteChart,
      label:
        "Mean latency over a 10-minute hold: it rises from 4 to about 8 milliseconds before the cache, peaking at 10.8, and stays between 4 and 5 milliseconds with it.",
      series: [
        minuteSeries("Sync workers, no cache", "load-20261102T052551Z", palette.off, "7.9 ms", LATENCY),
        minuteSeries("Threads and cache", "load-20261103T125112Z", palette.series[0], "4.8 ms", LATENCY),
      ],
      xMin: 1,
      xMax: 11,
      xStep: 2,
      yMax: 15,
      format: formatMs,
    },
    palette,
  )
}

export function soakDbCpuOption(palette: SeriesPalette): EChartsOption {
  return lineChartOption(
    {
      ...soakChart,
      label: "saas-db CPU by minute. Before the fixes it reaches 30 percent by minute 35. After them it reaches 31 percent at minute 43.",
      series: [
        minuteSeries("Before the fixes", SOAK_BEFORE, palette.off, "30 %", DB_CPU, 3),
        minuteSeries("After the fixes", SOAK_AFTER, palette.series[0], "29 %", DB_CPU, 3),
      ],
      yMax: 40,
      format: formatPct,
    },
    palette,
  )
}

export function soakDroppedOption(palette: SeriesPalette): EChartsOption {
  return lineChartOption(
    {
      ...soakChart,
      label: "Iterations k6 dropped each minute. Before the fixes drops begin at minute 29 and reach 2,260 a minute by minute 35. After them there are none.",
      series: [
        minuteSeries("Before the fixes", SOAK_BEFORE, palette.off, "2,260", DROPPED, 3),
        minuteSeries("After the fixes", SOAK_AFTER, palette.series[0], "0", DROPPED, 3),
      ],
      yMax: 2500,
      format: (value) => value.toLocaleString("en-US"),
    },
    palette,
  )
}

const SOAK_SPLIT = "soak-20261106T080534Z"
const splitSoakChart = {
  ...minuteChart,
  xMin: 0,
  xMax: 60,
  xStep: 10,
  marker: { x: 45, text: "k6 logs in again" },
}

export function splitSoakLatencyOption(palette: SeriesPalette): EChartsOption {
  return lineChartOption(
    {
      ...splitSoakChart,
      label:
        "Mean latency by minute at about 350 requests per second. Before the split it is 9.6 milliseconds at minute 35 and 33 at minute 45, where that run was stopped. The split is 9.7 at minute 35, 47 at minute 45 while k6 logs in again, and 9.8 at minute 59.",
      series: [
        minuteSeries("Before the split", SOAK_AFTER, palette.off, "33 ms", LATENCY, 3),
        minuteSeries("Split", SOAK_SPLIT, palette.series[0], "9.8 ms", LATENCY, 3),
      ],
      yMax: 50,
      format: formatMs,
    },
    palette,
  )
}

export function splitSoakCpuOption(palette: SeriesPalette): EChartsOption {
  return lineChartOption(
    {
      ...splitSoakChart,
      label:
        "CPU of the busiest app container by minute: saas-app before the split, saas-instances after. Before the split it reaches 77 percent at minute 43. The split stays between 45 and 62 percent and ends at 50.",
      series: [
        minuteSeries("Before the split", SOAK_AFTER, palette.off, "67 %", APP_CPU, 3),
        minuteSeries("Split", SOAK_SPLIT, palette.series[0], "50 %", APP_CPU, 3),
      ],
      yMax: 100,
      format: formatPct,
    },
    palette,
  )
}

export function holdCpuOption(palette: SeriesPalette): EChartsOption {
  return lineChartOption(
    {
      ...minuteChart,
      label: "saas-app CPU over the 10-minute hold: it peaks at 44 percent with sync workers and no cache, and stays between 28 and 32 percent with threads and the cache.",
      series: [
        minuteSeries("Sync workers, no cache", "load-20261102T052551Z", palette.off, "38 %", APP_CPU),
        minuteSeries("Threads and cache", "load-20261103T125112Z", palette.series[0], "31 %", APP_CPU),
      ],
      xMin: 1,
      xMax: 11,
      xStep: 2,
      yMax: 50,
      format: formatPct,
    },
    palette,
  )
}

export function fixesCpuOption(palette: SeriesPalette): EChartsOption {
  return lineChartOption(
    {
      ...rateChart,
      label: "saas-app CPU by request rate, before the dashboard fixes and in the three runs after them.",
      format: formatPct,
      series: [
        rateSeries("Before the fixes", "stress-20261103T115330Z", palette.off, "~480", APP_CPU),
        rateSeries("After, run 1", "stress-20261104T052442Z", palette.series[0], "~430", APP_CPU),
        rateSeries("After, run 2", "stress-20261104T053920Z", palette.series[2], "~497", APP_CPU),
        rateSeries("After, run 3", "stress-20261104T080836Z", palette.series[1], "~573", APP_CPU),
      ],
      xMin: 150,
      xMax: 650,
      xStep: 50,
      yMax: 100,
    },
    palette,
  )
}

export function nearPeakCpuOption(palette: SeriesPalette): EChartsOption {
  return lineChartOption(
    {
      ...minuteChart,
      label: "saas-app CPU by minute at about 445 requests per second. Run 1 reaches 90 percent in minute 6, then recovers to about 78. Run 2 holds about 60.",
      series: [
        minuteSeries("Run 1", "soak-20261104T074625Z", palette.series[0], "79 %", APP_CPU),
        minuteSeries("Run 2", "soak-20261104T083207Z", palette.series[2], "61 %", APP_CPU),
      ],
      xMin: 1,
      xMax: 14,
      xStep: 1,
      yMax: 100,
      format: formatPct,
    },
    palette,
  )
}

/** The number in a table cell: "1,120 MB" is 1120, "39 %" is 39. */
export function cellNumber(cell: string | number): number {
  return Number.parseFloat(String(cell).replace(/,/g, ""))
}

/** Both numbers in a cell such as "350 / 358". */
function cellPair(cell: string | number): [number, number] {
  const [first, second] = String(cell).split(" / ")
  return [cellNumber(first), cellNumber(second)]
}

function rowNamed(table: ResultTableData, name: string): (string | number)[] {
  const row = table.rows.find((r) => r[0] === name)
  if (!row) throw new Error(`No row named ${name}`)
  return row
}

function columnNumbers(table: ResultTableData, column: number, rows = table.rows): number[] {
  return rows.map((r) => cellNumber(r[column]))
}

const ENDPOINT_ROWS = matchingTable.rows.slice(0, 5)

function endpointP95Option(
  offColumn: number,
  onColumn: number,
  traffic: string,
  palette: SeriesPalette,
): EChartsOption {
  return barsOption(
    {
      label: `${traffic} traffic: k6 p95 per endpoint with the cache off and on. The table below has the same values.`,
      categories: ENDPOINT_ROWS.map((r) => String(r[0])),
      format: formatMs,
      series: [
        { name: "Cache off", color: palette.off, data: columnNumbers(matchingTable, offColumn, ENDPOINT_ROWS) },
        { name: "Cache on", color: palette.series[0], data: columnNumbers(matchingTable, onColumn, ENDPOINT_ROWS) },
      ],
    },
    palette,
  )
}

export function endpointMixedOption(palette: SeriesPalette): EChartsOption {
  return endpointP95Option(1, 2, "Mixed", palette)
}

export function endpointReadOption(palette: SeriesPalette): EChartsOption {
  return endpointP95Option(3, 4, "Read-mostly", palette)
}

/** Cache off and on, for mixed and read-mostly traffic, from one row of the table. */
function trafficBars(
  rowName: string,
  label: string,
  format: (value: number) => string,
  palette: SeriesPalette,
): EChartsOption {
  const row = rowNamed(matchingTable, rowName)
  return barsOption(
    {
      label,
      categories: ["Mixed", "Read-mostly"],
      format,
      labelWidth: 80,
      series: [
        { name: "Cache off", color: palette.off, data: [cellNumber(row[1]), cellNumber(row[3])] },
        { name: "Cache on", color: palette.series[0], data: [cellNumber(row[2]), cellNumber(row[4])] },
      ],
    },
    palette,
  )
}

export function postgresRowsOption(palette: SeriesPalette): EChartsOption {
  return trafficBars(
    "Postgres rows read/s",
    "Millions of Postgres rows read per second, cache off and on. The table below has the same values.",
    (value) => `${value} M`,
    palette,
  )
}

export function dbCpuOption(palette: SeriesPalette): EChartsOption {
  return trafficBars(
    "saas-db CPU",
    "saas-db CPU at matching rates, cache off and on. The table below has the same values.",
    formatPct,
    palette,
  )
}

export function hitRatioOption(palette: SeriesPalette): EChartsOption {
  const row = rowNamed(matchingTable, "Hit ratio: dashboard / scores")
  const [mixedDashboard, mixedScores] = cellPair(row[2])
  const [readDashboard, readScores] = cellPair(row[4])
  return barsOption(
    {
      label: "Cache hit ratio for the dashboard and scores endpoints. The table below has the same values.",
      categories: ["dashboard", "scores"],
      format: formatPct,
      labelWidth: 80,
      series: [
        { name: "Mixed", color: palette.series[0], data: [mixedDashboard, mixedScores] },
        { name: "Read-mostly", color: palette.series[1], data: [readDashboard, readScores] },
      ],
    },
    palette,
  )
}

function linesByRate(
  label: string,
  series: LineSeries[],
  yMax: number,
  format: (value: number) => string,
  palette: SeriesPalette,
): EChartsOption {
  return lineChartOption(
    { ...rateChart, label, series, format, xMin: 300, xMax: 600, xStep: 50, yMax },
    palette,
  )
}

function tableLine(
  table: ResultTableData,
  name: string,
  column: number,
  color: string,
): LineSeries {
  return {
    name,
    color,
    points: table.rows.map((r) => ({ x: cellNumber(r[0]), y: cellNumber(r[column]) })),
  }
}

export function trueP95LatencyOption(palette: SeriesPalette): EChartsOption {
  return linesByRate(
    "True per-minute latency by request rate: mean, slowest group p95 and Django p95. The table below has the same values.",
    [
      tableLine(trueP95Table, "Slowest group p95", 2, palette.series[0]),
      tableLine(trueP95Table, "Django p95", 3, palette.series[1]),
      tableLine(trueP95Table, "Mean", 1, palette.series[2]),
    ],
    120,
    formatMs,
    palette,
  )
}

export function trueP95CpuOption(palette: SeriesPalette): EChartsOption {
  return linesByRate(
    "saas-app and saas-db CPU by request rate in the same run. The table below has the same values.",
    [
      tableLine(trueP95Table, "saas-app CPU", 4, palette.series[0]),
      tableLine(trueP95Table, "saas-db CPU", 5, palette.series[1]),
    ],
    100,
    formatPct,
    palette,
  )
}

function beforeAfterBars(
  table: ResultTableData,
  beforeColumn: number,
  afterColumn: number,
  label: string,
  palette: SeriesPalette,
): EChartsOption {
  return barsOption(
    {
      label: `${label} The table below has the same values.`,
      categories: table.rows.map((r) => String(r[0])),
      format: formatMs,
      labelWidth: 110,
      series: [
        { name: "Before", color: palette.off, data: columnNumbers(table, beforeColumn) },
        { name: "After", color: palette.series[0], data: columnNumbers(table, afterColumn) },
      ],
    },
    palette,
  )
}

export function readsMissOption(palette: SeriesPalette): EChartsOption {
  return beforeAfterBars(readsTable, 1, 2, "Time for a cache miss on each read, before and after the fixes.", palette)
}

export function readsHitOption(palette: SeriesPalette): EChartsOption {
  return beforeAfterBars(readsTable, 3, 4, "Time for a cache hit on each read, before and after the fixes.", palette)
}

export function profileMissOption(palette: SeriesPalette): EChartsOption {
  return beforeAfterBars(profileTable, 1, 2, "Profile: total time for a cache miss, before and after the fixes.", palette)
}

export function profilePythonOption(palette: SeriesPalette): EChartsOption {
  return beforeAfterBars(profileTable, 3, 4, "Profile: Python CPU for a cache miss, before and after the fixes.", palette)
}

export function profileHitOption(palette: SeriesPalette): EChartsOption {
  return beforeAfterBars(profileTable, 5, 6, "Profile: time for a cache hit, before and after the fixes.", palette)
}

/** `rows`: table row name to chart category, each drawn for mixed and read-mostly traffic. */
function splitHoldBars(
  rows: { row: string; name: string }[],
  label: string,
  format: (value: number) => string,
  palette: SeriesPalette,
): EChartsOption {
  const pick = (mixedColumn: number, readColumn: number) => [
    ...rows.map(({ row }) => cellNumber(rowNamed(splitHoldTable, row)[mixedColumn])),
    ...rows.map(({ row }) => cellNumber(rowNamed(splitHoldTable, row)[readColumn])),
  ]
  return barsOption(
    {
      label: `${label} The table below has the same values.`,
      categories: [
        ...rows.map(({ name }) => `Mixed, ${name}`),
        ...rows.map(({ name }) => `Read, ${name}`),
      ],
      format,
      labelWidth: 90,
      series: [
        { name: "Before", color: palette.off, data: pick(1, 3) },
        { name: "Split", color: palette.series[0], data: pick(2, 4) },
      ],
    },
    palette,
  )
}

export function splitLatencyOption(palette: SeriesPalette): EChartsOption {
  return splitHoldBars(
    [
      { row: "Mean", name: "mean" },
      { row: "p95, all requests", name: "p95" },
    ],
    "Latency over 5 minutes at a fixed rate, before and after the split.",
    formatMs,
    palette,
  )
}

export function splitCpuOption(palette: SeriesPalette): EChartsOption {
  return splitHoldBars(
    [
      { row: "App-tier CPU, in cores", name: "app tier" },
      { row: "saas-db CPU, in cores", name: "saas-db" },
    ],
    "CPU in cores at a fixed rate, before and after the split.",
    (value) => `${value}`,
    palette,
  )
}

export function splitMemoryOption(palette: SeriesPalette): EChartsOption {
  return splitHoldBars(
    [{ row: "App-tier memory in use", name: "app tier" }],
    "App-tier memory in use at a fixed rate, before and after the split.",
    (value) => `${value.toLocaleString("en-US")} MB`,
    palette,
  )
}

/** One column of the before / after table, as a line for each deploy. */
function splitStressOption(
  column: number,
  label: string,
  yMax: number,
  format: (value: number) => string,
  palette: SeriesPalette,
): EChartsOption {
  const line = (name: string, color: string, side: 0 | 1): LineSeries => ({
    name,
    color,
    points: splitStressTable.rows.map((r) => ({
      x: cellPair(r[0])[side],
      y: cellPair(r[column])[side],
    })),
  })
  return linesByRate(
    `${label} The table below has the same values.`,
    [line("Before", palette.off, 0), line("Split", palette.series[0], 1)],
    yMax,
    format,
    palette,
  )
}

export function splitStressMeanOption(palette: SeriesPalette): EChartsOption {
  return splitStressOption(1, "Mean latency by request rate, before and after the split.", 20, formatMs, palette)
}

export function splitStressP95Option(palette: SeriesPalette): EChartsOption {
  return splitStressOption(2, "Slowest group p95 by request rate, before and after the split.", 120, formatMs, palette)
}

export function splitStressCpuOption(palette: SeriesPalette): EChartsOption {
  return splitStressOption(4, "CPU of the busiest app container by request rate, before and after the split.", 100, formatPct, palette)
}

/** Two engines on the same table: the baseline in the neutral colour, mixed and read-mostly traffic. */
function engineHoldBars(
  table: ResultTableData,
  [baseline, candidate]: [string, string],
  rows: { row: string; name: string }[],
  label: string,
  format: (value: number) => string,
  palette: SeriesPalette,
): EChartsOption {
  const pick = (mixedColumn: number, readColumn: number) => [
    ...rows.map(({ row }) => cellNumber(rowNamed(table, row)[mixedColumn])),
    ...rows.map(({ row }) => cellNumber(rowNamed(table, row)[readColumn])),
  ]
  return barsOption(
    {
      label: `${label} The table below has the same values.`,
      categories: [
        ...rows.map(({ name }) => `Mixed, ${name}`),
        ...rows.map(({ name }) => `Read, ${name}`),
      ],
      format,
      labelWidth: 90,
      series: [
        { name: baseline, color: palette.off, data: pick(1, 3) },
        { name: candidate, color: palette.series[0], data: pick(2, 4) },
      ],
    },
    palette,
  )
}

export function mongoLatencyOption(palette: SeriesPalette): EChartsOption {
  return engineHoldBars(
    mongoHoldTable,
    ["Postgres", "MongoDB"],
    [
      { row: "Mean", name: "mean" },
      { row: "p95, all requests", name: "p95" },
    ],
    "Latency over 5 minutes at a fixed rate, with instances on Postgres and on MongoDB.",
    formatMs,
    palette,
  )
}

export function mongoCpuOption(palette: SeriesPalette): EChartsOption {
  return engineHoldBars(
    mongoHoldTable,
    ["Postgres", "MongoDB"],
    [{ row: "Database CPU, minute 5", name: "database" }],
    "CPU of the database container at minute 5 of the same runs, Postgres on saas-db and MongoDB on saas-mongo.",
    formatPct,
    palette,
  )
}

export function mongoKneeOption(palette: SeriesPalette): EChartsOption {
  return barsOption(
    {
      label:
        "Knee of each stress run. Mixed traffic: Postgres about 575, 579 and 614 requests per second, MongoDB about 332 and 322. Read-mostly: Postgres about 495, 526 and 509, MongoDB about 404 and 419. The table below has the same values.",
      categories: mongoStressTable.rows.map((r) => String(r[0])),
      format: (value) => `~${value}`,
      labelWidth: 120,
      series: [
        {
          name: "Knee",
          color: palette.off,
          data: mongoStressTable.rows.map((r) => ({
            value: cellNumber(String(r[1]).replace("~", "")),
            itemStyle: { color: String(r[0]).includes("MongoDB") ? palette.series[0] : palette.off },
          })),
        },
      ],
    },
    palette,
  )
}

function soakLine(column: number, name: string, color: string, endLabel: string): LineSeries {
  return { ...tableLine(mongoSoakTable, name, column, color), endLabel }
}

const engineSoakChart = {
  ...minuteChart,
  xMin: 0,
  xMax: 18,
  xStep: 3,
  marker: { x: 13, text: "MongoDB drops begin" },
}

export function mongoSoakLatencyOption(palette: SeriesPalette): EChartsOption {
  return lineChartOption(
    {
      ...engineSoakChart,
      label:
        "Slowest endpoint group's p95 by minute at about 350 requests per second. Postgres rises from 13 to 57 milliseconds by minute 18. MongoDB rises from 34 to 1,388, and k6 began dropping iterations at minute 13. The table below has the same values.",
      series: [
        soakLine(1, "Postgres", palette.off, "57 ms"),
        soakLine(2, "MongoDB", palette.series[0], "1,388 ms"),
      ],
      yMax: 1500,
      format: formatMs,
    },
    palette,
  )
}

export function mongoSoakCpuOption(palette: SeriesPalette): EChartsOption {
  return lineChartOption(
    {
      ...engineSoakChart,
      label:
        "Database container CPU by minute in the same soaks. Postgres rises from 9 to 14 percent, MongoDB from 16 to 76. The table below has the same values.",
      series: [
        soakLine(3, "Postgres", palette.off, "14 %"),
        soakLine(4, "MongoDB", palette.series[0], "76 %"),
      ],
      yMax: 100,
      format: formatPct,
    },
    palette,
  )
}

export const changesTable: ResultTableData = {
  columns: [
    { title: "Change" },
    { title: "Effect", prose: true },
    { title: "Knee, req/s", num: true },
    { title: "Slowest group p95, since run start", num: true },
    { title: "Django p95", num: true },
    { title: "saas-app CPU", num: true },
    { title: "saas-db CPU", num: true },
    { title: "Whole-run requests", num: true },
    { title: "Run", code: true },
  ],
  rows: CHANGES.map((c) => [
    c.label,
    c.note,
    `~${c.knee}`,
    formatMs(c.p95),
    formatMs(c.django),
    `${c.app} %`,
    `${c.db} %`,
    c.requests.toLocaleString("en-US"),
    c.run,
  ]),
}

export const rampTable: ResultTableData = {
  columns: [
    { title: "Run" },
    { title: "Minute", num: true },
    { title: "req/s", num: true },
    { title: "Mean latency", num: true },
    { title: "saas-app CPU", num: true },
    { title: "saas-db CPU", num: true },
  ],
  rows: RAMP.flatMap((s) =>
    RUNS[s.run].map((r, i) => [s.name, i + 1, r[0], formatMs(r[1]), `${r[2]} %`, `${r[3]} %`]),
  ),
}

export function fastapiHoldOption(palette: SeriesPalette): EChartsOption {
  return engineHoldBars(
    fastapiHoldTable,
    ["Django", "FastAPI"],
    [
      { row: "questionnaire-type-list p95", name: "type list" },
      { row: "health p95", name: "health" },
    ],
    "p95 of catalog's endpoint groups over 5 minutes at a fixed rate, with catalog on Django and on FastAPI. Type list: 5.12 against 5.79 milliseconds mixed, 5.31 against 5.09 read. Health: 2.56 against 2.30 mixed, 3.02 against 2.34 read.",
    formatMs,
    palette,
  )
}

export function fastapiKneeOption(palette: SeriesPalette): EChartsOption {
  return barsOption(
    {
      label:
        "Knee of each stress run. Mixed traffic: Django about 575, 579 and 614 requests per second, FastAPI about 600. Read-mostly: Django about 495, 526 and 509, FastAPI about 518. The table below has the same values.",
      categories: fastapiKneeTable.rows.map((r) => String(r[0])),
      format: (value) => `~${value}`,
      labelWidth: 120,
      series: [
        {
          name: "Knee",
          color: palette.off,
          data: fastapiKneeTable.rows.map((r) => ({
            value: cellNumber(String(r[1]).replace("~", "")),
            itemStyle: { color: String(r[0]).includes("FastAPI") ? palette.series[0] : palette.off },
          })),
        },
      ],
    },
    palette,
  )
}

/** Knee per run of catalog's own traffic: Django neutral, FastAPI by fix, the final code in the series colour. */
export function catalogKneeOption(palette: SeriesPalette): EChartsOption {
  return barsOption(
    {
      label:
        "Knee of each stress run of catalog's own traffic. Django about 431 and 409 requests per second. FastAPI about 183 and 176 before the fixes, 375 and 350 with the signing-key fix, 532 and 594 with both fixes. The table below has the same values.",
      categories: catalogKneeTable.rows.map((r) => String(r[0])),
      format: (value) => `~${value}`,
      labelWidth: 140,
      series: [
        {
          name: "Knee",
          color: palette.off,
          data: catalogKneeTable.rows.map((r) => {
            const run = String(r[0])
            const color = run.includes("both fixes") ? palette.series[0] : run.includes("FastAPI") ? palette.series[2] : palette.off
            return { value: cellNumber(String(r[1]).replace("~", "")), itemStyle: { color } }
          }),
        },
      ],
    },
    palette,
  )
}

export function catalogGroupOption(palette: SeriesPalette): EChartsOption {
  return barsOption(
    {
      label:
        "p95 of each of catalog's endpoint groups at about 240 requests per second, Django then FastAPI. FastAPI is lower in every group: type list 8.52 against 4.07 milliseconds, type delete 43.74 against 22.25. The table below has the same values.",
      categories: catalogGroupTable.rows.map((r) => String(r[0])),
      format: formatMs,
      labelWidth: 110,
      series: [
        { name: "Django", color: palette.off, data: catalogGroupTable.rows.map((r) => cellNumber(r[1])) },
        { name: "FastAPI", color: palette.series[0], data: catalogGroupTable.rows.map((r) => cellNumber(r[2])) },
      ],
    },
    palette,
  )
}
