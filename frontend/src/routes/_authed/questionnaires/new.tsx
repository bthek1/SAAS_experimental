import { zodResolver } from "@hookform/resolvers/zod"
import { createFileRoute, Link } from "@tanstack/react-router"
import { useForm } from "react-hook-form"
import { z } from "zod"
import { ShareLink } from "@/components/questionnaire/ShareLink"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { Input } from "@/components/ui/input"
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select"
import { questionnaireTypesQuery, useQuestionnaireTypes } from "@/hooks/useQuestionnaireTypes"
import { useCreateQuestionnaire } from "@/hooks/useQuestionnaires"
import { takeUrl } from "@/lib/shareLinks"
import { questionnaireSchema, type QuestionnaireSchema } from "@/schemas/questionnaires"

export const Route = createFileRoute("/_authed/questionnaires/new")({
  validateSearch: z.object({ type: z.string().optional() }),
  loader: ({ context }) => context.queryClient.ensureQueryData(questionnaireTypesQuery()),
  component: NewQuestionnairePage,
})

function NewQuestionnairePage() {
  const { type } = Route.useSearch()
  const { data: types } = useQuestionnaireTypes()
  const create = useCreateQuestionnaire()
  const form = useForm<QuestionnaireSchema>({
    resolver: zodResolver(questionnaireSchema),
    defaultValues: { questionnaireTypeId: type ?? "", name: "" },
  })

  if (create.data) {
    const created = create.data
    return (
      <div className="mx-auto max-w-xl space-y-6">
        <h1 className="text-2xl font-semibold">Questionnaire ready</h1>
        <Card>
          <CardHeader>
            <CardTitle>
              Share this link{created.name ? ` with ${created.name}` : ""}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-muted-foreground">
              Anyone with the link can answer once, without an account.
            </p>
            <ShareLink url={takeUrl(created.shareToken)} />
          </CardContent>
        </Card>
        <div className="flex gap-2">
          <Button render={<Link to="/questionnaires/$id" params={{ id: created.id }} />}>
            Open questionnaire
          </Button>
          <Button
            variant="outline"
            onClick={() => {
              create.reset()
              form.reset({ questionnaireTypeId: created.questionnaireTypeId, name: "" })
            }}
          >
            Create another
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <h1 className="text-2xl font-semibold">New questionnaire</h1>
      {types?.length === 0 ? (
        <p className="text-muted-foreground">
          You need a questionnaire type first.{" "}
          <Link to="/questionnaire-types/new" className="underline">
            Create one.
          </Link>
        </p>
      ) : (
        <Form {...form}>
          <form
            onSubmit={form.handleSubmit((values) =>
              create.mutate(values, {
                onError: () =>
                  form.setError("root", { message: "Could not create. Please try again." }),
              }),
            )}
            className="space-y-5"
          >
            <FormField
              control={form.control}
              name="questionnaireTypeId"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Questionnaire type</FormLabel>
                  <FormControl>
                    <NativeSelect className="w-full" {...field}>
                      <NativeSelectOption value="">Choose a type…</NativeSelectOption>
                      {types?.map((t) => (
                        <NativeSelectOption key={t.id} value={t.id}>
                          {t.title}
                        </NativeSelectOption>
                      ))}
                    </NativeSelect>
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Respondent name (optional)</FormLabel>
                  <FormControl>
                    <Input placeholder="Only you see this" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            {form.formState.errors.root && (
              <p className="text-sm text-destructive">{form.formState.errors.root.message}</p>
            )}
            <div className="flex justify-between">
              <Button variant="outline" render={<Link to="/questionnaires" />}>
                Cancel
              </Button>
              <Button type="submit" disabled={create.isPending}>
                {create.isPending ? "Creating…" : "Create share link"}
              </Button>
            </div>
          </form>
        </Form>
      )}
    </div>
  )
}
