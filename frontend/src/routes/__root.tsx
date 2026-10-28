import type { QueryClient } from "@tanstack/react-query";
import {
  createRootRouteWithContext,
  Outlet,
  useRouterState,
} from "@tanstack/react-router";
import { AppLayout } from "@/components/layout/AppLayout";
import { isPublicPath } from "@/components/layout/publicPaths";

export interface RouterContext {
  queryClient: QueryClient;
}

export const Route = createRootRouteWithContext<RouterContext>()({
  component: RootComponent,
});

function RootComponent() {
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  if (isPublicPath(pathname)) return <Outlet />;
  return <AppLayout />;
}
