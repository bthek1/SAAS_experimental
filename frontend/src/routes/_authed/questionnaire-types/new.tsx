import { zodResolver } from "@hookform/resolvers/zod"
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router"
import { useForm } from "react-hook-form"
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
import { useCreateQuestionnaireType } from "@/hooks/useQuestionnaireTypes"
import { QUESTIONNAIRE_TEMPLATES, templateJson } from "@/lib/questionnaireTemplates"
import { cn } from "@/lib/utils"
import {
  questionnaireTypeSchema,
  type QuestionnaireTypeSchema,
} from "@/schemas/questionnaires"

export const Route = createFileRoute("/_authed/questionnaire-types/new")({
  component: NewQuestionnaireTypePage,
})

function NewQuestionnaireTypePage() {
  const navigate = useNavigate()
  const createType = useCreateQuestionnaireType()
  const form = useForm<QuestionnaireTypeSchema>({
    resolver: zodResolver(questionnaireTypeSchema),
    defaultValues: { title: "", template: "blank" },
  })

  function onSubmit(values: QuestionnaireTypeSchema) {
    createType.mutate(
      { title: values.title, questionnaireJson: templateJson(values.template) },
      {
        onSuccess: (created) =>
          navigate({ to: "/questionnaire-types/$id/json", params: { id: created.id } }),
        onError: () =>
          form.setError("root", { message: "Could not create the type. Please try again." }),
      },
    )
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">New questionnaire type</h1>
        <p className="text-sm text-muted-foreground">
          Name it and pick a starting point. You can edit everything afterwards.
        </p>
      </div>

      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Details</CardTitle>
            </CardHeader>
            <CardContent>
              <FormField
                control={form.control}
                name="title"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Title</FormLabel>
                    <FormControl>
                      <Input placeholder="e.g. Weekly check-in" autoFocus {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Starting template</CardTitle>
            </CardHeader>
            <CardContent>
              <FormField
                control={form.control}
                name="template"
                render={({ field }) => (
                  <div role="radiogroup" aria-label="Starting template" className="grid gap-3 sm:grid-cols-2">
                    {QUESTIONNAIRE_TEMPLATES.map((t) => {
                      const selected = field.value === t.id
                      return (
                        <button
                          key={t.id}
                          type="button"
                          role="radio"
                          aria-checked={selected}
                          onClick={() => field.onChange(t.id)}
                          className={cn(
                            "flex flex-col items-start gap-1 rounded-lg border p-4 text-left transition-colors hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none",
                            selected && "border-primary bg-primary/5 ring-1 ring-primary",
                          )}
                        >
                          <span className="text-sm font-medium">{t.label}</span>
                          <span className="text-xs text-muted-foreground">{t.description}</span>
                        </button>
                      )
                    })}
                  </div>
                )}
              />
            </CardContent>
          </Card>

          {form.formState.errors.root && (
            <p className="text-sm text-destructive">{form.formState.errors.root.message}</p>
          )}

          <div className="flex justify-between">
            <Button variant="outline" render={<Link to="/questionnaire-types" />}>
              Cancel
            </Button>
            <Button type="submit" disabled={createType.isPending}>
              {createType.isPending ? "Creating…" : "Create and open editor"}
            </Button>
          </div>
        </form>
      </Form>
    </div>
  )
}
