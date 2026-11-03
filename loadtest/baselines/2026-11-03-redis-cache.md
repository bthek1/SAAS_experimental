# Load-test baseline: 2026-11-03, Redis cache

**In progress.** Plan: #11. This file gains a section as each phase is measured. Phase 6 adds the
final summary.

**Summary so far.** Caching the two dashboard endpoints for 30 s raised the knee of the `mixed`
workload from **~353 req/s to ~466 req/s** in one pair of runs. At ~350 req/s the worst endpoint's
p95 fell from 145 ms to 40 ms, and saas-db CPU from 51 % to 15 %. Endpoints that are not cached got
faster too, because Postgres read about 7.6× fewer rows.

## Setup

Same deploy and data as [2026-11-03.md](2026-11-03.md), plus one container: saas-cache (245, 1 core,
512 MB) running Redis 7 with `maxmemory` 256 MB, `allkeys-lru` and no persistence. saas-app runs 5
gunicorn workers × 4 threads. Every run starts from `just loadtest-reset`: 20 owners × 200
questionnaires.

`cached()` stores the result of each dashboard read per owner and parameters, with a 30 s TTL. Auth
and `questionnaireType` validation still run on a hit, so a hit costs the JWT user lookup, the
validation query if a type is given, and two Redis reads.

## Phase 2: cache off

Nothing cached. 5 workers × 4 threads, 0 failed requests in all three.

| Run | Traffic | Last clean minute | Worst-group p95 | Django p95 | saas-app / saas-db CPU |
|---|---|---|---|---|---|
| `stress-20261103T091332Z` | `mixed` | ~353 req/s | 145 ms | 86 ms | 70 % / 51 % |
| `stress-20261103T093632Z` | `MIX=read` | ~329 req/s | 59 ms | 62 ms | 74 % / 40 % |
| `pdf-20261103T100800Z` | `pdf`, RATE=1, 2 min | 1.2 req/s | 138 ms (mean 96 ms) | | |

## Phase 3: dashboards cached, `mixed` traffic

Both runs: `just k6 stress TARGET=lxc STEP=10 STEP_TIME=1m MAX_RATE=500`.

| | Cache off (`stress-20261103T091332Z`) | Cache on (`stress-20261103T101330Z`) |
|---|---|---|
| Knee (0 dropped, worst-group p95 under ~150 ms) | ~353 req/s | ~466 req/s |
| Requests / failed | 248,047 / 0 | 453,214 / 0 |

Minute 22 of each run, at matching rates:

| | Cache off | Cache on |
|---|---|---|
| req/s | 353 | 350 |
| saas-db CPU | 51 % | 15 % |
| saas-app CPU | 70 % | 53 % |
| saas-cache CPU | 1 % | 1 % |
| Postgres rows read/s | 4.5 M | 0.59 M |
| Redis memory | 1 MB | 18 MB (no evictions, no errors) |
| Hit ratio: `dashboard` / `dashboard-scores` | | 91 % / 76 % |

k6 p95 by endpoint, same minute. Only the first two are cached:

| Endpoint | Cache off | Cache on |
|---|---|---|
| `dashboard` | 145 ms | 40 ms |
| `dashboard-scores` | 48 ms | 17 ms |
| `questionnaire-type-list` | 18 ms | 6 ms |
| `questionnaire-list` | 24 ms | 9 ms |
| `questionnaire-detail` | 16 ms | 6 ms |
| `battery-list` | 32 ms | 13 ms |
| `questionnaire-by-token` | 10 ms | 3 ms |
| `questionnaire-submit` | 22 ms | 9 ms |
| `questionnaire-create` | 22 ms | 8 ms |
| `battery-create` | 38 ms | 14 ms |

### How to read this

- **Most of the gain is Postgres contention.** Uncached endpoints sped up about as much as cached
  ones. The dashboards were the source of most rows read, so taking most of them away freed saas-db
  for everything else.
- **The hit ratios beat the estimate in #11** (~85 % and ~65 %), since these figures are at a much
  higher request rate than the estimate assumed. They would be lower at low traffic: a dashboard
  viewed once a minute would always miss.
- **`dashboard` p95 is the miss path.** With 91 % hits, the slowest 5 % are mostly misses, which
  still pay the full query. Caching hides the dashboard's cost as data grows but does not fix it.

### How far to trust it

- **One pair of runs.** Identical settings with nothing cached have broken at ~264 req/s
  (`stress-20261103T084653Z`) and ~353 req/s (`stress-20261103T091332Z`). The cause is unknown. The
  gain here is larger than that spread, and the row counts explain it, but the knee alone is not
  precise.
- **Row counts match up to minute 22,** because both runs followed the same ramp. Past that minute
  only the cache-on run has data.
- **`mixed` is 47 % writes,** which is heavy for this kind of product. The read-mostly comparison
  below covers the other end.

## Phase 3: dashboards cached, `MIX=read` traffic

A fixed-rate pair, back to back (cache off at 10:54 UTC, on at 11:01): `just k6 load TARGET=lxc RATE=200 HOLD=5m
MIX=read`. Each started from `just loadtest-reset`, and the cache-off run used
`-e cache_enabled=false`.

