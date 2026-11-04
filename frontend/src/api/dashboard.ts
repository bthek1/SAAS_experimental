import { apiClient } from "@/api/client"
import { browserTimeZone } from "@/lib/date"
import type {
  DashboardParams,
  DashboardScores,
  DashboardScoresParams,
  DashboardSummary,
} from "@/types/dashboard"

export async function getDashboard(params: DashboardParams): Promise<DashboardSummary> {
  const { data } = await apiClient.get<DashboardSummary>("/api/dashboard/", {
    params: { ...params, tz: browserTimeZone() },
  })
  return data
}

export async function getDashboardScores(params: DashboardScoresParams): Promise<DashboardScores> {
  const { data } = await apiClient.get<DashboardScores>("/api/dashboard/scores/", {
    params: { ...params, tz: browserTimeZone() },
  })
  return data
}
