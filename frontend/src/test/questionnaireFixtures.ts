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
