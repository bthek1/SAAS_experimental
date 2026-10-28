import { useEffect, useRef, useState } from "react"
import { Model, type ITheme } from "survey-core"
import { Survey } from "survey-react-ui"
import "survey-core/survey-core.min.css"
import "./survey-theme.css"
import { metricsFromModel } from "@/lib/metrics"
import type { Answers, Metrics, SurveyJson } from "@/types/questionnaires"

interface SurveyRendererProps {
  surveyJson: SurveyJson
  /** Called once when the respondent completes the survey. */
  onComplete?: (answers: Answers, metrics: Metrics) => void
  /** Pre-filled answers, e.g. when showing a submitted response. */
  data?: Answers
  /** Render without inputs (owner's view of a response). */
  readOnly?: boolean
}

export function SurveyRenderer({ surveyJson, onComplete, data, readOnly }: SurveyRendererProps) {
  // Keep the latest callback without rebuilding the model on every render.
  const onCompleteRef = useRef(onComplete)
  useEffect(() => {
    onCompleteRef.current = onComplete
  }, [onComplete])

  // Built in an effect (not useMemo) so each model is disposed by its own
  // cleanup: the editor preview rebuilds on every edit, and an undisposed
  // model's resize observers keep measuring elements that are gone.
  const [model, setModel] = useState<Model | null>(null)
  useEffect(() => {
    const m = new Model(surveyJson)
    if (surveyJson.themeJson && typeof surveyJson.themeJson === "object") {
      m.applyTheme(surveyJson.themeJson as ITheme)
    }
    if (data) m.data = data
    if (readOnly) {
      m.readOnly = true
      m.showCompleteButton = false
    }
    m.onComplete.add((sender) => {
      onCompleteRef.current?.(sender.data as Answers, metricsFromModel(sender))
    })
    setModel(m)
    return () => m.dispose()
  }, [surveyJson, data, readOnly])

  if (!model) return null
  return <Survey model={model} />
}
