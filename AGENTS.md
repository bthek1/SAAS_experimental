# AGENTS.md

Rules for AI coding agents working in this repository. This is the only agent instruction file.
`CLAUDE.md` contains just `@AGENTS.md`. Do not add rules anywhere else.

---

## What this repo is

**test_repo**, a Django + DRF + React project created from the `django_react_template` starter,
as a decoupled monorepo:

- **`backend/`**: Django REST Framework API (Python 3.14, PostgreSQL, Celery + Redis)
- **`frontend/`**: React 19 SPA (TypeScript, Vite, TanStack Router + Query)
- **`infra/docker/`**: Dockerfiles and compose files for both halves

The backend exposes only `/api/` endpoints. The frontend consumes them over HTTP. The two halves
share no code. The API contract is the only interface between them.

Prefer documented conventions over one-off solutions.

---

## Where to look first

| You need | Read |
|----------|------|
| Setup, endpoints and request/response shapes | [`README.md`](README.md) (Quick Start, API) |
| Env vars | [`.env.example`](.env.example) |
| Day-to-day commands | [`justfile`](justfile) (`just`) and the Commands section below |
| JWT handling | `frontend/src/api/client.ts`, `SIMPLE_JWT` in `backend/core/settings/base.py` |
| Celery wiring | `backend/core/celery.py`, `backend/apps/utils/tasks.py`, `frontend/src/hooks/useTaskPoller.ts` |
| Active / finished plans | GitHub issues labelled `plan` (`gh issue list --label plan [--state closed]`) |

---

## Commands

The [`justfile`](justfile) holds only day-to-day commands. Run `just` to list them. Do not add
recipes for one-off or rare tasks; document the raw command here instead. A new recipe gets a
`# doc comment` line, then `[group('<area>')]` (`dev`, `docker`, `backend`, `frontend`,
`database`), then the recipe. The comment must come before the attribute, or `just` fails with
"Extraneous attribute". Helpers that other recipes call are marked `[private]`: hidden from the
list but still runnable by name.

```bash
just dev            # db + redis + celery (docker) + backend + frontend dev servers
just install        # uv sync + npm install
just up / down      # everything via docker compose
just compose <args> # any docker compose command against the dev stack

just be-migrate
just be-makemigrations <app>
just be-superuser   # from DJANGO_SUPERUSER_* in .env
just be-test        # pytest
just be-lint        # ruff check (note: pyproject sets fix = true, so this rewrites files)
just be-fmt         # ruff format

just fe-test        # vitest
just fe-lint        # eslint
just fe-build       # type-check + build

just db-reset       # DESTRUCTIVE: drops the Postgres volume, then re-migrates
```

Rarer tasks have no recipe. Run them directly:

| Task | Command |
|---|---|
| Backend dev server only | `just be-dev` (private helper, :8005) |
| Frontend dev server only | `just fe-dev` (private helper, :5174) |
| Backend coverage | `cd backend && uv run pytest --cov=apps --cov-report=term-missing` |
| Type check backend | `cd backend && uv run mypy .` |
| New Django app | `mkdir backend/apps/<name> && cd backend && uv run python manage.py startapp <name> apps/<name>` |
| Celery worker outside Docker | `cd backend && uv run celery -A core worker --loglevel=info` |
| Flower UI on :5555 | `cd backend && uv run celery -A core flower --port=5555` |
| Logs | `just compose logs -f <service>` |
| Rebuild images | `just compose build [service]` |
| psql shell | `just compose exec db psql -U appuser -d appdb` |
| Prod backend image | `docker build -f infra/docker/backend.prod.Dockerfile backend` |
| Vitest UI | `cd frontend && npm run test:ui` |
| Frontend e2e (Playwright) | `cd frontend && npm run e2e` (first time: `npx playwright install chromium`) |
| Playwright UI / report | `cd frontend && npm run e2e:ui` / `npx playwright show-report` |
| Frontend e2e against a real backend | `cd frontend && npm run e2e:integration` (needs `uv sync` in `backend/`, no Docker) |

### Local services and ports

Host ports are offset so they do not clash with a locally installed Postgres or Redis.

