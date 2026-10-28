import { createFileRoute, Link } from "@tanstack/react-router"
import { ListSkeleton } from "@/components/questionnaire/ListSkeleton"
import { SurveyRenderer } from "@/components/survey/SurveyRenderer"
import { Button } from "@/components/ui/button"
import { questionnaireQuery, useQuestionnaire } from "@/hooks/useQuestionnaires"
import { responseDefinition } from "@/lib/responses"

export const Route = createFileRoute("/_authed/questionnaires/$id/view")({
  loader: ({ context, params }) =>
    context.queryClient.ensureQueryData(questionnaireQuery(params.id)),
  component: QuestionnaireViewPage,
})

function QuestionnaireViewPage() {
  const { id } = Route.useParams()
  const { data: q, isLoading } = useQuestionnaire(id)

  if (isLoading) return <ListSkeleton />
  if (!q) return <p className="text-muted-foreground">Questionnaire not found.</p>

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">
          {q.questionnaireType.title}
          {q.name && ` · ${q.name}`}
        </h1>
        <Button variant="outline" render={<Link to="/questionnaires/$id" params={{ id }} />}>
          Back
        </Button>
      </div>
      {!q.submittedAt && (
        <p className="text-sm text-muted-foreground">
          Not submitted yet. This is how the questionnaire looks to the respondent.
        </p>
      )}
      <div className="overflow-hidden rounded-lg border">
        <SurveyRenderer surveyJson={responseDefinition(q)} data={q.answers} readOnly />
      </div>
    </div>
  )
}
