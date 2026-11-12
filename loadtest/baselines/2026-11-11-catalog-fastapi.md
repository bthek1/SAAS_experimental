# Load-test baseline: 2026-11-11, `catalog` on FastAPI against Django

Plan: #38 (measure, then remove Django), in milestone "catalog on FastAPI" (#34 to #38). Code: `02e485a`
plus the uncommitted #34 to #38 working tree. Ansible's `catalog_impl` picked the implementation per reset:
`just converge --tags app --limit app,instances -e app_reset_db=true -e catalog_impl=<django|fastapi>`.

**Summary.** **With its two pool bugs fixed, FastAPI `catalog` performs the same as Django `catalog`.** At a
fixed rate, `catalog` gets only ~26 to ~34 req/s and uses ~3 % CPU on both, so the whole-run figures are
`instances`' and match. On the final code the stress knees were **~600 req/s mixed and ~518 read**, inside
Django's earlier ranges (~575 to ~614 and ~495 to ~526, on 2026-11-06), and the 1-hour soak held with **0
failed of 1,268,223**, drifting like Django's. The first stress runs found **two connection-pool bugs** in
FastAPI `catalog` that Django's threading model never hit. Both are fixed and covered by tests. FastAPI uses
~100 to 170 MiB more memory, and its logins are slower in k6's re-login burst.

## Deploy

Same containers, sizes and seed as [2026-11-06-microservices-full.md](2026-11-06-microservices-full.md)
(20 owners × 200 questionnaires, 2 + 2 cores). `saas-catalog` ran either:

| Implementation | Server | Pool |
|---|---|---|
| Django | gunicorn gthread, 3 workers × 4 threads | one connection per thread |
| FastAPI | gunicorn + `uvicorn_worker.UvicornWorker`, 3 workers | SQLAlchemy 5 + 10 per worker; final code caps AnyIO's threads at 15 |

Host load was not recorded.

## Fixed rate, Django against FastAPI

`just k6 load TARGET=lxc RATE=200 HOLD=5m`, back to back, each from its own reset. All four: 0 failed, 0 dropped.
`catalog`'s own groups over the last 5 minutes (`token` has no samples there: VUs log in at the start):

| Mix | Run | `questionnaire-type-list` mean / p95 | `health` mean / p95 | `catalog` req/s | `catalog` CPU | Memory |
|---|---|---:|---:|---:|---:|---:|
| mixed | Django `load-20261111T061836Z` | 2.92 / 5.12 ms | 1.25 / 2.56 ms | 26.1 | 2.8 % | 529 MiB |
| mixed | FastAPI `load-20261111T062549Z` | 3.16 / 5.79 ms | 1.01 / 2.30 ms | 26.2 | 2.9 % | 539 MiB |
| read | Django `load-20261111T063245Z` | 2.81 / 5.31 ms | 1.22 / 3.02 ms | 32.8 | 3.7 % | 510 MiB |
| read | FastAPI `load-20261111T063957Z` | 2.64 / 5.09 ms | 0.87 / 2.34 ms | 33.8 | 3.7 % | 636 MiB |

Differences are within a millisecond, with no direction that holds across both mixes. The server-side p95
reads ~9.5 ms on both, because it falls in the histogram's first bucket (10 ms) and can't separate them.
These ran before the pool fixes, which change behaviour only when connections run short.

## What the stress runs found

