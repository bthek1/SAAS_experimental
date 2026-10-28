import { createFileRoute, Link } from "@tanstack/react-router"
import { ArrowLeft } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { VisualEditor } from "@/components/formBuilder/VisualEditor"
import { ListSkeleton } from "@/components/questionnaire/ListSkeleton"
import { SurveyRenderer } from "@/components/survey/SurveyRenderer"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import {
  questionnaireTypeQuery,
  useQuestionnaireType,
  useUpdateQuestionnaireType,
} from "@/hooks/useQuestionnaireTypes"
import { useSurveyJsonDraft } from "@/hooks/useSurveyJsonDraft"
import type { QuestionnaireType } from "@/types/questionnaires"

export const Route = createFileRoute("/_authed/questionnaire-types/$id/json")({
  loader: ({ context, params }) =>
    context.queryClient.ensureQueryData(questionnaireTypeQuery(params.id)),
  component: QuestionnaireTypeEditorPage,
})

function QuestionnaireTypeEditorPage() {
  const { id } = Route.useParams()
  const { data: type, isLoading } = useQuestionnaireType(id)

  if (isLoading) return <ListSkeleton />
  if (!type) return <p className="text-muted-foreground">Questionnaire type not found.</p>
  // Keyed so that navigating to another type starts a fresh draft.
  return <Editor key={type.id} type={type} />
}

function Editor({ type }: { type: QuestionnaireType }) {
  const update = useUpdateQuestionnaireType(type.id)
  const draft = useSurveyJsonDraft(type.questionnaireJson)
  const [title, setTitle] = useState(type.title)
  const [saved, setSaved] = useState(false)

  const titleError = title.trim() ? null : "Title is required"
  const canSave = !draft.error && !titleError && !update.isPending

  function save() {
    if (!canSave) return
    update.mutate(
      { title: title.trim(), questionnaireJson: draft.json },
      {
        onSuccess: () => {
          draft.markSaved()
          setSaved(true)
        },
      },
    )
  }

  // Ctrl+S / Cmd+S saves. The ref keeps the listener stable across renders.
  const saveRef = useRef(save)
  useEffect(() => {
    saveRef.current = save
  })
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key === "s") {
        e.preventDefault()
        saveRef.current()
      }
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [])

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Button
          size="icon-sm"
          variant="ghost"
          aria-label="Back to questionnaire types"
          render={<Link to="/questionnaire-types" />}
        >
          <ArrowLeft />
        </Button>
        <Input
          aria-label="Title"
          aria-invalid={!!titleError}
          value={title}
          onChange={(e) => {
            setTitle(e.target.value)
            setSaved(false)
          }}
          className="max-w-md text-lg font-semibold"
        />
        <div className="ml-auto flex items-center gap-3 text-sm">
          {update.isError && <span className="text-destructive">Save failed. Try again.</span>}
          {saved && !draft.dirty && title === type.title && (
            <span className="text-muted-foreground">Saved</span>
          )}
          <Button onClick={save} disabled={!canSave}>
            {update.isPending ? "Saving…" : "Save"}
          </Button>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Tabs defaultValue="visual" className="min-w-0">
          <TabsList>
            <TabsTrigger value="visual">Visual</TabsTrigger>
            <TabsTrigger value="json">JSON</TabsTrigger>
          </TabsList>
          <TabsContent value="visual">
            <VisualEditor
              surveyJson={draft.json}
              onChange={(next) => {
                draft.setFromJson(next)
                setSaved(false)
              }}
            />
          </TabsContent>
          <TabsContent value="json" className="space-y-2">
            {draft.error && (
              <p role="alert" className="text-sm text-destructive">
                {draft.error}
              </p>
            )}
            <Textarea
              aria-label="Questionnaire JSON"
              value={draft.text}
              onChange={(e) => {
                draft.setFromText(e.target.value)
                setSaved(false)
              }}
              rows={36}
              spellCheck={false}
              className="font-mono text-xs"
            />
          </TabsContent>
        </Tabs>

        <section aria-label="Preview" className="min-w-0 space-y-2">
          <h2 className="text-sm font-medium text-muted-foreground">Preview</h2>
          <div className="overflow-hidden rounded-lg border">
            <SurveyRenderer surveyJson={draft.json} />
          </div>
        </section>
      </div>
    </div>
  )
}
