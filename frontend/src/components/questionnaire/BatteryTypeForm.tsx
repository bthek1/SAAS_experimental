import { zodResolver } from "@hookform/resolvers/zod"
import { Link } from "@tanstack/react-router"
import { useForm } from "react-hook-form"
import { OrderedTypePicker } from "@/components/questionnaire/OrderedTypePicker"
import { Button } from "@/components/ui/button"
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { batteryTypeSchema, type BatteryTypeSchema } from "@/schemas/questionnaires"
import type { QuestionnaireType } from "@/types/questionnaires"

interface BatteryTypeFormProps {
  defaultValues: BatteryTypeSchema
  questionnaireTypes: QuestionnaireType[]
  submitLabel: string
  isPending: boolean
  /** Shown above the buttons, e.g. a failed save. */
  error?: string | null
  onSubmit: (values: BatteryTypeSchema) => void
}

export function BatteryTypeForm({
  defaultValues,
  questionnaireTypes,
  submitLabel,
  isPending,
  error,
  onSubmit,
}: BatteryTypeFormProps) {
  const form = useForm<BatteryTypeSchema>({
    resolver: zodResolver(batteryTypeSchema),
    defaultValues,
  })

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-5">
        <FormField
          control={form.control}
          name="title"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Title</FormLabel>
              <FormControl>
                <Input placeholder="e.g. Intake assessment" {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="description"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Description (optional)</FormLabel>
              <FormControl>
                <Textarea rows={2} {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="questionnaireTypeIds"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Questionnaire types, in order</FormLabel>
              {questionnaireTypes.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  You have no questionnaire types yet.{" "}
                  <Link to="/questionnaire-types/new" className="underline">
                    Create one first.
                  </Link>
                </p>
              ) : (
                <OrderedTypePicker
                  value={field.value}
                  onChange={field.onChange}
                  options={questionnaireTypes}
                />
              )}
              <FormMessage />
            </FormItem>
          )}
        />

        {error && <p className="text-sm text-destructive">{error}</p>}

        <div className="flex justify-between">
          <Button variant="outline" render={<Link to="/battery-types" />}>
            Cancel
          </Button>
          <Button type="submit" disabled={isPending}>
            {isPending ? "Saving…" : submitLabel}
          </Button>
        </div>
      </form>
    </Form>
  )
}