The stress runs used FastAPI only, to compare with Django's earlier knees: mixed `STEP=10 STEP_TIME=1m
MAX_RATE=500 START_RATE=150`, read the same with `START_RATE=200 MIX=read`. A run ends when cumulative
dropped iterations reach 1,000, and every run here dropped almost nothing until one burst at its end.

1. **A request held a connection while it waited for a thread.** `stress-20261111T080102Z` ended with **93
   502s**, all on `catalog` (`token`, `questionnaire-type-list`, `health`). Its journal showed `QueuePool
   limit of size 5 overflow 10 reached, timeout 30` in waves 30 s apart, for 2 minutes after k6 stopped.
   `auth.current_user`, a sync dependency, kept its connection after returning, so the request waited for an
   AnyIO thread (40 per worker) while holding 1 of 15 connections. With every thread waiting for a
   connection, the worker stalled until the pool timeout. Fix: `current_user` commits before it returns.
2. **Logins held a connection through the password hash.** On the first fix, the read stress
   (`stress-20261111T090123Z`, 23 failed) and the soak (`soak-20261111T092725Z`, 101 failed) failed at
   their start, as every VU logged in: `authenticate` kept its connection through the pbkdf2 hash
   (1.2 million iterations), and a burst of logins held all 15. Fix: `authenticate` commits before the hash,
   `create_user` hashes before its first query, and the app caps AnyIO's threads at the pool's 15, so extra
   requests queue for a thread instead of failing after 30 s, as they did on gthread.

`catalog_fastapi/tests/test_pool_deadlock.py` reproduces both with 2 threads and 1 connection. Each test
failed before its fix. Django never hit these because each gthread thread had its own connection.

## Stress, final code

| Run | Mix | Code | Last clean minute | Slowest group p95 | `instances` CPU | `catalog` CPU | Failed |
|---|---|---|---:|---:|---:|---:|---:|
| `stress-20261111T103001Z` | mixed | final | 23 at **~600 req/s** | 99 ms | 79 % | 5 % | 0 |
| `stress-20261111T105429Z` | read | final | 28 at **~518 req/s** | 83 ms | 82 % | 8 % | 0 |
| `stress-20261111T083543Z` | mixed | fix 1 | 24 at ~605 req/s | 110 ms | 80 % | 6 % | 0 |
| `stress-20261111T064648Z` | mixed | no fix | 20 at ~536 req/s | 88 ms | 73 % | 4 % | 0 |
| `stress-20261111T073718Z` | mixed | no fix | 22 at ~584 req/s | 97 ms | 78 % | 4 % | 0 |
| `stress-20261111T070825Z` | read | no fix | 28 at ~519 req/s | 93 ms | 83 % | 14 % | 0 |
| `stress-20261111T080102Z` | read | no fix | 26 at ~501 req/s | 80 ms | 81 % | 8 % | 93 |

- **Against Django:** mixed ~511 to ~547 and read ~414 to ~434 on 2026-11-05/06 (busier host), and ~575 to
  ~614 and ~495 to ~526 on 2026-11-06 (the MongoDB baseline's Postgres runs). FastAPI's runs fall inside the
  later ranges.
- **What broke each run:** `instances` reached 80 to 90 % CPU, a latency spike made k6 add VUs (up to its 300),
  and every new VU logged in at once: `token` p95 5.2 to 5.6 s and `catalog` CPU 45 to 49 % in that minute.
  `catalog` was at 4 to 8 % CPU until then.

## Soak, final code

`soak-20261111T112357Z`: `just k6 soak TARGET=lxc RATE=220 DURATION=1h`, exit 0. **1,268,223 requests, 0
failed**, ~352 req/s, mean 9.5 ms, p95 22.1 ms. Django's split soak (`soak-20261106T080534Z`, same command):
1,267,568 requests, 0 failed, mean 10.7 ms, p95 27.7 ms.

**Dropped iterations: 1,342** (Django 989): 465 in minute 1 as VUs logged in, 394 in minute 46 (Django ~408
at minute 45) when k6 logs every VU in again, and the rest at the end. The stop rule never fired: minute 46 was
the only minute over 1 %.

| Minute | Mean | Slowest group p95 | Server p95 | `instances` CPU | saas-db CPU | `catalog` CPU |
|---|---:|---:|---:|---:|---:|---:|
| 5 | 4.3 ms | 19 ms | 10 ms | 43 % | 11 % | 3 % |
| 15 | 5.7 ms | 47 ms | 13 ms | 47 % | 14 % | 3 % |
| 25 | 9.1 ms | 97 ms | 23 ms | 55 % | 18 % | 3 % |
| 35 | 9.1 ms | 128 ms | 23 ms | 53 % | 22 % | 3 % |
| 44 | 11.6 ms | 174 ms | 25 ms | 55 % | 27 % | 3 % |
| 46 | 56.8 ms | 6,445 ms | 45 ms | 53 % | 25 % | 20 % |
| 55 | 11.2 ms | 190 ms | 25 ms | 52 % | 30 % | 3 % |

- **The slowest group is `dashboard`, in `instances`, in both soaks**, at the same sizes: 19 → 191 ms
  here, 21 → 184 ms on Django, at minutes 5 and 58.
- **`catalog` over the hour:** `questionnaire-type-list` p95 6.8 ms (Django 6.4), `health` p95 2.7 ms
  (2.9), CPU 3.5 % (3.4 %).
- **Memory:** `saas-catalog` 499 to 510 MiB, flat. Django's was 339 to 412 MiB.
- **Re-login burst:** `token` p95 6.4 s at minute 46, against 3.8 s on Django. FastAPI runs up to 15 hashes per
  worker at once, where Django ran 4, on the same 2 cores, so each login waits longer while the minute's
  dropped iterations stay about the same.

## How far to trust it

- **One fixed-rate run per mix and implementation**, at a rate where `catalog` is nearly idle. It shows no
  regression, not a speed-up.
- **Stress was FastAPI only.** Django's knees come from earlier days, with a different host load. Their
  ranges overlap, which is the claim.
- **Two fixes landed mid-measurement.** The fixed-rate runs predate them, and so do the stress rows marked "no
  fix" and "fix 1". The final-code rows and the soak are the ones that stand.

## Still open

- **Superseded for `catalog` itself** by [2026-11-11-catalog-alone.md](2026-11-11-catalog-alone.md) (#39). Loading only
  `catalog` found two more FastAPI bugs, the signing key parsed per token and a new HTTP client per call to
  `instances`. With them fixed, FastAPI's knee is above Django's. The runs here predate both fixes.

- **Login concurrency.** Fewer threads per worker would shorten each login in a burst, at the cost of
  queueing other `catalog` requests behind them. Worth a `load` comparison if logins matter.
- **Memory.** ~100 to 170 MiB more than Django, probably sqladmin, pydantic and uvicorn per worker. Not measured
  by component.
