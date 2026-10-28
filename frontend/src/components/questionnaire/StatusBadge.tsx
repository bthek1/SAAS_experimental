import { Badge } from "@/components/ui/badge"
import { formatDate } from "@/lib/date"

export function StatusBadge({ submittedAt }: { submittedAt: string | null }) {
  return submittedAt ? (
    <Badge>Submitted {formatDate(submittedAt)}</Badge>
  ) : (
    <Badge variant="outline">Pending</Badge>
  )
}
