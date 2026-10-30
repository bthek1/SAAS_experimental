import type { DashboardScores, DashboardSummary } from "@/types/dashboard"
import type {
  Battery,
  BatteryType,
  PublicBattery,
  PublicQuestionnaire,
  Questionnaire,
  QuestionnaireType,
} from "@/types/questionnaires"

export const surveyJson = {
  pages: [
    {
      name: "page1",
      elements: [
        { type: "rating", name: "q1", title: "How are you?", rateMax: 5 },
        { type: "text", name: "q2", title: "Anything else?" },
      ],
    },
  ],
  calculatedValues: [{ name: "totalScore", expression: "{q1} * 2" }],
}

export const questionnaireType: QuestionnaireType = {
  id: "qt-1",
  title: "Wellbeing",
  questionnaireJson: surveyJson,
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
}

export const questionnaire: Questionnaire = {
  id: "q-1",
  questionnaireTypeId: questionnaireType.id,
  questionnaireType,
  batteryId: null,
  batteryOrder: null,
  name: "Alice",
  shareToken: "11111111-1111-1111-1111-111111111111",
  answers: {},
  metrics: {},
  submittedAt: null,
  questionnaireJsonSnapshot: {},
  createdAt: "2026-01-02T00:00:00Z",
  updatedAt: "2026-01-02T00:00:00Z",
}

export const submittedQuestionnaire: Questionnaire = {
  ...questionnaire,
  id: "q-2",
  name: "Bob",
  shareToken: "22222222-2222-2222-2222-222222222222",
  answers: { q1: 4, q2: "All good" },
  metrics: { totalScore: 8 },
  submittedAt: "2026-01-03T10:00:00Z",
  questionnaireJsonSnapshot: surveyJson,
}

export const publicQuestionnaire: PublicQuestionnaire = {
  id: questionnaire.id,
  name: questionnaire.name,
  questionnaireTypeTitle: questionnaireType.title,
  questionnaireJson: surveyJson,
  submittedAt: null,
}

export const batteryType: BatteryType = {
  id: "bt-1",
  title: "Intake",
  description: "First visit",
  questionnaireTypeIds: [questionnaireType.id],
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
}

export const battery: Battery = {
  id: "b-1",
  batteryTypeId: batteryType.id,
  batteryTypeName: batteryType.title,
  name: "Carol",
  shareToken: "33333333-3333-3333-3333-333333333333",
  questionnaires: [
    {
      order: 0,
      questionnaireId: "q-3",
      shareToken: "44444444-4444-4444-4444-444444444444",
      questionnaireTypeName: "Wellbeing",
      submittedAt: null,
    },
    {
      order: 1,
      questionnaireId: "q-4",
      shareToken: "55555555-5555-5555-5555-555555555555",
      questionnaireTypeName: "Sleep",
      submittedAt: null,
    },
  ],
  isComplete: false,
  createdAt: "2026-01-04T00:00:00Z",
  updatedAt: "2026-01-04T00:00:00Z",
}

export const publicBattery: PublicBattery = {
  id: battery.id,
  name: battery.name,
  batteryTypeName: battery.batteryTypeName,
  questionnaires: battery.questionnaires.map(
    ({ order, shareToken, questionnaireTypeName, submittedAt }) => ({
      order,
      shareToken,
      questionnaireTypeName,
      submittedAt,
    }),
  ),
  isComplete: false,
}

export const dashboardSummary: DashboardSummary = {
  range: { days: 30, from: "2026-10-01T00:00:00Z", to: "2026-10-30T12:00:00Z" },
  kpis: {
    questionnairesSent: 12,
    questionnairesSubmitted: 9,
    questionnairesPending: 3,
    completionRate: 0.75,
    medianHoursToComplete: 5.5,
    batteriesTotal: 4,
    batteriesComplete: 2,
    batteriesInProgress: 1,
    batteriesNotStarted: 1,
  },
  submissionsByDay: [
    { date: "2026-10-28", count: 2 },
    { date: "2026-10-29", count: 0 },
    { date: "2026-10-30", count: 1 },
  ],
  byQuestionnaireType: [{ id: "qt-1", title: "Wellbeing", sent: 12, submitted: 9, pending: 3 }],
  byBatteryType: [{ id: "bt-1", title: "Intake", complete: 2, inProgress: 1, notStarted: 1 }],
  recentSubmissions: [
    {
      id: "q-2",
      name: "Bob",
      questionnaireTypeTitle: "Wellbeing",
      submittedAt: "2026-10-30T10:00:00Z",
    },
  ],
  stalePending: [
    {
      id: "q-1",
      name: "Alice",
      questionnaireTypeTitle: "Wellbeing",
      shareToken: "11111111-1111-1111-1111-111111111111",
      createdAt: "2026-10-01T00:00:00Z",
      ageDays: 29,
    },
  ],
}

export const dashboardScores: DashboardScores = {
  questionnaireTypeId: "qt-1",
  metrics: [
    {
      name: "total",
      label: "Total score",
      kind: "numeric",
      mean: 7,
      points: [
        { questionnaireId: "q-2", name: "Bob", submittedAt: "2026-10-28T10:00:00Z", value: 4 },
        { questionnaireId: "q-5", name: "Dee", submittedAt: "2026-10-29T10:00:00Z", value: 10 },
      ],
    },
    {
      name: "severity",
      label: "Severity",
      kind: "categorical",
      distribution: [
        { value: "Mild", count: 1 },
        { value: "Moderate", count: 1 },
      ],
      points: [
        { questionnaireId: "q-2", name: "Bob", submittedAt: "2026-10-28T10:00:00Z", value: "Mild" },
        {
          questionnaireId: "q-5",
          name: "Dee",
          submittedAt: "2026-10-29T10:00:00Z",
          value: "Moderate",
        },
      ],
    },
    {
      name: "flag",
      label: "Needs follow-up",
      kind: "boolean",
      distribution: [
        { value: false, count: 1 },
        { value: true, count: 1 },
      ],
      points: [
        { questionnaireId: "q-2", name: "Bob", submittedAt: "2026-10-28T10:00:00Z", value: false },
        { questionnaireId: "q-5", name: "Dee", submittedAt: "2026-10-29T10:00:00Z", value: true },
      ],
    },
  ],
}
