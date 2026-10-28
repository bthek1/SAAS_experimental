import { apiClient } from "@/api/client"
import type { Battery, BatteryPayload, PublicBattery } from "@/types/questionnaires"

export async function getBatteries(): Promise<Battery[]> {
  const { data } = await apiClient.get<Battery[]>("/api/batteries/")
  return data
}

export async function getBattery(id: string): Promise<Battery> {
  const { data } = await apiClient.get<Battery>(`/api/batteries/${id}/`)
  return data
}

export async function createBattery(payload: BatteryPayload): Promise<Battery> {
  const { data } = await apiClient.post<Battery>("/api/batteries/", payload)
  return data
}

export async function deleteBattery(id: string): Promise<void> {
  await apiClient.delete(`/api/batteries/${id}/`)
}

export async function getBatteryByToken(shareToken: string): Promise<PublicBattery> {
  const { data } = await apiClient.get<PublicBattery>(`/api/batteries/by-token/${shareToken}/`)
  return data
}
