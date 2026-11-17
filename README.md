# SAAS_experimental

A decoupled web application, created from the `django_react_template` starter:

- **`backend/`**: two services behind one gateway, each with its own PostgreSQL database: `catalog` on FastAPI (Python 3.14, Celery) and `instances` on ASP.NET Core (.NET 10)
- **`frontend/`**: React 19 SPA (TypeScript, Vite, TanStack Router, TanStack Query)

---

## Quick Start

```bash
# 1. Clone
git clone git@github.com:bthek1/SAAS_experimental.git && cd SAAS_experimental

# 2. Create the env file (one .env in the repo root, shared by backend and frontend)
cp .env.example .env

# 3. Start everything (compose files live in infra/docker/)
just up

# 4. Run catalog's migrations (first time), in a second terminal. instances (.NET) migrates
#    itself as it starts, adopting a database the Django version built.
just compose exec catalog python -m catalog migrate
```

`just compose <args>` runs any `docker compose` command against `infra/docker/docker-compose.yml`
with the project name set to the repo folder name (lowercased). Without `just`, pass the same
`-f` and `-p` flags yourself. Leaving out `-p` makes Compose name the project `docker`, after the
compose file's folder, and create a separate set of containers and volumes.

| Service | URL |
|---------|-----|
| Frontend | http://localhost:5174 |
| API (gateway) | http://localhost:8005/api/ |
| Admin | http://localhost:8005/admin/ (`catalog`, sqladmin: staff only, create one with `just be-superuser`) |
| Health check | http://localhost:8005/api/health/ |
| Flower (Celery UI) | http://localhost:5555 (`cd backend && uv run celery -A catalog.celery_app flower --port=5555`) |

---

## Local development without Docker

```bash
cp .env.example .env
just install            # uv sync + npm install
just dev                # dbs + redis + celery in Docker, services and frontend locally
```

The API is on `:8005` through the gateway's dev router (`catalog` `:8006`, `instances` `:8007`), and the frontend on `:5174`. Run `just --list` for every command.
`instances` runs under `dotnet watch`, which rebuilds and restarts it on every edit. Its
`❌ Failed to read …staticwebassets.development.json` line is harmless: the service has no static files.

