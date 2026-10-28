import { apiClient } from "@/api/client"
import type {
  PublicQuestionnaire,
  Questionnaire,
  QuestionnairePayload,
  SubmitPayload,
} from "@/types/questionnaires"

export async function getQuestionnaires(): Promise<Questionnaire[]> {
  const { data } = await apiClient.get<Questionnaire[]>("/api/questionnaires/")
  return data
}

export async function getQuestionnaire(id: string): Promise<Questionnaire> {
  const { data } = await apiClient.get<Questionnaire>(`/api/questionnaires/${id}/`)
  return data
}

export async function createQuestionnaire(payload: QuestionnairePayload): Promise<Questionnaire> {
  const { data } = await apiClient.post<Questionnaire>("/api/questionnaires/", payload)
  return data
}

export async function updateQuestionnaire(
  id: string,
  payload: { name: string },
): Promise<Questionnaire> {
  const { data } = await apiClient.patch<Questionnaire>(`/api/questionnaires/${id}/`, payload)
  return data
}

export async function deleteQuestionnaire(id: string): Promise<void> {
  await apiClient.delete(`/api/questionnaires/${id}/`)
}

// Public share-link endpoints. The backend ignores credentials on these, so a
// stale token in localStorage cannot make them fail.

export async function getQuestionnaireByToken(shareToken: string): Promise<PublicQuestionnaire> {
  const { data } = await apiClient.get<PublicQuestionnaire>(
    `/api/questionnaires/by-token/${shareToken}/`,
  )
  return data
}

export async function submitQuestionnaire(
  shareToken: string,
  payload: SubmitPayload,
): Promise<PublicQuestionnaire> {
  const { data } = await apiClient.patch<PublicQuestionnaire>(
    `/api/questionnaires/by-token/${shareToken}/submit/`,
    { answers: payload.answers, metrics: payload.metrics ?? {} },
  )
  return data
}
