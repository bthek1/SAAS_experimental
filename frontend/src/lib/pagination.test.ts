import { describe, expect, it } from "vitest"
import { pageAfterDelete, pageSearch } from "./pagination"

describe("pageSearch", () => {
  it("accepts a page number", () => {
    expect(pageSearch.parse({ page: 3 })).toEqual({ page: 3 })
  })

  it("falls back to page 1 (undefined) for a bad value", () => {
    expect(pageSearch.parse({ page: 0 })).toEqual({ page: undefined })
    expect(pageSearch.parse({ page: "x" })).toEqual({ page: undefined })
    expect(pageSearch.parse({})).toEqual({ page: undefined })
  })
})

describe("pageAfterDelete", () => {
  it("stays on the page while items remain", () => {
    expect(pageAfterDelete(2, 3)).toBe(2)
  })

  it("steps back after deleting the last item on a later page", () => {
    expect(pageAfterDelete(3, 1)).toBe(2)
  })

  it("never goes below page 1", () => {
    expect(pageAfterDelete(1, 1)).toBe(1)
  })
})
