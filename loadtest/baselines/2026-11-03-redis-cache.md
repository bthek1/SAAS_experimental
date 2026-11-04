# Load-test baseline: 2026-11-03, Redis cache

> **Correction (2026-11-04, #20).** Every `k6 p95 worst group` and per-endpoint k6 p95 figure here was
> calculated since the start of the run, not for that minute, so it lags and stays raised after a
> stall. Tables are left as recorded. Django p95, CPU, drops and overall run totals were correct.
> `just k6-report <testid>` now adds each minute's true mean for these runs. In particular: under "Unexplained stalls", the
> `read` off stall was one minute (mean 536 ms), and "p95 stays raised for ~6 minutes" is an artefact of this
> figure. Mean drift over the hold was 4.2 → 4.8 ms, not 11 → 29 ms.

Plan: #11.

**Summary.** With the dashboards, type lists and PDFs cached, the deploy holds about **28 % more
traffic**: the knee rose from ~375 to ~480 req/s under `mixed` and from ~360 to ~459 req/s under
`MIX=read`, in back-to-back pairs on the final code. A separate earlier `mixed` pair gave ~353 to
~466. Postgres reads 7–14× fewer rows at matching rates, and endpoints that are not cached get faster
too. **saas-app CPU is now the first limit** (~80 % at the knee, with saas-db at ~20 %). Almost all of
the gain comes from the dashboards. The type-list and PDF caches passed their gates by small margins.

| Final runs | Cache off | Cache on |
|---|---|---|
| `mixed` knee | ~375 req/s (`stress-20261103T114326Z`) | ~480 req/s (`stress-20261103T115330Z`) |
| `MIX=read` knee | ~360 req/s (`stress-20261103T121030Z`) | ~459 req/s (`stress-20261103T122641Z`) |
| `RATE=135`, 10-minute hold, overall p95 / max | 19 / 156 ms (2026-11-02, older code) | 8.9 / 135 ms (`load-20261103T125112Z`) |

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

## Phase 6: final pairs

Final code, everything cached. Each run started from `just loadtest-reset`, with 0 failed requests in
all five. Commands: `just k6 stress TARGET=lxc STEP=10 STEP_TIME=1m MAX_RATE=500`, with
`START_RATE=150` for `mixed` and `START_RATE=200 MIX=read` for read-mostly, cache off then on. A
later start adds fewer rows, so **compare within these pairs**, not with the longer ramps above.

Exit 99 on these four is how a stress run ends: k6 stops once dropped iterations cross the threshold.

| | `mixed` off | `mixed` on | `read` off | `read` on |
|---|---|---|---|---|
| Last clean minute | ~375 req/s | ~480 req/s | ~360 req/s | ~459 req/s |
| Worst-group p95 there | 86 ms | 68 ms | 91 ms | 25 ms |
| saas-app / saas-db CPU there | 65 % / 39 % | 83 % / 23 % | 77 % / 39 % | 77 % / 15 % |

At matching rates:

| k6 p95 | `mixed` off, 375 req/s | `mixed` on, 380 req/s | `read` off, 360 req/s | `read` on, 360 req/s |
|---|---|---|---|---|
| `dashboard` | 86 ms | 38 ms | 91 ms | 11 ms |
| `dashboard-scores` | 29 ms | 19 ms | 49 ms | 9 ms |
| `questionnaire-type-list` | 16 ms | 9 ms | 50 ms | 6 ms |
| `questionnaire-list` (not cached) | 21 ms | 14 ms | 59 ms | 10 ms |
| `questionnaire-submit` (not cached) | 20 ms | 14 ms | 50 ms | 10 ms |
| saas-db CPU | 39 % | 15 % | 39 % | 11 % |
| Postgres rows read/s | 3.1 M | 0.45 M | 3.5 M | 0.25 M |
| Hit ratio: `dashboard` / `dashboard-scores` | | 91 % / 77 % | | 96 % / 89 % |
| Redis memory | 1 MB | 15 MB | 1 MB | 7 MB |

No evictions and no cache errors in any of them.

### 10-minute hold

`load-20261103T125112Z`: `just k6 load TARGET=lxc RATE=135 HOLD=10m`, cache on, exit 0.

| | 2026-11-02 (`load-20261102T052551Z`, no cache) | Cache on |
|---|---|---|
| Requests / failed / dropped | | 139,335 / 0 / 0 |
| Overall p95 / max | 19 / 156 ms | 8.9 / 135 ms |
| Worst-group p95, start to end | 12 → 63 ms | 11 → 29 ms |

Over the hold the hit ratios were 88 % `dashboard`, 73 % `dashboard-scores` and 99 % `type-list`, with
0 evictions, 0 cache errors and ~9 MB in Redis. saas-app stayed at ~30 % CPU and saas-db at ~9 %.

The old run used sync workers as well as having no cache, so this table is not a pure cache
comparison. **The drift is reduced, not gone:** `dashboard` p95 still rises as the run adds rows,
because a miss pays the full query.

### What saturates first now

saas-app. At the `mixed` knee it is at 83 % CPU against saas-db's 23 %, and saas-cache stays at 2 %.
The cache moved the bottleneck out of Postgres, so the next gains are in the app: fewer Python
cycles per request, or more cores. The dashboard's miss path is still worth fixing for low-traffic
owners, who rarely get a hit.

### Unexplained stalls

Three of the four stress runs stalled briefly while well under their knee:

| Run | Minute | Rate | Effect |
|---|---|---|---|
| `mixed` on | 4 | 284 req/s | worst-group p95 1.2 s, 2 dropped, max 4.2 s |
| `read` off | 4 | 269 req/s | worst-group p95 20 s, 515 dropped, max 23.5 s; p95 stays raised for ~6 minutes |
| `read` on | 24 | 448 req/s | worst-group p95 3.4 s, 864 dropped, which ended the run |

**The cause is not known, and the cache is not the cause,** since the worst one had it switched off.
Gunicorn logged no timeouts or restarts, Postgres no errors, and `ListenDrops` stayed at 0 on saas-app.
k6 retried few connections (7 SYN retransmits since boot). In the `read` off stall, a Prometheus scrape
of saas-app was also missed and requests then arrived in a burst, which points to something below the
app freezing briefly, but that was not confirmed.

Two effects on the numbers above: the `read` on knee could be higher, since p95 was only 25 ms when
the stall ended the run, and the `read` off endpoint times at minute 14 may be inflated by the earlier
stall. The earlier `MIX=read` fixed-rate pair above does not have this problem.

## Walkthrough

Run through the API against the LXC deploy, as two newly registered owners. All passed.

| Step | Result |
|---|---|
| Dashboard twice | Hit counter rose by 2, identical bodies |
| Submit through a share link | Dashboard still showed 0 straight after, and 1 after 30.1 s |
| Delete a questionnaire | Gone from the next dashboard read |
| Create a type | In the next list read |
| PDF twice, rename, PDF again | Second was a hit with identical bytes. After the rename the bytes changed |
| Second owner | Empty dashboard and lists. First owner's PDF 404, their type 400 |
| Redis stopped | Dashboard, scores, lists and PDF 200, and deleting a type 204 |

`pdftotext` is not installed here, so the walkthrough saw the renamed PDF's bytes change but did not
read the name out of it. `test_pdf.py` covers that key.

## Data growth at a constant rate

`soak-20261103T133342Z`: `just k6 soak TARGET=lxc RATE=220 DURATION=3h`, cache on, from reset data, so
~350 req/s of `mixed`, about 73 % of the knee. Row counts come from a per-minute sample of
`pg_stat_user_tables`. It was stopped after 5 minutes in a row over 1 % dropped, so exit 105 is that
stop. 734,394 requests, 0 failed, 7,511 iterations dropped.

| Minute | Questionnaires | req/s | Dropped/min | Worst-group p95 | Django p95 | saas-app / saas-db CPU |
|---|---|---|---|---|---|---|
| 6 | 52 K | 349 | 0 | 41 ms | 23 ms | 56 % / 13 % |
| 16 | 132 K | 352 | 0 | 82 ms | 25 ms | 60 % / 19 % |
| 26 | 212 K | 354 | 0 | 121 ms | 37 ms | 63 % / 22 % |
| 28 | 228 K | 353 | 0 | 130 ms | 42 ms | 66 % / 23 % |
| 29 | 236 K | 341 | 357 | 144 ms | 110 ms | 83 % / 27 % |
| 31 | 251 K | 338 | 448 | 167 ms | 124 ms | 85 % / 27 % |
| 35 | 280 K | 290 | 2,260 | 422 ms | 228 ms | 93 % / 30 % |

- **Gradual, then a cliff.** Worst-group p95 rose steadily, about 0.5 ms per 1,000 questionnaires, and
  the rate held. At ~236 K rows (~12 K per owner, half of them submitted) drops began, and from ~251 K
  the deploy could no longer hold the rate. No request failed: it slows down and sheds iterations.
- **Hit ratios held** at ~90 % and ~75 %, and Redis had no evictions or errors, so the cache did not
  stop working. Postgres rows read rose from 0.17 M/s at minute 3 to 0.73 M/s at minute 15.
- **saas-app gave out, not Postgres:** 93 % against 30 %. Every endpoint slowed together, uncached ones
  included (`questionnaire-detail` p95 8 → 174 ms from minute 3 to 35), which is what CPU queueing
  looks like.

One owner's reads at the end, with no other traffic (15,346 questionnaires, 7,709 submitted):

| Read | Miss | Hit | Body |
|---|---|---|---|
| `dashboard/?days=30` | 275 ms | 4 ms | 5 KB |
| `dashboard/` | 239 ms | 4 ms | 7 KB |
| `dashboard/scores/` | 97 ms | 39 ms | **1.06 MB** |

**Likely cause.** The evidence points at the dashboard work done in Python, though no CPU profile was
taken: a dashboard miss loads every submitted row in the cohort for a median, and `dashboard/scores/`
returns every submitted row with no limit. A scores hit still costs 39 ms, since the 1 MB value is
unpickled and rendered as JSON each time, so **the cache does not bound that cost as data grows.**

**How to read it.** This is one run at one rate. Rows arrived about 130 per second, all dated today, so
each one falls inside every `days` window, which is the worst case for those windows. Read the result
as data size per owner rather than time. A lower rate should last longer on the same data, but that
was not measured.

## Quicker measuring

Long ramps cost ~30 minutes per run, most of it at rates that show nothing, so there are two shorter
forms (see AGENTS.md):

- `START_RATE` on `stress` skips the low rates.
- A fixed-rate `load` on each config, back to back.

Only compare runs that use the same settings: a shorter run adds fewer rows and looks better.
