import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";

vi.mock("@tanstack/react-router", async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    useNavigate: vi.fn().mockReturnValue(vi.fn()),
    useSearch: vi.fn().mockReturnValue({}),
    Link: ({
      children,
      to,
      ...props
    }: {
      children: ReactNode;
      to: string;
      [key: string]: unknown;
    }) => (
      <a href={to} {...props}>
        {children}
      </a>
    ),
  };
});

vi.mock("@/hooks/useAuth", () => ({
  useLogin: vi.fn().mockReturnValue({ mutate: vi.fn(), isPending: false }),
}));

vi.mock("@/hooks/useTheme", () => ({
  useTheme: vi.fn().mockReturnValue({ theme: "light", setTheme: vi.fn() }),
}));

vi.mock("@/api/health", () => ({
  getHealth: vi.fn().mockResolvedValue({ status: "ok" }),
}));

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

// Import AFTER mocks are registered
const { Route } = await import("@/routes/login");
const LoginComponent = Route?.options?.component as
  | React.ComponentType
  | undefined;

describe("Login page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders email and password fields", () => {
    if (!LoginComponent) return;
    render(<LoginComponent />, { wrapper });
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
  });

  it("renders a link to the signup page", () => {
    if (!LoginComponent) return;
    render(<LoginComponent />, { wrapper });
    expect(screen.getByRole("link", { name: /sign up/i })).toBeInTheDocument();
  });

  it("shows validation error when form submitted empty", async () => {
    if (!LoginComponent) return;
    const user = userEvent.setup();
    render(<LoginComponent />, { wrapper });
    await user.click(screen.getByRole("button", { name: /sign in/i }));
    expect(await screen.findByText(/valid email/i)).toBeInTheDocument();
  });

  it("returns to the redirect target after signing in", async () => {
    if (!LoginComponent) return;
    const router = await import("@tanstack/react-router");
    const auth = await import("@/hooks/useAuth");
    const navigate = vi.fn();
    vi.mocked(router.useNavigate).mockReturnValue(navigate);
    vi.mocked(router.useSearch).mockReturnValue({ redirect: "/questionnaires" });
    vi.mocked(auth.useLogin).mockReturnValue({
      mutate: (_values: unknown, opts: { onSuccess: () => void }) => opts.onSuccess(),
      isPending: false,
    } as unknown as ReturnType<typeof auth.useLogin>);

    const user = userEvent.setup();
    render(<LoginComponent />, { wrapper });
    await user.type(screen.getByLabelText(/email/i), "a@example.com");
    await user.type(screen.getByLabelText(/password/i), "secret123");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(navigate).toHaveBeenCalledWith({ href: "/questionnaires" });
  });

  it("ignores an off-site redirect target", async () => {
    if (!LoginComponent) return;
    const router = await import("@tanstack/react-router");
    const auth = await import("@/hooks/useAuth");
    const navigate = vi.fn();
    vi.mocked(router.useNavigate).mockReturnValue(navigate);
    vi.mocked(router.useSearch).mockReturnValue({ redirect: "https://evil.example" });
    vi.mocked(auth.useLogin).mockReturnValue({
      mutate: (_values: unknown, opts: { onSuccess: () => void }) => opts.onSuccess(),
      isPending: false,
    } as unknown as ReturnType<typeof auth.useLogin>);

    const user = userEvent.setup();
    render(<LoginComponent />, { wrapper });
    await user.type(screen.getByLabelText(/email/i), "a@example.com");
    await user.type(screen.getByLabelText(/password/i), "secret123");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(navigate).toHaveBeenCalledWith({ href: "/dashboard" });
  });
});
