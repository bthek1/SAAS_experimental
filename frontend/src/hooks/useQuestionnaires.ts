import { queryOptions, useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  createQuestionnaire,
  deleteQuestionnaire,
  downloadQuestionnairePdf,
  getQuestionnaire,
  getQuestionnaireByToken,
  getQuestionnaires,
  submitQuestionnaire,
  updateQuestionnaire,
} from "@/api/questionnaires"
import { queryKeys } from "@/api/queryKeys"
import { saveBlob } from "@/lib/download"
import type { QuestionnairePayload, SubmitPayload } from "@/types/questionnaires"

const keys = queryKeys.questionnaires

export const questionnairesQuery = () =>
  queryOptions({ queryKey: keys.all, queryFn: getQuestionnaires })

export const questionnaireQuery = (id: string) =>
  queryOptions({ queryKey: keys.detail(id), queryFn: () => getQuestionnaire(id) })

export const questionnaireByTokenQuery = (shareToken: string) =>
  queryOptions({
    queryKey: keys.byToken(shareToken),
    queryFn: () => getQuestionnaireByToken(shareToken),
    retry: false,
  })

export function useQuestionnaires() {
  return useQuery(questionnairesQuery())
}

export function useQuestionnaire(id: string) {
  return useQuery(questionnaireQuery(id))
}

export function useQuestionnaireByToken(shareToken: string) {
  return useQuery(questionnaireByTokenQuery(shareToken))
}

export function useCreateQuestionnaire() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: QuestionnairePayload) => createQuestionnaire(payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.all }),
  })
}

export function useUpdateQuestionnaire(id: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: { name: string }) => updateQuestionnaire(id, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.all }),
  })
}

export function useDeleteQuestionnaire() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => deleteQuestionnaire(id),
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: keys.all }),
        queryClient.invalidateQueries({ queryKey: queryKeys.batteries.all }),
      ]),
  })
}

export function useSubmitQuestionnaire(shareToken: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: SubmitPayload) => submitQuestionnaire(shareToken, payload),
    onSuccess: (submitted) => {
      queryClient.setQueryData(keys.byToken(shareToken), submitted)
      // A battery taker re-reads slot status after each submit.
      return queryClient.invalidateQueries({ queryKey: ["public", "batteries"] })
    },
  })
}

/** Download a submitted response as a PDF file. */
export function useDownloadQuestionnairePdf(id: string) {
  return useMutation({
    mutationFn: () => downloadQuestionnairePdf(id),
    onSuccess: ({ blob, filename }) => saveBlob(blob, filename),
  })
}
