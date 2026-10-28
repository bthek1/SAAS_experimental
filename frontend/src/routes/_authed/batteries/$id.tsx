import { createFileRoute, Link } from "@tanstack/react-router"
import { ListSkeleton } from "@/components/questionnaire/ListSkeleton"
import { ShareLink } from "@/components/questionnaire/ShareLink"
import { StatusBadge } from "@/components/questionnaire/StatusBadge"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { batteryQuery, useBattery } from "@/hooks/useBatteries"
import { slotProgress } from "@/lib/battery"
import { formatDateTime } from "@/lib/date"
import { takeBatteryUrl } from "@/lib/shareLinks"

export const Route = createFileRoute("/_authed/batteries/$id")({
  loader: ({ context, params }) => context.queryClient.ensureQueryData(batteryQuery(params.id)),
  component: BatteryDetailPage,
})

function BatteryDetailPage() {
  const { id } = Route.useParams()
  const { data: battery, isLoading } = useBattery(id)

  if (isLoading) return <ListSkeleton />
  if (!battery) return <p className="text-muted-foreground">Battery not found.</p>

  const { done, total } = slotProgress(battery.questionnaires)
  const slots = [...battery.questionnaires].sort((a, b) => a.order - b.order)

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold">{battery.name || "Untitled"}</h1>
        {battery.isComplete ? (
          <Badge>Complete</Badge>
        ) : (
          <Badge variant="outline">
            {done} of {total} done
          </Badge>
        )}
      </div>
      <p className="text-muted-foreground">
        {battery.batteryTypeName} · created {formatDateTime(battery.createdAt)}
      </p>

      {!battery.isComplete && <ShareLink url={takeBatteryUrl(battery.shareToken)} />}

      <ol className="divide-y rounded-lg border" aria-label="Questionnaires in this battery">
        {slots.map((slot) => (
          <li key={slot.questionnaireId} className="flex items-center gap-3 px-4 py-3">
            <span className="w-6 text-muted-foreground">{slot.order + 1}.</span>
            <span className="flex-1 font-medium">{slot.questionnaireTypeName}</span>
            <StatusBadge submittedAt={slot.submittedAt} />
            {slot.submittedAt && (
              <Button
                size="sm"
                variant="outline"
                render={
                  <Link to="/questionnaires/$id/results" params={{ id: slot.questionnaireId }} />
                }
              >
                Results
              </Button>
            )}
          </li>
        ))}
      </ol>

      <Button variant="ghost" render={<Link to="/batteries" />}>
        ← All batteries
      </Button>
    </div>
  )
}
