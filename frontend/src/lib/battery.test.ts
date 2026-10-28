import { describe, expect, it } from "vitest"
import { publicBattery } from "@/test/questionnaireFixtures"
import { nextSlot, slotProgress } from "./battery"

describe("nextSlot", () => {
  it("returns the first unsubmitted slot by order", () => {
    const [first, second] = publicBattery.questionnaires
    const battery = {
      ...publicBattery,
      questionnaires: [second, { ...first, submittedAt: "2026-01-01T00:00:00Z" }],
    }
    expect(nextSlot(battery)?.shareToken).toBe(second.shareToken)
  })

  it("is undefined when everything is submitted", () => {
    const battery = {
      ...publicBattery,
      questionnaires: publicBattery.questionnaires.map((s) => ({ ...s, submittedAt: "x" })),
    }
    expect(nextSlot(battery)).toBeUndefined()
  })
})

describe("slotProgress", () => {
  it("counts submitted slots", () => {
    expect(slotProgress([{ submittedAt: "x" }, { submittedAt: null }])).toEqual({ done: 1, total: 2 })
  })
})
