# Load-test baseline: 2026-11-05 to 06, full k6 suite on the split

Plan: #24, which merged #22 into it. Code: `47d153a` for the runs on 2026-11-05. The runs on 2026-11-06 used `b27f2ca` and `7cd788e`, which changed only docs, comments and a `justfile` comment, so the deployed backend, gateway and k6 scripts are the same for every run.

**Summary.** All seven scenarios ran on the split with **0 failed requests**. The connection reset in [2026-11-04-microservices.md](2026-11-04-microservices.md) is found and fixed: gunicorn closed idle connections after 2 s while nginx kept them for 60 s. Moving a core from `catalog` to `instances` did not pay, because logins slowed about 10 times, so the deploy stays on 2 + 2 cores. The split **held a 1-hour soak at ~350 req/s** to ~478,000 rows. Before the split, the same soak began to slow at minute 42 and was stopped at 45. Stress ranges are ~511 to ~547 req/s mixed and ~414 to ~434 req/s read. In every stress run, and in the soak at minute 45, the limit was **k6's users logging in at once on `catalog`**, not `instances`. The host was busier than in earlier baselines, so fixed-rate latency is 20 to 35 % higher than on 2026-11-04. That is probably the host, but it is not proven.

## Deploy

Same containers, seed and commands as [2026-11-04-microservices.md](2026-11-04-microservices.md): 20 owners × 200 questionnaires, `just loadtest-reset` before every measured run.

| Container | Size | Runs |
|---|---|---|
| saas-gateway | 1 core, 512 MB | nginx, upstream `keepalive 64`, `keepalive_timeout 60s` |
| saas-catalog | 2 cores, 2 GB | `catalog`, 3 workers × 4 threads, `keepalive` 75 s |
| saas-instances | 2 cores, 2 GB | `instances`, 5 workers × 4 threads, `keepalive` 75 s |
| saas-db | 2 cores, 1 GB | Postgres 16, `max_connections` 100 |
| saas-cache | 1 core, 512 MB | Redis, cache on |

The only change from 2026-11-04 is gunicorn's `keepalive`, from 2 s to 75 s. `catalog` was on 1 core and `instances` on 3 for the Phase 3 "after" runs only.

**Host load.** The containers share one Proxmox host with other guests and with the development machine. Its 1-minute load average was 4.0 to 4.4 during the 2026-11-04 fixed-rate runs. Here it was 4.2 to 11.1 for the fixed-rate runs and 5 to 16.5 during the soak. Per-guest CPU on the host wasn't available.

## The connection reset

`loadtest/keepalive_repro.py`, run from saas-loadgen through saas-gateway for 10 minutes each. It sends bursts of 40 PATCHes to `instances` and 40 POSTs to `catalog`, with random gaps of 2 to 3 s, which straddle gunicorn's old idle timeout. The requests change nothing: an unknown share token and a bad refresh token.

| | Requests | 502s | nginx errors |
|---|---:|---:|---:|
| gunicorn `keepalive` 2 s (before) | 19,120 | **306** (251 `instances`, 55 `catalog`) | 306 (287 reset by peer, 19 upstream prematurely closed) |
| gunicorn `keepalive` 75 s, nginx `keepalive_timeout` 60 s | 18,960 | **0** | 0 |

nginx retries a reset on an idempotent method, but returns 502 for a POST or PATCH, which is what #18 saw. Both services were affected. The reproduction is built to hit the race, so 1.6 % is not the rate in normal traffic. No reset appeared in any run after the fix.

**Did the longer keepalive cost anything?** At `RATE=200`, back to back on 2 + 2 cores. The two mixed runs ended with exit 99 on their latency limits:

| | Mixed p95 | Read p95 | `instances` cores, mixed / read | Host load, mixed / read |
|---|---:|---:|---:|---:|
| `keepalive` 2 s: `load-20261105T143640Z`, `load-20261105T144335Z` | 14.66 ms | 12.82 ms | 0.82 / 0.64 | 11.1 / 8.3 |
| `keepalive` 75 s: `load-20261105T145033Z`, `load-20261105T145727Z` | 19.93 ms | 10.05 ms | 0.81 / 0.54 | 8.2 / 4.8 |

No consistent cost: 75 s is slower on mixed and faster on read, with the same or lower CPU. Host noise is larger than any effect here.

## Sizing: 1 + 3 cores against 2 + 2

The same runs in the same order on each sizing, from `just loadtest-reset`. The 1 + 3 runs ran with `instances` on 7 workers.

