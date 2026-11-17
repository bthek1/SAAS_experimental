# backend/instances_GO/AGENTS.md

`instances` in Go (#52), on the same API, `instancesdb` schema and env var names as `instances_NET`. Read with
the root [`AGENTS.md`](../../AGENTS.md) and [`backend/AGENTS.md`](../AGENTS.md), which hold the rules every
implementation shares.

**It passes the whole API suite but is not deployed** (#52). The dev stack, Docker images and Playwright run
`instances_NET`. `backend/parity_instances/` checks it with `INSTANCES_IMPL=go`, and `just be-test` runs that and
`go test ./...`. A new parity test pins .NET's behaviour; port it here in the same change.

## Commands

From `backend/instances_GO/`, tests under the test lock (`go test` counts as backend testing):

| Task | Command |
|---|---|
| Build | `go build -o /tmp/instances ./cmd/instances` |
| Tests | `go test ./...` (the `store` and `cmd/instances` tests start a throwaway Postgres in Docker; they skip without it) |
| Vet / format | `go vet ./...` / `gofmt -l .` (lists files to fix) / `gofmt -w <paths>` |
| The shared API suite against it | `cd .. && INSTANCES_IMPL=go uv run pytest parity_instances` |
| Run by hand | build, then `<bin> migrate` and `<bin>` (`ASPNETCORE_URLS=http://127.0.0.1:8007`, env as in `backend/AGENTS.md`) |

## Rules

- **Toolchain.** Go, pinned by the `toolchain` line in `go.mod`. README's no-sudo install puts it in `~/.go`, off
  `PATH`; the justfile adds `~/.go/bin` for every recipe when it exists, and the parity suite looks there too. Run
  with `GOTOOLCHAIN=local`, so Go never downloads another toolchain. Dependencies are in `go.mod`/`go.sum` only.
- **Layout.** `cmd/instances/` (the binary: serve, or a verb), `internal/config` (settings), `internal/httpx` (wire
  format, pagination, field rules, metrics), `internal/server` (routing, auth, CORS, host filtering),
  `internal/store` (pool, `migrate`, the embedded baseline DDL), `internal/refs` (copies of types, ported from
  `RefService.cs`), `internal/api` (handlers), `internal/dashboard`, `internal/cache` (prefix `instances-go:`),
  `internal/pdf` (`go-pdf/fpdf`, core fonts), `internal/peers` (catalog client), `internal/ojson` (JSON with member
  order kept), `internal/commands` (seed-loadtest, reset-db, clear-cache, reconcile-refs), `internal/testdb`.
- **Same wire format as .NET**, ported from its `Http/` folder: DRF's errors, pages with absolute links and sorted
  query keys, `isoformat()` timestamps (`httpx.Format`), JSON columns passed through as stored text
  (`json.RawMessage`), no HTML escaping. Change any of it only with a parity test.
- **Routing matches ASP.NET's** (`internal/server/router.go`): case-insensitive literals beat parameters, a trailing
  slash is ignored, a known path with another method is 405, anything else 404. Templates are the .NET controllers'
  and become the `view` label, so metrics line up with .NET's.
- **The schema belongs to `instances_NET`'s EF migrations.** This service never adds a migration. `migrate` builds
  the baseline on an empty database, adopts one Django built, and records it in EF's `__EFMigrationsHistory`, so .NET
  can take over; it refuses a database with a migration it does not know (`store.Known`). A schema change lands in
  .NET first, then here (`tests/test_go_schema.py`).
- **Listens on `ASPNETCORE_URLS`** (first `http://host:port`), so one env file runs either implementation. Its idle
  timeout (75 s) outlasts the gateway's keep-alive (`tests/test_go_keepalive.py`).
- **Never imports or reads Python**, except the dev key test that compares `config.DevVerifyingKey` with
  `common/dev_keys.py` (`tests/test_service_boundary.py`).
- **Python where it shows** (`internal/dashboard/python.go`, `internal/ojson`): `round()` on the double's exact
  value, `zoneinfo`'s fold=0 for a local midnight in a DST change, `str()` of JSON values in the PDF. Go maps lose
  member order, so read stored JSON whose order matters (scores, survey labels) with `ojson`, never `map`.
- **Query counts.** `cmd/instances/http_test.go` fails if a hot path's query count grows with rows, as .NET's
  `HttpTests.cs` does; add new k6-loaded endpoints to `hotPaths`. Dashboard SQL uses named placeholders (`bind`),
  since Postgres refuses a parameter a statement never mentions.
- **PDFs** are drawn with `go-pdf/fpdf` core fonts (text in cp1252). Bump `pdfCacheVersion` in
  `internal/api/dashboard.go` when the drawing changes. `go-pdf/fpdf`'s last release is from 2023.
- **Commands**: `migrate`, `seed-loadtest`, `reset-db` and `clear-cache` (the last three dev or loadtest only),
  `reconcile-refs [--dry-run]`, `health`. `tests/test_instances_commands.py` runs each against .NET and Go.
