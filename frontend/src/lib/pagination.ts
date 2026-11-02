import { z } from "zod"

/** `?page=` on a paginated index route. A bad value falls back to page 1. */
export const pageSearch = z.object({
  page: z.number().int().min(1).optional().catch(undefined),
})

/**
 * The page to show after deleting one of `itemsOnPage` items on `page`.
 * Deleting the last item on a page past the first steps back, because the
 * server answers 404 for a page past the end.
 */
export function pageAfterDelete(page: number, itemsOnPage: number): number {
  return itemsOnPage <= 1 && page > 1 ? page - 1 : page
}
