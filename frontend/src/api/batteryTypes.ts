import { apiClient } from "@/api/client"
import { getAllPages, getPage } from "@/api/pagination"
import type { Paginated } from "@/types/pagination"
import type { BatteryType, BatteryTypePayload } from "@/types/questionnaires"

/** Every battery type (all pages), for pickers. */
export function getBatteryTypes(): Promise<BatteryType[]> {
  return getAllPages<BatteryType>("/api/battery-types/")
}

export function getBatteryTypesPage(page: number): Promise<Paginated<BatteryType>> {
  return getPage<BatteryType>("/api/battery-types/", page)
}

export async function getBatteryType(id: string): Promise<BatteryType> {
  const { data } = await apiClient.get<BatteryType>(`/api/battery-types/${id}/`)
  return data
}

export async function createBatteryType(payload: BatteryTypePayload): Promise<BatteryType> {
  const { data } = await apiClient.post<BatteryType>("/api/battery-types/", payload)
  return data
}

export async function updateBatteryType(
  id: string,
  payload: Partial<BatteryTypePayload>,
): Promise<BatteryType> {
  const { data } = await apiClient.patch<BatteryType>(`/api/battery-types/${id}/`, payload)
  return data
}

export async function deleteBatteryType(id: string): Promise<void> {
  await apiClient.delete(`/api/battery-types/${id}/`)
}
