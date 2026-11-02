import { apiClient } from "@/api/client"
import { getAllPages, getPage } from "@/api/pagination"
import type { Paginated } from "@/types/pagination"
import type { QuestionnaireType, QuestionnaireTypePayload } from "@/types/questionnaires"

/** Every type (all pages), for pickers. */
export function getQuestionnaireTypes(): Promise<QuestionnaireType[]> {
  return getAllPages<QuestionnaireType>("/api/questionnaire-types/")
}

export function getQuestionnaireTypesPage(page: number): Promise<Paginated<QuestionnaireType>> {
  return getPage<QuestionnaireType>("/api/questionnaire-types/", page)
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
