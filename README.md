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

### Load tests (k6 + Prometheus + Grafana)

A separate Docker stack runs the prod backend image (gunicorn, `core.settings.loadtest`) with its
own Postgres, Prometheus and Grafana. It never touches the dev stack. k6 runs in a container.

```bash
just loadtest-up                       # backend :8095, Prometheus :9095, Grafana :3005 (all 127.0.0.1)
just loadtest-seed --owners 5 --questionnaires-per-owner 200
just k6 smoke                          # 1 VU, 1 minute, every endpoint group
just k6 load RATE=20 HOLD=10m          # mixed traffic held at RATE iterations/s
just k6 stress                         # raise the rate until p95 > 1 s or errors > 1 %
just loadtest-down                     # stop (volumes kept)
```

Each run prints a `testid` and a Grafana link to the **k6** dashboard for that run (login `admin`,
password `GRAFANA_ADMIN_PASSWORD`, default `admin`). Other scenarios are `soak`, `respondent` and
`pdf`. Plan and baselines: issue #9.

### Load-test deploy (Proxmox LXC containers)

The baseline runs on four LXC containers on the Proxmox host (`saas-app` .241, `saas-db` .242,
`saas-monitor` .243, `saas-loadgen` .244 on `192.168.2.0/24`). Pulumi creates them and Ansible
configures them. One-time setup (state, passphrase, API token): `infra/pulumi/Pulumi.loadtest.yaml.example`.

```bash
just infra-test                 # Pulumi + Ansible helper tests (no Proxmox needed)
just infra-preview              # review: what would change on the host
just infra-up                   # apply exactly that plan
just converge                   # Ansible: install and configure everything (idempotent)
just k6 smoke TARGET=lxc        # k6 on saas-loadgen against saas-app
```

Grafana: `http://192.168.2.243:3000` (password: `just infra stack output grafana_admin_password
--show-secrets`), with dashboards k6, Django, Containers and Postgres.

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
| `GET` | `/api/questionnaire-types/?page=&page_size=` | JWT | | `200 Page[QuestionnaireType]` (own only) |
| `POST` | `/api/questionnaire-types/` | JWT | `{title, questionnaireJson?}` | `201 {id, title, questionnaireJson, createdAt, updatedAt}` |
| `GET` / `PATCH` / `DELETE` | `/api/questionnaire-types/<id>/` | JWT | `PATCH`: `{title?, questionnaireJson?}` | `200 QuestionnaireType` / `204` |
| `GET` | `/api/battery-types/?page=&page_size=` | JWT | | `200 Page[BatteryType]` (own only) |
| `POST` | `/api/battery-types/` | JWT | `{title, description?, questionnaireTypeIds?: [id]}` (ordered) | `201 {id, title, description, questionnaireTypeIds, createdAt, updatedAt}` |
| `GET` / `PATCH` / `DELETE` | `/api/battery-types/<id>/` | JWT | `PATCH`: same fields as `POST`, all optional | `200 BatteryType` / `204` |
| `GET` | `/api/questionnaires/?questionnaireType=&submitted=&page=&page_size=` | JWT | | `200 Page[Questionnaire]` (own only; filters optional) |
| `POST` | `/api/questionnaires/` | JWT | `{questionnaireTypeId, name?}` | `201 {id, questionnaireTypeId, questionnaireType, batteryId, batteryOrder, name, shareToken, answers, metrics, submittedAt, questionnaireJsonSnapshot, createdAt, updatedAt}` |
| `GET` / `PATCH` / `DELETE` | `/api/questionnaires/<id>/` | JWT | `PATCH`: `{name}` | `200 Questionnaire` / `204` |
| `GET` | `/api/questionnaires/<id>/pdf/` | JWT | | `200 application/pdf` download (`Content-Disposition: attachment; filename="<Title>-<YYYY-MM-DD>.pdf"`); `400 {detail}` if not submitted |
| `GET` | `/api/questionnaires/by-token/<shareToken>/` | Public | | `200 {id, name, questionnaireTypeTitle, questionnaireJson, submittedAt}` |
| `PATCH` | `/api/questionnaires/by-token/<shareToken>/submit/` | Public | `{answers: {}, metrics?: {}}` | `200` same shape as `GET by-token`; `409` if already submitted |
| `GET` | `/api/batteries/?page=&page_size=` | JWT | | `200 Page[Battery]` (own only) |
| `POST` | `/api/batteries/` | JWT | `{batteryTypeId, name?}` | `201 {id, batteryTypeId, batteryTypeName, name, shareToken, questionnaires: [{order, questionnaireId, shareToken, questionnaireTypeName, submittedAt}], isComplete, createdAt, updatedAt}` |
| `GET` / `DELETE` | `/api/batteries/<id>/` | JWT | | `200 Battery` / `204` |
| `GET` | `/api/batteries/by-token/<shareToken>/` | Public | | `200 {id, name, batteryTypeName, questionnaires: [{order, shareToken, questionnaireTypeName, submittedAt}], isComplete}` |
| `GET` | `/api/dashboard/?days=&questionnaireType=` | JWT | | `200 {range: {days, from, to}, kpis: {questionnairesSent, questionnairesSubmitted, questionnairesPending, completionRate, medianHoursToComplete, batteriesTotal, batteriesComplete, batteriesInProgress, batteriesNotStarted}, submissionsByDay: [{date, count}], byQuestionnaireType: [{id, title, sent, submitted, pending}], byBatteryType: [{id, title, complete, inProgress, notStarted}], recentSubmissions: [{id, name, questionnaireTypeTitle, submittedAt}], stalePending: [{id, name, questionnaireTypeTitle, shareToken, createdAt, ageDays}]}` |
| `GET` | `/api/dashboard/scores/?questionnaireType=&days=` | JWT | | `200 {questionnaireTypeId, metrics: [{name, label, kind: "numeric" \| "categorical" \| "boolean", points: [{questionnaireId, name, submittedAt, value}], mean?, distribution?: [{value, count}]}]}` |

