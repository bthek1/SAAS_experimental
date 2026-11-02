import { createFileRoute, Link, useNavigate } from "@tanstack/react-router"
import { Plus } from "lucide-react"
import { useState } from "react"
import { ConfirmDeleteDialog } from "@/components/questionnaire/ConfirmDeleteDialog"
import { ListSkeleton } from "@/components/questionnaire/ListSkeleton"
import { Pager } from "@/components/Pager"
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
  questionnaireTypesPageQuery,
  useDeleteQuestionnaireType,
  useQuestionnaireTypesPage,
} from "@/hooks/useQuestionnaireTypes"
import { apiErrorMessage } from "@/lib/apiErrors"
import { formatDate } from "@/lib/date"
import { pageAfterDelete, pageSearch } from "@/lib/pagination"
import type { QuestionnaireType } from "@/types/questionnaires"

export const Route = createFileRoute("/_authed/questionnaire-types/")({
  validateSearch: pageSearch,
  loaderDeps: ({ search }) => ({ page: search.page ?? 1 }),
  loader: ({ context, deps }) =>
    context.queryClient.ensureQueryData(questionnaireTypesPageQuery(deps.page)),
  component: QuestionnaireTypesPage,
})

function QuestionnaireTypesPage() {
  const { page = 1 } = Route.useSearch()
  const navigate = useNavigate({ from: "/questionnaire-types/" })
  const { data, isLoading } = useQuestionnaireTypesPage(page)
  const types = data?.results
  const goTo = (next: number) => navigate({ search: { page: next > 1 ? next : undefined } })
  const deleteType = useDeleteQuestionnaireType()
  const [pendingDelete, setPendingDelete] = useState<QuestionnaireType | null>(null)

  function closeDialog() {
    setPendingDelete(null)
    deleteType.reset()
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Questionnaire types</h1>
          <p className="text-sm text-muted-foreground">
            Templates you build once and send out as questionnaires.
          </p>
        </div>
        <Button render={<Link to="/questionnaire-types/new" />}>
          <Plus /> New type
        </Button>
      </div>

      {isLoading ? (
        <ListSkeleton />
      ) : !types?.length ? (
        <div className="rounded-lg border border-dashed p-12 text-center text-muted-foreground">
          <p className="mb-4">No questionnaire types yet.</p>
          <Button variant="outline" render={<Link to="/questionnaire-types/new" />}>
            Create one
          </Button>
        </div>
      ) : (
        <div className="rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Title</TableHead>
                <TableHead>Updated</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {types.map((t) => (
                <TableRow key={t.id}>
                  <TableCell className="font-medium">{t.title}</TableCell>
                  <TableCell className="text-muted-foreground">{formatDate(t.updatedAt)}</TableCell>
                  <TableCell>
                    <div className="flex justify-end gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        render={<Link to="/questionnaire-types/$id/json" params={{ id: t.id }} />}
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
