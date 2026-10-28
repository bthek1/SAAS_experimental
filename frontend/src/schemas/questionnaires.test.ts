import { describe, expect, it } from "vitest"
import {
  batterySchema,
  batteryTypeSchema,
  questionnaireSchema,
  questionnaireTypeSchema,
  TITLE_MAX,
} from "./questionnaires"

describe("questionnaireTypeSchema", () => {
  it("accepts a title and template, trimming the title", () => {
    expect(questionnaireTypeSchema.parse({ title: "  PHQ-9 ", template: "blank" })).toEqual({
      title: "PHQ-9",
      template: "blank",
    })
  })

  it("requires a non-blank title", () => {
    const result = questionnaireTypeSchema.safeParse({ title: "   ", template: "blank" })
    expect(result.success).toBe(false)
    expect(result.error?.issues[0].message).toBe("Title is required")
  })

  it("limits the title length", () => {
    const result = questionnaireTypeSchema.safeParse({
      title: "x".repeat(TITLE_MAX + 1),
      template: "blank",
    })
    expect(result.error?.issues[0].message).toMatch(/120 characters/)
  })
})

describe("batteryTypeSchema", () => {
  it("accepts an ordered list of type ids", () => {
    const parsed = batteryTypeSchema.parse({
      title: "Intake",
      description: "",
      questionnaireTypeIds: ["b", "a"],
    })
    expect(parsed.questionnaireTypeIds).toEqual(["b", "a"])
  })

  it("needs at least one questionnaire type", () => {
    const result = batteryTypeSchema.safeParse({
      title: "Intake",
      description: "",
      questionnaireTypeIds: [],
    })
    expect(result.error?.issues[0].message).toBe("Add at least one questionnaire type")
  })
})

describe("questionnaireSchema / batterySchema", () => {
  it("require a type and allow an empty name", () => {
    expect(questionnaireSchema.safeParse({ questionnaireTypeId: "qt", name: "" }).success).toBe(true)
    expect(questionnaireSchema.safeParse({ questionnaireTypeId: "", name: "" }).success).toBe(false)
    expect(batterySchema.safeParse({ batteryTypeId: "bt", name: "Run" }).success).toBe(true)
    expect(batterySchema.safeParse({ batteryTypeId: "", name: "" }).success).toBe(false)
  })
})
