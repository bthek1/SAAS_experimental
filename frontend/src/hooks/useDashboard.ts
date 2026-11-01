import { keepPreviousData, queryOptions, useQuery } from "@tanstack/react-query"
import { getDashboard, getDashboardScores } from "@/api/dashboard"
import { queryKeys } from "@/api/queryKeys"
import type { DashboardParams, DashboardRange, DashboardScoresParams } from "@/types/dashboard"

export const DEFAULT_RANGE: DashboardRange = 30

/** URL search params to API params; "all" means no `days` filter. */
export function dashboardParams(range: DashboardRange, type?: string): DashboardParams {
  return {
    ...(range !== "all" && { days: range }),
    ...(type && { questionnaireType: type }),
  }
}

// Respondents submit from other browsers, so no local mutation can invalidate these;
// a short freshness window makes each visit refetch. It is not 0, so the query mounting
// right after the loader fetched does not fetch the same data a second time.
const DASHBOARD_STALE_MS = 15_000

export const dashboardQuery = (params: DashboardParams) =>
  queryOptions({
    queryKey: queryKeys.dashboard.summary(params),
    queryFn: () => getDashboard(params),
    placeholderData: keepPreviousData,
    staleTime: DASHBOARD_STALE_MS,
  })

export function useDashboard(params: DashboardParams) {
  return useQuery(dashboardQuery(params))
}

export const dashboardScoresQuery = (params: DashboardScoresParams) =>
  queryOptions({
    queryKey: queryKeys.dashboard.scores(params),
    queryFn: () => getDashboardScores(params),
    // Keep charts up while the range changes, but never show another type's scores.
    placeholderData: (previous) =>
      previous?.questionnaireTypeId === params.questionnaireType ? previous : undefined,
    staleTime: DASHBOARD_STALE_MS,
  })

/** Scores need a questionnaire type; without one the query stays idle. */
export function useDashboardScores(params: DashboardParams) {
  const { questionnaireType, days } = params
  return useQuery({
    ...dashboardScoresQuery({ questionnaireType: questionnaireType ?? "", days }),
    enabled: !!questionnaireType,
  })
}
