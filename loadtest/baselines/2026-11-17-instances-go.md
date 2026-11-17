# Load-test baseline: 2026-11-17, `instances` in Go against .NET

Plan: #52 (phase 6). Code: `82b4cd2` plus the uncommitted #52 working tree (`backend/instances_GO/`). Every
measured run started from its own reset: `just loadtest-reset` for .NET, and for Go the same playbook with
`-e app_instances_impl=go`, which builds the Go binary on the control host, syncs it to saas-instances and
seeds through Go's own `seed-loadtest`. Same containers, sizes and seed as
[2026-11-14-instances-dotnet.md](2026-11-14-instances-dotnet.md) (20 owners × 200 questionnaires, 2 + 2 cores,
FastAPI `catalog`).

**Summary.** **Go serves the same traffic at about half .NET's latency on about a fifth of its CPU**, with 0
failed requests in every run. At a fixed 200 iterations/s its p95 is 2.97 against 5.50 ms (mixed) and 2.84
against 4.52 ms (read), with `instances` at 5 to 6 % CPU against 25 to 26 %, and saas-db's CPU about halved too.
In the ceiling search it held to **~1,567 req/s mixed** (.NET ~1,387 this morning) and, in a second read search
that went past the first one's maximum (#55), to **~2,362 req/s read** (.NET broke at ~1,525), with `instances` at
only 24 to 36 % CPU. The mixed search ran on a quieter host than .NET's (6.7 against 12.2), so read that gain as
an upper bound; the read searches had similar host load (8.95 against 8.2). The fixed-rate runs, back to back on
a host at 2.8 to 5.4, are the fairest comparison. The 1-hour soak held with **0 failed of 1,266,973**, mean 2.59
against 3.63 ms, `instances` CPU flat at 6 to 8 % where .NET's was flat at 27 %.

## Deploy

| Implementation | Server | Pool | Binary |
|---|---|---|---|
| .NET | Kestrel, one process | Npgsql, 20 connections (`dotnet_db_pool_size`) | published, on the ASP.NET runtime |
| Go | `net/http`, one process | pgx, 20 connections (`DB_POOL_SIZE`, the same env file) | one static binary, `CGO_ENABLED=0` |

Go 1.27.4; `GOMAXPROCS` follows the container's 2-core cgroup limit by itself.

## Fixed rate, .NET against Go

`just k6 load TARGET=lxc RATE=200 HOLD=5m MIX=<mix>` (`LOGIN=vu`, the default, as on 2026-11-14), back to back (.NET mixed, Go mixed, .NET read, Go read),
each from its own reset. Whole-run figures; CPU is a share of the container's 2 cores, from its cgroup, per
minute; memory is the working set's maximum.

| Mix | Run | Requests | Mean | p95 | `instances` CPU | saas-db CPU | Memory (max) | Host load | Dropped |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| mixed | .NET `load-20261117T081104Z` | 110,623 | 2.47 ms | 5.50 ms | 25 to 26 % | 9 to 11 % | 406 MiB | 5.4 | 0 |
| mixed | Go `load-20261117T081926Z` | 110,675 | 1.43 ms | 2.97 ms | 5 to 6 % | 4 to 5 % | 282 MiB | 2.8 | 0 |
| read | .NET `load-20261117T082628Z` | 76,205 | 2.10 ms | 4.52 ms | 17 to 18 % | 6 to 8 % | 401 MiB | 4.2 | 0 |
| read | Go `load-20261117T083330Z` | 76,053 | 1.17 ms | 2.84 ms | 4 to 5 % | 3 % | 307 MiB | 3.8 | 0 |

- **No cold start.** Go's first minute was as fast as the rest (mixed: 1.2 ms mean in minute 1). .NET's was
  1.8 ms here, with no drops this time; it dropped 50 at startup on 2026-11-14.
