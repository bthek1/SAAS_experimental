import { apiClient } from "@/api/client"
import { getAllPages, getPage } from "@/api/pagination"
import type { Paginated } from "@/types/pagination"
import type {
  PublicQuestionnaire,
  Questionnaire,
  QuestionnaireFilters,
  QuestionnairePayload,
  SubmitPayload,
} from "@/types/questionnaires"

/** Every matching questionnaire (all pages), e.g. for a type's response summary. */
export function getQuestionnaires(filters: QuestionnaireFilters = {}): Promise<Questionnaire[]> {
  return getAllPages<Questionnaire>("/api/questionnaires/", filters)
}

export function getQuestionnairesPage(
  filters: QuestionnaireFilters,
  page: number,
): Promise<Paginated<Questionnaire>> {
  return getPage<Questionnaire>("/api/questionnaires/", page, filters)
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

/** A submitted response as a PDF, with the filename the server suggests. */
export async function downloadQuestionnairePdf(
  id: string,
): Promise<{ blob: Blob; filename: string }> {
  const response = await apiClient.get<Blob>(`/api/questionnaires/${id}/pdf/`, {
    responseType: "blob",
  })
  const disposition = String(response.headers["content-disposition"] ?? "")
  const filename = /filename="([^"]+)"/.exec(disposition)?.[1] ?? "response.pdf"
  return { blob: response.data, filename }
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