| | 2 + 2 cores | 1 + 3 cores |
|---|---|---|
| Mixed `load`, RATE=200 | `load-20261105T135921Z`: p95 13.30 ms, mean 5.84 ms, host load 5.7 | `load-20261106T054339Z`: p95 11.86 ms, mean 5.50 ms, host load 8.9 |
| Read `load`, RATE=200 | `load-20261105T140637Z`: p95 11.00 ms, mean 5.03 ms, host load 6.7 | `load-20261106T055035Z`: p95 9.09 ms, mean 5.01 ms, host load 4.2. Exit 99: 18 dropped and one 2.28 s request at startup, during logins |
| `instances` CPU at RATE=200 | 0.78 / 0.58 cores | 0.79 / 0.51 cores |
| Mixed `stress`, last clean minute | `stress-20261105T141329Z`: ~511 req/s | `stress-20261106T055728Z`: ~594 req/s |
| Login mean near the stress break | 296 logins in 5 min, **1.4 s** | 280 logins in 5 min, **14 s** |
| Peak memory, working set | `catalog` 505 MB, `instances` 751 MB | `catalog` 563 MB, `instances` 923 MB |
| Postgres connections, peak sampled | 33 of 100 | 41 of 100 |

**Decision: reverted to 2 + 2.** The hot path was a little faster on 1 + 3 in both fixed-rate runs, the mixed one even with a busier host. But the gain is within the 13.3 to 19.9 ms spread seen at identical settings, and the stress gain of +83 req/s is under the ~100 req/s one pair can show. Logins hash passwords, so they need CPU, and on one core they were about 10 times slower. `topology.py` records why `catalog` keeps 2 cores.

## Fixed rate and stress

`load` at `RATE=200 HOLD=5m`. Mixed stress: `STEP=10 STEP_TIME=1m MAX_RATE=500 START_RATE=150`. Read stress: the same with `START_RATE=200 MIX=read`. All stress runs end with exit 99, which is how a stress run ends.

| Run | Mix | Result | `instances` CPU | Host load |
|---|---|---|---:|---:|
| `load-20261105T135921Z` | mixed | 110,418 requests, 0 dropped, p95 **13.30 ms** (10.17 on 2026-11-04), mean 5.84 ms | 0.78 cores | 5.7 |
| `load-20261105T140637Z` | read | 76,059 requests, 0 dropped, p95 **11.00 ms** (8.09), mean 5.03 ms | 0.58 cores | 6.7 |
| `stress-20261105T141329Z` | mixed | last clean minute 18 at **~511 req/s**, p95 81 ms | 76 % | 10.6 |
| `stress-20261106T070429Z` | mixed | last clean minute 20 at **~547 req/s**, p95 86 ms | 73 % | 5.0 |
| `stress-20261106T064255Z` | read | last clean minute 21 at **~434 req/s**, p95 34 ms | 63 % | 7.4 |
| `stress-20261106T072541Z` | read | last clean minute 19 at **~414 req/s**, p95 28 ms | 61 % | 7.7 |

- **Ranges:** mixed ~511 to ~547 req/s, read ~414 to ~434 req/s, two runs each. On 2026-11-04, one run each reached ~581 and ~431, on `keepalive` 2 s.
- **What broke each run:** k6 adding VUs. Each new VU logs in, the logins queue on `catalog`, and iterations drop, with `catalog` CPU jumping and `instances` at 61 to 76 %. So the knee here is set by login capacity, and partly by how k6 adds users.
- **Fixed-rate p95:** 20 to 35 % above 2026-11-04, on a busier host (5.7 to 6.7 against 4.0 to 4.4). The keepalive comparison found no cost from the fix. Most likely host load, not proven.

## Respondent and PDF

| Run | Result |
|---|---|
| `respondent-20261106T074535Z`, `RATE=50 DURATION=5m` | **150 req/s**, 45,042 requests, 0 failed, 0 failed checks (so no 409s or 5xx). p95 **5.4 ms** against a 500 ms limit, mean 3.2 ms. 2 iterations dropped at startup. saas-instances ~14 %, saas-db ~4 % |
| `pdf-20261106T075057Z`, `RATE=5 DURATION=5m` | 1,520 requests, 0 failed. p95 **118 ms** against a 3,000 ms limit, median 3.5 ms, mean 29 ms. Cache hits rose from 32 % in minute 1 to 97 % by minute 5, and saas-instances fell from 19 % to 2 %. saas-db ~1 % |

- **PDF against the monolith,** `pdf-20261103T112853Z`, cache on: p95 105 → 118 ms and mean 26.5 → 29 ms, from 1,520 requests each. These are within noise. Both ran WeasyPrint on 2 cores, and `pdf` runs on its own, so the monolith's cores were not shared during that run either.
- **Respondent:** the first figure at load. It sets the reference and can't show a regression.

## Outage

`outage-20261106T075734Z`: `just k6 outage TARGET=lxc RATE=5 DURATION=180`, exit 0, 2,752 requests, 0 failed.

- **`catalog` down:** `saas-relay` and `saas-app` were stopped 45 s after launch, from 07:58:19 to 08:00:39. Prometheus shows `catalog` down from 07:58:30 to 08:00:30.
  - **Opens and submits:** 900 of 900 opens and 900 of 900 submits succeeded.
  - **Logins:** 502 three times during the outage, and 200 after the restart.
