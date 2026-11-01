import { Link } from "@tanstack/react-router"
import { ChartCard } from "@/components/dashboard/ChartCard"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { formatDate } from "@/lib/date"
import {
  barChartHeight,
  type ChartPalette,
  distributionOption,
  flaggedPoints,
  numericScoreOption,
} from "@/lib/dashboard"
import type { BooleanScoreMetric, ScoreMetric } from "@/types/dashboard"

function FlagCard({ metric }: { metric: BooleanScoreMetric }) {
  const flagged = flaggedPoints(metric)
  return (
    <Card className="gap-2" role="region" aria-label={metric.label}>
      <CardHeader>
        <CardTitle>{metric.label}</CardTitle>
        <CardDescription>
          {flagged.length} of {metric.points.length} responses
        </CardDescription>
      </CardHeader>
      <CardContent>
        {flagged.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">None flagged.</p>
        ) : (
          <ul className="divide-y text-sm">
            {flagged.map((p) => (
              <li key={p.questionnaireId} className="flex justify-between gap-4 py-2">
                <Link
                  to="/questionnaires/$id/results"
                  params={{ id: p.questionnaireId }}
                  className="font-medium hover:underline"
                >
                  {p.name || "Untitled"}
                </Link>
                <span className="text-muted-foreground">{formatDate(p.submittedAt)}</span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}

function MetricCard({ metric, palette }: { metric: ScoreMetric; palette: ChartPalette }) {
  switch (metric.kind) {
    case "numeric":
      return (
        <ChartCard
          title={metric.label}
          description={`Average ${metric.mean} across ${metric.points.length} responses`}
          option={numericScoreOption(metric, palette)}
        />
      )
    case "categorical":
      return (
        <ChartCard
          title={metric.label}
          description={`${metric.points.length} responses`}
          option={distributionOption(metric, palette)}
          height={barChartHeight(metric.distribution.length)}
        />
      )
    case "boolean":
      return <FlagCard metric={metric} />
  }
}

interface ScoreChartsProps {
  typeTitle: string
  metrics: ScoreMetric[]
  palette: ChartPalette
}

/** One card per calculated value of the selected questionnaire type. */
export function ScoreCharts({ typeTitle, metrics, palette }: ScoreChartsProps) {
  return (
    <section className="space-y-4" aria-label="Scores">
      <div>
        <h2 className="text-lg font-semibold">Scores</h2>
        <p className="text-sm text-muted-foreground">
          Calculated values of submitted {typeTitle} responses in this period.
        </p>
      </div>
      {metrics.length === 0 ? (
        <p className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
          No scored responses in this period. Scores come from the type's calculated values.
        </p>
      ) : (
        <div className="grid gap-6 lg:grid-cols-2">
          {metrics.map((m) => (
            <MetricCard key={m.name} metric={m} palette={palette} />
          ))}
        </div>
      )}
    </section>
  )
}
