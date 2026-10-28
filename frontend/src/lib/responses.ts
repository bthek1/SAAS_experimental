import type { Questionnaire, SurveyJson } from "@/types/questionnaires"

/**
 * The definition a response should be read against: the snapshot taken at
 * submit time, so later edits to the type cannot change how it reads.
 */
export function responseDefinition(q: Questionnaire): SurveyJson {
  if (q.submittedAt && Object.keys(q.questionnaireJsonSnapshot).length > 0) {
    return q.questionnaireJsonSnapshot
  }
  return q.questionnaireType.questionnaireJson
}
