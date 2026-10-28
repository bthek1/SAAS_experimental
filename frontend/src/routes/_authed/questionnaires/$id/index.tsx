import { createFileRoute, Link } from "@tanstack/react-router"
import { ListSkeleton } from "@/components/questionnaire/ListSkeleton"
import { ShareLink } from "@/components/questionnaire/ShareLink"
import { StatusBadge } from "@/components/questionnaire/StatusBadge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { questionnaireQuery, useQuestionnaire } from "@/hooks/useQuestionnaires"
import { formatDateTime } from "@/lib/date"
import { takeUrl } from "@/lib/shareLinks"

export const Route = createFileRoute("/_authed/questionnaires/$id/")({
  loader: ({ context, params }) =>
    context.queryClient.ensureQueryData(questionnaireQuery(params.id)),
  component: QuestionnaireDetailPage,
})

function QuestionnaireDetailPage() {
  const { id } = Route.useParams()
  const { data: q, isLoading } = useQuestionnaire(id)

  if (isLoading) return <ListSkeleton />
  if (!q) return <p className="text-muted-foreground">Questionnaire not found.</p>

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold">{q.name || "Untitled"}</h1>
        <StatusBadge submittedAt={q.submittedAt} />
      </div>
      <p className="text-muted-foreground">
        {q.questionnaireType.title} · created {formatDateTime(q.createdAt)}
      </p>

      {q.submittedAt ? (
        <div className="flex gap-2">
          <Button render={<Link to="/questionnaires/$id/results" params={{ id }} />}>
            View results
          </Button>
          <Button variant="outline" render={<Link to="/questionnaires/$id/view" params={{ id }} />}>
            View answers
          </Button>
        </div>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Share link</CardTitle>
          </CardHeader>
          <CardContent>
            <ShareLink url={takeUrl(q.shareToken)} />
          </CardContent>
        </Card>
      )}
      <Button variant="ghost" render={<Link to="/questionnaires" />}>
        ← All questionnaires
      </Button>
    </div>
  )
}
