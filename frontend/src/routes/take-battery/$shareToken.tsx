import { createFileRoute } from "@tanstack/react-router"
import { Notice, PublicShell } from "@/components/questionnaire/PublicShell"
import { TakeQuestionnaire } from "@/components/questionnaire/TakeQuestionnaire"
import { useBatteryByToken } from "@/hooks/useBatteries"
import { nextSlot, slotProgress } from "@/lib/battery"

export const Route = createFileRoute("/take-battery/$shareToken")({
  component: TakeBatteryPage,
})

function TakeBatteryPage() {
  const { shareToken } = Route.useParams()
  const { data: battery, isLoading } = useBatteryByToken(shareToken)

  if (isLoading) return <PublicShell><Notice title="Loading…" /></PublicShell>
  if (!battery) {
    return (
      <PublicShell>
        <Notice title="Battery not found">
          The link may be wrong, or the battery was removed.
        </Notice>
      </PublicShell>
    )
  }

  const slot = nextSlot(battery)
  if (!slot) {
    return (
      <PublicShell>
        <Notice title="All done!">Thank you. Every questionnaire in this set is complete.</Notice>
      </PublicShell>
    )
  }

  const { done, total } = slotProgress(battery.questionnaires)
  return (
    <PublicShell>
      <div className="mb-4 flex items-center justify-between rounded-lg border bg-card px-4 py-3 text-sm">
        <span className="font-medium">
          Questionnaire {done + 1} of {total}
        </span>
        <span className="text-muted-foreground">{battery.batteryTypeName}</span>
      </div>
      {/* Keyed by slot so each questionnaire starts with a fresh survey model. The
          submit invalidates the battery query, which then moves on to the next slot. */}
      <TakeQuestionnaire key={slot.shareToken} shareToken={slot.shareToken} inBattery />
    </PublicShell>
  )
}
