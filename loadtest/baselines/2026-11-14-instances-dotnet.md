# Load-test baseline: 2026-11-14, `instances` on .NET against Django

Plan: #45 (measure, then remove Django), in milestone "instances on .NET" (#40 to #45). Code: `6b47566`
plus the uncommitted #40 to #44 working tree. Every measured run started from
`just converge --tags app --limit app,instances -e app_reset_db=true -e instances_impl=django`, so both
implementations got the same rows from the same (Django) seeder; a .NET run then switched saas-instances
with `just converge --tags app --limit instances`, which adopts the database in place.

**Summary.** **.NET `instances` is faster and uses less CPU in every run, with 0 failed requests in all of
them.** At a fixed 200 iterations/s its p95 is about half Django's (5.45 against 10.69 ms mixed, 4.59 against
8.46 ms read) on about two thirds of the CPU. The like-for-like stress runs reached their `MAX_RATE` without
a knee, at **~784 req/s mixed and ~539 to ~546 read**, with `instances` at 46 % and 37 % CPU. Django broke at ~575 to
~614 and ~495 to ~526, with `instances` at 73 to 85 %. Two further runs from a higher start found its knees at **~1,315 req/s mixed and ~1,378 read**, about 2.2 and 2.6 times Django's, broken by k6's login burst with `instances` still at 57 to 60 % CPU. The 1-hour soak held with **0 failed
of 1,267,551**, mean 3.6 ms against 9.5, `instances` CPU flat at 27 % where Django's rose from 43 to 55 %.
Dropped iterations come from the same places as on Django (k6 logging users in), plus a cold start: a fresh
.NET process is slow for its first seconds while it compiles.

## Deploy

Same containers, sizes and seed as [2026-11-11-catalog-fastapi.md](2026-11-11-catalog-fastapi.md) (20 owners ×
200 questionnaires, 2 + 2 cores, FastAPI `catalog`). `saas-instances` ran either:

| Implementation | Server | Pool |
|---|---|---|
| Django | gunicorn gthread, 3 workers × 4 threads | one connection per thread |
| .NET | Kestrel, one process | Npgsql, 20 connections (`dotnet_db_pool_size`) |

Host load (1-minute load average of the Proxmox host, averaged over each run) was 3.3 to 8.1.

## Fixed rate, Django against .NET

`just k6 load TARGET=lxc RATE=200 HOLD=5m MIX=<mix>`, back to back, each from its own reset. Whole-run figures,
which are mostly `instances`' traffic:

| Mix | Run | Requests | Mean | p95 | `instances` CPU | Memory (max) | Host load | Dropped |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| mixed | Django `load-20261114T035659Z` | 110,531 | 4.86 ms | 10.69 ms | 37 % | 589 MiB | 5.6 | 0 |
| mixed | .NET `load-20261114T040421Z` | 110,136 | 2.87 ms | 5.45 ms | 24 % | 486 MiB | 4.1 | 50 |
| read | Django `load-20261114T041110Z` | 76,085 | 3.94 ms | 8.46 ms | 29 % | 878 MiB | 3.4 | 0 |
| read | .NET `load-20261114T041832Z` | 76,150 | 2.07 ms | 4.59 ms | 17 % | 615 MiB | 5.0 | 0 |

- **The .NET mixed run exited 99** on k6's `dropped_iterations` threshold: 51 dropped, all in minute 1, whose
  slowest group p95 was 933 ms. The service had just restarted, so it compiled its code while every VU logged
  in. From minute 2 the slowest group p95 was 8 to 10 ms. Django has done the same once
  (`load-20261106T055035Z`, 18 dropped at startup).
- **CPU** is a share of the container's 2 cores, from its cgroup.

## Stress, like for like

.NET only, with Django's settings: mixed `STEP=10 STEP_TIME=1m MAX_RATE=500 START_RATE=150`, read the same with
`START_RATE=200 MIX=read`. Two runs per mix. None found a knee: each ran to `MAX_RATE` (500 iterations/s).

| Run | Mix | Last minute | Slowest group p95 | `instances` CPU | saas-db CPU | Dropped | Failed |
|---|---|---:|---:|---:|---:|---:|---:|
| `stress-20261114T042538Z` | mixed | 35 at **~784 req/s** | 63 ms | 46 % | 37 % | 1 | 0 |
| `stress-20261114T050228Z` | mixed | 35 at **~785 req/s** | 62 ms | 46 % | 36 % | 4 | 0 |
| `stress-20261114T053858Z` | read | 31 at **~546 req/s** | 9 ms | 37 % | 18 % | 0 | 0 |
| `stress-20261114T061033Z` | read | 30 at **~539 req/s** | 11 ms | 36 % | 17 % | 0 | 0 |

