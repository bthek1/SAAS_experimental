/**
 * Pure helpers for applying targeted patches to a SurveyJS JSON object.
 * Every function returns a new object; the original is never mutated.
 * These are the building blocks for the visual editor's "surgical edit" model:
 * a user action produces one small patch to the JSON rather than a full rebuild.
 */

export type JsonPath = (string | number)[]

type Container = Record<string, unknown> | unknown[]

function asContainer(value: unknown): Container {
  return typeof value === "object" && value !== null ? (value as Container) : {}
}

/**
 * Return a copy of `json` with the value at `path` replaced by `value`.
 * Only the objects along the path are copied; everything else is shared.
 * An empty path replaces the root.
 *
 * @example
 * patchSurveyJson(json, ["pages", 0, "elements", 1, "title"], "New title")
 */
export function patchSurveyJson<T>(json: T, path: JsonPath, value: unknown): T {
  if (path.length === 0) return value as T

  const [head, ...tail] = path
  const container = asContainer(json)

  if (Array.isArray(container)) {
    const copy = [...container]
    const index = head as number
    copy[index] = tail.length === 0 ? value : patchSurveyJson(copy[index] ?? {}, tail, value)
    return copy as T
  }

  const key = String(head)
  return {
    ...container,
    [key]: tail.length === 0 ? value : patchSurveyJson(container[key] ?? {}, tail, value),
  } as T
}

/** Read the value at a nested path, or `undefined` if any segment is missing. */
export function getNestedValue(obj: unknown, path: JsonPath): unknown {
  let current: unknown = obj
  for (const key of path) {
    if (current == null || typeof current !== "object") return undefined
    current = (current as Record<string | number, unknown>)[key]
  }
  return current
}

/**
 * Return a copy of `json` with the array at `arrayPath` spliced: `deleteCount`
 * items removed from `index`, then `items` inserted. Covers add, delete and reorder.
 *
 * @example
 * spliceJsonArray(json, ["pages", 0, "elements"], 2, 1) // delete element 2
 */
export function spliceJsonArray<T>(
  json: T,
  arrayPath: JsonPath,
  index: number,
  deleteCount: number,
  ...items: unknown[]
): T {
  const current = getNestedValue(json, arrayPath)
  const arr = Array.isArray(current) ? [...current] : []
  arr.splice(index, deleteCount, ...items)
  return patchSurveyJson(json, arrayPath, arr)
}