- **saas-db works less for Go**, at the same queries per request (`cmd/instances/http_test.go` pins the same
  counts as .NET's `HttpTests.cs`). Likely cause, not measured: pgx prepares and caches each statement per
  connection by default, so Postgres parses and plans it once, where Npgsql (without `Max Auto Prepare`) sends
  each one unprepared.
- **.NET's p95 here is close to 2026-11-14's** (5.50 against 5.45 ms mixed), so the deploy is comparable.

## Ceiling search

`just k6 stress TARGET=lxc STEP=20 STEP_TIME=1m START_RATE=500 MAX_RATE=1500 LOGIN=setup MIX=<mix>`, the command
of [2026-11-17-prelogin.md](2026-11-17-prelogin.md), so .NET's figures are that baseline's runs from earlier
today, not rerun.

| Run | Mix | Last clean minute | Slowest group p95 | `instances` CPU | saas-db CPU | Memory (max) | Host load (run mean) | Requests | Failed |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| .NET `stress-20261117T051903Z` | mixed | 19 at **~1,387 req/s** | 56 ms | 57 % | 61 % | 606 MiB | 12.2 | 1,405,479 | 0 |
| Go `stress-20261117T084034Z` | mixed | 25 at **~1,567 req/s** | 43 ms | 24 % | 57 % | 185 MiB | 6.7 | 1,819,374 | 0 |
| .NET `stress-20261117T054059Z` | read | 46 at **~1,525 req/s** | 72 ms | 62 % | 54 % | 651 MiB | 8.2 | 2,974,601 | 0 |
| Go `stress-20261117T090724Z` | read | 50 at **~1,630 req/s**, no knee | 14 ms | 26 % | 39 % | 238 MiB | 4.7 | 3,317,902 | 0 |
| Go `stress-20261117T153125Z` (#55) | read | 16 at **~2,362 req/s** | 32 ms | 36 % | 47 % | – | 8.95 | 1,908,750 | 0 |

- **Go's mixed run** dropped 54 iterations in minute 19, then none until minute 26, when it passed k6's 1,000
  limit (1,208 in all). From minute 21 the slowest group's p95 rose (51 to 60 ms) while `instances` stayed at 22 to
  24 % CPU and saas-db climbed from 43 to 57 %: by then the database, not `instances`, was the busier side.
- **Go's read run reached `MAX_RATE`** (1,500 iterations/s) and exited 0, with 74 dropped in all.
- **What this does not show:** how much of Go's higher mixed knee is Go's and how much the quieter host's.
  .NET's mixed run had about twice the host load, and the prelogin baseline found that host CPU contention, not
  `instances`, ended it. The read searches are closer: see the next section. What is clear is that Go reaches
  the same rates with less than half of `instances`' CPU.

### Go's read ceiling, past 1,500 iterations/s (#55)

`stress-20261117T153125Z`: `just k6 stress TARGET=lxc STEP=50 STEP_TIME=1m START_RATE=1400 MAX_RATE=3000
LOGIN=setup MIX=read`, from its own Go reset, with #52's Go code. **0 failed of 1,908,750.** k6 stopped in
minute 17 (target ~2,200 iterations/s), when its 300 VUs (`maxVUs` in `stress.js`) ran out and dropped iterations
passed 1,000, all in that minute; the whole run's p95 was 6.47 ms. Host load averaged 8.95 over the run, close to
.NET's read search (8.2).

| Minute | req/s | Slowest group p95 | Server p99 | `instances` CPU | saas-db CPU | `catalog` CPU | loadgen CPU | CPU pressure, instances / db (s/s) | Host load |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1,379 | 5 ms | 10 ms | 20 % | 16 % | 16 % | 15 % | 0.21 / 0.09 | 6.9 |
| 10 | 2,035 | 9 ms | 10 ms | 30 % | 28 % | 21 % | 19 % | 0.32 / 0.23 | 9.5 |
| 16 | **2,362** | 32 ms | 47 ms | 36 % | 47 % | 28 % | 23 % | 0.39 / 0.36 | 10.0 |

- **Last clean minute: 16, at ~2,362 req/s**, about 1.5 times .NET's ~1,525 at similar host load. Latency had
  been rising since minute 11 (k6 mean 1.8 → 4.5 ms).
- **No container was near its CPU limit.** `instances` used ~0.7 of 2 cores and saas-db ~0.9, and nothing was
  throttled. Yet every container's CPU-pressure wait rose with the rate as host load went from 6.9 to 10.0. The
  limit is the shared Proxmox host's CPU, as in [2026-11-17-prelogin.md](2026-11-17-prelogin.md). The VUs ran
  out because slow tails (max 796 ms) held them.
- `START_RATE` and `STEP` differ from the other searches, so compare the rate reached, not the minute.

## Soak

`soak-20261117T095910Z`: `just k6 soak TARGET=lxc RATE=220 DURATION=1h` (`LOGIN=vu`), the command of .NET's
`soak-20261114T064208Z`, exit 0. **1,266,973 requests, 0 failed**, ~352 req/s, mean 2.59 ms, p95 4.04 ms, rows
4,000 → **479,161** (`instancesdb` 377 MB). .NET's: 1,267,551 requests, 0 failed, mean 3.63 ms, p95 6.56 ms. Host
load averaged 3.3.

**Dropped iterations: 514** (.NET 958), all as VUs logged in at the start. Minute 45, when k6 logs every VU in
again, dropped none (.NET 188), though its slowest group's p95 reached 3.6 s that minute, as .NET's did (3.7 s):
that burst is `catalog` hashing passwords. The stop rule never fired.

| Minute | Mean | Slowest group p95, Go | Slowest group p95, .NET | `instances` CPU, Go | `instances` CPU, .NET | saas-db CPU, Go | saas-db CPU, .NET |
|---|---:|---:|---:|---:|---:|---:|---:|
| 5 | 1.6 ms | 7 ms | 10 ms | 6 % | 27 % | 6 % | 13 % |
| 15 | 1.8 ms | 17 ms | 21 ms | 7 % | 27 % | 7 % | 13 % |
| 25 | 1.9 ms | 28 ms | 35 ms | 7 % | 27 % | 9 % | 15 % |
| 35 | 2.1 ms | 40 ms | 48 ms | 8 % | 27 % | 11 % | 17 % |
| 44 | 2.2 ms | 52 ms | 67 ms | 8 % | 27 % | 13 % | 20 % |
| 55 | 2.3 ms | 65 ms | 85 ms | 8 % | 27 % | 15 % | 22 % |

- **The slowest group still grows with rows** on Go, as on .NET and Django: a dashboard miss aggregates every row
  in its window in the database, whichever language asks. Go is about a fifth faster there, since the work is
  Postgres's.
- **Memory:** 94 to 192 MiB working set, with no upward trend (.NET 491 to 736 MiB).

## How far to trust it

- **One run per mix and implementation**, as on 2026-11-14, and one ceiling search per mix rather than the two a
  full baseline takes. The fixed-rate gaps (about half the latency, a fifth
  of the CPU) are far larger than the 20 to 35 % run-to-run variation seen here.
- **Host load was not controlled.** It was similar for the back-to-back fixed-rate runs (2.8 to 5.4) and for
  the read ceilings (8.95 against 8.2), and much lower for Go's mixed search than for .NET's.
- **Same API, checked.** Before these runs Go passed the same 212-test parity suite as .NET
  (`INSTANCES_IMPL=go uv run pytest parity_instances`).

## Still open

- **Rerun the mixed ceiling searches back to back**, to split Go's mixed gain from the host's.
- **Go's read ceiling is the host's**, not Go's: past ~2,362 req/s it needs a quieter host or pinned cores.
- **Try Npgsql's `Max Auto Prepare`** on .NET: if prepared statements are why saas-db works less for Go, .NET
  can have that too.
- **saas-instances runs .NET again** after these runs; switching is one converge
  (`-e app_instances_impl=go`, `infra/AGENTS.md`).
