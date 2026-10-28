import { describe, expect, it } from "vitest"
import { questionnaire, submittedQuestionnaire } from "@/test/questionnaireFixtures"
import { responseDefinition } from "./responses"

describe("responseDefinition", () => {
  it("uses the snapshot for a submitted response", () => {
    const snapshot = { pages: [{ name: "old" }] }
    expect(
      responseDefinition({ ...submittedQuestionnaire, questionnaireJsonSnapshot: snapshot }),
    ).toBe(snapshot)
  })

  it("uses the live type for a pending one", () => {
    expect(responseDefinition(questionnaire)).toBe(questionnaire.questionnaireType.questionnaireJson)
  })
})
