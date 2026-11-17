# backend/AGENTS.md

Rules shared by both backend services. Read with the root [`AGENTS.md`](../AGENTS.md). Each service has its
own file too: [`catalog/AGENTS.md`](catalog/AGENTS.md) (FastAPI), [`instances_NET/AGENTS.md`](instances_NET/AGENTS.md)
(.NET, the one that runs), [`instances_Django/AGENTS.md`](instances_Django/AGENTS.md) (Django, kept to compare, #51)
and [`instances_GO/AGENTS.md`](instances_GO/AGENTS.md) (Go, passes the same suite, not deployed, #52).

## Commands

Run Python commands from `backend/` and .NET ones from `backend/instances_NET/`, under the test lock (root
`AGENTS.md`, "Working alongside other agents").

| Task | Command |
|---|---|
| catalog unit tests | `uv run pytest catalog` |
| catalog parity suite (#34) | `uv run pytest parity` (starts `catalog` and a stub `instances` itself) |
| instances API suite (#40) | `uv run pytest parity_instances` (builds `instances`, a throwaway Postgres in Docker and a stub `catalog`) |
| instances on Django (#51) | `cd instances_Django && uv run pytest` |
| instances API suite, against Django (#51) | `INSTANCES_IMPL=django uv run pytest parity_instances` (default `dotnet`) |
| instances API suite, against Go (#52) | `INSTANCES_IMPL=go uv run pytest parity_instances` |
| instances in Go (#52) | `cd instances_GO && go test ./...` |
| Repo-level checks | `uv run pytest tests` |
| Scoped lint / format (Python) | `uv run ruff check <paths> && uv run ruff format <paths>` |
| Upgrade Python dependencies | `uv lock --upgrade` (the workspace root: `catalog`, `common` and `instances_Django`) |

.NET package versions live in `backend/instances_NET/Directory.Packages.props` only.

## Stack and history

**Stack.** `catalog`: Python 3.14, FastAPI, Pydantic v2, pydantic-settings, SQLAlchemy 2 (sync), Alembic,
PyJWT, sqladmin, Celery + Redis, gunicorn with uvicorn workers; uv, ruff, mypy, pytest, pytest-mock.
`instances`: .NET 10, ASP.NET Core controllers, EF Core + Npgsql, JwtBearer, StackExchange.Redis,
prometheus-net, QuestPDF; xUnit v3 with Testcontainers. Both on PostgreSQL 16.

Both services began as Django and kept the tables and the API it left. `catalog` moved to FastAPI in #34 to
#38 (the Django version is at `edb8acd`), and `instances` to .NET in #40 to #45 (at `6b47566`). The Django
`instances` is back beside it as `instances_Django/` (#51): tested and checked by the API suite, never deployed.
Both comparisons are in `loadtest/baselines/` and on `/load-tests`. `instances` on MongoDB was tried and removed
(#29, #30): it was slower and got slower as rows grew (`loadtest/baselines/2026-11-06-instances-mongodb.md`).

**Layout.** `catalog/` (Python package `catalog/catalog/`), `instances_NET/` (`Instances.slnx`: `src/Instances.Api/`
and `tests/Instances.Tests/`), `instances_Django/` (`apps/`, `core/`, `shared/`; #51), `instances_GO/` (`cmd/`,
`internal/`; #52), `common/` (the published dev JWT pair and gunicorn settings, used by `catalog`,
`instances_Django` and the tests), `contracts/` (JSON shapes of `/internal/`), `parity/` and `parity_instances/`
(each service's API over HTTP), `tests/` (repo-level checks).

The services never import each other, including in tests: `catalog` is Python and `instances` is .NET, and
`tests/test_service_boundary.py` checks that no Python reaches into either `instances_*` folder, that Django stays
inside `instances_Django`, and that `common` holds only `dev_keys` and `gunicorn_conf` (#13, #45, #51).

## Service boundary (#13)

`instances` reads only its own copies of types (`QuestionnaireTypeRef`, `BatteryTypeRef`), written only by
`Refs/RefService.cs`. Every write to a type must call `events.record_change()` in `catalog` in the same
transaction, including admin and seeding, and a delete goes through `services.delete_type()`. Peers are reached
only through clients: `instances` uses `Peers/CatalogClient.cs` (`ICatalogClient`; tests swap in a fake),
`catalog` uses `catalog/peers.py` (`HttpInstances`; tests swap in `RecordingInstances` from
`tests/conftest.py`). `/internal/` is never routed by the gateway. Its shapes are `backend/contracts/`, tested by
both services: change those files together with both sides. The subtle rules (versions, tombstones, why
read-through is authoritative) are at the top of `RefService.cs`. `frontend/src/routes/_authed/service-interface.tsx`
explains all this in the app and is hand-written, so a change to `/internal/`, an event or an outage behaviour
updates it too (#27).

## API rules, both services

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
- **API docs:** the API table in `README.md` is the hand-written contract. `catalog` serves its OpenAPI schema
  at `/api/docs/` under `debug` only; it does not replace the table.

## Settings

Both read `SETTINGS` (`dev`, `test`, `e2e`, `prod`, `loadtest`; `catalog` also `parity`) and the root `.env`,
with the same rules: the test profiles never read `JWT_*` from `.env` and always use the dev JWT pair in
`common/dev_keys.py` (#33); `prod` and `loadtest` require their secrets and refuse the dev key; `loadtest` (#9)
is `prod` over plain HTTP for k6 on a private network, and refuses any public `ALLOWED_HOSTS` entry. If
throttles are ever added, raise them there for k6 (every VU shares one IP). `instances` reads
`INSTANCES_DATABASE_URL`, never `DATABASE_URL`, which is `catalog`'s. Never hardcode secrets or credentials.

## Auth

JWT, RS256 (#13). `catalog` signs (`POST /api/token/`, `POST /api/token/refresh/`) and holds the users;
`instances` verifies with the public key only (`Auth/OwnerAuth.cs`): it has no user table, so a request's owner
is just the token's `user_id`. Deactivation and deletion arrive as events (`services.set_active` and
`delete_user` in `catalog`) into `BlockedOwner`, which `OwnerAuth` checks.

## Metrics and load tests (#9)

The k6 side is in [`loadtest/AGENTS.md`](../loadtest/AGENTS.md).

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

## Cache (#11)

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

## Cross-service tests

Each service's own tests are described in its file. `backend/parity/` tests `catalog` over HTTP only: it starts
the service on a free port, with a fresh SQLite database and a stub `instances` that records events and answers
retire. It imports no service code, so it outlived the Django version it was written against (#34). Pin there
anything the SPA or `instances` relies on.

`backend/parity_instances/` does the same for `instances` (#40), for either implementation (#42, #51):
`INSTANCES_IMPL=dotnet` (default) builds `instances_NET`, `INSTANCES_IMPL=django` runs `instances_Django` under
gunicorn with `core.settings.parity`, `INSTANCES_IMPL=go` builds `instances_GO` (#52). All pass the same tests; a
new test pins .NET, the Go version follows it, and if Django lacks the behaviour, mark it `xfail` under Django
with the reason. It runs the service on a throwaway Postgres in Docker,
with a stub `catalog` serving `/internal/` (switchable to 404, 500 or no answer). It plays `catalog` itself:
tokens signed with the dev key, types sent as events. The dashboard tests move rows in time with a plain `UPDATE`
(`support.Clock`), so it runs with the cache off. Pin there anything the SPA, respondents or `catalog` rely on from `instances`.

Repo-level checks that are not tied to a service live in `backend/tests/`, run with `uv run pytest tests`.
`tests/test_infra_docker.py` checks the `infra/docker/` layout; its `docker compose config` tests skip when
Docker is not installed, as do the throwaway-Postgres tests. Markers: `slow`, `integration`, `development`.
