import { beforeEach, describe, expect, it, vi } from "vitest"
import { createBattery, deleteBattery, getBatteries, getBattery, getBatteryByToken } from "./batteries"
import {
  createBatteryType,
  deleteBatteryType,
  getBatteryType,
  getBatteryTypes,
  updateBatteryType,
} from "./batteryTypes"
import {
  createQuestionnaireType,
  deleteQuestionnaireType,
  getQuestionnaireType,
  getQuestionnaireTypes,
  updateQuestionnaireType,
} from "./questionnaireTypes"

vi.mock("./client", () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}))

const { apiClient } = await import("./client")

beforeEach(() => {
  for (const method of ["get", "post", "patch", "delete"] as const) {
    vi.mocked(apiClient[method]).mockResolvedValue({ data: method })
  }
})

describe("questionnaire types API", () => {
  it("calls the expected endpoints", async () => {
    await getQuestionnaireTypes()
    await getQuestionnaireType("qt-1")
    await createQuestionnaireType({ title: "T" })
    await updateQuestionnaireType("qt-1", { title: "U" })
    await deleteQuestionnaireType("qt-1")
    expect(apiClient.get).toHaveBeenNthCalledWith(1, "/api/questionnaire-types/")
    expect(apiClient.get).toHaveBeenNthCalledWith(2, "/api/questionnaire-types/qt-1/")
    expect(apiClient.post).toHaveBeenCalledWith("/api/questionnaire-types/", { title: "T" })
    expect(apiClient.patch).toHaveBeenCalledWith("/api/questionnaire-types/qt-1/", { title: "U" })
    expect(apiClient.delete).toHaveBeenCalledWith("/api/questionnaire-types/qt-1/")
  })
})

describe("battery types API", () => {
  it("calls the expected endpoints", async () => {
    await getBatteryTypes()
    await getBatteryType("bt-1")
    await createBatteryType({ title: "B", questionnaireTypeIds: ["qt-1"] })
    await updateBatteryType("bt-1", { questionnaireTypeIds: [] })
    await deleteBatteryType("bt-1")
    expect(apiClient.get).toHaveBeenNthCalledWith(1, "/api/battery-types/")
    expect(apiClient.get).toHaveBeenNthCalledWith(2, "/api/battery-types/bt-1/")
    expect(apiClient.post).toHaveBeenCalledWith("/api/battery-types/", {
      title: "B",
      questionnaireTypeIds: ["qt-1"],
    })
    expect(apiClient.patch).toHaveBeenCalledWith("/api/battery-types/bt-1/", {
      questionnaireTypeIds: [],
    })
    expect(apiClient.delete).toHaveBeenCalledWith("/api/battery-types/bt-1/")
  })
})

describe("batteries API", () => {
  it("calls the expected endpoints", async () => {
    await getBatteries()
    await getBattery("b-1")
    await getBatteryByToken("tok")
    await createBattery({ batteryTypeId: "bt-1", name: "N" })
    await deleteBattery("b-1")
    expect(apiClient.get).toHaveBeenNthCalledWith(1, "/api/batteries/")
    expect(apiClient.get).toHaveBeenNthCalledWith(2, "/api/batteries/b-1/")
    expect(apiClient.get).toHaveBeenNthCalledWith(3, "/api/batteries/by-token/tok/")
    expect(apiClient.post).toHaveBeenCalledWith("/api/batteries/", {
      batteryTypeId: "bt-1",
      name: "N",
    })
    expect(apiClient.delete).toHaveBeenCalledWith("/api/batteries/b-1/")
  })
})
