# frontend/AGENTS.md

The React SPA. Read with the root [`AGENTS.md`](../AGENTS.md).

## Commands

npm runs only in `frontend/` (the only `package.json` and `package-lock.json`). Never run `npm` or `npx` from the
repo root. Run tests under the test lock (root `AGENTS.md`, "Working alongside other agents").

| Task | Command |
|---|---|
| Unit tests | `npx vitest run --reporter=dot <paths>` (all: `just fe-test`) |
| Lint | `npx eslint <paths>` (all: `just fe-lint`) |
| Type-check + build | `just fe-build` |
| Vitest UI | `npm run test:ui` |
| e2e (Playwright, mocked) | `npm run e2e -- --workers=1` (first time: `npx playwright install chromium`) |
| Playwright UI / report | `npm run e2e:ui` / `npx playwright show-report` |
| e2e against a real backend | `npm run e2e:integration -- --workers=1` (needs `uv sync` in `backend/`, the .NET SDK and Docker) |
| Add a shadcn component | `npx shadcn@latest add <component>` |

## Stack

React 19, TypeScript ~6.0 (strict), Vite 8, TanStack Router, TanStack Query v5, Axios, Tailwind CSS v4,
shadcn/ui (`base-nova` style on `@base-ui/react`), React Hook Form + Zod, Zustand + Immer, date-fns, ECharts,
react-markdown, SurveyJS (`survey-core` + `survey-react-ui`), Vitest 5 + Testing Library + MSW 3, Playwright,
ESLint 10. Node 24 LTS (`frontend/.nvmrc`; `engines` allows 22.12+, 24, 26+. Odd releases like 25 are
unsupported by Vitest 5). TypeScript stays on 6.0 until `typescript-eslint` supports 7 (it requires
`typescript <6.1`).

**Layout (`src/`):** `api/` (client, endpoint functions, `queryKeys.ts`), `components/` (`ui/`
for shadcn, `charts/`, `layout/`, one folder per feature), `hooks/`, `lib/`, `routes/`, `schemas/`, `store/`, `test/`,
`__tests__/routes/`, `types/`.

## Conventions

- Functional components only. No business logic in components; extract it to `src/hooks/`.
- All API calls go through `src/api/client.ts` (Axios with JWT header and silent 401 refresh).
- Server state lives only in TanStack Query. Query keys are constants in `src/api/queryKeys.ts`.
  Mutations invalidate the affected queries on success.
- Global UI state lives in Zustand stores in `src/store/`, one file per concern, with the `immer`
  middleware. Never put server data in Zustand. Local state uses `useState` / `useReducer`.
- Routing is file-based under `src/routes/`. Use TanStack Router's typed `useParams()` /
  `useSearch()`. Loaders prefetch with `context.queryClient.ensureQueryData(...)` (the
  `QueryClient` is router context, see `createRootRouteWithContext` in `__root.tsx`). Hooks export
  `queryOptions` factories (e.g. `questionnaireTypesQuery()`) for loaders to reuse.
- Pages that need a logged-in user go under `src/routes/_authed/` (pathless layout; its
  `beforeLoad` redirects to `/login?redirect=…`). Pages without the app shell are listed in
  `src/components/layout/publicPaths.ts`. Route components are code-split (`autoCodeSplitting`,
  disabled under Vitest).
- **Lists are paginated** (#10). API modules export `get<X>Page(page)` (one page,
  `Paginated<T>`) and, for pickers, a full list through `getAllPages()` (`src/api/pagination.ts`).
  Index routes use `pageSearch` (`src/lib/pagination.ts`) for `?page=`, `loaderDeps`, the
  `Pager` component, and `pageAfterDelete()`. Page query keys sit under the resource's `all` key,
  so existing invalidations cover them. MSW handlers return `paginated(items, request)`.
- Forms use React Hook Form + `zodResolver`, with schemas in `src/schemas/` (one file per
  domain) and the shadcn `Form`, `FormField`, `FormItem`, `FormMessage` primitives.
- No `any`. API response types go in `src/types/`, matching the API contract.
- Import with the `@/` alias (`src/`). No relative `../../` imports across feature boundaries.
- Env vars are prefixed `VITE_` and read via `import.meta.env.VITE_*`. Vite loads them from the
  repo-root `.env` (`envDir` in `vite.config.ts`). Only `VITE_` vars reach the browser bundle.