| Minute 5, ~220 req/s | Cache off (`load-20261103T105451Z`) | Cache on (`load-20261103T110134Z`) |
|---|---|---|
| All requests: mean / p95 | 5.5 / 12.0 ms | 4.1 / 8.5 ms |
| `dashboard` p95 | 16 ms | 9 ms |
| `dashboard-scores` p95 | 7 ms | 6 ms |
| `questionnaire-list` p95 (not cached) | 9 ms | 8 ms |
| saas-db CPU | 12 % | 6.5 % |
| saas-app CPU | 41 % | 35 % |
| Postgres rows read/s | 602 K | 77 K |
| Redis memory | 1 MB | 4 MB (no evictions, no errors) |
| Hit ratio: `dashboard` / `dashboard-scores` | | 94 % / 83 % |
| Requests / failed / dropped | 75,986 / 0 / 0 | 75,868 / 0 / 0 |

Below the knee the database has room, so the gain is smaller than under `mixed` stress: 3.5 ms off
the p95 of all requests. The bigger effect is the headroom: saas-db does half the work at this rate.

**Gate (#11, Phase 3): passed.** Both groups are over 50 % hit ratio with a lower p95, and `mixed`
did not regress.

## Phase 3: Redis outage

`load-20261103T110839Z`: `MIX=read`, ~110 req/s. `redis-server` stopped on saas-cache for 105 s.

| | Before | During | After restart (75 s) |
|---|---|---|---|
| Hits/s: `dashboard` + `dashboard-scores` | 24.6 | 0 | 23.0 |
| Errors/s | 0 | 29.7 | 0 |

38,077 requests, 0 failed, 0 dropped, p95 8.9 ms, max 163 ms. `CacheErrors` fired and no request
raised an exception. The worst-group p95 stayed at 11 ms through the outage: at this rate Postgres
absorbs the extra reads without trouble. Every failed read logs one warning, about 30 lines per
second here, so a long outage is noisy in the app's journal.

## Phase 3: Redis hung

`load-20261103T111556Z`: `MIX=read`, ~110 req/s. `redis-server` frozen with SIGSTOP on saas-cache for
80 s, so connections hang rather than being refused.

| k6 p95 | Before | During |
|---|---|---|
| `dashboard` | 9 ms | 112 ms |
| `dashboard-scores` | 6 ms | 106 ms |
| `questionnaire-list` (not cached) | 9 ms | 8 ms |

31,500 requests, 0 failed, 0 dropped, max 145 ms. Each cached read waits out the 100 ms socket
timeout once, and other endpoints are unaffected, so the socket timeouts do bound the cost. k6
exited 99 because `load.js`'s p95 threshold tripped, which is expected here. A circuit breaker is
not needed at this size.

## Phase 4: PDF exports cached

A fixed-rate pair, back to back: `just k6 pdf TARGET=lxc RATE=5 DURATION=5m`. Cache off:
`pdf-20261103T112340Z`. Cache on: `pdf-20261103T112853Z`. 0 failed in both.

| | Cache off | Cache on |
|---|---|---|
| Requests | 1,521 | 1,520 |
| Median | 101 ms | 2.9 ms |
| Mean | 99 ms | 26.5 ms |
| p90 / p95 | 108 / 113 ms | 102 / 105 ms |
| saas-app CPU, last minute | 25 % | 1 % |
| Hits / misses | | ~1,160 / ~360 (76.5 %) |

Redis holds ~350 PDFs in under 5 MB (this test survey's PDFs are small), with no evictions.

**Gate (#11, Phase 4): passed, narrowly.** p95 is lower, but 8 ms may be noise: with 76.5 % hits, p95
is still a miss paying for WeasyPrint. The real gain is on a hit: ~35× faster, and it uses almost no
CPU.

**This overstates the benefit.** k6 redownloads from a small set of PDFs. In real use a hit needs the
same person to download the same response twice within 24 hours, and how often that happens is not
known. Keeping these PDFs in Redis also holds respondents' answers there for up to a day.

## Phase 5: type lists cached

`load-20261103T113600Z` against `load-20261103T110134Z` (dashboards only), same settings:
`just k6 load TARGET=lxc RATE=200 HOLD=5m MIX=read`. They ran 35 minutes apart, not back to back.
Minute 5, ~220 req/s, 0 failed in both.

| | Dashboards only | + type lists |
|---|---|---|
| `questionnaire-type-list` p95 | 4.6 ms | 3.7 ms |
| All requests: mean / p95 | 4.1 / 8.5 ms | 3.8 / 8.0 ms |
| saas-app CPU | 35 % | 33 % |
| Postgres rows read/s | 77 K | 74 K |
| Redis commands/s | 130 | 192 |
| `type-list` hit ratio | | 99.5 % |

**Gate (#11, Phase 5): passed, by a small margin.** These lists were already cheap, and a hit still
makes two Redis round trips. k6 never writes a type, so 99.5 % is a best case. Kept because it costs
little: API writes invalidate at once, and only admin edits can lag, by up to 5 minutes.

## Quicker measuring

Long ramps cost ~30 minutes per run, most of it at rates that show nothing, so there are two shorter
forms (see AGENTS.md):

- `START_RATE` on `stress` skips the low rates.
- A fixed-rate `load` on each config, back to back.

Only compare runs that use the same settings: a shorter run adds fewer rows and looks better.