| Service | Host port | Notes |
|---|---|---|
| `db` | `5435` -> 5432 | Postgres 16 (`appuser` / `apppassword` / `appdb`) |
| `redis` | `6380` -> 6379 | Celery broker |
| `backend` | `8005` | Django dev server |
| `celery_worker`, `celery_beat` | none | beat uses `DatabaseScheduler` |
| `frontend` | `5174` | Vite dev server |
| e2e backend, e2e frontend | `8015`, `5184` | Started by `npm run e2e:integration` only (dev + 10) |

All Docker files live in `infra/docker/`: `docker-compose.yml` (dev stack),
`docker-compose.prod.yml` (gunicorn backend + db), `<service>[.prod].Dockerfile`, and a
`<name>.Dockerfile.dockerignore` next to each Dockerfile (BuildKit reads it in place of the build
context's `.dockerignore`). Paths in the compose files are relative to `infra/docker/`. The justfile
passes `-f infra/docker/docker-compose.yml -p <repo folder name>`. Run other compose commands
through `just compose <args>` rather than bare `docker compose`. Without `-p` the project is named
`docker` and you get a second set of containers and volumes. Put new Docker files in
`infra/docker/` as `<service>[.<variant>].Dockerfile` with a matching `.dockerignore`.
`backend/tests/test_infra_docker.py` enforces this layout.

Inside Compose, the `environment:` blocks set `DATABASE_URL` and `CELERY_BROKER_URL` to the
in-network hosts (`db:5432`, `redis:6379`). These override the `localhost` values in the root `.env`.

---

## Backend (`backend/`)

**Stack:** Python 3.14, Django 6.0, DRF, PostgreSQL (psycopg3), simplejwt, Celery + Redis
(`django-celery-results`, `django-celery-beat`), django-environ, uv, ruff, mypy, pytest +
pytest-django, factory-boy, faker, freezegun, pytest-mock.

Django is held at 6.0.x because `django-celery-beat` 2.9.0 requires `django<6.1`. Upgrade with
`uv lock --upgrade` from `backend/`; it moves to 6.1 once celery-beat allows it.

**Layout:** project package `core/` (settings, `celery.py`, `urls.py`), one app per domain under
`apps/<name>/`. Current apps: `accounts` (CustomUser, registration, `/me`) and `utils` (health
check and Celery task demo endpoints).

**Views and URLs**
- All endpoints are under `/api/`.
- Use class-based views (`APIView`, `generics.*`, `ViewSet`). `apps/utils/views.py` uses
  `@api_view` function views. It is a legacy exception. Do not copy it.
- Serializers go in `serializers.py`. Business logic goes in `services.py`, never in views or
  serializers.
- Use `get_object_or_404` and DRF exception handling, not try/except for HTTP errors.
- Return DRF `Response`, never `JsonResponse`.
- Default permission is `IsAuthenticated` (set in `REST_FRAMEWORK`). Mark public views explicitly.

**Models and data**
- UUID primary keys: `models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)`.
- `AUTH_USER_MODEL = "accounts.CustomUser"` (email is `USERNAME_FIELD`, no `username`). Always
  use `get_user_model()`, never import `User` directly.
- Avoid N+1 with `select_related` / `prefetch_related`. Use `bulk_create` / `bulk_update` for
  batches. Add indexes for frequently queried fields.
- All DB access goes through the ORM. Raw SQL only when unavoidable, and always parameterised.
- Run `makemigrations` with an explicit app name after model changes. Never edit or delete
  migration files by hand.
- Datetimes are timezone-aware (`USE_TZ = True`, `TIME_ZONE = "UTC"`). Use
  `django.utils.timezone.now()`, or `datetime.now(UTC)` outside the ORM. Never naive
  `datetime.now()` or `datetime.utcnow()`. Freeze time in tests with `freezegun`.

**Settings:** split into `core/settings/{base,dev,prod,test,e2e}.py`. `manage.py` defaults
`DJANGO_SETTINGS_MODULE` to `core.settings`, whose `__init__.py` picks `dev`, `test` or `prod` from
the `SETTINGS` env var (default `dev`). pytest uses `core.settings.test` directly. `e2e` extends
`test` with its own `e2e.sqlite3` and CORS for :5184; only the Playwright integration config
selects it (via `DJANGO_SETTINGS_MODULE`). All config comes from env vars via `django-environ`, loaded from the
repo-root `.env` (`base.py` reads `BASE_DIR.parent / ".env"`). Never hardcode secrets or
credentials. `DATABASE_URL` configures the database.

**Auth:** JWT via simplejwt. `POST /api/token/` and `POST /api/token/refresh/`.

**Celery**
- App in `core/celery.py`. Tasks in `apps/<app>/tasks.py`, auto-discovered, defined with
  `@shared_task`.
- Broker is Redis. Results are stored in Postgres (`CELERY_RESULT_BACKEND = "django-db"`).
  Periodic schedules are managed in Django admin.
- Test settings run tasks eagerly (`CELERY_TASK_ALWAYS_EAGER`), so tests need no broker.

**Testing:** `core.settings.test` uses SQLite and a fast password hasher. Fixtures go in
`conftest.py` (app-level or `backend/conftest.py`). App tests live in `apps/<name>/`.
Repo-level checks that are not tied to an app live in `backend/tests/` (both are in pytest's
`testpaths`). `tests/test_infra_docker.py` checks the `infra/docker/` layout. Its
`docker compose config` tests skip when Docker is not installed. Markers: `slow`, `integration`, `development`.

**API docs:** no OpenAPI generator is installed. The API table in `README.md` is the
hand-written contract.

---

## Frontend (`frontend/`)

**Stack:** React 19, TypeScript ~6.0 (strict), Vite 8, TanStack Router, TanStack Query v5, Axios,
Tailwind CSS v4, shadcn/ui (`base-nova` style on `@base-ui/react`), React Hook Form + Zod,
Zustand + Immer, date-fns, ECharts, react-markdown, Vitest 5 + Testing Library + MSW 3, Playwright,
ESLint 10. Node 24 LTS (`frontend/.nvmrc`; `engines` allows 22.12+, 24, 26+. Odd releases like 25 are
unsupported by Vitest 5).
TypeScript stays on 6.0 until `typescript-eslint` supports 7 (it requires `typescript <6.1`). npm runs only in `frontend/` (the only `package.json` and
`package-lock.json`). Never run `npm` or `npx` from the repo root.

**Layout (`src/`):** `api/` (client, endpoint functions, `queryKeys.ts`), `components/` (`ui/`
for shadcn, `charts/`, `layout/`), `hooks/`, `lib/`, `routes/`, `schemas/`, `store/`, `test/`,
`__tests__/routes/`, `types/`.

**Conventions**
- Functional components only. No business logic in components; extract it to `src/hooks/`.
- All API calls go through `src/api/client.ts` (Axios with JWT header and silent 401 refresh).
- Server state lives only in TanStack Query. Query keys are constants in `src/api/queryKeys.ts`.
  Mutations invalidate the affected queries on success.
- Global UI state lives in Zustand stores in `src/store/`, one file per concern, with the `immer`
  middleware. Never put server data in Zustand. Local state uses `useState` / `useReducer`.
- Routing is file-based under `src/routes/`. Use TanStack Router's typed `useParams()` /
  `useSearch()`. Loaders prefetch with `queryClient.ensureQueryData(...)`.
- Forms use React Hook Form + `zodResolver`, with schemas in `src/schemas/` (one file per
  domain) and the shadcn `Form`, `FormField`, `FormItem`, `FormMessage` primitives.
- No `any`. API response types go in `src/types/`, matching the API contract.
- Import with the `@/` alias (`src/`). No relative `../../` imports across feature boundaries.
- Env vars are prefixed `VITE_` and read via `import.meta.env.VITE_*`. Vite loads them from the
  repo-root `.env` (`envDir` in `vite.config.ts`). Only `VITE_` vars reach the browser bundle.

**Styling**
- Tailwind v4 is CSS-first (`@import "tailwindcss"` in `src/index.css`). There is no
  `tailwind.config.js`.
- Merge conditional classes with `cn()` from `src/lib/utils.ts`.
- Theme through the shadcn CSS variables, not arbitrary Tailwind values.
- Add shadcn components with `npx shadcn@latest add <component>`. Do not hand-edit the generated
  files in `src/components/ui/`.

**Base UI gotchas (`@base-ui/react`, not Radix)**
1. No `asChild` and no `<Slot>`. Compose with the `render` prop:
   `<Button render={<Link to="/x" />} />`.
2. No `forwardRef`. React 19 passes `ref` as a normal prop, so `ui/` wrappers spread `{...props}`
   onto the primitive. This is what lets RHF's `{...field}` (which carries a `ref`) bind to
   `<Input>`.
3. `FormControl` merges ARIA/id props onto its child with `useRender`, so it must wrap exactly
   one React element: `<FormControl><Input {...field} /></FormControl>`.

**Utilities**
- Dates: always through the `src/lib/date.ts` wrappers, never `date-fns` directly in components.
- Charts: ECharts only, through the lazy-loaded `src/components/charts/EChart.tsx` wrapper (keep
  it code-split). Do not add another chart library.
- Markdown / LLM output: render with `src/components/Markdown.tsx`.

**Testing**
- Environment is `happy-dom`. `src/test/setup.ts` loads jest-dom (`@testing-library/jest-dom/vitest`,
  which types the matchers for Vitest), starts the MSW server with `onUnhandledFrame: "bypass"`, and
  polyfills `localStorage` (Node 25+ ships a stub that shadows the DOM one).
- Vitest 5 defaults to `clearMocks: true`: mock call history is cleared before every test. Calls
  made in `beforeAll` (e.g. at module import) are gone by the time a test runs, so record what you
  need inside `beforeAll` (see `src/api/client.test.ts`).
- Mock HTTP with MSW (default handlers in `src/test/handlers.ts`, override with
  `server.use(...)`) or mock Axios at module level. Never make real HTTP calls.
- Co-locate tests with the code they test (`Button.test.tsx` next to `button.tsx`). Route tests
  live in `src/__tests__/routes/`. Zod schemas get plain unit tests.
- End-to-end tests use Playwright and live in `frontend/e2e/*.spec.ts` (outside `src/`, excluded
  from Vitest in `vite.config.ts`). `playwright.config.ts` starts Vite on :5174, or reuses a dev
  server already running there. Specs mock the backend with `page.route` on URLs whose pathname
  starts with `/api/` (a `**/api/**` glob also matches Vite's `/src/api/*.ts` modules), so they run
  without Docker. Prefer role-based locators (`getByRole`, `getByLabel`). Behaviour that happy-dom
  can test belongs in Vitest, not Playwright.
- Full-stack specs live in `frontend/e2e/integration/` and run only with `npm run e2e:integration`
  (`playwright.integration.config.ts`; the mocked config ignores that folder). That config starts
  its own Django on :8015 (`core.settings.e2e`, database deleted and re-migrated every run) and
  Vite on :5184 pointed at it, and never reuses running servers. It never touches the dev stack.
  Each test registers its own user with a unique email, so tests do not share state. Use them for
  the API contract (auth, real responses); keep UI-only checks in the mocked suite.

---

## Docs

There is no `docs/` folder. Project knowledge lives in two files, and docs travel with code in
the same change:

| File | Holds |
|---|---|
| `README.md` | Quick start, local setup, the API table, project structure, tech stack |
| `AGENTS.md` | Conventions and rules for agents (this file) |

- A new or changed endpoint updates the API table in `README.md`: method, path, auth (public or
  JWT), request body, response shape with status code. Note non-obvious error behaviour below
  the table.
- Changed setup steps or ports update the Quick Start in `README.md` and the ports table here.
- A changed convention updates this file.
- New env vars go in `.env.example` with a comment.
- If you find an outdated doc, fix it in the same change.

---

## Plans (GitHub issues)

Any change touching more than one file needs a plan issue before implementation.

- Create it with labels `plan` + `status: draft`. Once per repo, create the labels first:
  `gh label create plan --force`, `gh label create "status: draft" --force`,
  `gh label create "status: in-progress" --force`. Then:
  `gh issue create --title "Plan: <feature>" --label plan --label "status: draft" --body-file <file>`.
  Write the body file outside the repo.
- The body has these sections: **Goal** (one paragraph), **Background**, **Phases** (each with an
  **Outcome** line, task checkboxes and a **Validation** block), **Testing**, **Risks & Notes**.
- Plans are phased. Each phase is **stable**: it leaves the repo working (migrations applied,
  existing suites green, nothing half-wired).
- Each phase's **Validation** names the tests (file + test name) and manual steps that prove it
  landed. Progress is measured by those checks passing. If a step can only be verified after a
  later phase, merge it into that phase.
- The plan-level **Testing** section covers cross-cutting strategy and the end-to-end
  walkthrough.
- When work starts, swap `status: draft` for `status: in-progress`
  (`gh issue edit <n> --remove-label "status: draft" --add-label "status: in-progress"`).
- When a phase lands, tick its boxes in the issue body (`gh issue edit <n> --body-file <file>`)
  and comment with the validation results (`gh issue comment <n> --body "..."`).
- When all phases are done, close the issue as completed (`Closes #<n>` in the final PR, or
  `gh issue close <n> --reason completed`). Close abandoned plans as `not planned` with a reason.
- Reference the issue (`#<n>`) in related commits and PRs. Never delete plan issues.
- Run a phase's **Validation** and confirm it passes before starting the next phase. Say what
  you ran and the result.
- Larger plans get a milestone, with a sub-issue for each phase.

---

## General rules

- Backend and frontend communicate only through the API contract. Never mix their concerns.
- Never commit `.env` files. `.env.example` is the source of truth for required vars.
- There is exactly one env file: `.env` in the repo root, from `.env.example` (`cp .env.example .env`).
  Django, Vite, docker-compose (`env_file`), direnv (`backend/.envrc`) and VS Code all read it.
  Do not add per-folder `.env` files. Add new vars to the root `.env.example`, grouped under the
  backend or frontend heading.
- There is exactly one `.gitignore`, in the repo root. Do not add per-folder `.gitignore` files.
  Scope folder-specific rules with a path prefix (`frontend/dist/`, `backend/.venv/`). The
  `.gitignore` files that ruff, pytest and mypy write inside their own cache folders are
  untracked tool output; leave them.
- Prefer explicit, readable code over clever code.

## Working alongside other agents

Other agents may edit this working tree at the same time.

- Claims live in `.agents/claims.md` (repo root). Before editing a file, check it. If another
  agent claimed the file, stop and tell the user. Otherwise add `<file path> - <task>`, and
  remove your lines when done.
- Lint, format and test only what you changed. `just be-lint` and `just be-fmt` rewrite the
  whole backend (`fix = true`), so run them only when asked. Scoped equivalents:

  ```bash
  cd backend && uv run ruff check <paths> && uv run ruff format <paths>
  cd backend && uv run pytest <path>[::<test>]
  cd frontend && npx eslint <paths> && npx vitest run <paths>
  ```

- Always pass an app to `just be-makemigrations <app>`. Do not run `just dev` or `just be-dev`:
  they run a bare `makemigrations` and start shared dev servers.
- At the end, list every file you changed so the user can commit them separately.

## Never do without explicit confirmation

- Git: no write operations (`add`, `commit`, `push`, `merge`, `rebase`, branch `checkout` /
  `switch`, `branch -D`). Make the change and give the user the commands to run. Never run
  `git stash`, `git checkout -- <file>`, `git restore`, `git reset` or `git clean`: they discard
  other agents' work.
- Files: `rm -rf` on non-temporary directories, deleting migration files.
- Infrastructure: `docker compose down -v` or `just db-reset` (destroy DB volumes), editing
  shared `.env` files.
- Shared services: restarting, stopping or resetting Postgres, Redis, Celery or the dev servers
  (`just down`, `just up`, `just compose restart|stop|down`).
- Process: bypassing hooks (`--no-verify`), dropping or truncating tables directly.

`.claude/settings.json` allows all `Bash(*)` commands to keep the dev loop free of prompts.
The list above still applies. The allowlist removes prompts, not judgement.
