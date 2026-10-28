import { apiClient } from "@/api/client"
import type { BatteryType, BatteryTypePayload } from "@/types/questionnaires"

export async function getBatteryTypes(): Promise<BatteryType[]> {
  const { data } = await apiClient.get<BatteryType[]>("/api/battery-types/")
  return data
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
