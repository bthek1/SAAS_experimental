import { isAxiosError } from "axios"

/**
 * A user-facing message for a failed API call: the API's `detail` when it
 * sent one (e.g. 409 "in use"), otherwise `fallback`.
 */
export function apiErrorMessage(error: unknown, fallback: string): string {
  if (isAxiosError<{ detail?: unknown }>(error)) {
    const detail = error.response?.data?.detail
    if (typeof detail === "string" && detail) return detail
  }
  return fallback
}

export function isConflict(error: unknown): boolean {
  return isAxiosError(error) && error.response?.status === 409
}
