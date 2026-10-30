import type { EChartsOption } from "echarts"
import { formatDate } from "@/lib/date"
import type {
  BooleanScoreMetric,
  CategoricalScoreMetric,
  DashboardSummary,
  NumericScoreMetric,
} from "@/types/dashboard"

/** Resolved theme colours for charts (see `useChartPalette`). */
export interface ChartPalette {
  /** Done (submitted, complete). */
  strong: string
  /** Partly done (in progress). */
  mid: string
  /** Waiting (pending, not started). */
  light: string
  text: string
  border: string
}

export function formatPercent(rate: number): string {
  return `${Math.round(rate * 100)}%`
}

/** Hours under two days stay in hours, longer spans become days. */
export function formatDuration(hours: number | null): string {
  if (hours === null) return "—"
  if (hours < 1) return `${Math.round(hours * 60)} min`
  if (hours < 48) return `${Math.round(hours * 10) / 10} h`
  return `${Math.round((hours / 24) * 10) / 10} d`
}

function axisStyle(palette: ChartPalette) {
  return {
    axisLabel: { color: palette.text },
    axisLine: { lineStyle: { color: palette.border } },
    splitLine: { lineStyle: { color: palette.border } },
  }
}

export function submissionsOption(
  days: DashboardSummary["submissionsByDay"],
  palette: ChartPalette,
): EChartsOption {
  return {
    grid: { top: 16, right: 16, bottom: 32, left: 40 },
    tooltip: { trigger: "axis" },
    xAxis: {
      type: "category",
      data: days.map((d) => formatDate(d.date, "dd MMM")),
      ...axisStyle(palette),
    },
    yAxis: { type: "value", minInterval: 1, ...axisStyle(palette) },
    series: [
      {
        name: "Submissions",
        type: "bar",
        barMaxWidth: 32,
        data: days.map((d) => d.count),
        itemStyle: { color: palette.strong, borderRadius: [3, 3, 0, 0] },
      },
    ],
  }
}

/** Horizontal stacked bars, one row per category. */
function stackedBarsOption(
  categories: string[],
  series: { name: string; data: number[]; color: string }[],
  palette: ChartPalette,
): EChartsOption {
  return {
    grid: { top: 32, right: 16, bottom: 24, left: 8, containLabel: true },
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
    legend: { top: 0, textStyle: { color: palette.text } },
    xAxis: { type: "value", minInterval: 1, ...axisStyle(palette) },
    yAxis: { type: "category", data: categories, inverse: true, ...axisStyle(palette) },
    series: series.map(({ color, ...s }) => ({
      ...s,
      type: "bar",
      stack: "total",
      barMaxWidth: 28,
      itemStyle: { color },
    })),
  }
}

export function questionnaireTypesOption(
  rows: DashboardSummary["byQuestionnaireType"],
  palette: ChartPalette,
): EChartsOption {
  return stackedBarsOption(
    rows.map((r) => r.title),
    [
      { name: "Submitted", data: rows.map((r) => r.submitted), color: palette.strong },
      { name: "Pending", data: rows.map((r) => r.pending), color: palette.light },
    ],
    palette,
  )
}

export function batteryTypesOption(
  rows: DashboardSummary["byBatteryType"],
  palette: ChartPalette,
): EChartsOption {
  return stackedBarsOption(
    rows.map((r) => r.title),
    [
      { name: "Complete", data: rows.map((r) => r.complete), color: palette.strong },
      { name: "In progress", data: rows.map((r) => r.inProgress), color: palette.mid },
      { name: "Not started", data: rows.map((r) => r.notStarted), color: palette.light },
    ],
    palette,
  )
}

/** Chart height that fits one bar row per category. */
export function barChartHeight(rows: number): number {
  return Math.max(160, 64 + rows * 36)
}

/** ECharts tooltips render HTML, and respondent names are free text. */
export function escapeHtml(text: string): string {
  return text.replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c] ?? c,
  )
}

export function numericScoreOption(
  metric: NumericScoreMetric,
  palette: ChartPalette,
): EChartsOption {
  return {
    grid: { top: 16, right: 16, bottom: 32, left: 40 },
    tooltip: {
      trigger: "item",
      formatter: (params) => {
        const { data } = params as unknown as {
          data: { name: string; value: [string, number] }
        }
        const who = escapeHtml(data.name || "Untitled")
        return `${who}<br/>${formatDate(data.value[0])}: <b>${data.value[1]}</b>`
      },
    },
    xAxis: { type: "time", ...axisStyle(palette), splitLine: { show: false } },
    yAxis: { type: "value", scale: true, ...axisStyle(palette) },
    series: [
      {
        name: metric.label,
        type: "line",
        symbolSize: 8,
        // Points on the first and last day sit on the plot edge; don't cut them in half.
        clip: false,
        lineStyle: { color: palette.mid },
        itemStyle: { color: palette.strong },
        data: metric.points.map((p) => ({ name: p.name, value: [p.submittedAt, p.value] })),
        markLine: {
          silent: true,
          symbol: "none",
          label: { formatter: "Average", position: "insideEndTop", color: palette.text },
          lineStyle: { color: palette.text, type: "dashed" },
          data: [{ yAxis: metric.mean }],
        },
      },
    ],
  }
}

export function distributionOption(
  metric: CategoricalScoreMetric,
  palette: ChartPalette,
): EChartsOption {
  return {
    grid: { top: 8, right: 16, bottom: 24, left: 8, containLabel: true },
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
    xAxis: { type: "value", minInterval: 1, ...axisStyle(palette) },
    yAxis: {
      type: "category",
      data: metric.distribution.map((d) => d.value),
      inverse: true,
      ...axisStyle(palette),
    },
    series: [
      {
        name: "Responses",
        type: "bar",
        barMaxWidth: 28,
        data: metric.distribution.map((d) => d.count),
        itemStyle: { color: palette.strong },
      },
    ],
  }
}

/** Responses whose boolean metric is true, newest first. */
export function flaggedPoints(metric: BooleanScoreMetric) {
  return metric.points.filter((p) => p.value).reverse()
}
