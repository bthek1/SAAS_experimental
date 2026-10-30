import { beforeEach, describe, expect, it } from "vitest"
import { hasAccessToken, safeRedirect } from "./auth"

describe("hasAccessToken", () => {
  beforeEach(() => localStorage.clear())

  it("is false without a token", () => {
    expect(hasAccessToken()).toBe(false)
  })

  it("is true with a token", () => {
    localStorage.setItem("access_token", "abc")
    expect(hasAccessToken()).toBe(true)
  })
})

describe("safeRedirect", () => {
  it("keeps same-origin paths", () => {
    expect(safeRedirect("/questionnaires?x=1")).toBe("/questionnaires?x=1")
  })

  it.each([undefined, "", "https://evil.example", "//evil.example", "javascript:alert(1)"])(
    "falls back for %s",
    (target) => {
      expect(safeRedirect(target)).toBe("/dashboard")
    },
  )
})
