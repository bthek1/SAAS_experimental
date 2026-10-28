/** Whether an access token is stored. The API still decides if it is valid. */
export function hasAccessToken(): boolean {
  return !!localStorage.getItem("access_token")
}

/**
 * Only follow post-login redirects to same-origin paths, so a crafted
 * `/login?redirect=https://evil.example` link cannot send users elsewhere.
 */
export function safeRedirect(target: string | undefined, fallback = "/demo/chart"): string {
  if (!target || !target.startsWith("/") || target.startsWith("//")) return fallback
  return target
}