- **Against Django** (the 2026-11-06 Postgres runs and 2026-11-11's FastAPI-`catalog` runs, as on `/load-tests`):
  knees ~575 to ~614 mixed and ~495 to ~526 read, `instances` at 73 to 85 % CPU, slowest group p95 62 to 123 ms.
  .NET passed every one of those rates at under half that CPU.
- **Why no login burst broke it:** Django's runs broke when a latency spike made k6 add VUs, each logging in at
  once. .NET's latency stayed low enough that k6 rarely needed new VUs.

## Ceiling search

To find where .NET does break: `just k6 stress TARGET=lxc STEP=20 STEP_TIME=1m START_RATE=500 MAX_RATE=1500
MIX=<mix>`, one run per mix, each from its own reset. The higher start means fewer rows at a given rate than a
like-for-like run would have, so read these knees as approximate, and don't put them in a range with the runs above.

| Run | Mix | Last clean minute | Slowest group p95 | `instances` CPU | saas-db CPU | `catalog` CPU | Host load | Failed |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `stress-20261114T074428Z` | mixed | 17 at **~1,315 req/s** | 28 ms | 57 % | 55 % | 8 % | 9.9 | 0 |
| `stress-20261114T080350Z` | read | 39 at **~1,378 req/s** | 27 ms | 60 % | 47 % | 16 % | 6.7 | 0 |

- **What broke each run:** the same as Django's. In the next minute k6 added VUs, which all logged in at once:
  `catalog` CPU rose to 17 % and 28 %, the slowest group p95 reached 4.1 s (mixed), and dropped iterations
  passed k6's 1,000 limit (2,575 and 3,193 in all). `instances` had CPU to spare throughout.
- **What would break next:** saas-db, at 55 % CPU in the mixed run's last clean minute and rising ~2 % per step.
- **k6's own load** stayed at 12 to 15 % CPU on saas-loadgen, so the generator was not the limit.

## Soak

`soak-20261114T064208Z`: `just k6 soak TARGET=lxc RATE=220 DURATION=1h`, exit 0. **1,267,551 requests, 0
failed**, ~352 req/s, mean 3.63 ms, p95 6.56 ms, rows 4,000 → **478,580** (`instancesdb` 371 MB). Django's
(`soak-20261111T112357Z`, FastAPI `catalog`, same command): 1,268,223 requests, 0 failed, mean 9.5 ms, p95 22.1 ms.

**Dropped iterations: 958** (Django 1,342): 770 in minute 1, as VUs logged in during the cold start, and 188 in
minute 45, when k6 logs every VU in again (slowest group p95 3.7 s that minute). The stop rule never fired.

| Minute | Mean | Slowest group p95 | `instances` CPU | saas-db CPU | `catalog` CPU |
|---|---:|---:|---:|---:|---:|
| 5 | 2.7 ms | 10 ms | 27 % | 13 % | 3 % |
| 15 | 2.7 ms | 21 ms | 27 % | 13 % | 2 % |
| 25 | 2.9 ms | 35 ms | 27 % | 15 % | 2 % |
| 35 | 3.0 ms | 48 ms | 27 % | 17 % | 3 % |
| 44 | 3.2 ms | 67 ms | 27 % | 20 % | 3 % |
| 45 | 29.9 ms | 3,663 ms | 27 % | 21 % | 13 % |
| 55 | 3.6 ms | 85 ms | 27 % | 22 % | 2 % |

- **The slowest group is `dashboard` in both soaks**, and grows with rows in both: 8.9 → 87.5 ms here, 19 → 191 ms
  on Django, at minutes 5 and 58. A cache miss aggregates every row in the window; .NET does it in about half the
  time, but the growth is the same.
- **`instances` CPU:** 27 % from minute 1 to 60, where Django's went 43 → 55 %. saas-db rose 13 → 23 % (Django
  11 → 30 %).
- **Memory:** 491 to 736 MiB working set, moving with the garbage collector, with no upward trend.
- **Postgres connections:** 26 to 36 sampled.

## How far to trust it

- **One fixed-rate run per mix and implementation.** The gap (about half the p95) is far larger than run-to-run
  variation here, which has been 20 to 35 %.
- **Stress for .NET only.** Django's knees come from earlier days on the same deploy. .NET's like-for-like runs
  never reached a knee, and the ceiling search is one run per mix with a different start, so its knees are rough.
  The gap, over twice Django's, is far larger than the ~140 req/s that identical runs have varied by.
- **Host load was not controlled.** It was 3.3 to 8.1, similar for both implementations.
- **Cold start.** A freshly started .NET process drops iterations in its first minute under a login burst. A real
  deploy restarts with traffic arriving, so this is a real cost, if a brief one.

## Still open

- **Cold start:** ReadyToRun publishing or a warm-up request before the service reports healthy would shorten
  the first minute.
- **Dashboard growth with rows:** the same on both; a materialized per-day aggregate would bound a miss.
