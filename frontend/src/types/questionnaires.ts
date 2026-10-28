/** SurveyJS definition. Kept loose: the builder and SurveyJS own its shape. */
export type SurveyJson = Record<string, unknown>

export type Answers = Record<string, unknown>
export type Metrics = Record<string, unknown>

export interface QuestionnaireType {
  id: string
  title: string
  questionnaireJson: SurveyJson
  createdAt: string
  updatedAt: string
}

export type QuestionnaireTypePayload = Pick<QuestionnaireType, "title"> &
  Partial<Pick<QuestionnaireType, "questionnaireJson">>

export interface Questionnaire {
  id: string
  questionnaireTypeId: string
  questionnaireType: QuestionnaireType
  batteryId: string | null
  batteryOrder: number | null
  name: string
  shareToken: string
  answers: Answers
  metrics: Metrics
  submittedAt: string | null
  questionnaireJsonSnapshot: SurveyJson
  createdAt: string
  updatedAt: string
}

export interface QuestionnairePayload {
  questionnaireTypeId: string
  name?: string
}

export interface BatteryType {
  id: string
  title: string
  description: string
  questionnaireTypeIds: string[]
  createdAt: string
  updatedAt: string
}

export interface BatteryTypePayload {
  title: string
  description?: string
  questionnaireTypeIds?: string[]
}

export interface BatterySlot {
  order: number
  questionnaireId: string
  shareToken: string
  questionnaireTypeName: string
  submittedAt: string | null
}

export interface Battery {
  id: string
  batteryTypeId: string
  batteryTypeName: string
  name: string
  shareToken: string
  questionnaires: BatterySlot[]
  isComplete: boolean
  createdAt: string
  updatedAt: string
}

export interface BatteryPayload {
  batteryTypeId: string
  name?: string
}

// ── Public (share-token) payloads ────────────────────────────────────────────

export interface PublicQuestionnaire {
  id: string
  name: string
  questionnaireTypeTitle: string
  questionnaireJson: SurveyJson
  submittedAt: string | null
}

export type PublicBatterySlot = Omit<BatterySlot, "questionnaireId">

export interface PublicBattery {
  id: string
  name: string
  batteryTypeName: string
  questionnaires: PublicBatterySlot[]
  isComplete: boolean
}

export interface SubmitPayload {
  answers: Answers
  metrics?: Metrics
}
