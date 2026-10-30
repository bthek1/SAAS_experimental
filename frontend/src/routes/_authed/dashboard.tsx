import { createFileRoute, Link, useNavigate } from "@tanstack/react-router"
import { Plus } from "lucide-react"
import { z } from "zod"
import { ChartCard } from "@/components/dashboard/ChartCard"
import { DashboardFilters } from "@/components/dashboard/DashboardFilters"
import { KpiCards } from "@/components/dashboard/KpiCards"
import { RecentSubmissions } from "@/components/dashboard/RecentSubmissions"
import { ScoreCharts } from "@/components/dashboard/ScoreCharts"
import { StalePending } from "@/components/dashboard/StalePending"
import { Button } from "@/components/ui/button"
import { useChartPalette } from "@/hooks/useChartPalette"
import {
  dashboardParams,
  dashboardQuery,
  dashboardScoresQuery,
  DEFAULT_RANGE,
  useDashboard,
  useDashboardScores,
} from "@/hooks/useDashboard"
import { questionnaireTypesQuery, useQuestionnaireTypes } from "@/hooks/useQuestionnaireTypes"
import { apiErrorMessage } from "@/lib/apiErrors"
import {
  barChartHeight,
  batteryTypesOption,
  questionnaireTypesOption,
  submissionsOption,
} from "@/lib/dashboard"

const searchSchema = z.object({
  // Numbers, so the URL reads `?range=7` rather than a JSON-quoted string.
  range: z
    .union([z.literal(7), z.literal(30), z.literal(90), z.literal("all")])
    .optional()
    .catch(undefined),
  type: z.string().optional().catch(undefined),
})

export const Route = createFileRoute("/_authed/dashboard")({
  validateSearch: searchSchema,
  loaderDeps: ({ search }) => search,
  loader: ({ context, deps }) => {
    const params = dashboardParams(deps.range ?? DEFAULT_RANGE, deps.type)
    return Promise.all([
      context.queryClient.ensureQueryData(dashboardQuery(params)),
      context.queryClient.ensureQueryData(questionnaireTypesQuery()),
      params.questionnaireType &&
        context.queryClient.ensureQueryData(
          dashboardScoresQuery({ questionnaireType: params.questionnaireType, days: params.days }),
        ),
    ])
  },
  errorComponent: ({ error }) => (
    <p role="alert" className="p-8 text-center text-destructive">
      {apiErrorMessage(error, "Could not load the dashboard. Please try again.")}
    </p>
  ),
  component: DashboardPage,
})

function DashboardPage() {
  const { range = DEFAULT_RANGE, type } = Route.useSearch()
  const navigate = useNavigate({ from: "/dashboard" })
  const params = dashboardParams(range, type)
  const { data, isFetching } = useDashboard(params)
  const { data: scores } = useDashboardScores(params)
  const { data: types = [] } = useQuestionnaireTypes()
  const selectedType = types.find((t) => t.id === type)
  const palette = useChartPalette()

  if (!data) return null

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Dashboard</h1>
          <p className="text-sm text-muted-foreground">
            Questionnaires and batteries you have sent, and how respondents are getting on.
          </p>
        </div>
        <DashboardFilters
          range={range}
          type={type}
          types={types}
          onRangeChange={(r) => navigate({ search: (s) => ({ ...s, range: r }) })}
          onTypeChange={(t) => navigate({ search: (s) => ({ ...s, type: t }) })}
        />
      </div>

      {types.length === 0 ? (
        <div className="rounded-lg border border-dashed p-12 text-center">
          <p className="mb-4 text-muted-foreground">
            No data yet. Create a questionnaire type, then send it to someone.
          </p>
          <Button render={<Link to="/questionnaire-types/new" />}>
            <Plus /> New questionnaire type
          </Button>
        </div>
      ) : (
        <div className={isFetching ? "space-y-6 opacity-70 transition-opacity" : "space-y-6"}>
          <KpiCards kpis={data.kpis} />

          <ChartCard
            title="Submissions over time"
            option={submissionsOption(data.submissionsByDay, palette)}
            isEmpty={data.submissionsByDay.every((d) => d.count === 0)}
          />

          <div className="grid gap-6 lg:grid-cols-2">
            <ChartCard
              title="Questionnaires by type"
              option={questionnaireTypesOption(data.byQuestionnaireType, palette)}
              height={barChartHeight(data.byQuestionnaireType.length)}
              isEmpty={data.byQuestionnaireType.every((t) => t.sent === 0)}
            />
            <ChartCard
              title="Batteries by type"
              option={batteryTypesOption(data.byBatteryType, palette)}
              height={barChartHeight(data.byBatteryType.length)}
              isEmpty={data.kpis.batteriesTotal === 0}
            />
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <RecentSubmissions rows={data.recentSubmissions} />
            <StalePending rows={data.stalePending} />
          </div>

          {selectedType && scores && (
            <ScoreCharts typeTitle={selectedType.title} metrics={scores.metrics} palette={palette} />
          )}
        </div>
      )}
    </div>
  )
}
