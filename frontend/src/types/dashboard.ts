export type DashboardRange = 7 | 30 | 90 | "all"

export interface DashboardParams {
  days?: number
  questionnaireType?: string
}

export interface DashboardKpis {
  questionnairesSent: number
  questionnairesSubmitted: number
  questionnairesPending: number
  /** 0-1 share of the window's questionnaires that have been submitted. */
  completionRate: number
  medianHoursToComplete: number | null
  batteriesTotal: number
  batteriesComplete: number
  batteriesInProgress: number
  batteriesNotStarted: number
}

export interface DashboardSummary {
  range: { days: number | null; from: string | null; to: string }
  kpis: DashboardKpis
  submissionsByDay: { date: string; count: number }[]
  byQuestionnaireType: { id: string; title: string; sent: number; submitted: number; pending: number }[]
  byBatteryType: { id: string; title: string; complete: number; inProgress: number; notStarted: number }[]
  recentSubmissions: { id: string; name: string; questionnaireTypeTitle: string; submittedAt: string }[]
  stalePending: {
    id: string
    name: string
    questionnaireTypeTitle: string
    shareToken: string
    createdAt: string
    ageDays: number
  }[]
}

export interface DashboardScoresParams {
  questionnaireType: string
  days?: number
}

export interface ScorePoint<V> {
  questionnaireId: string
  name: string
  submittedAt: string
  value: V
}

interface ScoreMetricBase<K extends string, V> {
  name: string
  label: string
  kind: K
  points: ScorePoint<V>[]
}

export type NumericScoreMetric = ScoreMetricBase<"numeric", number> & { mean: number }
export type CategoricalScoreMetric = ScoreMetricBase<"categorical", string> & {
  distribution: { value: string; count: number }[]
}
export type BooleanScoreMetric = ScoreMetricBase<"boolean", boolean> & {
  distribution: { value: boolean; count: number }[]
}
export type ScoreMetric = NumericScoreMetric | CategoricalScoreMetric | BooleanScoreMetric

export interface DashboardScores {
  questionnaireTypeId: string
  metrics: ScoreMetric[]
}
