import { useRef, useState } from "react"
import { useQuestionnaireByToken, useSubmitQuestionnaire } from "@/hooks/useQuestionnaires"
import { isConflict } from "@/lib/apiErrors"
import type { Answers, Metrics, PublicQuestionnaire } from "@/types/questionnaires"

export type TakeState =
  | { status: "loading" }
  | { status: "not-found" }
  | { status: "already-submitted"; questionnaire: PublicQuestionnaire }
  | { status: "thanks"; questionnaire: PublicQuestionnaire }
  | { status: "ready"; questionnaire: PublicQuestionnaire }

/** Everything a respondent's page needs to show and submit one share link. */
export function useTakeQuestionnaire(shareToken: string) {
  const query = useQuestionnaireByToken(shareToken)
  const submitMutation = useSubmitQuestionnaire(shareToken)
  const [justSubmitted, setJustSubmitted] = useState(false)
  // SurveyJS has already shown its completed page when a submit fails, so a
  // retry resends the same answers instead of asking for them again.
  const lastPayload = useRef<{ answers: Answers; metrics: Metrics; onSubmitted?: () => void }>(
    undefined,
  )

  const questionnaire = query.data
  let state: TakeState
  if (query.isLoading) state = { status: "loading" }
  else if (!questionnaire) state = { status: "not-found" }
  else if (justSubmitted) state = { status: "thanks", questionnaire }
  else if (questionnaire.submittedAt || isConflict(submitMutation.error))
    state = { status: "already-submitted", questionnaire }
  else state = { status: "ready", questionnaire }

  function submit(answers: Answers, metrics: Metrics, onSubmitted?: () => void) {
    lastPayload.current = { answers, metrics, onSubmitted }
    submitMutation.mutate(
      { answers, metrics },
      {
        onSuccess: () => {
          setJustSubmitted(true)
          onSubmitted?.()
        },
      },
    )
  }

  const submitError =
    submitMutation.isError && !isConflict(submitMutation.error)
      ? "Your answers could not be sent. Please check your connection and try again."
      : null

  return {
    state,
    submit,
    isSubmitting: submitMutation.isPending,
    submitError,
    retry: () => {
      const payload = lastPayload.current
      if (payload) submit(payload.answers, payload.metrics, payload.onSubmitted)
    },
  }
}
