# SAAS_experimental

A decoupled web application, created from the `django_react_template` starter:

- **`backend/`** — Django REST Framework API (Python 3.14, PostgreSQL, Celery)
- **`frontend/`** — React 19 SPA (TypeScript, Vite, TanStack Router, TanStack Query)

---

## Quick Start

```bash
# 1. Clone
git clone git@github.com:bthek1/SAAS_experimental.git && cd SAAS_experimental

# 2. Create the env file (one .env in the repo root, shared by backend and frontend)
cp .env.example .env

# 3. Start everything (compose files live in infra/docker/)
just up

# 4. Run migrations (first time), in a second terminal
just compose exec backend python manage.py migrate
```

`just compose <args>` runs any `docker compose` command against `infra/docker/docker-compose.yml`
with the project name set to the repo folder name (lowercased). Without `just`, pass the same
`-f` and `-p` flags yourself. Leaving out `-p` makes Compose name the project `docker`, after the
compose file's folder, and create a separate set of containers and volumes.

| Service | URL |
|---------|-----|
| Frontend | http://localhost:5174 |
| Backend API | http://localhost:8005/api/ |
| Django admin | http://localhost:8005/admin/ |
| Health check | http://localhost:8005/api/health/ |
| Flower (Celery UI) | http://localhost:5555 (`cd backend && uv run celery -A core flower --port=5555`) |

---

## Local development without Docker

```bash
cp .env.example .env
just install            # uv sync + npm install
just dev                # db + redis + celery in Docker, backend and frontend locally
```

The backend runs on `:8005` and the frontend on `:5174`. Run `just --list` for every command.

PDF export (WeasyPrint) needs Pango and a font on the host. The Docker images already include
them. On Debian/Ubuntu run `sudo apt install libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b
fonts-dejavu-core`; on macOS run `brew install pango`. Without them, everything except
`GET /api/questionnaires/<id>/pdf/` still works.

### Tests

```bash
just be-test            # backend (pytest)
just fe-test            # frontend unit and route tests (Vitest)

cd frontend
npx playwright install chromium   # first time only: downloads the browser
npm run e2e             # end-to-end tests (Playwright); starts Vite itself, API is mocked
npm run e2e:ui          # same, in Playwright's UI mode
npm run e2e:integration # end-to-end against a real Django backend (fresh SQLite, ports 8015 / 5184)
```

The integration suite (`frontend/e2e/integration/questionnaires.spec.ts`) walks the questionnaire
flow end to end: build a type, share a link, answer it logged out, see the score, step through a
battery, and check that one user cannot see another's data.

---

## API

All endpoints are under `/api/`. Authenticated endpoints need `Authorization: Bearer <access>`.

| Method | Path | Auth | Body | Response |
|--------|------|------|------|----------|
| `POST` | `/api/token/` | Public | `{email, password}` | `200 {access, refresh}` |
| `POST` | `/api/token/refresh/` | Public | `{refresh}` | `200 {access, refresh}` (refresh tokens rotate) |
| `POST` | `/api/accounts/register/` | Public | `{email, password}` (password min 8) | `201 {id, email}` |
| `GET` | `/api/accounts/me/` | JWT | | `200 {id, email, first_name, last_name, date_joined}` |
| `PUT` / `PATCH` | `/api/accounts/me/` | JWT | `{first_name?, last_name?, email?}` | `200` same shape as `GET` |
| `GET` | `/api/health/` | Public | | `200 {status: "ok"}` |
| `POST` | `/api/tasks/trigger/` | Public | any JSON object | `202 {task_id}` |
| `GET` | `/api/tasks/<task_id>/` | Public | | `200 {task_id, status, result, traceback}` |
| `POST` | `/api/tasks/<task_id>/revoke/` | Public | `{terminate?: bool}` | `200 {task_id, revoked: true}` |
| `GET` | `/api/questionnaire-types/` | JWT | | `200 [QuestionnaireType]` (own only) |
| `POST` | `/api/questionnaire-types/` | JWT | `{title, questionnaireJson?}` | `201 {id, title, questionnaireJson, createdAt, updatedAt}` |
| `GET` / `PATCH` / `DELETE` | `/api/questionnaire-types/<id>/` | JWT | `PATCH`: `{title?, questionnaireJson?}` | `200 QuestionnaireType` / `204` |
| `GET` | `/api/battery-types/` | JWT | | `200 [BatteryType]` (own only) |
| `POST` | `/api/battery-types/` | JWT | `{title, description?, questionnaireTypeIds?: [id]}` (ordered) | `201 {id, title, description, questionnaireTypeIds, createdAt, updatedAt}` |
| `GET` / `PATCH` / `DELETE` | `/api/battery-types/<id>/` | JWT | `PATCH`: same fields as `POST`, all optional | `200 BatteryType` / `204` |
| `GET` | `/api/questionnaires/` | JWT | | `200 [Questionnaire]` (own only) |
| `POST` | `/api/questionnaires/` | JWT | `{questionnaireTypeId, name?}` | `201 {id, questionnaireTypeId, questionnaireType, batteryId, batteryOrder, name, shareToken, answers, metrics, submittedAt, questionnaireJsonSnapshot, createdAt, updatedAt}` |
| `GET` / `PATCH` / `DELETE` | `/api/questionnaires/<id>/` | JWT | `PATCH`: `{name}` | `200 Questionnaire` / `204` |
| `GET` | `/api/questionnaires/<id>/pdf/` | JWT | | `200 application/pdf` download (`Content-Disposition: attachment; filename="<Title>-<YYYY-MM-DD>.pdf"`); `400 {detail}` if not submitted |
| `GET` | `/api/questionnaires/by-token/<shareToken>/` | Public | | `200 {id, name, questionnaireTypeTitle, questionnaireJson, submittedAt}` |
| `PATCH` | `/api/questionnaires/by-token/<shareToken>/submit/` | Public | `{answers: {}, metrics?: {}}` | `200` same shape as `GET by-token`; `409` if already submitted |
| `GET` | `/api/batteries/` | JWT | | `200 [Battery]` (own only) |
| `POST` | `/api/batteries/` | JWT | `{batteryTypeId, name?}` | `201 {id, batteryTypeId, batteryTypeName, name, shareToken, questionnaires: [{order, questionnaireId, shareToken, questionnaireTypeName, submittedAt}], isComplete, createdAt, updatedAt}` |
| `GET` / `DELETE` | `/api/batteries/<id>/` | JWT | | `200 Battery` / `204` |
| `GET` | `/api/batteries/by-token/<shareToken>/` | Public | | `200 {id, name, batteryTypeName, questionnaires: [{order, shareToken, questionnaireTypeName, submittedAt}], isComplete}` |

