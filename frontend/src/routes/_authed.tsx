import { createFileRoute, Outlet, redirect } from "@tanstack/react-router"
import { hasAccessToken } from "@/lib/auth"

/**
 * Pathless layout for every route that needs a logged-in user. Anonymous
 * visitors are sent to /login and returned here after signing in.
 */
export const Route = createFileRoute("/_authed")({
  beforeLoad: ({ location }) => {
    if (!hasAccessToken()) {
      throw redirect({ to: "/login", search: { redirect: location.href } })
    }
  },
  component: Outlet,
})
