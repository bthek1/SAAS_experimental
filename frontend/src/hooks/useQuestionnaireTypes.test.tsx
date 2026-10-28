import { renderHook, waitFor } from "@testing-library/react"
import { http, HttpResponse } from "msw"
import { describe, expect, it } from "vitest"
import { queryKeys } from "@/api/queryKeys"
import { API } from "@/test/handlers"
import { questionnaireType } from "@/test/questionnaireFixtures"
import { createQueryWrapper } from "@/test/queryWrapper"
import { server } from "@/test/server"
import {
  useCreateQuestionnaireType,
  useDeleteQuestionnaireType,
  useQuestionnaireType,
  useQuestionnaireTypes,
  useUpdateQuestionnaireType,
} from "./useQuestionnaireTypes"

describe("useQuestionnaireTypes", () => {
  it("loads the list", async () => {
    const { wrapper } = createQueryWrapper()
    const { result } = renderHook(() => useQuestionnaireTypes(), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual([questionnaireType])
  })

  it("loads one type", async () => {
    const { wrapper } = createQueryWrapper()
    const { result } = renderHook(() => useQuestionnaireType("qt-1"), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.title).toBe("Wellbeing")
  })

  it("surfaces API errors", async () => {
    server.use(
      http.get(`${API}/api/questionnaire-types/`, () => new HttpResponse(null, { status: 500 })),
    )
    const { wrapper } = createQueryWrapper()
    const { result } = renderHook(() => useQuestionnaireTypes(), { wrapper })
    await waitFor(() => expect(result.current.isError).toBe(true))
  })

  it("create invalidates the list", async () => {
    const { wrapper, queryClient } = createQueryWrapper()
    queryClient.setQueryData(queryKeys.questionnaireTypes.all, [])
    const { result } = renderHook(() => useCreateQuestionnaireType(), { wrapper })
    const created = await result.current.mutateAsync({ title: "New" })
    expect(created.title).toBe("New")
    expect(queryClient.getQueryState(queryKeys.questionnaireTypes.all)?.isInvalidated).toBe(true)
  })

  it("update stores the result and invalidates the list", async () => {
    const { wrapper, queryClient } = createQueryWrapper()
    queryClient.setQueryData(queryKeys.questionnaireTypes.all, [questionnaireType])
    const { result } = renderHook(() => useUpdateQuestionnaireType("qt-1"), { wrapper })
    await result.current.mutateAsync({ title: "Renamed" })
    expect(
      queryClient.getQueryData<typeof questionnaireType>(queryKeys.questionnaireTypes.detail("qt-1"))
        ?.title,
    ).toBe("Renamed")
    expect(queryClient.getQueryState(queryKeys.questionnaireTypes.all)?.isInvalidated).toBe(true)
  })

  it("delete reports a 409 when the type is in use", async () => {
    server.use(
      http.delete(`${API}/api/questionnaire-types/:id/`, () =>
        HttpResponse.json({ detail: "in use" }, { status: 409 }),
      ),
    )
    const { wrapper } = createQueryWrapper()
    const { result } = renderHook(() => useDeleteQuestionnaireType(), { wrapper })
    await expect(result.current.mutateAsync("qt-1")).rejects.toMatchObject({
      response: { status: 409 },
    })
  })
})