- Validation errors return `400` with DRF's `{field: [messages]}` shape. Missing or bad JWTs return `401`.
- **Pagination (#10).** Every list endpoint returns `Page[X]` = `{count, next, previous, results: [X]}`.
  `page` starts at 1. `page_size` defaults to 25 and is capped at 100. A page past the end returns
  `404`. Lists are newest first (`createdAt`, then `id`, so pages never repeat or skip a row).
- The `/api/tasks/` endpoints are a Celery demo (`apps/utils/tasks.py`). They are public so the
  demo works without login. Add auth before reusing them.
- `GET /metrics` (not under `/api/`, not part of the contract) is Prometheus text for the
  scraper. It answers only peers in `METRICS_ALLOWED_CIDRS` (default loopback), and returns `404`
  to everyone else and to any request with a forwarding header.
- Task `status` is a Celery state (`PENDING`, `STARTED`, `SUCCESS`, `FAILURE`, `REVOKED`, ...).
  `result` is set only on `SUCCESS` and `traceback` only on `FAILURE`. An unknown `task_id`
  returns `PENDING`.
- **Questionnaire filters.** `GET /api/questionnaires/` takes `questionnaireType` (one of your types,
  else `400`) and `submitted` (`true`/`false`, else `400`). Both are optional and combine.
- **Questionnaires.** Every owner endpoint is scoped to the requesting user. Another user's ids
  return `404`, and ids of another user's types in a request body return `400`. `PUT` is not
  supported (use `PATCH`).
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
- **Dashboard.** `days` is `7`, `30` or `90` (omit for all time; anything else is `400`). A
  window starts at UTC midnight `days - 1` days ago, and day buckets are UTC. KPIs and
  `byQuestionnaireType` count the questionnaires *created* in the window and how many of those
  are submitted, so `completionRate` (0-1) never exceeds 1. `submissionsByDay` (zero-filled) and
  `recentSubmissions` (latest 10) go by `submittedAt`. `stalePending` lists up to 10 unsubmitted
  questionnaires older than 7 days, whatever the window. `questionnaireType` must be one of your
  types (`400` otherwise); it narrows batteries to those containing that type, but a battery's
  status still counts all of its questionnaires. `medianHoursToComplete` is `null` with no
  submissions.
- **Dashboard scores.** `questionnaireType` is required. Covers that type's submitted
  questionnaires (by `submittedAt` in the window), grouped by `metrics` key. A metric's `kind`
  comes from its first value; later values of another kind are skipped. Numeric metrics get
  `mean`; categorical and boolean ones get `distribution` (most common first). Labels and order
  follow the type's current `calculatedValues` (`title`, else `name`), then names only older
  responses have.

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
│   ├── tests/        Repo-level tests (infra layout, k6 targets, observability config)
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
├── infra/docker/     Dockerfiles + compose files (dev stack, prod backend, load-test stack)
├── infra/observability/  Prometheus config + rules, Grafana provisioning and generated dashboards
├── infra/pulumi/     Pulumi program: the load-test LXC containers on Proxmox (#9)
├── infra/ansible/    Ansible: configures those containers (just converge)
├── loadtest/         k6 scenarios (k6/), run.sh (`just k6`), results/ (gitignored)
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
| Cache | Redis, through Django's cache framework and `apps/utils/cache.py` |
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
