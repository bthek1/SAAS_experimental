import { queryOptions, useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  createBatteryType,
  deleteBatteryType,
  getBatteryType,
  getBatteryTypes,
  updateBatteryType,
} from "@/api/batteryTypes"
import { queryKeys } from "@/api/queryKeys"
import type { BatteryTypePayload } from "@/types/questionnaires"

const keys = queryKeys.batteryTypes

export const batteryTypesQuery = () =>
  queryOptions({ queryKey: keys.all, queryFn: getBatteryTypes })

export const batteryTypeQuery = (id: string) =>
  queryOptions({ queryKey: keys.detail(id), queryFn: () => getBatteryType(id) })

export function useBatteryTypes() {
  return useQuery(batteryTypesQuery())
}

export function useBatteryType(id: string) {
  return useQuery(batteryTypeQuery(id))
}

export function useCreateBatteryType() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: BatteryTypePayload) => createBatteryType(payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.all }),
  })
}

export function useUpdateBatteryType(id: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: Partial<BatteryTypePayload>) => updateBatteryType(id, payload),
    onSuccess: (updated) => {
      queryClient.setQueryData(keys.detail(id), updated)
      return queryClient.invalidateQueries({ queryKey: keys.all })
    },
  })
}

export function useDeleteBatteryType() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => deleteBatteryType(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.all }),
  })
}
