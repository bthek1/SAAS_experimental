import { Model } from "survey-core"
import type { Answers, Metrics, SurveyJson } from "@/types/questionnaires"

export interface MetricResult {
  name: string
  label: string
  value: unknown
}

interface CalculatedValueDef {
  name: string
  title?: string
}

/** Convert snake_case / camelCase names to "Title Case" for display. */
export function formatLabel(name: string): string {
  return name
    .replace(/_/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

function calculatedValueDefs(surveyJson: SurveyJson): CalculatedValueDef[] {
  const defs = surveyJson.calculatedValues
  if (!Array.isArray(defs)) return []
  return defs.filter(
    (d): d is CalculatedValueDef =>
      typeof d === "object" && d !== null && typeof (d as CalculatedValueDef).name === "string",
  )
}

function labelOf(def: CalculatedValueDef): string {
  return def.title ? String(def.title) : formatLabel(def.name)
}

/** Read every calculatedValue off a live SurveyJS model, keyed by name. */
export function metricsFromModel(model: Model): Metrics {
  return Object.fromEntries(model.calculatedValues.map((cv) => [cv.name, cv.value]))
}

/**
 * Evaluate the survey's calculatedValues against a set of answers by loading
 * them into a fresh SurveyJS model. Fallback for responses without stored metrics.
 */
export function evaluateMetrics(surveyJson: SurveyJson, answers: Answers): MetricResult[] {
  const defs = calculatedValueDefs(surveyJson)
  if (defs.length === 0) return []

  const model = new Model(surveyJson)
  model.data = answers
  const values = metricsFromModel(model)

  return defs.map((def) => ({
    name: def.name,
    label: labelOf(def),
    value: def.name in values ? values[def.name] : answers[def.name],
  }))
}

/** Label stored metrics using the survey's calculatedValues definitions. */
export function metricsFromStored(surveyJson: SurveyJson, stored: Metrics): MetricResult[] {
  return calculatedValueDefs(surveyJson)
    .filter((def) => def.name in stored)
    .map((def) => ({ name: def.name, label: labelOf(def), value: stored[def.name] }))
}

/** Stored metrics when present, otherwise evaluated from the answers. */
export function resolveMetrics(
  surveyJson: SurveyJson,
  answers: Answers,
  stored: Metrics | undefined,
): MetricResult[] {
  if (stored && Object.keys(stored).length > 0) return metricsFromStored(surveyJson, stored)
  return evaluateMetrics(surveyJson, answers)
}
