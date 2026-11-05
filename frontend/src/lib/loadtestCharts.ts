import type { EChartsOption } from "echarts"
import {
  CACHE_PAIRS,
  CHANGES,
  RAMP,
  RUNS,
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
  return {
    aria: { enabled: true, label: { description: spec.label } },
    grid: { top: spec.marker ? 60 : 40, right: hasEndLabels ? 64 : 16, bottom: 48, left: 44 },
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

function rateSeries(name: string, run: string, color: string, endLabel?: string): LineSeries {
  return { name, color, endLabel, points: RUNS[run].map((r) => ({ x: r[0], y: r[1] })) }
}

/** `column`: 1 is mean latency, 2 is app CPU. */
function minuteSeries(
  name: string,
  run: string,
  color: string,
  endLabel: string,
  column: 1 | 2,
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

/** Horizontal bars with the value at the end of each. */
function kneeBars(
  categories: string[],
  series: { name: string; data: (number | { value: number; itemStyle: { color: string } })[]; color: string }[],
  label: string,
  palette: SeriesPalette,
  tooltip: EChartsOption["tooltip"],
): EChartsOption {
  return {
    aria: { enabled: true, label: { description: label } },
    grid: { top: series.length > 1 ? 32 : 8, right: 48, bottom: 24, left: 8, containLabel: true },
    legend: series.length > 1 ? { top: 0, textStyle: { color: palette.text } } : undefined,
    tooltip,
    xAxis: { type: "value", ...axisStyle(palette) },
    yAxis: {
      type: "category",
      data: categories,
      inverse: true,
      ...axisStyle(palette),
      axisLabel: { color: palette.text, width: 150, overflow: "break" },
    },
    series: series.map(({ color, ...s }) => ({
      ...s,
      type: "bar",
      barMaxWidth: 24,
      barGap: "10%",
      itemStyle: { color, borderRadius: [0, 4, 4, 0] },
      label: { show: true, position: "right", formatter: "~{c}", color: palette.text, fontWeight: 600 },
    })),
  }
}

export function changesOption(palette: SeriesPalette): EChartsOption {
  return kneeBars(
    CHANGES.map((c) => c.label),
    [
      {
        name: "Knee",
        color: palette.series[0],
        // The grey bar repeated the settings above it: it is not a change.
        data: CHANGES.map((c) =>
          c.repeat ? { value: c.knee, itemStyle: { color: palette.off } } : c.knee,
        ),
      },
    ],
    `Knee per stress run, from about ${CHANGES[0].knee} to about ${CHANGES[CHANGES.length - 1].knee} requests per second. The table below has the same values.`,
    palette,
    {
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
  )
}

export function cacheKneesOption(palette: SeriesPalette): EChartsOption {
  return kneeBars(
    CACHE_PAIRS.map((p) => `${p.label} (${p.note})`),
    [
      { name: "Cache off", color: palette.off, data: CACHE_PAIRS.map((p) => p.off) },
      { name: "Cache on", color: palette.series[0], data: CACHE_PAIRS.map((p) => p.on) },
    ],
    "Knee with the cache off and on: about 375 and 480 requests per second on mixed traffic, about 360 and 459 on read-mostly traffic.",
    palette,
    { trigger: "axis", axisPointer: { type: "shadow" } },
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
        minuteSeries("Before the fixes", SOAK_BEFORE, palette.off, "327 ms", 1, 3),
        minuteSeries("After the fixes", SOAK_AFTER, palette.series[0], "33 ms", 1, 3),
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
        minuteSeries("Before the fixes", SOAK_BEFORE, palette.off, "93 %", 2, 3),
        minuteSeries("After the fixes", SOAK_AFTER, palette.series[0], "67 %", 2, 3),
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
        minuteSeries("Run 1", "soak-20261104T074625Z", palette.series[0], "24 ms", 1),
        minuteSeries("Run 2", "soak-20261104T083207Z", palette.series[2], "16 ms", 1),
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
        minuteSeries("Sync workers, no cache", "load-20261102T052551Z", palette.off, "7.9 ms", 1),
        minuteSeries("Threads and cache", "load-20261103T125112Z", palette.series[0], "4.8 ms", 1),
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
