import { createFileRoute, Link, useNavigate } from "@tanstack/react-router"
import { Plus } from "lucide-react"
import { useState } from "react"
import { ConfirmDeleteDialog } from "@/components/questionnaire/ConfirmDeleteDialog"
import { ListSkeleton } from "@/components/questionnaire/ListSkeleton"
import { Pager } from "@/components/Pager"
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
import {
  batteryTypesPageQuery,
  useBatteryTypesPage,
  useDeleteBatteryType,
} from "@/hooks/useBatteryTypes"
import { apiErrorMessage } from "@/lib/apiErrors"
import { formatDate } from "@/lib/date"
import { pageAfterDelete, pageSearch } from "@/lib/pagination"
import type { BatteryType } from "@/types/questionnaires"

export const Route = createFileRoute("/_authed/battery-types/")({
  validateSearch: pageSearch,
  loaderDeps: ({ search }) => ({ page: search.page ?? 1 }),
  loader: ({ context, deps }) => context.queryClient.ensureQueryData(batteryTypesPageQuery(deps.page)),
  component: BatteryTypesPage,
})

function BatteryTypesPage() {
  const { page = 1 } = Route.useSearch()
  const navigate = useNavigate({ from: "/battery-types/" })
  const { data, isLoading } = useBatteryTypesPage(page)
  const types = data?.results
  const goTo = (next: number) => navigate({ search: { page: next > 1 ? next : undefined } })
  const deleteType = useDeleteBatteryType()
  const [pendingDelete, setPendingDelete] = useState<BatteryType | null>(null)

  function closeDialog() {
    setPendingDelete(null)
    deleteType.reset()
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Battery types</h1>
          <p className="text-sm text-muted-foreground">
            Ordered sets of questionnaire types, sent as one link.
          </p>
        </div>
        <Button render={<Link to="/battery-types/new" />}>
          <Plus /> New battery type
        </Button>
      </div>

      {isLoading ? (
        <ListSkeleton />
      ) : !types?.length ? (
        <div className="rounded-lg border border-dashed p-12 text-center text-muted-foreground">
          <p className="mb-4">No battery types yet.</p>
          <Button variant="outline" render={<Link to="/battery-types/new" />}>
            Create one
          </Button>
        </div>
      ) : (
        <div className="rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Title</TableHead>
                <TableHead>Questionnaires</TableHead>
                <TableHead>Updated</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {types.map((t) => (
                <TableRow key={t.id}>
                  <TableCell>
                    <div className="font-medium">{t.title}</div>
                    {t.description && (
                      <div className="text-xs text-muted-foreground">{t.description}</div>
                    )}
                  </TableCell>
                  <TableCell>
                    <Badge variant="secondary">{t.questionnaireTypeIds.length}</Badge>
                  </TableCell>
                  <TableCell className="text-muted-foreground">{formatDate(t.updatedAt)}</TableCell>
                  <TableCell>
                    <div className="flex justify-end gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        render={<Link to="/battery-types/$id" params={{ id: t.id }} />}
                      >
                        Edit
                      </Button>
                      <Button size="sm" variant="destructive" onClick={() => setPendingDelete(t)}>
                        Delete
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <Pager page={page} count={data?.count ?? 0} onPageChange={goTo} />

      <ConfirmDeleteDialog
        itemLabel={pendingDelete ? `"${pendingDelete.title}"` : null}
        isPending={deleteType.isPending}
        error={
          deleteType.isError
            ? apiErrorMessage(deleteType.error, "Could not delete. Please try again.")
            : null
        }
        onCancel={closeDialog}
        onConfirm={() =>
          pendingDelete &&
          deleteType.mutate(pendingDelete.id, {
            onSuccess: () => {
              closeDialog()
              goTo(pageAfterDelete(page, types?.length ?? 0))
            },
          })
        }
      />
    </div>
  )
}
