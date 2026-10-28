import { zodResolver } from "@hookform/resolvers/zod"
import { createFileRoute, Link } from "@tanstack/react-router"
import { useForm } from "react-hook-form"
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
import { useCreateBattery } from "@/hooks/useBatteries"
import { batteryTypesQuery, useBatteryTypes } from "@/hooks/useBatteryTypes"
import { takeBatteryUrl } from "@/lib/shareLinks"
import { batterySchema, type BatterySchema } from "@/schemas/questionnaires"

export const Route = createFileRoute("/_authed/batteries/new")({
  loader: ({ context }) => context.queryClient.ensureQueryData(batteryTypesQuery()),
  component: NewBatteryPage,
})

function NewBatteryPage() {
  const { data: types } = useBatteryTypes()
  const create = useCreateBattery()
  const form = useForm<BatterySchema>({
    resolver: zodResolver(batterySchema),
    defaultValues: { batteryTypeId: "", name: "" },
  })

  if (create.data) {
    const created = create.data
    return (
      <div className="mx-auto max-w-xl space-y-6">
        <h1 className="text-2xl font-semibold">Battery ready</h1>
        <Card>
          <CardHeader>
            <CardTitle>Share this link{created.name ? ` with ${created.name}` : ""}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-muted-foreground">
              It takes the respondent through {created.questionnaires.length} questionnaires in
              order.
            </p>
            <ShareLink url={takeBatteryUrl(created.shareToken)} />
          </CardContent>
        </Card>
        <div className="flex gap-2">
          <Button render={<Link to="/batteries/$id" params={{ id: created.id }} />}>
            Open battery
          </Button>
          <Button variant="outline" onClick={() => create.reset()}>
            Create another
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <h1 className="text-2xl font-semibold">New battery</h1>
      {types?.length === 0 ? (
        <p className="text-muted-foreground">
          You need a battery type first.{" "}
          <Link to="/battery-types/new" className="underline">
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
              name="batteryTypeId"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Battery type</FormLabel>
                  <FormControl>
                    <NativeSelect className="w-full" {...field}>
                      <NativeSelectOption value="">Choose a battery type…</NativeSelectOption>
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
              <Button variant="outline" render={<Link to="/batteries" />}>
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
