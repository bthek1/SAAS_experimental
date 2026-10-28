import { createFileRoute, Link, useNavigate } from "@tanstack/react-router"
import { Plus } from "lucide-react"
import { useState } from "react"
import { z } from "zod"
import { ConfirmDeleteDialog } from "@/components/questionnaire/ConfirmDeleteDialog"
import { CopyButton } from "@/components/questionnaire/CopyButton"
import { ListSkeleton } from "@/components/questionnaire/ListSkeleton"
import { RawResponsesTable } from "@/components/questionnaire/RawResponsesTable"
import { StatusBadge } from "@/components/questionnaire/StatusBadge"
import { SurveyDashboard } from "@/components/survey/SurveyDashboard"
import { Button } from "@/components/ui/button"
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { questionnaireTypesQuery, useQuestionnaireTypes } from "@/hooks/useQuestionnaireTypes"
import {
  questionnairesQuery,
  useDeleteQuestionnaire,
  useQuestionnaires,
} from "@/hooks/useQuestionnaires"
import { apiErrorMessage } from "@/lib/apiErrors"
import { formatDate } from "@/lib/date"
import { responseDefinition } from "@/lib/responses"
import { takeUrl } from "@/lib/shareLinks"
import type { Questionnaire } from "@/types/questionnaires"

export const Route = createFileRoute("/_authed/questionnaires/")({
  validateSearch: z.object({ type: z.string().optional() }),
  loader: ({ context }) =>
    Promise.all([
      context.queryClient.ensureQueryData(questionnairesQuery()),
      context.queryClient.ensureQueryData(questionnaireTypesQuery()),
    ]),
  component: QuestionnairesPage,
})

function QuestionnairesPage() {
  const { type: typeFilter } = Route.useSearch()
  const navigate = useNavigate({ from: "/questionnaires/" })
  const { data: questionnaires, isLoading } = useQuestionnaires()
  const { data: types } = useQuestionnaireTypes()
  const deleteQuestionnaire = useDeleteQuestionnaire()
  const [pendingDelete, setPendingDelete] = useState<Questionnaire | null>(null)

  const shown = (questionnaires ?? []).filter(
    (q) => !typeFilter || q.questionnaireTypeId === typeFilter,
  )
  const submitted = shown.filter((q) => q.submittedAt)

  function closeDialog() {
    setPendingDelete(null)
    deleteQuestionnaire.reset()
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Questionnaires</h1>
          <p className="text-sm text-muted-foreground">
            Each one has its own share link and collects one response.
          </p>
        </div>
        <Button render={<Link to="/questionnaires/new" search={{ type: typeFilter }} />}>
          <Plus /> New questionnaire
        </Button>
      </div>

      <NativeSelect
        aria-label="Filter by questionnaire type"
        value={typeFilter ?? ""}
        onChange={(e) => navigate({ search: { type: e.target.value || undefined } })}
      >
        <NativeSelectOption value="">All types</NativeSelectOption>
        {types?.map((t) => (
          <NativeSelectOption key={t.id} value={t.id}>
            {t.title}
          </NativeSelectOption>
        ))}
      </NativeSelect>

      {isLoading ? (
        <ListSkeleton />
      ) : shown.length === 0 ? (
        <div className="rounded-lg border border-dashed p-12 text-center text-muted-foreground">
          No questionnaires yet.
        </div>
      ) : (
        <div className="rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Created</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {shown.map((q) => (
                <TableRow key={q.id}>
                  <TableCell className="font-medium">
                    <Link to="/questionnaires/$id" params={{ id: q.id }} className="hover:underline">
                      {q.name || "Untitled"}
                    </Link>
                  </TableCell>
                  <TableCell>{q.questionnaireType.title}</TableCell>
                  <TableCell>
                    <StatusBadge submittedAt={q.submittedAt} />
                  </TableCell>
                  <TableCell className="text-muted-foreground">{formatDate(q.createdAt)}</TableCell>
                  <TableCell>
                    <div className="flex justify-end gap-2">
                      {q.submittedAt ? (
                        <Button
                          size="sm"
                          variant="outline"
                          render={<Link to="/questionnaires/$id/results" params={{ id: q.id }} />}
                        >
                          Results
                        </Button>
                      ) : (
                        <CopyButton text={takeUrl(q.shareToken)} />
                      )}
                      <Button size="sm" variant="destructive" onClick={() => setPendingDelete(q)}>
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

      {typeFilter && submitted.length > 0 && (
        <section className="space-y-4" aria-label="Summary">
          <h2 className="text-lg font-semibold">Summary of {submitted.length} responses</h2>
          <SurveyDashboard
            surveyJson={responseDefinition(submitted[0])}
            responses={submitted.map((q) => q.answers)}
          />
          <RawResponsesTable responses={submitted} />
        </section>
      )}

      <ConfirmDeleteDialog
        itemLabel={pendingDelete ? `"${pendingDelete.name || "Untitled"}"` : null}
        isPending={deleteQuestionnaire.isPending}
        error={
          deleteQuestionnaire.isError
            ? apiErrorMessage(deleteQuestionnaire.error, "Could not delete. Please try again.")
            : null
        }
        onCancel={closeDialog}
        onConfirm={() =>
          pendingDelete && deleteQuestionnaire.mutate(pendingDelete.id, { onSuccess: closeDialog })
        }
      />
    </div>
  )
}
