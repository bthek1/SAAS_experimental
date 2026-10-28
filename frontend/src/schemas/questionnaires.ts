import { z } from "zod"

export const TITLE_MAX = 120

const title = z
  .string()
  .trim()
  .min(1, "Title is required")
  .max(TITLE_MAX, `Title must be ${TITLE_MAX} characters or fewer`)

export const questionnaireTypeSchema = z.object({
  title,
  template: z.string().min(1),
})

export type QuestionnaireTypeSchema = z.infer<typeof questionnaireTypeSchema>

export const batteryTypeSchema = z.object({
  title,
  description: z.string().trim().max(1000, "Description is too long"),
  questionnaireTypeIds: z.array(z.string()).min(1, "Add at least one questionnaire type"),
})

export type BatteryTypeSchema = z.infer<typeof batteryTypeSchema>

export const questionnaireSchema = z.object({
  questionnaireTypeId: z.string().min(1, "Pick a questionnaire type"),
  name: z.string().trim().max(255, "Name is too long"),
})

export type QuestionnaireSchema = z.infer<typeof questionnaireSchema>

export const batterySchema = z.object({
  batteryTypeId: z.string().min(1, "Pick a battery type"),
  name: z.string().trim().max(255, "Name is too long"),
})

export type BatterySchema = z.infer<typeof batterySchema>
