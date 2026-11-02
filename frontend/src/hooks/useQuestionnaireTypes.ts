import { queryOptions, useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  createQuestionnaireType,
  deleteQuestionnaireType,
  getQuestionnaireType,
  getQuestionnaireTypes,
  getQuestionnaireTypesPage,
  updateQuestionnaireType,
} from "@/api/questionnaireTypes"
import { queryKeys } from "@/api/queryKeys"
import type { QuestionnaireTypePayload } from "@/types/questionnaires"

const keys = queryKeys.questionnaireTypes

/** Every type, for pickers. */
export const questionnaireTypesQuery = () =>
  queryOptions({ queryKey: keys.all, queryFn: getQuestionnaireTypes })

export const questionnaireTypesPageQuery = (page: number) =>
  queryOptions({ queryKey: keys.page(page), queryFn: () => getQuestionnaireTypesPage(page) })

export const questionnaireTypeQuery = (id: string) =>
  queryOptions({ queryKey: keys.detail(id), queryFn: () => getQuestionnaireType(id) })

export function useQuestionnaireTypes() {
  return useQuery(questionnaireTypesQuery())
}

export function useQuestionnaireTypesPage(page: number) {
  return useQuery(questionnaireTypesPageQuery(page))
}

export function useQuestionnaireType(id: string) {
  return useQuery(questionnaireTypeQuery(id))
}

export function useCreateQuestionnaireType() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: QuestionnaireTypePayload) => createQuestionnaireType(payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.all }),
  })
}

export function useUpdateQuestionnaireType(id: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: Partial<QuestionnaireTypePayload>) =>
      updateQuestionnaireType(id, payload),
    onSuccess: (updated) => {
      queryClient.setQueryData(keys.detail(id), updated)
      return queryClient.invalidateQueries({ queryKey: keys.all })
    },
  })
}

export function useDeleteQuestionnaireType() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => deleteQuestionnaireType(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.all }),
  })
}
