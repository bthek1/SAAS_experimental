import { describe, expect, it } from "vitest"
import { Model } from "survey-core"
import {
  evaluateMetrics,
  formatLabel,
  metricsFromModel,
  metricsFromStored,
  resolveMetrics,
} from "@/lib/metrics"

const scored = {
  pages: [
    {
      name: "p1",
      elements: [
        { type: "rating", name: "q1", rateMax: 5 },
        { type: "rating", name: "q2", rateMax: 5 },
      ],
    },
  ],
  calculatedValues: [
    { name: "totalScore", expression: "{q1} + {q2}", includeIntoResult: true },
    { name: "risk_level", title: "Risk", expression: "iif({q1} > 3, 'high', 'low')" },
  ],
}

describe("formatLabel", () => {
  it.each([
    ["total_score", "Total Score"],
    ["bonusPoints", "Bonus Points"],
    ["score", "Score"],
  ])("%s -> %s", (input, expected) => {
    expect(formatLabel(input)).toBe(expected)
  })
})

describe("evaluateMetrics", () => {
  it("returns nothing without calculatedValues", () => {
    expect(evaluateMetrics({ pages: [] }, {})).toEqual([])
  })

  it("evaluates expressions against the answers", () => {
    expect(evaluateMetrics(scored, { q1: 4, q2: 2 })).toEqual([
      { name: "totalScore", label: "Total Score", value: 6 },
      { name: "risk_level", label: "Risk", value: "high" },
    ])
  })

  it("ignores malformed definitions", () => {
    const json = { pages: [], calculatedValues: [null, "x", { title: "no name" }] }
    expect(evaluateMetrics(json, {})).toEqual([])
  })
})

describe("metricsFromModel", () => {
  it("reads every calculated value off a live model", () => {
    const model = new Model(scored)
    model.data = { q1: 1, q2: 1 }
    expect(metricsFromModel(model)).toEqual({ totalScore: 2, risk_level: "low" })
  })
})

describe("metricsFromStored", () => {
  it("returns nothing without calculatedValues", () => {
    expect(metricsFromStored({ pages: [] }, { total_score: 42 })).toEqual([])
  })

  it("labels stored metrics in definition order and skips missing ones", () => {
    expect(metricsFromStored(scored, { risk_level: "low" })).toEqual([
      { name: "risk_level", label: "Risk", value: "low" },
    ])
  })
})

describe("resolveMetrics", () => {
  it("prefers stored metrics", () => {
    const result = resolveMetrics(scored, { q1: 1, q2: 1 }, { totalScore: 99 })
    expect(result).toEqual([{ name: "totalScore", label: "Total Score", value: 99 }])
  })

  it("evaluates when nothing is stored", () => {
    expect(resolveMetrics(scored, { q1: 1, q2: 1 }, {})[0].value).toBe(2)
  })
})