`instances` runs on .NET (`backend/instances/`, #42 to #45), so `just dev` and the tests need
the .NET 10 SDK. Either Microsoft's apt feed (`sudo apt install dotnet-sdk-10.0` on Ubuntu 24.04), or,
without sudo, the official tarball in `~/.dotnet` (check its SHA-512 against
`https://builds.dotnet.microsoft.com/dotnet/release-metadata/10.0/releases.json`, then put
`~/.dotnet` on `PATH` and set `DOTNET_ROOT=~/.dotnet` for running `dotnet` yourself; `just` recipes find
`~/.dotnet` without it). `global.json` pins the SDK band. Its tests and its parity run need Docker, for a throwaway Postgres. Its PDFs are drawn with
[QuestPDF](https://www.questpdf.com/license/) under the Community licence (free for this project's
size), so hosts need no Pango or fonts. Its commands are verbs of the binary: `migrate`,
`seed-loadtest [--questionnaires-per-owner N] [--seed N]`, `reset-db` and `clear-cache` (the last three
dev or loadtest only), `reconcile-refs [--dry-run]` and `health`.

The Django version of `instances` was measured against .NET (`loadtest/baselines/2026-11-14-instances-dotnet.md`)
and removed in #45. It is at `6b47566`, with its admin site and `import_from_monolith`.

### Tests

```bash
just be-test            # backend: catalog's pytest, both API suites, instances' xUnit, then the repo-level checks
just fe-test            # frontend unit and route tests (Vitest)
just infra-test         # Pulumi program and Ansible role checks, no containers needed

cd backend
uv run pytest parity    # catalog's API over real HTTP, against a stub instances (what the SPA and instances rely on)
uv run pytest parity_instances   # instances' API over real HTTP, against a stub catalog (#40); needs Docker
cd ..

cd backend/instances
dotnet test             # xUnit, on a throwaway Postgres (Testcontainers)
cd ../..

cd frontend
npx playwright install chromium   # first time only: downloads the browser
npm run e2e             # end-to-end tests (Playwright); starts Vite itself, API is mocked
npm run e2e:ui          # same, in Playwright's UI mode
npm run e2e:integration # end-to-end against both real services behind the router (catalog on fresh SQLite, instances on a throwaway Postgres in Docker; ports 8015-8017 / 5184 / 5447)
```

The integration suite (`frontend/e2e/integration/questionnaires.spec.ts`) walks the questionnaire
flow end to end: build a type, share a link, answer it logged out, see the score, step through a
battery, and check that one user cannot see another's data.

### Load tests (k6 + Prometheus + Grafana)

A separate Docker stack runs both prod service images (`SETTINGS=loadtest`) behind the
gateway, with their own Postgres databases, Prometheus and Grafana. It needs `JWT_SIGNING_KEY` and
`JWT_VERIFYING_KEY` in `.env` (see `.env.example`). It never touches the dev stack. k6 runs in a container.

```bash
just loadtest-up                       # gateway :8095, Prometheus :9095, Grafana :3005 (all 127.0.0.1)
just loadtest-seed --owners 5 --questionnaires-per-owner 200
just k6 smoke                          # 1 VU, 1 minute, every endpoint group
just k6 load RATE=20 HOLD=10m          # mixed traffic held at RATE iterations/s
just k6 stress                         # raise the rate until p95 > 1 s or errors > 1 %
just loadtest-down                     # stop (volumes kept)
```

Each run prints a `testid` and a Grafana link to the **k6** dashboard for that run (login `admin`,
password `GRAFANA_ADMIN_PASSWORD`, default `admin`). Other scenarios are `soak`, `respondent`,
`pdf` and `outage`. Plan: issue #9. Write-ups of measured runs are in `loadtest/baselines/`, and their charts are
on the app's **Load tests** page (`/load-tests`, login required). That page is updated by hand when a baseline is added.

### Load-test deploy (Proxmox LXC containers)

The baseline runs on seven LXC containers on the Proxmox host (`saas-catalog` .241,
`saas-db` .242, `saas-monitor` .243, `saas-loadgen` .244, `saas-cache` .245, `saas-instances` .246,
`saas-gateway` .247, on `192.168.2.0/24`). Pulumi creates them and Ansible
configures them. One-time setup (state, passphrase, API token): `infra/pulumi/Pulumi.loadtest.yaml.example`.

```bash
just infra-test                 # Pulumi + Ansible helper tests (no Proxmox needed)
just infra-preview              # review: what would change on the host
just infra-up                   # apply exactly that plan
just converge                   # Ansible: install and configure everything (idempotent)
just k6 smoke TARGET=lxc        # k6 on saas-loadgen, through saas-gateway
```

Grafana: `http://192.168.2.243:3000` (password: `just infra stack output grafana_admin_password
--show-secrets`), with dashboards k6, Django, Gateway, Containers, Postgres and Redis cache.

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
| `GET` | `/api/dashboard/?days=&questionnaireType=&tz=` | JWT | | `200 {range: {days, from, to}, kpis: {questionnairesSent, questionnairesSubmitted, questionnairesPending, completionRate, medianHoursToComplete, batteriesTotal, batteriesComplete, batteriesInProgress, batteriesNotStarted}, submissionsByDay: [{date, count}], byQuestionnaireType: [{id, title, sent, submitted, pending}], byBatteryType: [{id, title, complete, inProgress, notStarted}], recentSubmissions: [{id, name, questionnaireTypeTitle, submittedAt}], stalePending: [{id, name, questionnaireTypeTitle, shareToken, createdAt, ageDays}]}` |
| `GET` | `/api/dashboard/scores/?questionnaireType=&days=&tz=` | JWT | | `200 {questionnaireTypeId, metrics: [{name, label, kind: "numeric" \| "categorical" \| "boolean", count, points: [{questionnaireId, name, submittedAt, value}], mean?, distribution?: [{value, count}]}]}` |

- Validation errors return `400` with DRF's `{field: [messages]}` shape. Missing or bad JWTs return `401`.
- **Pagination (#10).** Every list endpoint returns `Page[X]` = `{count, next, previous, results: [X]}`.
  `page` starts at 1. `page_size` defaults to 25 and is capped at 100. A page past the end returns
  `404`. Lists are newest first (`createdAt`, then `id`, so pages never repeat or skip a row).
- The `/api/tasks/` endpoints are a Celery demo (`catalog/catalog/celery_app.py`). They are public so the
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
- **Dashboards are cached for up to 30 s (#11).** New questionnaires, batteries, submissions and
  renamed questionnaires can take that long to appear. `range.to` says when a response was computed.
  Creating or changing a type, and deleting anything, shows up at once. Authentication and
  `questionnaireType` validation still run on every request.
- **Questionnaire-type and battery-type lists are cached for up to 5 minutes (#11).** Any write
  through the API shows up at once. Only edits in the admin can take that long.
- Share tokens are bearer secrets: anyone holding the link can submit once. They do not expire.
- **Dashboard.** `days` is `7`, `30` or `90` (omit for all time; anything else is `400`). `tz` is
  an IANA time zone such as `Australia/Sydney` (default UTC; an unknown name is `400`). The SPA
  sends the browser's. A window starts at midnight in `tz`, `days - 1` days ago, and
  `submissionsByDay` uses dates in `tz`; `range.from` and `range.to` carry its offset. KPIs and
  `byQuestionnaireType` count the questionnaires *created* in the window and how many of those
  are submitted, so `completionRate` (0-1) never exceeds 1. `submissionsByDay` (zero-filled) and
  `recentSubmissions` (latest 10) go by `submittedAt`. `stalePending` lists up to 10 unsubmitted
  questionnaires older than 7 days, whatever the window. `questionnaireType` must be one of your
  types (`400` otherwise); it narrows batteries to those containing that type, but a battery's
  status still counts all of its questionnaires. `medianHoursToComplete` is `null` with no
  submissions.
- **Dashboard scores.** `questionnaireType` is required, and `days` and `tz` work as above. Covers
  that type's submitted questionnaires (by `submittedAt` in the window), grouped by `metrics` key. A
  metric's `kind` comes from its first value; later values of another kind are skipped. `count`
  (responses with that metric) and `mean` (numeric) or `distribution` (categorical and boolean, most
  common first) cover every row in the window. `points` holds only the latest 500 rows, oldest
  first, so it can be shorter than `count`, and empty for a metric only older rows have. Labels and
  order follow the type's current `calculatedValues` (`title`, else `name`), then names only older
  responses have.

---

**AI assistants:** agent rules live in `AGENTS.md` files: [the root one](AGENTS.md) for the whole repo, and one per area (`backend/`, `backend/catalog/`, `backend/instances/`, `frontend/`, `loadtest/`, `infra/`) beside its code. Each has a `CLAUDE.md` beside it that only imports it (`@AGENTS.md`), for Claude Code. Add rules to the `AGENTS.md` for the area they govern, never to a `CLAUDE.md`.

---

### How type changes reach instances

Types are owned by `catalog`, and questionnaires and batteries by `instances`, which reads from its
own copy of each type (#13):

- `DELETE` on a questionnaire type or battery type can return `503 {detail}` if `instances` cannot
  be asked whether the type is in use. Nothing is deleted. `POST`/`PATCH` on instances that name a
  type whose copy has not arrived fetch it once, and return `503` if `catalog` cannot be reached.
- While `catalog` is down, an owner whose access token expires can't refresh it, so their requests fail
  until it returns, but they stay logged in. `src/api/client.ts` clears the tokens only when the refresh
  is refused (`400` or `401`). Respondents have no token, so they are not affected.
- An edited type normally reaches `instances` right after the write. If `instances` is down, it
  waits in the outbox and `python -m catalog relay-outbox` retries it. Until then a share link shows the
  older definition, and the response's snapshot records that same version, so a response always
  matches what the respondent saw.
- Access tokens are signed with RS256, and `instances` holds only the public key. **Moving to RS256
  logged everyone out once.** Set `JWT_SIGNING_KEY` and `JWT_VERIFYING_KEY` for `prod` and `loadtest`
  (see `.env.example`); `dev` needs nothing.
- Deactivating or deleting a user reaches `instances` as an event, so a token keeps working there
  until it arrives. That is normally immediate. Deleting a user also removes their rows there.
- `instances`' `reconcile-refs [--dry-run]` compares every copy with `catalog` and repairs differences.
  It lists any copy whose type is gone but which instances still use, and leaves those in place.

The app's **Service interface** page (`/service-interface`, login required) explains the same flow
in more detail.

### A stuck outbox

`OutboxStuck` fires when an event has waited over a minute (`app_outbox_oldest_pending_seconds`). Respondents are
not affected, but `instances` serves older definitions and deactivated users keep access there.

```bash
just compose logs -f relay_outbox                      # or: journalctl -u saas-relay on saas-catalog
cd backend && uv run python -m catalog relay-outbox --once   # delivered: N, pending: M
```

- **`delivered: 0` and all events pending:** `instances` is unreachable, or the tokens differ. The event's `last_error`
  (catalog's admin, Outbox Event) says which. They drain by themselves once it is back.
- **One event keeps failing while others deliver:** `instances` refuses it (`400`). The event's `last_error` has the
  reason. Fix the cause, or repair the copies with `reconcile-refs`.
- After any long outage, `cd backend/instances && dotnet run --project src/Instances.Api -- reconcile-refs --dry-run`
  shows whether copies differ (on LXC: `dotnet Instances.Api.dll reconcile-refs --dry-run` with the unit's environment).

### Moving a pre-split database

A database from before #13 holds everything. It stays `catalog`'s, and instance rows are copied out.
Each step needs the Django version that did it: `catalog`'s, removed in #38, is at `edb8acd` (the last
commit with `adopt_monolith_db`), and `instances`', removed in #45, is at `6b47566` (the last with
`import_from_monolith`). Then, on the current code:

```bash
cd backend
# at edb8acd:
uv run python catalog/manage.py adopt_monolith_db   # adds the new columns, safe to repeat
uv run python catalog/manage.py migrate
# at 6b47566:
uv run python instances/manage.py migrate
uv run python instances/manage.py import_from_monolith --source "$OLD_DATABASE_URL"
# on the current code:
uv run python -m catalog migrate                     # adopts the Django-built schema (Alembic stamp)
cd instances && dotnet run --project src/Instances.Api -- migrate             # adopts instances' the same way
dotnet run --project src/Instances.Api -- reconcile-refs --dry-run            # expect no differences, with both services up
```

`import_from_monolith` only reads the source, refuses a destination that already has rows, and fails if a
row count differs. Afterwards the old `questionnaires_questionnaire` and `questionnaires_battery` tables are
unused in `catalog`'s database. Dropping them is a separate, deliberate step: check the service first.
`questionnaires_questionnairetype`, `questionnaires_batterytype` and `questionnaires_batterytypeitem` keep
their names and belong to `catalog`, so never drop those.

## Project Structure

```
/
├── backend/          uv workspace: one lock, a package per service
│   ├── common/       What catalog shares with the tests: the published dev JWT pair, gunicorn settings
│   ├── catalog/      Service on FastAPI: alembic.ini, gunicorn.conf.py, tests/
│   │   └── catalog/  app, models, routers/ (accounts, types, internal, health and tasks), outbox,
│   │                 admin, Celery, CLI (`python -m catalog`), migrations/ (Alembic)
│   ├── instances/    Service on ASP.NET Core + EF Core (.NET 10, #42 to #45): Instances.slnx
│   │   ├── src/Instances.Api/     questionnaires, batteries, share links, dashboards, PDFs, type copies
│   │   └── tests/Instances.Tests/ xUnit, on a throwaway Postgres
│   ├── contracts/    JSON shapes of /internal/ calls, tested by both services
│   ├── parity/       catalog's API tested over HTTP only, against a stub instances (#34)
│   ├── parity_instances/  instances' API tested over HTTP only, against a stub catalog (#40)
│   └── tests/        Repo-level tests (service boundary, gateway, infra layout, k6 targets)
├── frontend/         React SPA
│   ├── e2e/          Playwright end-to-end specs
│   └── src/
│       ├── api/      Axios client, query keys, API functions
│       ├── components/ui/  shadcn/ui components
│       ├── hooks/    Custom hooks (auth, etc.)
│       ├── lib/      Plain logic: cn(), date wrappers, pagination, dashboards, load-test figures and charts
│       ├── routes/   TanStack Router file-based routes (_authed/ needs login; take*/ are public share links)
│       ├── schemas/  Zod validation schemas
│       ├── store/    Zustand global state slices
│       └── types/    TypeScript types from API contracts
├── infra/docker/     Dockerfiles + compose files (dev stack, prod services, load-test stack)
├── infra/gateway/    routes.json, the only route table; generated nginx.conf; dev router
├── infra/observability/  Prometheus config + rules, Grafana provisioning and generated dashboards
├── infra/pulumi/     Pulumi program: the load-test LXC containers on Proxmox (#9)
├── infra/ansible/    Ansible: configures those containers (just converge)
├── loadtest/         k6 scenarios (k6/), run.sh (`just k6`), report.py (`just k6-report`), baselines/, results/ (gitignored)
└── AGENTS.md         Rules for AI coding agents (plus one per area; each with a CLAUDE.md that imports it)
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend language | Python 3.14 (`catalog`), C# on .NET 10 (`instances`) |
| Backend framework | `catalog`: FastAPI + SQLAlchemy 2 + Alembic, sqladmin. `instances`: ASP.NET Core + EF Core + Npgsql, QuestPDF (#42 to #45) |
| Auth | JWT, RS256: `catalog` signs with PyJWT (simplejwt's claims), `instances` verifies with ASP.NET Core's JwtBearer |
| Database | PostgreSQL 16 |
| Async tasks | Celery + Redis (`catalog` only; results in Postgres through Celery's SQLAlchemy backend) |
| Cache | Redis, JSON values: `catalog/catalog/cache.py` and `instances`' `Caching/Cache.cs` |
| Dependency manager | [uv](https://github.com/astral-sh/uv) (`catalog`), NuGet with central versions (`instances`) |
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
