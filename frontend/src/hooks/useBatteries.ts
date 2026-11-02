import { queryOptions, useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  createBattery,
  deleteBattery,
  getBatteriesPage,
  getBattery,
  getBatteryByToken,
} from "@/api/batteries"
import { queryKeys } from "@/api/queryKeys"
import type { BatteryPayload } from "@/types/questionnaires"

const keys = queryKeys.batteries

export const batteriesPageQuery = (page: number) =>
  queryOptions({ queryKey: keys.page(page), queryFn: () => getBatteriesPage(page) })

export const batteryQuery = (id: string) =>
  queryOptions({ queryKey: keys.detail(id), queryFn: () => getBattery(id) })

export const batteryByTokenQuery = (shareToken: string) =>
  queryOptions({
    queryKey: keys.byToken(shareToken),
    queryFn: () => getBatteryByToken(shareToken),
    retry: false,
  })

export function useBatteriesPage(page: number) {
  return useQuery(batteriesPageQuery(page))
}

export function useBattery(id: string) {
  return useQuery(batteryQuery(id))
}

export function useBatteryByToken(shareToken: string) {
  return useQuery(batteryByTokenQuery(shareToken))
}

export function useCreateBattery() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: BatteryPayload) => createBattery(payload),
    // A new battery also creates one questionnaire per slot.
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: keys.all }),
        queryClient.invalidateQueries({ queryKey: queryKeys.questionnaires.all }),
      ]),
  })
}

export function useDeleteBattery() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => deleteBattery(id),
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: keys.all }),
        queryClient.invalidateQueries({ queryKey: queryKeys.questionnaires.all }),
      ]),
  })
}
