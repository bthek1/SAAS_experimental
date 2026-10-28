import { createFileRoute } from "@tanstack/react-router"
import { PublicShell } from "@/components/questionnaire/PublicShell"
import { TakeQuestionnaire } from "@/components/questionnaire/TakeQuestionnaire"

export const Route = createFileRoute("/take/$shareToken")({
  component: TakePage,
})

function TakePage() {
  const { shareToken } = Route.useParams()
  return (
    <PublicShell>
      <TakeQuestionnaire shareToken={shareToken} />
    </PublicShell>
  )
}
