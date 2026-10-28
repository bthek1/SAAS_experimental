import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { BatteryTypeForm } from "@/components/questionnaire/BatteryTypeForm"
import { ListSkeleton } from "@/components/questionnaire/ListSkeleton"
import { useCreateBatteryType } from "@/hooks/useBatteryTypes"
import { questionnaireTypesQuery, useQuestionnaireTypes } from "@/hooks/useQuestionnaireTypes"
import { apiErrorMessage } from "@/lib/apiErrors"

export const Route = createFileRoute("/_authed/battery-types/new")({
  loader: ({ context }) => context.queryClient.ensureQueryData(questionnaireTypesQuery()),
  component: NewBatteryTypePage,
})

function NewBatteryTypePage() {
  const navigate = useNavigate()
  const { data: questionnaireTypes, isLoading } = useQuestionnaireTypes()
  const createType = useCreateBatteryType()

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <h1 className="text-2xl font-semibold">New battery type</h1>
      {isLoading ? (
        <ListSkeleton rows={2} />
      ) : (
        <BatteryTypeForm
          defaultValues={{ title: "", description: "", questionnaireTypeIds: [] }}
          questionnaireTypes={questionnaireTypes ?? []}
          submitLabel="Create"
          isPending={createType.isPending}
          error={
            createType.isError
              ? apiErrorMessage(createType.error, "Could not create. Please try again.")
              : null
          }
          onSubmit={(values) =>
            createType.mutate(values, { onSuccess: () => navigate({ to: "/battery-types" }) })
          }
        />
      )}
    </div>
  )
}
