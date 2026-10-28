import { AxiosError, AxiosHeaders } from "axios"
import { describe, expect, it } from "vitest"
import { apiErrorMessage, isConflict } from "./apiErrors"

function axiosError(status: number, data: unknown) {
  return new AxiosError("fail", "ERR", undefined, undefined, {
    status,
    statusText: "",
    data,
    headers: {},
    config: { headers: new AxiosHeaders() },
  })
}

describe("apiErrorMessage", () => {
  it("uses the API detail", () => {
    expect(apiErrorMessage(axiosError(409, { detail: "In use" }), "x")).toBe("In use")
  })

  it("falls back for other errors", () => {
    expect(apiErrorMessage(axiosError(500, "<html>"), "Try again")).toBe("Try again")
    expect(apiErrorMessage(new Error("boom"), "Try again")).toBe("Try again")
  })
})

describe("isConflict", () => {
  it("detects 409", () => {
    expect(isConflict(axiosError(409, {}))).toBe(true)
    expect(isConflict(axiosError(400, {}))).toBe(false)
    expect(isConflict(new Error())).toBe(false)
  })
})
