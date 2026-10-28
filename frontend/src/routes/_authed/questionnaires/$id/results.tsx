import { createFileRoute, Link } from "@tanstack/react-router"
import { Download } from "lucide-react"
import { useMemo } from "react"
import { ListSkeleton } from "@/components/questionnaire/ListSkeleton"
import { MetricCards } from "@/components/questionnaire/MetricCards"
import { RawResponsesTable } from "@/components/questionnaire/RawResponsesTable"
import { StatusBadge } from "@/components/questionnaire/StatusBadge"
import { SurveyDashboard } from "@/components/survey/SurveyDashboard"
import { Button } from "@/components/ui/button"
import {
  questionnaireQuery,
  useDownloadQuestionnairePdf,
  useQuestionnaire,
} from "@/hooks/useQuestionnaires"
import { resolveMetrics } from "@/lib/metrics"
import { responseDefinition } from "@/lib/responses"

export const Route = createFileRoute("/_authed/questionnaires/$id/results")({
  loader: ({ context, params }) =>
    context.queryClient.ensureQueryData(questionnaireQuery(params.id)),
  component: ResultsPage,
})

function ResultsPage() {
  const { id } = Route.useParams()
  const { data: q, isLoading } = useQuestionnaire(id)
  const downloadPdf = useDownloadQuestionnairePdf(id)

  const definition = useMemo(() => (q ? responseDefinition(q) : null), [q])
  const metrics = useMemo(
    () => (q && definition ? resolveMetrics(definition, q.answers, q.metrics) : []),
    [q, definition],
  )
  const responses = useMemo(() => (q ? [q.answers] : []), [q])

  if (isLoading) return <ListSkeleton />
  if (!q || !definition) return <p className="text-muted-foreground">Questionnaire not found.</p>

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold">
          {q.questionnaireType.title}
          {q.name && ` · ${q.name}`}
        </h1>
        <StatusBadge submittedAt={q.submittedAt} />
        <div className="ml-auto flex gap-2">
          {q.submittedAt && (
            <Button
              variant="outline"
              onClick={() => downloadPdf.mutate()}
              disabled={downloadPdf.isPending}
            >
              <Download />
              {downloadPdf.isPending ? "Preparing…" : "Download PDF"}
            </Button>
          )}
          <Button variant="outline" render={<Link to="/questionnaires/$id/view" params={{ id }} />}>
            View as form
          </Button>
          <Button variant="ghost" render={<Link to="/questionnaires" />}>
            All questionnaires
          </Button>
        </div>
      </div>

      {downloadPdf.isError && (
        <p role="alert" className="text-sm text-destructive">
          The PDF could not be created. Please try again.
        </p>
      )}

      {!q.submittedAt ? (
        <p className="rounded-lg border border-dashed p-12 text-center text-muted-foreground">
          No response yet.
        </p>
      ) : (
        <>
          <MetricCards metrics={metrics} />
          <SurveyDashboard surveyJson={definition} responses={responses} />
          <RawResponsesTable responses={[q]} />
        </>
      )}
    </div>
  )
}
