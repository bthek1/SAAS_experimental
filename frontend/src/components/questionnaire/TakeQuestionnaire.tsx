import { Notice } from "@/components/questionnaire/PublicShell"
import { SurveyRenderer } from "@/components/survey/SurveyRenderer"
import { Button } from "@/components/ui/button"
import { useTakeQuestionnaire } from "@/hooks/useTakeQuestionnaire"

interface TakeQuestionnaireProps {
  shareToken: string
  /** Called after a successful submit (a battery moves to its next slot). */
  onSubmitted?: () => void
  /** Part of a battery: after submitting, wait for the next slot instead of thanking. */
  inBattery?: boolean
}

export function TakeQuestionnaire({ shareToken, onSubmitted, inBattery }: TakeQuestionnaireProps) {
  const { state, submit, isSubmitting, submitError, retry } = useTakeQuestionnaire(shareToken)

  switch (state.status) {
    case "loading":
      return <Notice title="Loading…" />
    case "not-found":
      return (
        <Notice title="Questionnaire not found">
          The link may be wrong, or the questionnaire was removed.
        </Notice>
      )
    case "already-submitted":
      return (
        <Notice title="Already submitted">
          {state.questionnaire.questionnaireTypeTitle} has already been completed with this link.
        </Notice>
      )
    case "thanks":
      if (inBattery) return <Notice title="Saved. Loading the next questionnaire…" />
      return (
        <Notice title="Thank you!">
          Your answers to {state.questionnaire.questionnaireTypeTitle} have been sent.
        </Notice>
      )
    case "ready":
      if (submitError) {
        return (
          <Notice title="Something went wrong">
            <p className="mb-4">{submitError}</p>
            <Button onClick={retry} disabled={isSubmitting}>
              {isSubmitting ? "Sending…" : "Try again"}
            </Button>
          </Notice>
        )
      }
      if (isSubmitting) return <Notice title="Sending your answers…" />
      return (
        <div className="space-y-4">
          <h1 className="text-2xl font-semibold">{state.questionnaire.questionnaireTypeTitle}</h1>
          <div className="overflow-hidden rounded-lg border">
            <SurveyRenderer
              surveyJson={state.questionnaire.questionnaireJson}
              onComplete={(answers, metrics) => submit(answers, metrics, onSubmitted)}
            />
          </div>
        </div>
      )
  }
}
