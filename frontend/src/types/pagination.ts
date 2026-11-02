/** A page of a list endpoint (DRF PageNumberPagination, #10). */
export interface Paginated<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}
