import { useCallback, useState } from "react"
import type { SurveyJson } from "@/types/questionnaires"

function isSurveyJson(value: unknown): value is SurveyJson {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

/**
 * Editing state for a SurveyJS definition shown both as raw JSON text and in
 * the visual editor. The text is the single source of truth; `json` is the
 * last version of it that parsed, which drives the preview and visual editor.
 */
export function useSurveyJsonDraft(initial: SurveyJson) {
  const [text, setText] = useState(() => JSON.stringify(initial, null, 2))
  const [json, setJson] = useState<SurveyJson>(initial)
  const [error, setError] = useState<string | null>(null)
  const [dirty, setDirty] = useState(false)

  const setFromText = useCallback((value: string) => {
    setText(value)
    setDirty(true)
    try {
      const parsed: unknown = JSON.parse(value)
      if (!isSurveyJson(parsed)) {
        setError("The definition must be a JSON object")
        return
      }
      setJson(parsed)
      setError(null)
    } catch {
      setError("Invalid JSON")
    }
  }, [])

  const setFromJson = useCallback((value: SurveyJson) => {
    setJson(value)
    setText(JSON.stringify(value, null, 2))
    setError(null)
    setDirty(true)
  }, [])

  const markSaved = useCallback(() => setDirty(false), [])

  return { text, json, error, dirty, setFromText, setFromJson, markSaved }
}
