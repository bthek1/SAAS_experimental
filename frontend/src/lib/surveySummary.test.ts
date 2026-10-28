import { describe, expect, it } from "vitest"
import { buildSummaries } from "./surveySummary"

const survey = {
  pages: [
    {
      name: "p",
      elements: [
        { type: "radiogroup", name: "color", title: "Colour", choices: ["red", "blue"] },
        { type: "checkbox", name: "pets", choices: ["cat", "dog"] },
        { type: "text", name: "note", title: "Note" },
      ],
    },
  ],
}

describe("buildSummaries", () => {
  it("returns nothing without responses", () => {
    expect(buildSummaries(survey, [])).toEqual([])
  })

  it("tallies choices and lists text answers", () => {
    const [color, pets, note] = buildSummaries(survey, [
      { color: "red", pets: ["cat", "dog"], note: "hi" },
      { color: "red", pets: ["cat"], note: "" },
      { color: "blue" },
    ])
    expect(color).toEqual({
      kind: "choice",
      name: "color",
      title: "Colour",
      choices: [
        { text: "red", count: 2 },
        { text: "blue", count: 1 },
      ],
      total: 3,
    })
    expect(pets).toMatchObject({ title: "pets", choices: [{ text: "cat", count: 2 }, { text: "dog", count: 1 }] })
    expect(note).toEqual({ kind: "text", name: "note", title: "Note", answers: ["hi"] })
  })
})
