import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { formatDuration, formatPercent } from "@/lib/dashboard"
import type { DashboardKpis } from "@/types/dashboard"

interface Kpi {
  label: string
  value: string
  hint: string
}

function kpiList(k: DashboardKpis): Kpi[] {
  return [
    { label: "Sent", value: String(k.questionnairesSent), hint: "Questionnaires created" },
    { label: "Submitted", value: String(k.questionnairesSubmitted), hint: "Of those sent" },
    { label: "Pending", value: String(k.questionnairesPending), hint: "Awaiting a response" },
    { label: "Completion rate", value: formatPercent(k.completionRate), hint: "Submitted / sent" },
    {
      label: "Median time to complete",
      value: formatDuration(k.medianHoursToComplete),
      hint: "Sent to submitted",
    },
    {
      label: "Batteries complete",
      value: `${k.batteriesComplete} / ${k.batteriesTotal}`,
      hint: `${k.batteriesInProgress} in progress, ${k.batteriesNotStarted} not started`,
    },
  ]
}

export function KpiCards({ kpis }: { kpis: DashboardKpis }) {
  return (
    <ul className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6" aria-label="Key figures">
      {kpiList(kpis).map((kpi) => (
        <li key={kpi.label}>
          <Card className="h-full gap-2 py-4">
            <CardHeader className="px-4">
              <CardDescription>{kpi.label}</CardDescription>
              <CardTitle className="text-2xl tabular-nums">{kpi.value}</CardTitle>
            </CardHeader>
            <CardContent className="px-4 text-xs text-muted-foreground">{kpi.hint}</CardContent>
          </Card>
        </li>
      ))}
    </ul>
  )
}
