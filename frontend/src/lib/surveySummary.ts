import { Model } from "survey-core"
import type { Answers, SurveyJson } from "@/types/questionnaires"

export interface ChoiceSummary {
  kind: "choice"
  name: string
  title: string
  choices: { text: string; count: number }[]
  total: number
}

export interface TextSummary {
  kind: "text"
  name: string
  title: string
  answers: string[]
}

export type QuestionSummary = ChoiceSummary | TextSummary

const CHOICE_TYPES = new Set([
  "radiogroup",
  "checkbox",
  "dropdown",
  "tagbox",
  "imagepicker",
  "ranking",
  "rating",
  "boolean",
])

function present(value: unknown): boolean {
  return value !== undefined && value !== null && value !== ""
}

/** Per-question tallies (choice-like questions) or answer lists across responses. */
export function buildSummaries(surveyJson: SurveyJson, responses: Answers[]): QuestionSummary[] {
  if (responses.length === 0) return []
  const model = new Model(surveyJson)

  return model.getAllQuestions().map((q): QuestionSummary => {
    const name = q.name
    const title = q.title || name
    const values = responses.map((r) => r[name]).filter(present)

    if (CHOICE_TYPES.has(q.getType())) {
      const tally = new Map<string, number>()
      for (const value of values) {
        for (const item of Array.isArray(value) ? value : [value]) {
          const key = String(item)
          tally.set(key, (tally.get(key) ?? 0) + 1)
        }
      }
      return {
        kind: "choice",
        name,
        title,
        choices: [...tally].map(([text, count]) => ({ text, count })),
        total: responses.length,
      }
    }

    return {
      kind: "text",
      name,
      title,
      answers: values.map((v) => (typeof v === "object" ? JSON.stringify(v) : String(v))),
    }
  })
}