- `src/routes/_authed/service-interface.tsx` (`/service-interface`, #27) explains how the services talk and is
  hand-written; see "Service boundary" in `backend/AGENTS.md`. The `/load-tests` page is copied by hand from
  `loadtest/baselines/`; see `loadtest/AGENTS.md`.

## Styling

- Tailwind v4 is CSS-first (`@import "tailwindcss"` in `src/index.css`). There is no
  `tailwind.config.js`.
- Merge conditional classes with `cn()` from `src/lib/utils.ts`.
- Theme through the shadcn CSS variables, not arbitrary Tailwind values.
- Do not hand-edit the generated files in `src/components/ui/`.

## Base UI gotchas (`@base-ui/react`, not Radix)

1. No `asChild` and no `<Slot>`. Compose with the `render` prop:
   `<Button render={<Link to="/x" />} />`.
2. No `forwardRef`. React 19 passes `ref` as a normal prop, so `ui/` wrappers spread `{...props}`
   onto the primitive. This is what lets RHF's `{...field}` (which carries a `ref`) bind to
   `<Input>`.
3. `FormControl` merges ARIA/id props onto its child with `useRender`, so it must wrap exactly
   one React element: `<FormControl><Input {...field} /></FormControl>`.

## Utilities

- Dates: always through the `src/lib/date.ts` wrappers, never `date-fns` directly in components.
- Charts: ECharts only, through the lazy-loaded `src/components/charts/EChart.tsx` wrapper (keep
  it code-split, as `ChartCard` does). Do not add another chart library. For done / waiting charts, use
  `useChartPalette`. For separate series, use `useSeriesPalette` (`--series-*` in `index.css`), and give each
  series a fixed slot so it keeps its colour. Keep that order: it is what keeps neighbouring series distinct
  under colour blindness. Never use two y-axes.
- Markdown / LLM output: render with `src/components/Markdown.tsx`.
- Surveys: render with `src/components/survey/SurveyRenderer.tsx`. It maps SurveyJS's CSS
  variables onto the shadcn tokens. Read a submitted response against its
  `questionnaireJsonSnapshot` (`src/lib/responses.ts`), not the live type.

## Testing

- Environment is `happy-dom`. `src/test/setup.ts` loads jest-dom (`@testing-library/jest-dom/vitest`,
  which types the matchers for Vitest), starts the MSW server with `onUnhandledFrame: "bypass"`, and
  polyfills `localStorage` (Node 25+ ships a stub that shadows the DOM one).
- Vitest 5 defaults to `clearMocks: true`: mock call history is cleared before every test. Calls
  made in `beforeAll` (e.g. at module import) are gone by the time a test runs, so record what you
  need inside `beforeAll` (see `src/api/client.test.ts`).
- Mock HTTP with MSW (default handlers in `src/test/handlers.ts`, override with
  `server.use(...)`) or mock Axios at module level. Never make real HTTP calls. `vite.config.ts`
  sets happy-dom's `disableSameOriginPolicy`; without it every request starts with a CORS
  preflight that no handler answers, so MSW silently passes it through.
- Route tests can render the real router at a path with `renderRoute(path, { authed })` from
  `src/test/renderRoute.tsx` (loaders, guards and links all run).
- Co-locate tests with the code they test (`Button.test.tsx` next to `button.tsx`). Route tests
  live in `src/__tests__/routes/`. Zod schemas get plain unit tests.
- happy-dom has no canvas, so route tests mock `echarts-for-react` and test the option objects in `lib/`.
  What needs a real canvas (chart size, tooltips, ECharts' aria label) goes in Playwright, as
  `e2e/load-tests.spec.ts` does.
- End-to-end tests use Playwright and live in `frontend/e2e/*.spec.ts` (outside `src/`, excluded
  from Vitest in `vite.config.ts`). `playwright.config.ts` starts Vite on :5174, or reuses a dev
  server already running there. Specs mock the backend with `page.route` on URLs whose pathname
  starts with `/api/` (a `**/api/**` glob also matches Vite's `/src/api/*.ts` modules), so they run
  without Docker. Prefer role-based locators (`getByRole`, `getByLabel`). Behaviour that happy-dom
  can test belongs in Vitest, not Playwright.
- Full-stack specs live in `frontend/e2e/integration/` and run only with `npm run e2e:integration`
  (`playwright.integration.config.ts`; the mocked config ignores that folder). That config starts
  its own gateway router on :8015, `catalog` on :8016 (SQLite, deleted and re-migrated every run),
  `instances` on .NET on :8017 (`SETTINGS=e2e`, on a throwaway Postgres in Docker on 127.0.0.1:5447 that
  stops with the run, #44) and Vite on :5184 pointed at the router, and never reuses running servers, because a
  reused backend would carry data over from an earlier run. It stops them when the run ends, and never touches
  the dev stack. Each test registers its own user with a unique email, so tests do not share state. Use them for
  the API contract (auth, real responses); keep UI-only checks in the mocked suite.
  `e2e/integration/helpers.ts` has `registerUser` / `loginAs` (log in by storing the JWT, skipping
  the form), an owner-side `api()` caller, and a scored test survey with `answerScoredSurvey`.
  Test anonymous respondents in a separate `browser.newContext()` so no token leaks in.
