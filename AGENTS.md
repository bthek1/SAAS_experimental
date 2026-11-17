# AGENTS.md

Rules for AI coding agents working in this repository. This is the only agent instruction file.
`CLAUDE.md` contains just `@AGENTS.md`. Do not add rules anywhere else.

---

## What this repo is

**SAAS_experimental**, a FastAPI + ASP.NET Core + React project created from the `django_react_template`
starter, as a decoupled monorepo:

- **`backend/`**: two services, each with its own PostgreSQL database: `catalog` on FastAPI (Python 3.14,
  Celery + Redis, a uv workspace with `common`) and `instances` on ASP.NET Core (.NET 10, `backend/instances/`).
  Both began as Django and keep the tables and API Django left: `catalog` moved in #34 to #38, `instances`
  in #40 to #45
- **`infra/gateway/`**: nginx route table that gives both services one public origin
- **`frontend/`**: React 19 SPA (TypeScript, Vite, TanStack Router + Query)
- **`infra/docker/`**: Dockerfiles and compose files for both halves

The services expose only `/api/` endpoints publicly, and `/internal/` to each other. The frontend consumes them over HTTP. The two halves
share no code. The API contract is the only interface between them.

Prefer documented conventions over one-off solutions.

---

## Where to look first

| You need | Read |
|----------|------|
| Setup, endpoints and request/response shapes | [`README.md`](README.md) (Quick Start, API) |
| Env vars | [`.env.example`](.env.example) |
| Day-to-day commands | [`justfile`](justfile) (`just`) and the Commands section below |
| JWT handling | `frontend/src/api/client.ts`, `backend/catalog/catalog/auth.py` (signs), `backend/instances/src/Instances.Api/Auth/OwnerAuth.cs` (`instances` verifies) |
| Celery wiring | `backend/catalog/catalog/celery_app.py`, `frontend/src/hooks/useTaskPoller.ts` |
| Load test results page | `frontend/src/routes/_authed/load-tests.tsx`, `frontend/src/lib/loadtestResults.ts` (figures), `frontend/src/lib/loadtestCharts.ts` (charts) |
| How the services talk, in the app | `frontend/src/routes/_authed/service-interface.tsx` (`/service-interface`, hand-written, #27) |
| Active / finished plans | GitHub issues labelled `plan` (`gh issue list --label plan [--state closed]`) |

---

## Commands

The [`justfile`](justfile) holds only day-to-day commands. Run `just` to list them. Do not add
recipes for one-off or rare tasks; document the raw command here instead. A new recipe gets a
`# doc comment` line, then `[group('<area>')]` (`dev`, `docker`, `backend`, `frontend`,
`loadtest`, `infra`, `database`), then the recipe. The comment must come before the attribute, or `just` fails with
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
just be-test        # catalog's pytest, both API suites, instances' xUnit, repo checks
just be-lint        # ruff check (note: pyproject sets fix = true, so this rewrites files)
just be-fmt         # ruff format

just fe-test        # vitest
just fe-lint        # eslint
just fe-build       # type-check + build

just db-reset       # DESTRUCTIVE: drops the Postgres volume, then re-migrates

just loadtest-up    # load-test stack: prod backend + Postgres + Prometheus + Grafana (#9)
just loadtest-seed --owners 5 --questionnaires-per-owner 200
just k6 <scenario> [KEY=VALUE…]  # smoke load stress soak respondent pdf outage catalog
just loadtest-down  # keeps its volumes

just infra-test     # Pulumi program tests (mocks, no Proxmox)
just infra-preview  # preview the LXC containers, save the plan
just infra-up       # apply exactly the saved plan
just infra <args>   # any pulumi command on the loadtest stack
just converge [--tags app] [--check --diff]  # Ansible: configure the containers
just k6 <scenario> TARGET=lxc  # run from saas-loadgen through saas-gateway
```

Agents run every test command, recipes included, under the machine-wide test lock. See
"Working alongside other agents".

Rarer tasks have no recipe. Run them directly:

| Task | Command |
|---|---|
| Backend dev servers only | `just be-dev` (private helper: gateway router :8005, catalog :8006, instances :8007) |
| Frontend dev server only | `just fe-dev` (private helper, :5174) |
| catalog parity suite (#34) | `cd backend && uv run pytest parity` (starts `catalog` and a stub `instances` itself) |
| instances API suite (#40) | `cd backend && uv run pytest parity_instances` (builds `instances`, a throwaway Postgres in Docker and a stub `catalog`) |
| instances tests | `cd backend/instances && dotnet test` (one category: `dotnet test -- --filter-trait "Category=Refs"`) |
| instances lint / format | `cd backend/instances && dotnet format --verify-no-changes` / `dotnet format` |
| instances migration | `just be-makemigrations instances <Name>` (`dotnet ef migrations add`; read it) |
| .NET service by hand | `dotnet build src/Instances.Api -c Release -o <dir>`, then `dotnet <dir>/Instances.Api.dll migrate` and `dotnet <dir>/Instances.Api.dll` (`ASPNETCORE_URLS`, env as below) |
| catalog coverage | `cd backend && uv run pytest catalog --cov=catalog --cov-report=term-missing` |
| Type check catalog | `cd backend && uv run mypy catalog common` (`instances` is type-checked by its build) |
| catalog migration | `just be-makemigrations catalog "<message>"` (Alembic autogenerate against the dev db; read the result) |
| Celery worker outside Docker | `cd backend && uv run celery -A catalog.celery_app worker --loglevel=info` |
| Flower UI on :5555 | `cd backend && uv run celery -A catalog.celery_app flower --port=5555` |
| Logs | `just compose logs -f <service>` |
| Rebuild images | `just compose build [service]` |
| psql shell | `just compose exec db psql -U appuser -d appdb` |
| Prod service image | `docker build -f infra/docker/<catalog\|instances>.prod.Dockerfile backend` |
| Staff account for `/admin/` (catalog) | `just be-superuser` (`python -m catalog create-superuser`, from `DJANGO_SUPERUSER_*`) |
| Regenerate the gateway config | `python3 infra/gateway/build_nginx.py` (after editing `routes.json`) |
| Move data from a database from before the split | See "Moving a pre-split database" in `README.md` |
| Vitest UI | `cd frontend && npm run test:ui` |
| Frontend e2e (Playwright) | `cd frontend && npm run e2e` (first time: `npx playwright install chromium`) |
| Playwright UI / report | `cd frontend && npm run e2e:ui` / `npx playwright show-report` |
| Frontend e2e against a real backend | `cd frontend && npm run e2e:integration` (needs `uv sync` in `backend/`, the .NET SDK and Docker) |

### Local services and ports

Host ports are offset so they do not clash with a locally installed Postgres or Redis.

| Service | Host port | Notes |
|---|---|---|
| `db` | `5435` -> 5432 | Postgres 16 (`appuser` / `apppassword` / `appdb`) |
| `redis` | `127.0.0.1:6380` -> 6379 | Celery broker (db 0) and cache (db 1). Loopback only: see Cache |
| `db` (`instances_db`) | `5437` -> 5432 | The `instances` database (`instancesdb`). `db` above is `catalog`'s |
| e2e `instances` database | `127.0.0.1:5447` | Throwaway Postgres in Docker, `npm run e2e:integration` only (#44) |
| `gateway` | `8005` | One public origin, so `VITE_API_BASE_URL` stays valid |
| `catalog` | `8006` | uvicorn `--reload` |
| `instances` | `8007` | `dotnet watch` (rebuilds on every edit) |
| `relay_outbox` | none | Retries undelivered events |
| `celery_worker`, `celery_beat` | none | `catalog.celery_app`; beat's schedule is code (`beat_schedule`) |
| `frontend` | `5174` | Vite dev server |
| e2e gateway, catalog, instances, frontend | `8015`, `8016`, `8017`, `5184` | Started by `npm run e2e:integration` only (dev + 10) |
| load-test `gateway`, `prometheus`, `grafana` | `8095`, `9095`, `3005` | `just loadtest-up` only; bound to 127.0.0.1 |

All Docker files live in `infra/docker/`: `docker-compose.yml` (dev stack),
`docker-compose.prod.yml` (gunicorn services + gateway + dbs), `docker-compose.loadtest.yml` (load tests, its
own project `<repo folder name>-loadtest`, see below), `<service>[.prod].Dockerfile`, and a
`<name>.Dockerfile.dockerignore` next to each Dockerfile (BuildKit reads it in place of the build
context's `.dockerignore`). Paths in the compose files are relative to `infra/docker/`. The justfile
passes `-f infra/docker/docker-compose.yml -p <repo folder name>`. Run other compose commands
through `just compose <args>` rather than bare `docker compose`. Without `-p` the project is named
`docker` and you get a second set of containers and volumes. Put new Docker files in
`infra/docker/` as `<service>[.<variant>].Dockerfile` with a matching `.dockerignore`.
`backend/tests/test_infra_docker.py` enforces this layout.

Inside Compose, the `environment:` blocks set `DATABASE_URL`, `INSTANCES_DATABASE_URL`, `CELERY_BROKER_URL`
and `CACHE_REDIS_URL` to the in-network hosts (`db:5432`, `instances_db:5432`, `redis:6379`). These override the `localhost`
values in the root `.env`.

---

## Backend (`backend/`)

**Stack.** `catalog`: Python 3.14, FastAPI, Pydantic v2, pydantic-settings, SQLAlchemy 2 (sync), Alembic,
PyJWT, sqladmin, Celery + Redis, gunicorn with uvicorn workers; uv, ruff, mypy, pytest, pytest-mock.
`instances`: .NET 10, ASP.NET Core controllers, EF Core + Npgsql, JwtBearer, StackExchange.Redis,
prometheus-net, QuestPDF; xUnit v3 with Testcontainers. Both on PostgreSQL 16. Each has its own section below.

Both services began as Django and kept the tables and the API it left. `catalog` moved to FastAPI in #34 to
#38 (the Django version is at `edb8acd`), and `instances` to .NET in #40 to #45 (at `6b47566`). Both
comparisons are in `loadtest/baselines/` and on `/load-tests`. `instances` on MongoDB was tried and removed
(#29, #30): it was slower and got slower as rows grew (`loadtest/baselines/2026-11-06-instances-mongodb.md`).

Upgrade Python dependencies with `uv lock --upgrade` from `backend/` (the workspace root: `catalog` and
`common`). .NET package versions live in `backend/instances/Directory.Packages.props` only.

**Layout.** `catalog/` (Python package `catalog/catalog/`), `instances/` (`Instances.slnx`: `src/Instances.Api/`
and `tests/Instances.Tests/`), `common/` (the published dev JWT pair and gunicorn settings, used by `catalog`
and the tests), `contracts/` (JSON shapes of `/internal/`), `parity/` and `parity_instances/` (each service's
API over HTTP), `tests/` (repo-level checks). Run Python commands from `backend/`: `uv run python -m catalog
<cmd>`, `uv run pytest catalog`, `uv run pytest parity`, `uv run pytest parity_instances`, `uv run pytest
tests`; .NET ones from `backend/instances/`.

The services never import each other, including in tests: `catalog` is Python and `instances` is .NET, and
`tests/test_service_boundary.py` checks that no Python reaches into `instances` and that `common` holds only
`dev_keys` and `gunicorn_conf` (#13, #45).

**Service boundary (#13).** `instances` reads only its own copies of types (`QuestionnaireTypeRef`,
`BatteryTypeRef`), written only by `Refs/RefService.cs`. Every write to a type must call
`events.record_change()` in `catalog` in the same transaction, including admin and seeding, and a delete
goes through `services.delete_type()`. Peers are reached only through clients: `instances` uses
`Peers/CatalogClient.cs` (`ICatalogClient`; tests swap in a fake), `catalog` uses `catalog/peers.py`
(`HttpInstances`; tests swap in `RecordingInstances` from `tests/conftest.py`). `/internal/` is never routed by
the gateway. Its shapes are `backend/contracts/`, tested by both services: change those files together with
both sides. The subtle rules (versions, tombstones, why read-through is authoritative) are at the top of
`RefService.cs`. `frontend/src/routes/_authed/service-interface.tsx` explains all this in the app and is
hand-written, so a change to `/internal/`, an event or an outage behaviour updates it too (#27).

**API rules, both services**
- All public endpoints are under `/api/`. Every endpoint needs a JWT unless it is marked public.
- **The wire format is DRF's, kept on purpose**, because the SPA and the other service read it: validation
  errors are `400 {field: [messages]}`, other errors `{detail}`, timestamps `...123456Z`. The parity suites
  pin it; change it only with a parity test.
- Business logic goes in services (`catalog/services.py`; `instances`' `*Service` classes), never in routers
  or controllers.
- **Every list endpoint is paginated** (#10): `?page=`, `?page_size=` (default 25, max 100), DRF's
  `{count, next, previous, results}` with absolute links (`catalog/pagination.py`, `Http/Pagination.cs`). Give
  list queries a total order (`-created_at`, `-id`), or pages repeat and skip rows. Filters that a page needs go
  on the server, never in the browser.
- Primary keys are UUIDs. Owners live in `catalog`; rows in `instances` hold a plain `owner_id`.
- Avoid N+1 queries; batch writes. Raw SQL only when unavoidable, and always parameterised.
- Never edit an applied migration (Alembic revision or EF migration), and read every generated one.
- Datetimes are UTC and timezone-aware: `datetime.now(UTC)` in Python, never naive `datetime.now()` or
  `utcnow()`; `ApiJson.UtcNow()` in `instances`, which keeps Python's microsecond precision.
- File downloads (PDFs) set `Content-Disposition`; any response header the SPA must read is exposed through
  CORS (`.WithExposedHeaders(...)` in `Program.cs`).

**Settings.** Both read `SETTINGS` (`dev`, `test`, `e2e`, `prod`, `loadtest`; `catalog` also `parity`) and the
root `.env`, with the same rules: the test profiles never read `JWT_*` from `.env` and always use the dev JWT
pair in `common/dev_keys.py` (#33); `prod` and `loadtest` require their secrets and refuse the dev key;
`loadtest` (#9) is `prod` over plain HTTP for k6 on a private network, and refuses any public `ALLOWED_HOSTS`
entry. If throttles are ever added, raise them there for k6 (every VU shares one IP). `instances` reads
`INSTANCES_DATABASE_URL`, never `DATABASE_URL`, which is `catalog`'s. Never hardcode secrets or credentials.

**Auth.** JWT, RS256 (#13). `catalog` signs (`POST /api/token/`, `POST /api/token/refresh/`) and holds the
users; `instances` verifies with the public key only (`Auth/OwnerAuth.cs`): it has no user table, so a request's
owner is just the token's `user_id`. Deactivation and deletion arrive as events (`services.set_active` and
`delete_user` in `catalog`) into `BlockedOwner`, which `OwnerAuth` checks.

**Metrics and load tests (#9)** (the k6 side is under "Load tests" below)
- Both export `http_requests_total`, `http_request_duration_seconds` and `db_query*` series, labelled by route
  template (`view`), with django-prometheus's buckets, so runs from before #44 still line up
  (`tests/test_observability.py`). `/metrics` is answered ahead of routing, so Prometheus can scrape by IP over
  plain HTTP. It is deliberately not under `/api/`. It answers only peers in `METRICS_ALLOWED_CIDRS`, and returns
  404 to any request carrying a forwarding header, so a proxy can never make it public.
- Under gunicorn with several workers, `catalog` needs `PROMETHEUS_MULTIPROC_DIR`, or each scrape sees one
  worker. `common/gunicorn_conf.py` empties it on start and marks dead workers.
- Both servers' keep-alive must outlast the gateway's upstream `keepalive_timeout` (`common/gunicorn_conf.py`,
  `Program.KeepAliveSeconds`, `infra/gateway/build_nginx.py`; `tests/test_gunicorn_conf.py` and
  `tests/test_kestrel_keepalive.py` check it). Otherwise a server can close a connection as nginx reuses it, and a
  POST or PATCH gets a 502 (#24). `loadtest/keepalive_repro.py` reproduces this.
- Seeding exists in both services (`python -m catalog seed-loadtest`, `Instances.Api.dll seed-loadtest`), and
  `just loadtest-seed` runs them in order: `catalog`'s creates owners and types, then `instances`' creates rows
  from the copies, using ids derived from the email so repeated runs match. It creates deterministic
  `loadtest-<n>@example.com` owners with data spread over 90 days. It runs only under `dev` or `loadtest`.
  `tests/Instances.Tests/HttpTests.cs` fails if a hot path's query count grows with rows; add new k6-loaded
  endpoints to it.

**Dashboard (#19)** (`instances`' `Dashboard/DashboardService.cs`)
- Keep work on a miss, and the size of what is cached, bounded by the page rather than the owner's rows. A
  cache hit still deserializes and sends the whole value, so a large response costs on every request.
  `dashboard/scores/` returns only the latest `ScorePointLimit` rows as `points`, while `count`, `mean` and
  `distribution` cover the whole window. In the SPA, read counts from those fields, never `points.length`.
- Let the database sort or aggregate instead of loading rows into the service.
- `tz` must be an IANA zone name, and is part of the cache key. Windows are the owner's local days; stored
  datetimes stay UTC. Rounding is Python's `round()` (`Dashboard/Python.cs`), and a local midnight in a DST change
  is read as `zoneinfo` reads it.
- Check a dashboard query with `EXPLAIN` on Postgres with realistic rows, and with stale statistics too: a
  fast-growing table is where a plan turns into a full scan.
- To profile or compare without touching the dev or load-test stacks, start a throwaway Postgres with its own
  port (`docker run --rm --tmpfs /var/lib/postgresql/data -p 127.0.0.1:5499:5432 ...`), point
  `INSTANCES_DATABASE_URL` at it (it overrides `.env`), then run `migrate`, add copies and `seed-loadtest`. Run
  `VACUUM (PARALLEL 0, ANALYZE)` first: plain `VACUUM ANALYZE` can run out of Docker's small `/dev/shm`, and
  without statistics the plans are not realistic.

**Celery**
- `catalog` only. App and tasks in `catalog/celery_app.py` (`@app.task`).
- Broker is Redis. Results are stored in Postgres through Celery's SQLAlchemy backend
  (`celery_taskmeta`). Periodic schedules are code: `beat_schedule` in the same file.
- The test profiles run tasks eagerly, with an in-memory broker, so tests need no Redis.

**Cache (#11)**
- Redis, JSON values, each service under its own key prefix (`catalog/cache.py`, `instances`' `Caching/Cache.cs`
  with prefix `instances-net:`). Every cached read goes through `cached()` / `Cache.Cached`. It requires an
  owner id, so a key cannot be built without a tenant. Parameters come from validated data, never a raw query
  string. The group is one of the service's fixed groups: it is a Prometheus label, like k6's `name` tag.
- It fails open. A Redis error is logged and counted (`app_cache_requests_total`), then the value is
  computed. `CACHE_ENABLED=false` bypasses the cache without a code change.
- Run auth and validation before reading the cache, so a deactivated user or a foreign id is still refused on
  a hit.
- Anything that changes a cached value goes in its parameters, including `tz` on the dashboards. Bump the
  version when the value's shape changes.
- Bumping an owner's generation makes all their entries unreachable, after the commit (`UnitOfWork` in
  `instances`). Do not delete keys or scan for them. Type writes and any delete bump it; questionnaire or battery
  creation and submit do not, since they are too frequent, so dashboards lag them by up to the TTL. A new write
  to something a cached response reads needs a bump, or its staleness in `README.md`.
- Cached today: dashboards (30 s) and PDFs (24 h) in `instances`, type lists (5 min) in `catalog`. PDFs skip the
  generation, because their key holds `updated_at`: bump `PdfCacheVersion` when the drawing changes. Lists and
  details are not cached, since owners expect to see a row they just created. A new cached endpoint gets a test
  that two owners never share a value, and an off-versus-on k6 run. Paginated bodies hold absolute URLs, so
  their key includes scheme and host.
- Never publish the cache Redis: loopback on dev, no port on the other Compose stacks, firewall and password
  on LXC. It holds every owner's cached responses.
- A cache Redis runs `allkeys-lru`, which could drop a broker's queued tasks. If a stack with a cache Redis
  gains Celery, its broker gets a second instance. Only the dev stack shares one, with no `maxmemory`.

**Testing.** `catalog/tests/` (see its section) and `instances/tests/Instances.Tests/` (see its section).
`backend/parity/` tests `catalog` over HTTP only: it starts the service on a free port, with a fresh SQLite
database and a stub `instances` that records events and answers retire. It imports no service code, so it
outlived the Django version it was written against (#34). Pin there anything the SPA or `instances` relies on.
`backend/parity_instances/` does the same for `instances` (#40), and checked Django against .NET until #45: it
builds the service and runs it on a throwaway Postgres in Docker, with a stub `catalog` serving `/internal/`
(switchable to 404, 500 or no answer). It plays `catalog` itself: tokens signed with the dev key, types sent as
events. The dashboard tests move rows in time with a plain `UPDATE` (`support.Clock`), so it runs with the cache
off. Pin there anything the SPA, respondents or `catalog` rely on from `instances`. Repo-level checks that are not
tied to a service live in `backend/tests/`, run with `uv run pytest tests`. `tests/test_infra_docker.py` checks
the `infra/docker/` layout; its `docker compose config` tests skip when Docker is not installed, as do the
throwaway-Postgres tests. Markers: `slow`, `integration`, `development`.

**API docs:** the API table in `README.md` is the hand-written contract. `catalog` serves its
OpenAPI schema at `/api/docs/` under `debug` only; it does not replace the table.

### `catalog` (FastAPI, #35 to #38)

The package is `backend/catalog/catalog/`; tests are in `backend/catalog/tests/`, Alembic config in
`backend/catalog/alembic.ini`.

- **Same contract as the Django version had** (see "API rules" above). Never FastAPI's 422: bodies go
  through `errors.parse()`. Timestamps are `...123456Z` in responses and `+00:00` in events.
- **Layout.** `routers/` (thin), `schemas.py` (Pydantic bodies and response dicts), `services.py` (all
  writes), `events.py` (outbox), `models.py`, `auth.py`, `cache.py`, `metrics.py`, `admin.py`
  (sqladmin), `celery_app.py`, `__main__.py` (commands). Business logic goes in `services.py`.
  Endpoints return `responses.json_response(...)`, never a dict: FastAPI walks a returned dict
  through `jsonable_encoder`, ~10 times the cost of encoding it (#41). A returned Response skips the
  decorator's `status_code`, so a create passes 201 itself. `cache.cached()` returns the body as bytes.
- **Database.** SQLAlchemy 2, sync sessions, one per request (`db.get_session`). The tables are the
  ones Django created, with Django's names; `models.py` explains. Django's `on_delete` was never in the
  database, so `services.py` does CASCADE and RESTRICT by hand. Work that must wait for the commit goes
  through `db.on_commit()`. Postgres connections set `client_encoding=utf8` and `TimeZone=UTC`: the LXC
  databases are `SQL_ASCII`. No `pool_pre_ping`: a connection is pinged only after `PING_AFTER_IDLE`
  seconds in the pool, and replaced if dead (#41).
- **Never hold a connection while waiting or doing slow work** (#38). The pool has 15 connections
  per worker (`db.POOL_SIZE + db.POOL_OVERFLOW`), and `app.py` caps AnyIO's threads at the same
  number, so extra requests queue for a thread instead of failing on the 30 s pool timeout. Keep
  that cap if the pool changes. A dependency that queries ends its transaction before it returns,
  as `auth.current_user` does, or a request waits for the endpoint's thread holding a connection.
  End the transaction before CPU-heavy work too: `authenticate` commits before the pbkdf2 hash, and
  `create_user` hashes before its first query. Both once failed requests on a stress run's login
  burst. `tests/test_pool_deadlock.py` reproduces each with 2 threads and 1 connection.
- **Migrations.** Alembic, revision 0001 is the schema Django left. `python -m catalog migrate` stamps a
  Django-built database at 0001 by itself, then upgrades. New revision: `just be-makemigrations catalog
  "<message>"`, then read it. Never edit an applied revision. `tests/catalog_django_schema.txt` is 0001's
  schema, frozen from Django's while both existed: never regenerate it to make a test pass.
- **Settings.** `settings.py` (pydantic-settings) reads the env and the root `.env`, with the rules under
  "Settings" above.
- **Auth.** `auth.py` signs RS256 tokens with simplejwt's claims and lifetimes, and stores passwords
  in Django's `pbkdf2_sha256` format at Django 6.0's iteration count, so `instances` and old hashes
  keep working. `tests/test_catalog_compat.py` checks both against values frozen from Django.
- **Metrics.** As under "Metrics and load tests" above (`metrics.py`, `db.py`).
- **Server.** gunicorn with `-k uvicorn_worker.UvicornWorker`, which passes gunicorn's `keepalive` on to
  uvicorn (#24). `gunicorn_threads` does not apply: sync endpoints run in uvicorn's thread pool, and
  SQLAlchemy pools 5 connections (15 under load) per worker.
- **Tests.** `catalog/tests/` on in-memory SQLite (`Base.metadata.create_all`), with `RecordingInstances`
  for the peer and `cache_on` (an in-memory Redis stand-in). `test_app.py` builds the app with other
  settings (HTTPS redirect, hosts, CORS); the parity suite covers the API itself. Postgres checks
  (0001 against Django's frozen schema, adopting a Django-built database, Alembic against the models,
  concurrent writers, a `SQL_ASCII` database) are in `tests/test_catalog_schema.py`; Django compatibility
  (hashes, token claims, seed ids, all frozen) in `tests/test_catalog_compat.py`. `tests/test_observability.py` checks the dashboards read both metric
  families and that the latency buckets match django-prometheus's. `infra/ansible/tests/test_app_role.py`
  checks every command the app role runs is defined.

### `instances` (.NET, #42 to #45)

`backend/instances/`: ASP.NET Core with EF Core + Npgsql. It replaced the Django version (measured in
`loadtest/baselines/2026-11-14-instances-dotnet.md`) on the same API, the same `instancesdb` schema and the same
env var names. `backend/parity_instances/` pins its API; its `xUnit` tests are in `tests/Instances.Tests/`
(Testcontainers Postgres, so they need Docker).

- **Layout** (`src/Instances.Api/`). `Api/` (controllers and response shapes), `Refs/` (copies of types),
  `Dashboard/`, `Pdf/`, `Caching/`, `Auth/`, `Peers/`, `Http/` (wire format, pagination, metrics),
  `Data/` (EF model, migrations, `UnitOfWork`), `Config/` (settings), `Commands/`, `Program.cs`.

- **Toolchain.** .NET 10 SDK, pinned in `global.json` (with `"test": {"runner": "Microsoft.Testing.Platform"}`:
  .NET 10's `dotnet test` no longer runs VSTest). Package versions live in `Directory.Packages.props` only.
  `TreatWarningsAsErrors` and nullable are on. `InvariantGlobalization` is on, so only IANA zone names resolve,
  as with Python's `zoneinfo`. It shares no code with Python: it reads `backend/contracts/` and, in tests,
  `common/dev_keys.py` as files (`tests/test_service_boundary.py`).
- **DRF's wire format, kept on purpose.** Errors are `Http/ApiErrors.cs`, pages `Http/Pagination.cs` (absolute
  links from the request's `Host`, sorted query keys), timestamps Python's `isoformat()` with `Z`
  (`Http/ApiJson.cs`), and JSON columns are passed through as stored text (`RawJson`), never typed classes.
  Change any of it only with a parity test.
- **Schema.** The tables Django created, unchanged. EF entities map onto them by name (`Data/InstancesDb.cs`);
  the baseline migration is Django's own DDL, and the model snapshot is generated from the model, so later
  migrations diff against the real schema. `Instances.Api.dll migrate` adopts a database Django built (marks the
  baseline applied) instead of rebuilding it. `tests/instances_django_schema.txt` is the reference and
  `tests/instances_django_built.sql` a database Django's migrations built, both checked by
  `tests/test_instances_schema.py`; never regenerate either to make a test pass. Django's `on_delete` was never
  in the database: RESTRICT, CASCADE and SET NULL are done in code, as Django's ORM did. Django's own tables
  (`django_*`, `auth_*`) are still in `instancesdb`, unused; dropping them is a migration of its own.
- **Copies and events** (`Refs/RefService.cs`) follow the rules at its top. An upsert is `INSERT ... ON CONFLICT DO
  NOTHING` then `SELECT ... FOR UPDATE`, so two events for one type serialize and the higher version wins. Owner
  generations are bumped only after the commit (`Data/UnitOfWork.cs`).
- **Cache** (`Caching/Cache.cs`): the rules under "Cache" above, under the key prefix `instances-net:`.
- **Settings** (`Config/Settings.cs`): the rules under "Settings" above. Postgres only, so even `test` needs
  `INSTANCES_DATABASE_URL` (a throwaway database).
- **Metrics** carry `catalog`'s names, labels and buckets (`Http/RequestMetrics.cs`), so Grafana and
  `k6-report` need no query of their own (`tests/test_observability.py`). Kestrel's keep-alive (75 s) outlasts
  the gateway's (`tests/test_kestrel_keepalive.py`).
- **Query counts.** `tests/Instances.Tests/HttpTests.cs` fails if a hot path's query count grows with rows; add
  new k6-loaded endpoints to it.
- **PDFs** (#43) are QuestPDF (Community licence), drawn in `Pdf/ResponsePdf.cs` from `Pdf/ResponseContent.cs`
  (Django's `pdf.py` resolution, ported). Kerning is off so text extraction reads words whole; the parity suite compares
  text, never bytes. Bump `PdfCacheVersion` in `QuestionnairesController` when the drawing changes.
- **Commands** are verbs of the binary (`Program.cs`, `Cli`): `migrate`, `seed-loadtest`, `reset-db` and
  `clear-cache` (the last three dev or loadtest only), `reconcile-refs`, and `health` (the runtime image has no
  curl, so Compose's health check asks the binary). `tests/test_instances_commands.py` checks the seeder's shape
  (the shape Django's gave) and runs `reconcile-refs` against the parity stub.
- **Cold start.** A freshly started process compiles as it goes, so its first minute under a login burst is
  slow (#45 baseline). Keep that in mind when a run starts right after a converge.

---

## Frontend (`frontend/`)

**Stack:** React 19, TypeScript ~6.0 (strict), Vite 8, TanStack Router, TanStack Query v5, Axios,
Tailwind CSS v4, shadcn/ui (`base-nova` style on `@base-ui/react`), React Hook Form + Zod,
Zustand + Immer, date-fns, ECharts, react-markdown, SurveyJS (`survey-core` + `survey-react-ui`), Vitest 5 + Testing Library + MSW 3, Playwright,
ESLint 10. Node 24 LTS (`frontend/.nvmrc`; `engines` allows 22.12+, 24, 26+. Odd releases like 25 are
unsupported by Vitest 5).
TypeScript stays on 6.0 until `typescript-eslint` supports 7 (it requires `typescript <6.1`). npm runs only in `frontend/` (the only `package.json` and
`package-lock.json`). Never run `npm` or `npx` from the repo root.

**Layout (`src/`):** `api/` (client, endpoint functions, `queryKeys.ts`), `components/` (`ui/`
for shadcn, `charts/`, `layout/`, one folder per feature), `hooks/`, `lib/`, `routes/`, `schemas/`, `store/`, `test/`,
`__tests__/routes/`, `types/`.

**Conventions**
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
  it code-split, as `ChartCard` does). Do not add another chart library. For done / waiting charts, use
  `useChartPalette`. For separate series, use `useSeriesPalette` (`--series-*` in `index.css`), and give each
  series a fixed slot so it keeps its colour. Keep that order: it is what keeps neighbouring series distinct
  under colour blindness. Never use two y-axes.
- Markdown / LLM output: render with `src/components/Markdown.tsx`.
- Surveys: render with `src/components/survey/SurveyRenderer.tsx`. It maps SurveyJS's CSS
  variables onto the shadcn tokens. Read a submitted response against its
  `questionnaireJsonSnapshot` (`src/lib/responses.ts`), not the live type.

**Testing**
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
  stops with the run, #44) and Vite on :5184 pointed at the router, and never reuses running servers, because a reused backend would carry data over from an earlier run. It stops them when the run ends, and never touches the dev stack.
  Each test registers its own user with a unique email, so tests do not share state. Use them for
  the API contract (auth, real responses); keep UI-only checks in the mocked suite.
  `e2e/integration/helpers.ts` has `registerUser` / `loginAs` (log in by storing the JWT, skipping
  the form), an owner-side `api()` caller, and a scored test survey with `answerScoredSurvey`.
  Test anonymous respondents in a separate `browser.newContext()` so no token leaks in.

---

## Load tests (`loadtest/`, `infra/observability/`)

k6 scripts live in `loadtest/k6/` (`lib/config.js`, `lib/api.js`, `scenarios/*.js`).
`loadtest/run.sh` (`just k6`) runs one scenario in the `grafana/k6` container against the local
load-test stack's gateway. `outage` proves the respondent flow survives `catalog` being stopped: stop it
yourself once the run starts (see the scenario's header). Results go to Prometheus by remote write, tagged `testid=<scenario>-<UTC time>`.
The summary JSON goes to `loadtest/results/` (gitignored). Plan: #9.

- ⚠️ **k6 only ever targets a private address.** `lib/config.js` refuses any other `BASE_URL`
  before the first request, and `backend/tests/test_k6_targets.py` fails on any public host in
  `loadtest/`. Load-testing a site you do not own is a denial-of-service attack.
- Every request carries a `name` tag (endpoint group, such as `questionnaire-detail`). Never
  tag by URL: UUIDs would create one Prometheus series per row.
- Scenarios read from the `just loadtest-seed` owners. Each VU logs in as `loadtest-<n>@example.com`
  (`OWNERS`, default 5), so seed at least that many. The respondent flow creates a fresh
  questionnaire per submit, so a 409 is a real failure.
- Run one scenario at a time. `run.sh` stops a k6 left behind by an interrupted run.
- `load`, `stress` and `soak` take `MIX=mixed` (default, 47 % writes) or `MIX=read` (mostly reads).
  A cache's value depends heavily on the mix, so compare both.
- `catalog` (#39) loads `catalog` alone, since the other mixes leave it near idle: `CATALOG_MIX=crud`
  (default: lists, details, `/me`, token refresh, type create/update/delete) or `CATALOG_MIX=login` (one
  login per iteration, the pbkdf2 path). `RATE`/`HOLD` hold a rate; with `MAX_RATE` it steps up as `stress` does.
- k6 sends trends as native histograms (`K6_PROMETHEUS_RW_TREND_AS_NATIVE_HISTOGRAM`, #20), so
  `k6_http_req_duration_seconds` gives true per-minute latency through `rate()`. Runs before that have
  only `k6_http_req_duration_{p95,avg,…}`, calculated since the run began, so they lag and stay raised after a
  stall. Never read those as one minute's latency, and don't compare them with new p95. `just k6-report`
  labels them "since start", and recovers an old run's per-minute mean from `avg × count`, per series,
  since k6 stops sending a series with no new samples and it goes stale after 5 minutes. Its
  `dropped/min` misses a counter's first jump, usually a soak's startup drops, so take totals from the
  run's summary JSON.
- Prometheus and Grafana config lives in `infra/observability/`. Dashboards are generated:
  edit `grafana/build_dashboards.py`, then run `python3 infra/observability/grafana/build_dashboards.py`.
  `backend/tests/test_observability.py` fails if the committed JSON is stale, and also runs
  promtool on the config and rules (needs Docker).
- Prometheus scrapes each service directly, with a `service` label. On the load-test stack, `/metrics` admits only Prometheus's fixed address (`10.95.0.10/32`).
  A subnet-wide rule would also admit the host, because published ports arrive from the
  subnet's gateway.

---

## Infra: Proxmox LXC containers (`infra/pulumi/`)

The load-test deploy (#9, Phases 3 to 5, #13) runs in seven unprivileged LXC containers on the Proxmox
host `192.168.2.70` (node `bthek1`): `saas-catalog` 241 (the `catalog` service; it kept its `app` role and id so
Pulumi never replaces it), `saas-db` 242, `saas-monitor` 243, `saas-loadgen` 244, `saas-cache` 245,
`saas-instances` 246, `saas-gateway` 247. A container's IP is its id as the last octet (`192.168.2.241`…). Pulumi
creates bare containers. Ansible (Phase 4) configures them.

- ⚠️ **Guest ids 241 to 249 only.** Ids are fixed per role in `saas_loadtest/topology.py`, never
  positional: renumbering makes Pulumi *replace* a guest and its data. So does a new name, unless the old one
  stays in `PREVIOUS_NAMES` as an alias. A new hostname reboots the container. 220 to 240 belong to
  the `kubernates_project` repo and are refused. The host's other guests (100 to 209) are unrelated.
- **State is local and per repo**: `~/.pulumi-state/saas-experimental`, passphrase in
  `~/.pulumi-state/saas-experimental.passphrase`. The justfile sets `PULUMI_BACKEND_URL` and
  `PULUMI_CONFIG_PASSPHRASE_FILE` per command. Never run `pulumi login`: it is global and would
  repoint other projects. Use `just infra <args>`, not bare `pulumi`.
- `Pulumi.loadtest.yaml` is gitignored. `Pulumi.loadtest.yaml.example` documents every key, and
  the one-time setup, including a dedicated API token scoped to a `saas-loadtest` pool. For now
  the stack uses kubernates_project's token (copied, encrypted, 2026-11-02) and no pool.
  Revoking that token breaks both stacks.
- Containers are unprivileged with `nesting=1` (the Proxmox default; systemd needs it) and
  `keyctl=0`, so Docker cannot run inside. Install services natively. `test_program.py` enforces
  this, and that root logs in by SSH key only.
- `infra-up` applies only the plan `infra-preview` saved. Read the preview, especially any
  replace or delete, before applying.
- The pulumi venv is Python 3.13 (`pulumi-proxmoxve` is not on 3.14 yet), separate from
  `backend/`. `just infra-test` also runs `infra/ansible/tests/`.

**Measuring** (`loadtest/baselines/`): run `just loadtest-reset` before every measured k6 run,
since runs add data and change the numbers (it also empties the cache). Change one thing at a time and re-stress. Quicker runs:
`just k6 stress TARGET=lxc STEP=10 MAX_RATE=500 START_RATE=150` skips the low rates, and to compare two
configs, `just k6 load TARGET=lxc RATE=<fixed> HOLD=5m` on each, back to back, is quicker and less
affected by run-to-run variation than comparing knees. Only compare runs with the same settings. A full
baseline takes two stress runs per mix, for a range, and a 1-hour soak (`DURATION=1h`), which covers the
45-minute monolith reference `soak-20261104T055745Z`. Soak for 3 hours only to find where a soak gives out. Stop a soak
after 5 minutes in a row over 1 % dropped iterations: it won't stop itself. Record each
baseline as `loadtest/baselines/<date>.md` (`just k6-report <testid>` makes the tables), then add
it to the `/load-tests` page, which is copied by hand: figures in `frontend/src/lib/loadtestResults.ts`, charts in
`lib/loadtestCharts.ts`, text in `components/loadtest/LoadTestTabs.tsx`. Prefer a chart to a bare table. A chart of table
figures reads them from that table (`cellNumber`), so there is one copy, and the table goes behind `TableDetails`. Check any
figure written in a chart's end label or aria text against the data. The page needs a login but its JS chunk does not, so keep
LAN addresses and secrets out of it.
Tuning knobs: `gunicorn_workers`, `gunicorn_threads` and `conn_max_age` for `catalog` (`infra/ansible/group_vars/app.yml`);
`dotnet_db_pool_size` (Npgsql's pool) and `dotnet_min_threads` (the thread pool's minimum) for `instances`
(`group_vars/instances.yml`); `cache_enabled` in both. For a cache-off run: `just converge --tags app -e cache_enabled=false`.
`just loadtest-reset` rsyncs the working tree, so it deploys whatever is checked out.

**Ansible (`infra/ansible/`, `just converge`)** configures the containers. Roles are `common`
(all), `postgres` (saas-db), `redis` (saas-cache), `app` (saas-catalog and saas-instances, told apart by
`app_service` and `app_unit` in `group_vars`), `gateway` (saas-gateway), `monitor` (saas-monitor) and
`loadgen` (saas-loadgen). The inventory (`inventory/pulumi.py`) reads the Pulumi stack outputs, secrets
included, and refuses any non-private address. Nothing secret is stored in the repo.

- Everything is installed natively, with no Docker:
  - `catalog`: the working tree rsynced to `/srv/app/backend` (without `instances/`), `uv sync --package
    catalog` (Python 3.14), gunicorn with uvicorn workers under systemd (`saas-app.service`), and
    `saas-relay.service`, which retries events (`roles/app/tasks/python.yml`);
  - `instances` (#44, #45): the ASP.NET Core runtime in `/opt/dotnet` (pinned by version and sha256), the
    service published on the control host (`dotnet publish` into the gitignored `backend/instances/publish/`,
    needing the SDK there) and rsynced to `/srv/app/instances-dotnet`, run by `saas-instances.service` on
    Kestrel. No Python. Its commands are verbs of the binary (`migrate`, `reset-db`, `clear-cache`,
    `seed-loadtest`). `app_commands` in `roles/app/defaults/main.yml` holds each service's commands, and env
    is in `/etc/<unit>/app.env`;
  - nginx from apt on saas-gateway, its config from `infra/gateway/build_nginx.py --address ...`;
  - saas-db holds `catalogdb` and `instancesdb` with separate login roles. The monolith's `appdb` is still
    there, unused, as a way back;
  - Postgres 16 and Redis from apt (Redis: no RDB or AOF, `maxmemory` + `allkeys-lru`);
  - Prometheus, Grafana, node_exporter, postgres_exporter, redis_exporter, k6 and uv as release binaries
    pinned by version **and sha256** in `group_vars/all.yml`. Bump both together.
- A second run must report `changed=0`, and `--check --diff` must show nothing. A task that
  always reports changed hides real changes: fix it rather than ignore it. `ansible-lint`
  (production profile) passes: `uvx --from 'ansible-lint==25.*' ansible-lint site.yml`.
- **Firewall:** nftables, input default-deny, per group in `group_vars/<group>.yml`. SSH only from
  `admin_hosts`. A service's port admits only the gateway, its peer service and the scraper, so
  `/internal/` is unreachable from anywhere else, and k6 and you go through the gateway. Never enable the Proxmox datacenter firewall for this (it covers the whole host).
- **CPU and memory per container come from its cgroup**, not node_exporter. Inside an LXC,
  `/proc/stat` counts the host's work on the container's cores (an idle container read 16 %
  busy). `roles/common/files/container-metrics.sh` writes `container_*` metrics to node_exporter's
  textfile collector every 5 s. Read memory as the working set: `memory.current` includes page
  cache.
- The Grafana datasource URL is `${PROMETHEUS_URL}` (compose: `http://prometheus:9090`,
  saas-monitor: `http://localhost:9090`). Rules, provisioning and dashboards are the same files
  as the local stack's.
- `TARGET=lxc` runs k6 on saas-loadgen, through saas-gateway. `/root/k6.env` (written by `roles/loadgen`) holds
  `BASE_URL`, `OWNERS`, the owner password and the remote-write settings, so `run.sh` passes no
  secret on a command line. Grafana is `http://192.168.2.243:3000` (user `admin`, password:
  `just infra stack output grafana_admin_password --show-secrets`).

---

## Docs

There is no `docs/` folder. Project knowledge lives in two files, and docs travel with code in
the same change:

| File | Holds |
|---|---|
| `README.md` | Quick start, local setup, the API table, project structure, tech stack |
| `AGENTS.md` | Conventions and rules for agents (this file) |

Two folders also hold their own records: `backend/contracts/README.md` explains the contract files
beside it, and `loadtest/baselines/` holds measured results.

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
- For a larger feature, create a GitHub milestone for the feature. Each plan in it is its own
  `plan` issue with stable phases, as above, linked to the milestone.

---

## General rules

- Backend and frontend communicate only through the API contract. Never mix their concerns.
- Never commit `.env` files. `.env.example` is the source of truth for required vars.
- There is exactly one env file: `.env` in the repo root, from `.env.example` (`cp .env.example .env`).
  Both services, Vite, docker-compose (`env_file`), direnv (a local, gitignored `.envrc`) and VS Code all read it.
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
- Only edit files your task needs. Changes you did not make belong to another agent. Leave them
  alone.
- Re-read a file immediately before editing it. If an edit fails because the file changed, re-read
  and retry. Never overwrite the whole file.
- Lint, format and test only what you changed. Report failures in code you did not touch, but do
  not fix them. `just be-lint` and `just be-fmt` rewrite the whole backend (`fix = true`), so run
  them only when asked. Scoped lint and format:

  ```bash
  cd backend && uv run ruff check <paths> && uv run ruff format <paths>
  cd backend/instances && dotnet format --include <paths>
  cd frontend && npx eslint <paths>
  ```

- Run only one type of testing (backend, frontend or Playwright) at a time on a machine, across
  all agents. Running them together, or running tests from several agents at once, has crashed
  low-RAM machines.
- Run every test command under the machine-wide lock. If another agent holds the lock, your command
  waits, so set a tool timeout long enough to cover the wait:

  ```bash
  cd backend && flock -o /tmp/agent-tests.lock uv run pytest -q -x <service>/<path>[::<test>]
  cd backend/instances && flock -o /tmp/agent-tests.lock dotnet test   # counts as backend
  cd frontend && flock -o /tmp/agent-tests.lock npx vitest run --reporter=dot <paths>
  cd frontend && flock -o /tmp/agent-tests.lock npm run e2e -- --workers=1
  cd frontend && flock -o /tmp/agent-tests.lock npm run e2e:integration -- --workers=1
  flock -o /tmp/agent-tests.lock just be-test   # same for fe-test and infra-test
  ```

  The quiet flags keep output short; failures still print in full. Filter long logs with `tail` or
  `grep`, never in a way that hides a failure.

- Wrap a recipe in the lock from outside. Never put `flock` inside a recipe: an agent's outer lock
  would then block the recipe's inner lock, and the command would wait forever.
- A local `just k6` run takes the lock too. `TARGET=lxc` runs k6 on saas-loadgen, so it does not.
- Always pass `--workers=1` to Playwright. Its configs leave the worker count open for people, so
  the flag is what limits an agent's run.
- Playwright reuses servers where the suite allows it. The mocked suite needs only Vite: it reuses
  a server on :5174, or starts one and stops it when the run ends. The integration suite never
  reuses servers (see "Testing" under Frontend). It starts its own on separate ports, inside the
  locked command, and stops them when the run ends. Start no other servers for either suite.
- Always pass an app to `just be-makemigrations <app>`. Do not run `just dev` or `just be-dev`:
  they start shared dev servers.
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
