import { act, renderHook } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { useSurveyJsonDraft } from "./useSurveyJsonDraft"

const initial = { pages: [{ name: "p1", elements: [] }] }

describe("useSurveyJsonDraft", () => {
  it("starts from the formatted initial JSON", () => {
    const { result } = renderHook(() => useSurveyJsonDraft(initial))
    expect(result.current.text).toBe(JSON.stringify(initial, null, 2))
    expect(result.current.json).toEqual(initial)
    expect(result.current.dirty).toBe(false)
  })

  it("parses valid text into json", () => {
    const { result } = renderHook(() => useSurveyJsonDraft(initial))
    act(() => result.current.setFromText('{"title":"T"}'))
    expect(result.current.json).toEqual({ title: "T" })
    expect(result.current.error).toBeNull()
    expect(result.current.dirty).toBe(true)
  })

  it("keeps the last valid json when text is broken", () => {
    const { result } = renderHook(() => useSurveyJsonDraft(initial))
    act(() => result.current.setFromText("{ nope"))
    expect(result.current.error).toBe("Invalid JSON")
    expect(result.current.json).toEqual(initial)
    expect(result.current.text).toBe("{ nope")
  })

  it("rejects non-object JSON", () => {
    const { result } = renderHook(() => useSurveyJsonDraft(initial))
    act(() => result.current.setFromText("[1,2]"))
    expect(result.current.error).toMatch(/must be a JSON object/)
  })

  it("visual edits rewrite the text and clear errors", () => {
    const { result } = renderHook(() => useSurveyJsonDraft(initial))
    act(() => result.current.setFromText("{ nope"))
    act(() => result.current.setFromJson({ title: "Visual" }))
    expect(result.current.text).toBe(JSON.stringify({ title: "Visual" }, null, 2))
    expect(result.current.error).toBeNull()
  })

  it("markSaved clears dirty", () => {
    const { result } = renderHook(() => useSurveyJsonDraft(initial))
    act(() => result.current.setFromJson({}))
    act(() => result.current.markSaved())
    expect(result.current.dirty).toBe(false)
  })
})
