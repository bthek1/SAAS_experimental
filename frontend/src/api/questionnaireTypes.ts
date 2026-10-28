import { apiClient } from "@/api/client"
import type { QuestionnaireType, QuestionnaireTypePayload } from "@/types/questionnaires"

export async function getQuestionnaireTypes(): Promise<QuestionnaireType[]> {
  const { data } = await apiClient.get<QuestionnaireType[]>("/api/questionnaire-types/")
  return data
}

export async function getQuestionnaireType(id: string): Promise<QuestionnaireType> {
  const { data } = await apiClient.get<QuestionnaireType>(`/api/questionnaire-types/${id}/`)
  return data
}

export async function createQuestionnaireType(
  payload: QuestionnaireTypePayload,
): Promise<QuestionnaireType> {
  const { data } = await apiClient.post<QuestionnaireType>("/api/questionnaire-types/", payload)
  return data
}

export async function updateQuestionnaireType(
  id: string,
  payload: Partial<QuestionnaireTypePayload>,
): Promise<QuestionnaireType> {
  const { data } = await apiClient.patch<QuestionnaireType>(
    `/api/questionnaire-types/${id}/`,
    payload,
  )
  return data
}

export async function deleteQuestionnaireType(id: string): Promise<void> {
  await apiClient.delete(`/api/questionnaire-types/${id}/`)
}