- Validation errors return `400` with DRF's `{field: [messages]}` shape. Missing or bad JWTs return `401`.
- The `/api/tasks/` endpoints are a Celery demo (`apps/utils/tasks.py`). They are public so the
  demo works without login. Add auth before reusing them.
- Task `status` is a Celery state (`PENDING`, `STARTED`, `SUCCESS`, `FAILURE`, `REVOKED`, ...).
  `result` is set only on `SUCCESS` and `traceback` only on `FAILURE`. An unknown `task_id`
  returns `PENDING`.
- **Questionnaires.** Every owner endpoint is scoped to the requesting user. Another user's ids
  return `404`, and ids of another user's types in a request body return `400`. `PUT` is not
  supported (use `PATCH`). Lists are not paginated.
- Deleting a questionnaire type that has questionnaires, or that a battery type uses, returns
  `409 {detail}`. The same applies to a battery type that has batteries. Deleting a battery keeps
  its questionnaires (their `batteryId` becomes `null`).
- `POST /api/batteries/` also creates one questionnaire per battery-type slot, in order.
- The `by-token` endpoints are for respondents. They ignore any `Authorization` header (a
  stale token cannot cause a `401`) and expose no owner data. Submitting is write-once. It stores
  `answers` and `metrics` (the survey's `calculatedValues`, computed client-side) and snapshots
  the type's definition into `questionnaireJsonSnapshot`, so later edits to the type do not
  change how a response reads. After submit, `GET by-token` returns the snapshot.
- The PDF renders the submitted snapshot (answers plus labelled metrics). `Content-Disposition`
  is exposed to the browser via CORS (`CORS_EXPOSE_HEADERS`), so the SPA can read the filename.
- Share tokens are bearer secrets: anyone holding the link can submit once. They do not expire.

---

**AI assistants:** [AGENTS.md](AGENTS.md) holds all agent rules. `CLAUDE.md` only imports it (`@AGENTS.md`). Add new rules to `AGENTS.md`, not anywhere else.

---

## Project Structure

```
/
├── backend/          Django REST API
│   ├── core/         Settings, URLs, WSGI
│   ├── apps/         Domain applications
│   │   ├── accounts/ User model (email-based), registration, JWT auth
│   │   ├── questionnaires/ Questionnaire/battery types and instances, share-link completion
│   │   └── utils/    Health check, Celery task demo endpoints
│   ├── tests/        Repo-level tests (infra/docker layout)
│   └── manage.py
├── frontend/         React SPA
│   ├── e2e/          Playwright end-to-end specs
│   └── src/
│       ├── api/      Axios client, query keys, API functions
│       ├── components/ui/  shadcn/ui components
│       ├── hooks/    Custom hooks (auth, etc.)
│       ├── lib/      cn() helper, date-fns wrappers
│       ├── routes/   TanStack Router file-based routes (_authed/ needs login; take*/ are public share links)
│       ├── schemas/  Zod validation schemas
│       ├── store/    Zustand global state slices
│       └── types/    TypeScript types from API contracts
├── infra/docker/     Dockerfiles + compose files (dev stack, prod backend)
└── AGENTS.md         Rules for AI coding agents
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend language | Python 3.14 |
| Backend framework | Django 6 + Django REST Framework |
| Auth | JWT (`djangorestframework-simplejwt`) |
| Database | PostgreSQL 16 |
| Async tasks | Celery + Redis (`django-celery-results`, `django-celery-beat`) |
| Dependency manager | [uv](https://github.com/astral-sh/uv) |
| Frontend language | TypeScript |
| Frontend bundler | Vite |
| UI framework | React 19 |
| Routing | TanStack Router |
| Server state | TanStack Query v5 |
| HTTP client | Axios |
| Styling | Tailwind CSS v4 + shadcn/ui |
| Forms | React Hook Form + Zod |
| Global state | Zustand |
| Testing (frontend) | Vitest + React Testing Library + MSW, Playwright (e2e) |
| Utilities | date-fns, ECharts, react-markdown, SurveyJS |
| Container | Docker Compose |
| Task runner | [just](https://github.com/casey/just) |
