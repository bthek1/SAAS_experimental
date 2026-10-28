import { beforeEach, describe, expect, it, vi } from "vitest"
import {
  createQuestionnaire,
  deleteQuestionnaire,
  getQuestionnaire,
  getQuestionnaireByToken,
  getQuestionnaires,
  submitQuestionnaire,
  updateQuestionnaire,
} from "./questionnaires"

vi.mock("./client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}))

const { apiClient } = await import("./client")

describe("questionnaires API", () => {
  beforeEach(() => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: "get" })
    vi.mocked(apiClient.post).mockResolvedValue({ data: "post" })
    vi.mocked(apiClient.patch).mockResolvedValue({ data: "patch" })
    vi.mocked(apiClient.delete).mockResolvedValue({ data: undefined })
  })

  it("lists questionnaires", async () => {
    expect(await getQuestionnaires()).toBe("get")
    expect(apiClient.get).toHaveBeenCalledWith("/api/questionnaires/")
  })

  it("gets one questionnaire", async () => {
    await getQuestionnaire("q-1")
    expect(apiClient.get).toHaveBeenCalledWith("/api/questionnaires/q-1/")
  })

  it("creates a questionnaire", async () => {
    expect(await createQuestionnaire({ questionnaireTypeId: "qt-1", name: "A" })).toBe("post")
    expect(apiClient.post).toHaveBeenCalledWith("/api/questionnaires/", {
      questionnaireTypeId: "qt-1",
      name: "A",
    })
  })

  it("renames a questionnaire", async () => {
    await updateQuestionnaire("q-1", { name: "B" })
    expect(apiClient.patch).toHaveBeenCalledWith("/api/questionnaires/q-1/", { name: "B" })
  })

  it("deletes a questionnaire", async () => {
    await deleteQuestionnaire("q-1")
    expect(apiClient.delete).toHaveBeenCalledWith("/api/questionnaires/q-1/")
  })

  it("fetches by share token", async () => {
    await getQuestionnaireByToken("tok")
    expect(apiClient.get).toHaveBeenCalledWith("/api/questionnaires/by-token/tok/")
  })

  it("submits answers with metrics defaulting to an empty object", async () => {
    expect(await submitQuestionnaire("tok", { answers: { q1: 1 } })).toBe("patch")
    expect(apiClient.patch).toHaveBeenCalledWith("/api/questionnaires/by-token/tok/submit/", {
      answers: { q1: 1 },
      metrics: {},
    })
  })
})
