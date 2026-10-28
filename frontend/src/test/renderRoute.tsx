import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { createMemoryHistory, createRouter, RouterProvider } from "@tanstack/react-router"
import { render } from "@testing-library/react"
import { routeTree } from "@/routeTree.gen"

/**
 * Render the real app router at `path`, with API calls served by MSW.
 * Pass `authed: false` to render as an anonymous visitor.
 */
export function renderRoute(path: string, { authed = true }: { authed?: boolean } = {}) {
  localStorage.clear()
  if (authed) localStorage.setItem("access_token", "test-token")
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const router = createRouter({
    routeTree,
    context: { queryClient },
    history: createMemoryHistory({ initialEntries: [path] }),
  })
  const utils = render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
  return { ...utils, router, queryClient }
}
