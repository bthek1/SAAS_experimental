import { useMemo } from "react"
import { buildSummaries } from "@/lib/surveySummary"
import type { Answers, SurveyJson } from "@/types/questionnaires"

interface SurveyDashboardProps {
  surveyJson: SurveyJson
  responses: Answers[]
}

/** Per-question breakdown of one or more responses. */
export function SurveyDashboard({ surveyJson, responses }: SurveyDashboardProps) {
  const summaries = useMemo(() => buildSummaries(surveyJson, responses), [surveyJson, responses])

  if (responses.length === 0) {
    return <p className="py-8 text-center text-sm text-muted-foreground">No responses yet.</p>
  }

  return (
    <div className="space-y-4">
      {summaries.map((s) => (
        <section key={s.name} className="rounded-lg border p-4" aria-label={s.title}>
          <h3 className="mb-3 font-medium">{s.title}</h3>
          {s.kind === "choice" ? (
            <ul className="space-y-2">
              {s.choices.map((c) => {
                const pct = s.total > 0 ? Math.round((c.count / s.total) * 100) : 0
                return (
                  <li key={c.text} className="text-sm">
                    <div className="mb-1 flex justify-between">
                      <span>{c.text}</span>
                      <span className="text-muted-foreground">
                        {c.count} ({pct}%)
                      </span>
                    </div>
                    <div className="h-2 overflow-hidden rounded-full bg-muted">
                      <div className="h-2 rounded-full bg-primary" style={{ width: `${pct}%` }} />
                    </div>
                  </li>
                )
              })}
            </ul>
          ) : s.answers.length === 0 ? (
            <p className="text-sm text-muted-foreground italic">No answers</p>
          ) : (
            <ul className="space-y-1 text-sm">
              {s.answers.map((a, i) => (
                <li key={i} className="rounded-md bg-muted px-3 py-1">
                  {a}
                </li>
              ))}
            </ul>
          )}
        </section>
      ))}
    </div>
  )
}
