import { apiClient } from "@/api/client"
import type { Paginated } from "@/types/pagination"

/** The server's default page size (core/pagination.py). */
export const PAGE_SIZE = 25
/** The largest page the server returns. */
const MAX_PAGE_SIZE = 100

/** One page of a list endpoint. */
export async function getPage<T>(
  url: string,
  page: number,
  params: object = {},
): Promise<Paginated<T>> {
  const { data } = await apiClient.get<Paginated<T>>(url, { params: { ...params, page } })
  return data
}

/**
 * Every item of a list endpoint, page by page (largest pages, until `next` is
 * null). For pickers and summaries that need the whole list.
 */
export async function getAllPages<T>(url: string, params: object = {}): Promise<T[]> {
  const items: T[] = []
  for (let page = 1; ; page += 1) {
    const { data } = await apiClient.get<Paginated<T>>(url, {
      params: { ...params, page, page_size: MAX_PAGE_SIZE },
    })
    items.push(...data.results)
    if (!data.next) return items
  }
}
