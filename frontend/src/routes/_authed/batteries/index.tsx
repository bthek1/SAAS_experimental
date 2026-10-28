import { createFileRoute, Link } from "@tanstack/react-router"
import { Plus } from "lucide-react"
import { useState } from "react"
import { ConfirmDeleteDialog } from "@/components/questionnaire/ConfirmDeleteDialog"
import { CopyButton } from "@/components/questionnaire/CopyButton"
import { ListSkeleton } from "@/components/questionnaire/ListSkeleton"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { batteriesQuery, useBatteries, useDeleteBattery } from "@/hooks/useBatteries"
import { apiErrorMessage } from "@/lib/apiErrors"
import { slotProgress } from "@/lib/battery"
import { formatDate } from "@/lib/date"
import { takeBatteryUrl } from "@/lib/shareLinks"
import type { Battery } from "@/types/questionnaires"

export const Route = createFileRoute("/_authed/batteries/")({
  loader: ({ context }) => context.queryClient.ensureQueryData(batteriesQuery()),
  component: BatteriesPage,
})

function BatteriesPage() {
  const { data: batteries, isLoading } = useBatteries()
  const deleteBattery = useDeleteBattery()
  const [pendingDelete, setPendingDelete] = useState<Battery | null>(null)

  function closeDialog() {
    setPendingDelete(null)
    deleteBattery.reset()
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Batteries</h1>
          <p className="text-sm text-muted-foreground">
            One link that walks a respondent through several questionnaires.
          </p>
        </div>
        <Button render={<Link to="/batteries/new" />}>
          <Plus /> New battery
        </Button>
      </div>

      {isLoading ? (
        <ListSkeleton />
      ) : !batteries?.length ? (
        <div className="rounded-lg border border-dashed p-12 text-center text-muted-foreground">
          No batteries yet.
        </div>
      ) : (
        <div className="rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Battery type</TableHead>
                <TableHead>Progress</TableHead>
                <TableHead>Created</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {batteries.map((b) => {
                const { done, total } = slotProgress(b.questionnaires)
                return (
                  <TableRow key={b.id}>
                    <TableCell className="font-medium">
                      <Link to="/batteries/$id" params={{ id: b.id }} className="hover:underline">
                        {b.name || "Untitled"}
                      </Link>
                    </TableCell>
                    <TableCell>{b.batteryTypeName}</TableCell>
                    <TableCell>
                      {b.isComplete ? (
                        <Badge>Complete</Badge>
                      ) : (
                        <Badge variant="outline">
                          {done}/{total}
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-muted-foreground">{formatDate(b.createdAt)}</TableCell>
                    <TableCell>
                      <div className="flex justify-end gap-2">
                        {!b.isComplete && <CopyButton text={takeBatteryUrl(b.shareToken)} />}
                        <Button size="sm" variant="destructive" onClick={() => setPendingDelete(b)}>
                          Delete
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      )}

      <ConfirmDeleteDialog
        itemLabel={pendingDelete ? `"${pendingDelete.name || "Untitled"}"` : null}
        isPending={deleteBattery.isPending}
        error={
          deleteBattery.isError
            ? apiErrorMessage(deleteBattery.error, "Could not delete. Please try again.")
            : null
        }
        onCancel={closeDialog}
        onConfirm={() =>
          pendingDelete && deleteBattery.mutate(pendingDelete.id, { onSuccess: closeDialog })
        }
      />
    </div>
  )
}