- **`instances` down:** stopped from 08:03:58 to 08:04:22.
  - **Writes:** 3 type edits (200) and 1 create (201) through `catalog` all succeeded.
  - **Catch-up:** `app_outbox_pending_events` held 4 and was 0 within 15 s of the restart. `instancesdb` then held the last edit at version 4 and the new type at version 1.
  - **Retire failures:** `app_retire_failures_total` stayed at 0.

## Soak

`soak-20261106T080534Z`: `just k6 soak TARGET=lxc RATE=220 DURATION=1h`, exit 0. **1,267,568 requests, 0 failed**, ~352 req/s, mean 10.7 ms, p95 27.7 ms, rows 4,000 → **478,216**.

**Dropped iterations: 989**, from the summary JSON:
- **Startup:** 581 by minute 5, as VUs logged in.
- **Minute 45:** ~408. k6 logs every VU in again after 45 minutes (`SESSION_MAX_AGE_MS` in `lib/api.js`), so `catalog` took a burst of logins. The worst group's p95 hit 3.8 s that minute, and `catalog` CPU 15 %.
- **Stop rule:** never came close, as no other minute dropped anything.

| Minute | Rows | Mean | Django p95 | `instances` CPU | saas-db CPU | Host load |
|---|---:|---:|---:|---:|---:|---:|
| 5 | 46 K | 5.6 ms | 14 ms | 45 % | 12 % | 9.5 |
| 15 | 125 K | 8.0 ms | 22 ms | 50 % | 15 % | 6.3 |
| 25 | 204 K | 8.6 ms | 23 ms | 54 % | 18 % | 9.4 |
| 28 | ~228 K | 41 ms | 73 ms | 62 % | 22 % | 16.5 |
| 35 | 284 K | 9.7 ms | 24 ms | 56 % | 24 % | 8.6 |
| 44 | ~356 K | 11.4 ms | 25 ms | 56 % | 31 % | ~10.4 |
| 45 | 364 K | 47 ms | 47 ms | 58 % | 27 % | 10.4 |
| 55 | 443 K | 9.3 ms | 24 ms | 50 % | 27 % | 5.6 |

- **Minute 28:** a one-minute spike at the run's highest host load, which recovered the next minute. Most likely host noise.
- **Drift:**
  - **Mean:** 5.6 → 9 to 11 ms as rows grew tenfold.
  - **saas-db CPU:** 12 → 27 to 31 %.
  - **`instances` CPU:** 45 → 50 to 56 %, levelling off.
  - **Memory, flat:** `instances` 598 to 636 MB, `catalog` 340 to 412 MB.
  - **Postgres connections:** 30 to 33 of 100.
  - **Outbox:** 0 throughout.
  - **saas-db disk:** 1.6 → 2.0 GB of 9.8 GB; `instancesdb` 45 → 377 MB.

**Against the monolith,** `soak-20261104T055745Z`, same command, stopped at minute 45:

| | Monolith | Split |
|---|---|---|
| Minute 35 (~283 K rows): mean | 9.6 ms | 9.7 ms |
| Minute 35: app CPU / saas-db CPU | 55 % / 22 % | 56 % / 24 % |
| Minute 44 (~355 K rows): Django p95 | 48 ms | 25 ms |
| Minute 44: app CPU / saas-db CPU | 70 % / 30 % | 56 % / 31 % |

They match to minute 35. After that the monolith's CPU and Django p95 rose from minute 42, while the split's stayed level to minute 60.

## How far to trust it

- **Busy host.** Its load was 4 to 16 throughout, against about 4 for earlier baselines. Identical settings gave a mixed p95 of 13.3 and 19.9 ms within an hour. Compare fixed-rate figures here only with each other, not with 2026-11-04.
- **Two stress runs per mix.** That gives a range, but a narrow sample: identical settings have varied by ~140 req/s before.
- **One soak each side.** The split's level CPU after minute 42 suggests it handles row growth better, but one run each can't prove it. The soak's rows are all dated today, which is the worst case for the `days` windows.
- **Login capacity sets the knee.** Every stress break, and the soak's minute 45, came from k6 logging users in at once. A deploy with users logged in ahead of time could have a higher knee.
- **The keepalive comparison is noisy.** It shows no cost from the fix, but it can't rule out a small one.

## Still open

- **Where the split gives out past 1 hour** (~480 K rows). A 3-hour soak would find it.
- **Pre-allocate k6's VUs,** or log them in before the ramp, to see the knee without the login burst.
- **Measure on a quiet host,** or one with reserved cores, to settle how much of the variation the host causes.
- **`catalog`'s login capacity,** if real login bursts matter. It is CPU-bound password hashing.
