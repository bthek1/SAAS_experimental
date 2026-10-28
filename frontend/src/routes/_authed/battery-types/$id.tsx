import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { BatteryTypeForm } from "@/components/questionnaire/BatteryTypeForm"
import { ListSkeleton } from "@/components/questionnaire/ListSkeleton"
import { batteryTypeQuery, useBatteryType, useUpdateBatteryType } from "@/hooks/useBatteryTypes"
import { questionnaireTypesQuery, useQuestionnaireTypes } from "@/hooks/useQuestionnaireTypes"
import { apiErrorMessage } from "@/lib/apiErrors"

export const Route = createFileRoute("/_authed/battery-types/$id")({
  loader: ({ context, params }) =>
    Promise.all([
      context.queryClient.ensureQueryData(batteryTypeQuery(params.id)),
      context.queryClient.ensureQueryData(questionnaireTypesQuery()),
    ]),
  component: EditBatteryTypePage,
})

function EditBatteryTypePage() {
  const { id } = Route.useParams()
  const navigate = useNavigate()
  const { data: batteryType, isLoading } = useBatteryType(id)
  const { data: questionnaireTypes } = useQuestionnaireTypes()
  const update = useUpdateBatteryType(id)

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <h1 className="text-2xl font-semibold">Edit battery type</h1>
      {isLoading ? (
        <ListSkeleton rows={2} />
      ) : !batteryType ? (
        <p className="text-muted-foreground">Battery type not found.</p>
      ) : (
        <BatteryTypeForm
          key={batteryType.id}
          defaultValues={{
            title: batteryType.title,
            description: batteryType.description,
            questionnaireTypeIds: batteryType.questionnaireTypeIds,
          }}
          questionnaireTypes={questionnaireTypes ?? []}
          submitLabel="Save"
          isPending={update.isPending}
          error={update.isError ? apiErrorMessage(update.error, "Could not save. Please try again.") : null}
          onSubmit={(values) =>
            update.mutate(values, { onSuccess: () => navigate({ to: "/battery-types" }) })
          }
        />
      )}
    </div>
  )
}
