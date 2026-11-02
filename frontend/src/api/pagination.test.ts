import { http } from "msw"
import { describe, expect, it } from "vitest"
import { API, paginated } from "@/test/handlers"
import { server } from "@/test/server"
import { getAllPages, getPage } from "./pagination"

const items = Array.from({ length: 230 }, (_, i) => ({ id: i }))

describe("getAllPages", () => {
  it("follows `next` until every item is loaded, 100 at a time", async () => {
    const pages: string[] = []
    server.use(
      http.get(`${API}/api/things/`, ({ request }) => {
        pages.push(new URL(request.url).searchParams.toString())
        return paginated(items, request)
      }),
    )
    expect(await getAllPages("/api/things/", { kind: "x" })).toEqual(items)
    expect(pages).toEqual([
      "kind=x&page=1&page_size=100",
      "kind=x&page=2&page_size=100",
      "kind=x&page=3&page_size=100",
    ])
  })

  it("stops after one request when everything fits", async () => {
    let calls = 0
    server.use(
      http.get(`${API}/api/things/`, ({ request }) => {
        calls += 1
        return paginated(items.slice(0, 3), request)
      }),
    )
    expect(await getAllPages("/api/things/")).toHaveLength(3)
    expect(calls).toBe(1)
  })
})

describe("getPage", () => {
  it("returns one page with its count", async () => {
    server.use(http.get(`${API}/api/things/`, ({ request }) => paginated(items, request)))
    const page = await getPage<{ id: number }>("/api/things/", 2)
    expect(page.count).toBe(230)
    expect(page.results[0]).toEqual({ id: 25 })
    expect(page.previous).toContain("page=1")
  })
})

