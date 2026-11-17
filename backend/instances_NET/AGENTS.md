# backend/instances_NET/AGENTS.md

`instances` on ASP.NET Core (.NET, #42 to #45). Read with the root [`AGENTS.md`](../../AGENTS.md) and
[`backend/AGENTS.md`](../AGENTS.md), which hold the rules both services share.

`backend/instances_NET/`: ASP.NET Core with EF Core + Npgsql. It replaced the Django version (measured in
`loadtest/baselines/2026-11-14-instances-dotnet.md`) on the same API, the same `instancesdb` schema and the same
env var names. `backend/parity_instances/` pins its API; its `xUnit` tests are in `tests/Instances.Tests/`
(Testcontainers Postgres, so they need Docker).

## Commands

From `backend/instances_NET/`, tests under the test lock (`dotnet test` counts as backend testing):

| Task | Command |
|---|---|
| Tests | `dotnet test` (one category: `dotnet test -- --filter-trait "Category=Refs"`) |
| Lint / format | `dotnet format --verify-no-changes` / `dotnet format` (scoped: `dotnet format --include <paths>`) |
| New migration | `just be-makemigrations instances <Name>` (`dotnet ef migrations add`; read it) |
| Run by hand | `dotnet build src/Instances.Api -c Release -o <dir>`, then `dotnet <dir>/Instances.Api.dll migrate` and `dotnet <dir>/Instances.Api.dll` (`ASPNETCORE_URLS`, env as in `backend/AGENTS.md`) |

The build is the type check.

## Rules

- **Layout** (`src/Instances.Api/`). `Api/` (controllers and response shapes), `Refs/` (copies of types),
  `Dashboard/`, `Pdf/`, `Caching/`, `Auth/`, `Peers/`, `Http/` (wire format, pagination, metrics),
  `Data/` (EF model, migrations, `UnitOfWork`), `Config/` (settings), `Commands/`, `Program.cs`.
- **Toolchain.** .NET 10 SDK, pinned in `global.json` (with `"test": {"runner": "Microsoft.Testing.Platform"}`:
  .NET 10's `dotnet test` no longer runs VSTest). Package versions live in `Directory.Packages.props` only.
  `TreatWarningsAsErrors` and nullable are on. `InvariantGlobalization` is on, so only IANA zone names resolve,
  as with Python's `zoneinfo`. It shares no code with Python: it reads `backend/contracts/` and, in tests,
  `common/dev_keys.py` as files (`tests/test_service_boundary.py`).
- **Finding the SDK.** It may be in `~/.dotnet`, off `PATH` (README's no-sudo install). The justfile puts
  `~/.dotnet` first on `PATH` for every recipe when that folder exists (`tests/test_justfile.py`, #48), and the
  parity suite and the Playwright integration config look there too. Any other place that runs `dotnet` must
  do the same. `dotnet run` needs only `PATH`, not `DOTNET_ROOT`. Outside `just`, run `dotnet` as
  `~/.dotnet/dotnet` or with `PATH="$HOME/.dotnet:$PATH"`.
- **`dotnet watch` noise** (`just be-dev`): `❌ Failed to read …obj\Debug\…staticwebassets.development.json` is
  `dotnet watch` building a Windows path on Linux. The service has no static files; it starts and reloads
  regardless. `Hosting environment: Production` is ASP.NET's own setting, which the service ignores: its
  profile is `SETTINGS` (default `dev`).
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
- **Cache** (`Caching/Cache.cs`): the rules under "Cache" in `backend/AGENTS.md`, under the key prefix
  `instances-net:`.
- **Settings** (`Config/Settings.cs`): the rules under "Settings" in `backend/AGENTS.md`. Postgres only, so even
  `test` needs `INSTANCES_DATABASE_URL` (a throwaway database).
- **Metrics** carry `catalog`'s names, labels and buckets (`Http/RequestMetrics.cs`), so Grafana and
  `k6-report` need no query of their own (`tests/test_observability.py`). Kestrel's keep-alive (75 s) outlasts
  the gateway's (`tests/test_kestrel_keepalive.py`).
- **Query counts.** `tests/Instances.Tests/HttpTests.cs` fails if a hot path's query count grows with rows; add
  new k6-loaded endpoints to it.
- **PDFs** (#43) are QuestPDF (Community licence), drawn in `Pdf/ResponsePdf.cs` from `Pdf/ResponseContent.cs`
  (Django's `pdf.py` resolution, ported). Kerning is off so text extraction reads words whole; the parity suite
  compares text, never bytes. Bump `PdfCacheVersion` in `QuestionnairesController` when the drawing changes.
- **Commands** are verbs of the binary (`Program.cs`, `Cli`): `migrate`, `seed-loadtest`, `reset-db` and
  `clear-cache` (the last three dev or loadtest only), `reconcile-refs`, and `health` (the runtime image has no
  curl, so Compose's health check asks the binary). `tests/test_instances_commands.py` checks the seeder's shape
  (the shape Django's gave) and runs `reconcile-refs` against the parity stub.
- **Cold start.** A freshly started process compiles as it goes, so its first minute under a login burst is
  slow (#45 baseline). Keep that in mind when a run starts right after a converge.

## Dashboard (#19)

`Dashboard/DashboardService.cs`:

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
