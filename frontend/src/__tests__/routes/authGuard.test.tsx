import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  createMemoryHistory,
  createRouter,
  RouterProvider,
} from "@tanstack/react-router";
import { render, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { routeTree } from "@/routeTree.gen";

function renderAt(path: string) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const router = createRouter({
    routeTree,
    context: { queryClient },
    history: createMemoryHistory({ initialEntries: [path] }),
  });
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return router;
}

describe("auth guard", () => {
  beforeEach(() => localStorage.clear());

  it("redirects anonymous user to /login", async () => {
    const router = renderAt("/dashboard");
    await waitFor(() =>
      expect(router.state.location.pathname).toBe("/login"),
    );
    expect(router.state.location.search).toEqual({ redirect: "/dashboard" });
  });

  it("lets a user with a token through", async () => {
    localStorage.setItem("access_token", "token");
    const router = renderAt("/dashboard");
    await waitFor(() => expect(router.state.status).toBe("idle"));
    expect(router.state.location.pathname).toBe("/dashboard");
  });

  it("leaves public pages alone", async () => {
    const router = renderAt("/signup");
    await waitFor(() => expect(router.state.status).toBe("idle"));
    expect(router.state.location.pathname).toBe("/signup");
  });
});
