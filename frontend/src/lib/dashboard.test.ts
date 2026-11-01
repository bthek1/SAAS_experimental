import { describe, expect, it } from "vitest"
import {
  barChartHeight,
  batteryTypesOption,
  type ChartPalette,
  distributionOption,
  escapeHtml,
  flaggedPoints,
  numericScoreOption,
  formatDuration,
  formatPercent,
  questionnaireTypesOption,
  submissionsOption,
} from "@/lib/dashboard"
import { dashboardScores, dashboardSummary } from "@/test/questionnaireFixtures"
import type {
  BooleanScoreMetric,
  CategoricalScoreMetric,
  NumericScoreMetric,
} from "@/types/dashboard"

const [numeric, categorical, flag] = dashboardScores.metrics as [
  NumericScoreMetric,
  CategoricalScoreMetric,
  BooleanScoreMetric,
]

const palette: ChartPalette = {
  strong: "#111",
  mid: "#222",
  light: "#333",
  text: "#aaa",
  border: "#bbb",
}

describe("formatPercent", () => {
  it.each([
    [0, "0%"],
    [0.7143, "71%"],
    [1, "100%"],
  ])("%s -> %s", (rate, expected) => expect(formatPercent(rate)).toBe(expected))
})

describe("formatDuration", () => {
  it.each([
    [null, "—"],
    [0.5, "30 min"],
    [5.25, "5.3 h"],
    [47, "47 h"],
    [72, "3 d"],
  ])("%s hours -> %s", (hours, expected) => expect(formatDuration(hours)).toBe(expected))
})

describe("chart options", () => {
  it("plots one bar per day with formatted labels", () => {
    const option = submissionsOption(dashboardSummary.submissionsByDay, palette)
    expect(option.xAxis).toMatchObject({ data: ["28 Oct", "29 Oct", "30 Oct"] })
    expect(option.series).toMatchObject([{ type: "bar", data: [2, 0, 1] }])
  })

  it("stacks submitted and pending per questionnaire type", () => {
    const option = questionnaireTypesOption(dashboardSummary.byQuestionnaireType, palette)
    expect(option.yAxis).toMatchObject({ data: ["Wellbeing"] })
    expect(option.series).toMatchObject([
      { name: "Submitted", data: [9], stack: "total", itemStyle: { color: "#111" } },
      { name: "Pending", data: [3], stack: "total", itemStyle: { color: "#333" } },
    ])
  })

  it("stacks battery statuses per battery type", () => {
    const option = batteryTypesOption(dashboardSummary.byBatteryType, palette)
    expect(option.series).toMatchObject([
      { name: "Complete", data: [2], itemStyle: { color: "#111" } },
      { name: "In progress", data: [1], itemStyle: { color: "#222" } },
      { name: "Not started", data: [1], itemStyle: { color: "#333" } },
    ])
  })

  it("grows bar charts with their row count", () => {
    expect(barChartHeight(0)).toBe(160)
    expect(barChartHeight(10)).toBe(424)
  })
})

describe("score options", () => {
  it("plots numeric scores over time with an average line", () => {
    const option = numericScoreOption(numeric, palette)
    expect(option.xAxis).toMatchObject({ type: "time" })
    expect(option.series).toMatchObject([
      {
        type: "line",
        data: [
          { name: "Bob", value: ["2026-10-28T10:00:00Z", 4] },
          { name: "Dee", value: ["2026-10-29T10:00:00Z", 10] },
        ],
        markLine: { data: [{ yAxis: 7 }] },
      },
    ])
  })

  it("escapes respondent names in the tooltip", () => {
    const { tooltip } = numericScoreOption(numeric, palette) as {
      tooltip: { formatter: (p: unknown) => string }
    }
    const html = tooltip.formatter({
      data: { name: "<img src=x>", value: ["2026-10-28T10:00:00Z", 4] },
    })
    expect(html).toContain("&lt;img src=x&gt;")
    expect(html).toContain("<b>4</b>")
  })

  it("charts a categorical distribution", () => {
    const option = distributionOption(categorical, palette)
    expect(option.yAxis).toMatchObject({ data: ["Mild", "Moderate"] })
    expect(option.series).toMatchObject([{ type: "bar", data: [1, 1] }])
  })

  it("lists flagged responses newest first", () => {
    expect(flaggedPoints(flag).map((p) => p.name)).toEqual(["Dee"])
  })

  it("escapes HTML", () => {
    expect(escapeHtml(`<a href="x">Tom & 'Jo'</a>`)).toBe(
      "&lt;a href=&quot;x&quot;&gt;Tom &amp; &#39;Jo&#39;&lt;/a&gt;",
    )
  })
})
