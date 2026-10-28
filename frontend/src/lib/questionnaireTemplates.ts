import type { SurveyJson } from "@/types/questionnaires"

export interface QuestionnaireTemplate {
  id: string
  label: string
  description: string
  questionnaireJson: SurveyJson
}

/** Starting points offered when creating a questionnaire type. */
export const QUESTIONNAIRE_TEMPLATES: QuestionnaireTemplate[] = [
  {
    id: "blank",
    label: "Blank",
    description: "Start from scratch",
    questionnaireJson: { pages: [{ name: "page1", elements: [] }] },
  },
  {
    id: "satisfaction",
    label: "Customer satisfaction",
    description: "NPS + open feedback",
    questionnaireJson: {
      pages: [
        {
          name: "page1",
          elements: [
            {
              type: "rating",
              name: "nps",
              title: "How likely are you to recommend us?",
              rateMin: 0,
              rateMax: 10,
              minRateDescription: "Not likely",
              maxRateDescription: "Extremely likely",
            },
            { type: "comment", name: "feedback", title: "What could we do better?" },
          ],
        },
      ],
    },
  },
  {
    id: "feedback",
    label: "Event feedback",
    description: "Rating + comments",
    questionnaireJson: {
      pages: [
        {
          name: "page1",
          elements: [
            {
              type: "rating",
              name: "overall",
              title: "How would you rate the overall event?",
              rateValues: [1, 2, 3, 4, 5],
            },
            {
              type: "checkbox",
              name: "highlights",
              title: "What did you enjoy most?",
              choices: ["Content", "Networking", "Speakers", "Venue"],
            },
            { type: "comment", name: "suggestions", title: "Any suggestions for next time?" },
          ],
        },
      ],
    },
  },
  {
    id: "scored",
    label: "Scored check-in",
    description: "Ratings with a total score",
    questionnaireJson: {
      pages: [
        {
          name: "page1",
          elements: [
            { type: "rating", name: "mood", title: "How is your mood today?", rateMax: 5 },
            { type: "rating", name: "energy", title: "How is your energy today?", rateMax: 5 },
          ],
        },
      ],
      calculatedValues: [
        { name: "totalScore", expression: "{mood} + {energy}", includeIntoResult: true },
      ],
    },
  },
]

export function templateJson(id: string): SurveyJson {
  return (QUESTIONNAIRE_TEMPLATES.find((t) => t.id === id) ?? QUESTIONNAIRE_TEMPLATES[0])
    .questionnaireJson
}
