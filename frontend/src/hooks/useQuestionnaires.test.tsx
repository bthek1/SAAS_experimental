import { renderHook, waitFor } from "@testing-library/react"
import { http, HttpResponse } from "msw"
import { describe, expect, it } from "vitest"
import { queryKeys } from "@/api/queryKeys"
import { useCreateBattery } from "@/hooks/useBatteries"
import { API } from "@/test/handlers"
import { publicQuestionnaire } from "@/test/questionnaireFixtures"
import { createQueryWrapper } from "@/test/queryWrapper"
import { server } from "@/test/server"
import { useQuestionnaireByToken, useSubmitQuestionnaire } from "./useQuestionnaires"

describe("useQuestionnaireByToken", () => {
  it("loads the public payload", async () => {
    const { wrapper } = createQueryWrapper()
    const { result } = renderHook(() => useQuestionnaireByToken("tok"), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual(publicQuestionnaire)
  })
})

describe("useSubmitQuestionnaire", () => {
  it("caches the submitted payload and refreshes battery status", async () => {
    const { wrapper, queryClient } = createQueryWrapper()
    queryClient.setQueryData(queryKeys.batteries.byToken("bat"), { isComplete: false })
    const { result } = renderHook(() => useSubmitQuestionnaire("tok"), { wrapper })
    await result.current.mutateAsync({ answers: { q1: 1 }, metrics: {} })
    expect(
      queryClient.getQueryData<typeof publicQuestionnaire>(queryKeys.questionnaires.byToken("tok"))
        ?.submittedAt,
    ).not.toBeNull()
    expect(queryClient.getQueryState(queryKeys.batteries.byToken("bat"))?.isInvalidated).toBe(true)
  })

  it("rejects with 409 on a second submit", async () => {
    server.use(
      http.patch(`${API}/api/questionnaires/by-token/:token/submit/`, () =>
        HttpResponse.json({ detail: "Already submitted." }, { status: 409 }),
      ),
    )
    const { wrapper } = createQueryWrapper()
    const { result } = renderHook(() => useSubmitQuestionnaire("tok"), { wrapper })
    await expect(result.current.mutateAsync({ answers: {} })).rejects.toMatchObject({
      response: { status: 409 },
    })
  })
})

describe("useCreateBattery", () => {
  it("invalidates batteries and questionnaires", async () => {
    const { wrapper, queryClient } = createQueryWrapper()
    queryClient.setQueryData(queryKeys.batteries.all, [])
    queryClient.setQueryData(queryKeys.questionnaires.all, [])
    const { result } = renderHook(() => useCreateBattery(), { wrapper })
    await result.current.mutateAsync({ batteryTypeId: "bt-1" })
    expect(queryClient.getQueryState(queryKeys.batteries.all)?.isInvalidated).toBe(true)
    expect(queryClient.getQueryState(queryKeys.questionnaires.all)?.isInvalidated).toBe(true)
  })
})
