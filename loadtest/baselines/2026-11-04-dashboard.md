# Load-test baseline: 2026-11-04, cheaper dashboards

Plan: #19. Code: `94b9645`.

> **Correction (2026-11-04, #20).** "Slowest group p95" below was calculated since the start of each run,
> not for that minute, so the summary and comparisons now use each minute's mean from `just k6-report`.
> Tables marked "since run start" are left as recorded. See [Re-runs with true p95](#re-runs-with-true-p95).

**Summary.** The cliff in the soak did not come back. The old run fell off it at ~236,000 questionnaires and was stopped at minute 35 with saas-app at 93 % CPU. This run held ~350 req/s to minute 44 (~355,000 rows) with no dropped iterations after startup. It was stopped at minute 45 to save time, so the new limit, if there is one nearby, was not found: CPU and Django p95 started rising at minute 42, and the mean went from about 11 ms to 21–39 ms. Peak capacity is not shown to have moved: the same stress test on this code ended at ~430, ~497 and ~573 req/s, against ~480 before, so run-to-run variation is bigger than any gain it could show.

| | Before | After |
|---|---|---|
| Soak, minute 35 (~280 K rows): mean latency | 327 ms | 9.6 ms |
| Soak, minute 35: saas-app / saas-db CPU | 93 % / 30 % | 55 % / 22 % |
| Soak, dropped iterations after startup, by minute 35 | 7,074 | 0 |
| Stress, ~480 req/s: mean latency | 32 ms | 16 and 7 ms, in two runs |
| Stress, last clean minute | ~480 req/s | ~430, ~497 and ~573 req/s, in three runs |
| Scores cache hit, deploy, ~18 K rows per owner | 39 ms, 1.06 MB | 10 ms, 205 KB |

## What changed

All deployed together, so **k6 cannot separate their effects**. The profile below can.

1. `dashboard/scores/` returns the latest 500 rows as `points`, and `count`, `mean` and `distribution` still cover the window.
2. The median is found in the database, so only the middle one or two rows reach Python.
3. `battery_rows` has the owner on the join, which avoids a table scan when statistics are stale.
4. Partial indexes on `(owner, -submitted_at)` and `(owner, questionnaire_type, -submitted_at)`.
5. A `tz` parameter, which k6 does not send. It should not affect these numbers.

Same deploy and settings as [2026-11-03-redis-cache.md](2026-11-03-redis-cache.md). Each run started from `just loadtest-reset`.

## Profile of a cache miss

The profile the last baseline lacked. A throwaway Postgres 16 on the dev host, not the deploy, so read these as ratios: 300,000 questionnaires, the owner has 15,000 (10,571 submitted), one request at a time, cache off. `HEAD` against the working tree, 3 alternating rounds. Medians:

| Call | Miss wall | Python CPU | Hit (unpickle + render) | Body |
|---|---|---|---|---|
| summary, 30 days | 36.4 → 14.7 ms | 15.1 → 3.7 ms | 0.1 ms | 5.4 KB |
| summary, all time | 66.4 → 17.9 ms | 39.5 → 4.3 ms | 0.1 ms | 7.4 KB |
| scores, 30 days | 9.6 → 8.5 ms | 6.0 → 6.4 ms | 8.1 → 3.0 ms | 548 → 208 KB |
| scores, all time | 26.3 → 18.3 ms | 19.3 → 13.7 ms | 27.6 → 3.0 ms | 1,616 → 208 KB |

- **Median:** this confirms the likely cause in the last baseline. Parsing the timestamps it loaded was the largest Python cost of a summary miss.
- **Scores:** a hit cost as much as a miss, because it unpickled and rendered the whole body.
- **`battery_rows`, current → owner on the join:** 4.3 → 4.3 ms with normal statistics, and 73.7 ms (full table scan) → 5.3 ms with stale ones. That reproduces the scan in [2026-11-03.md](2026-11-03.md).
- **`by_qtype`:** the same change was slower (4.6 → 6.0 ms, and 4.2 → 5.6 ms when stale) and it never scanned, so it was left alone.
- **Indexes:** recent list 2.45 → 0.32 ms, daily chart 3.0 → 2.0 ms. A submit-style `UPDATE` went from ~0.266 to ~0.277 ms per row. They take 8.6 MB and 12 MB on this data.

Postgres responses matched the old code's, apart from the capped `points`. The ten recent rows were compared by value, since the seeder gives them one `submitted_at`.

## Soak

`soak-20261104T055745Z`: `just k6 soak TARGET=lxc RATE=220 DURATION=3h`, the same command as `soak-20261103T133342Z`. 964,645 requests, 0 failed, 1,243 iterations dropped: 1,007 in the first 30 seconds as k6's users logged in, and 236 at the end. Exit 105 is the manual stop at minute 45, 10 minutes past where the old run ended.

| Minute | Rows, old / new | Slowest group p95 since run start, old / new | Django p95, old / new | saas-app CPU, old / new | saas-db CPU, old / new |
|---|---|---|---|---|---|
| 6 | 52 K / 51 K | 41 / 24 ms | 23 / 15 ms | 56 / 49 % | 13 / 13 % |
| 16 | 132 K / 131 K | 82 / 39 ms | 25 / 36 ms | 60 / 66 % | 19 / 20 % |
| 26 | 212 K / 211 K | 121 / 57 ms | 37 / 20 ms | 63 / 53 % | 22 / 19 % |
| 28 | 228 K / 227 K | 130 / 61 ms | 42 / 22 ms | 66 / 48 % | 23 / 19 % |
| 35 | 280 K / 283 K | 422 / 74 ms | 228 / 23 ms | 93 / 55 % | 30 / 22 % |
| 41 | / 331 K | / 83 ms | / 25 ms | / 59 % | / 25 % |
| 43 | / 347 K | / 89 ms | / 56 ms | / 77 % | / 31 % |
| 44 | / 355 K | / 93 ms | / 48 ms | / 70 % | / 30 % |
| 45 | / 363 K | / 9,466 ms | / 58 ms | / 67 % | / 29 % |

- **Drift is much smaller:** at minute 28 (~228 K rows) the mean was 33 ms before and 7.5 ms after. Hit ratios held at ~90 % and ~75 %.
- **Minutes 42 to 44 may be the start of the next limit.** CPU went from ~57 % to ~70–77 %, Django p95 about doubled, and the mean went from about 11 ms to 21–39 ms. The run ended too soon to tell.
- **The 9,466 ms at minute 45 was not a collapse.** That minute's mean was 33 ms. A since-start figure can jump when a rarely seen group appears with a few slow requests.

One owner's reads on the deploy at the end, with no other traffic. Median of 3, 18,416 questionnaires (9,255 submitted). The old run's owner had 15,346 (7,709 submitted), so this one has more data:

| Read | Miss, old / new | Hit, old / new | Body, old / new |
|---|---|---|---|
| `dashboard/?days=30` | 275 / 172 ms | 4 / 2.7 ms | 5 KB |
| `dashboard/` | 239 / 141 ms | 4 / 3.2 ms | 7 KB |
| `dashboard/scores/` | 97 / 48 ms | 39 / 9.9 ms | 1.06 MB / 205 KB |

A summary miss is still far slower here than on the throwaway database (~18 ms), which has less data per owner and more CPU, and this gap was not profiled.

## Stress

`just k6 stress TARGET=lxc STEP=10 STEP_TIME=1m MAX_RATE=500 START_RATE=150`, against `stress-20261103T115330Z` on the same settings. 0 failed in all three. Exit 99 is how a stress run ends.

| ~req/s | Slowest group p95 since run start: before | `stress-20261104T052442Z` | `stress-20261104T053920Z` | saas-app CPU: before / runs |
|---|---|---|---|---|
| 350 | 31 ms | 20 ms | 19 ms | 54 / 49 / 52 % |
| 370 | 34 ms | 22 ms | 20 ms | 54 / 55 / 53 % |
| 430 | 50 ms | 33 ms | 27 ms | 69 / 76 / 64 % |
| 480 | 68 ms | | 34 ms | 83 / / 77 % |
| Last clean minute | ~480 | ~430 | ~497 | 83 / 76 / 74 % |

- **The knee did not clearly move.** Both runs stopped with the rate steady, then a sudden collapse within seconds, at ~440 and ~500 req/s, with saas-app at 76 % and 74 %. Gunicorn logged no errors in the first, and `ListenDrops` stayed at 0. A third run went further: see below.
- **Means at matching rates, before / run 1 / run 2:** 7.4 / 5.6 / 6.1 ms at ~350 req/s, 11.4 / 16.7 / 7.5 ms at ~430, and 32.3 / / 16.2 ms at ~480. The 16.7 is run 1's last minute before it collapsed.
- **Short runs save little CPU.** With about 90 % hits and few rows, the misses are rare and cheap. The gain shows as data grows.
- `stress-20261104T053920Z` also stalled at minute 10 (892 ms) and recovered.

## Re-runs with true p95

From #20, k6 sends native histograms, so these are the first runs with real per-minute p95. Same code, each from `just loadtest-reset`.

`stress-20261104T080836Z`: the same stress command. 564,143 requests, 0 failed, 1,629 dropped. Its last clean minute was ~573 req/s, and it broke the next minute at 85 % saas-app CPU, with slowest group p95 at 5.1 s.

| req/s | Mean | Slowest group p95 | Django p95 | saas-app / saas-db CPU |
|---|---|---|---|---|
| 350 | 5.3 ms | 25 ms | 12 ms | 48 % / 11 % |
| 433 | 6.3 ms | 39 ms | 18 ms | 60 % / 16 % |
| 476 | 7.3 ms | 50 ms | 21 ms | 67 % / 18 % |
| 546 | 10.7 ms | 76 ms | 24 ms | 77 % / 22 % |
| 573 | 15.1 ms | 98 ms | 36 ms | 82 % / 24 % |

**15 minutes near peak rate**, `just k6 soak TARGET=lxc RATE=280 DURATION=15m`, ~445 req/s, about 10,000 new questionnaires a minute, reaching ~150,000 rows. Exit 0 and 0 failed in both. Neither reached the stop rule (5 minutes in a row over 1 % dropped).

| | `soak-20261104T074625Z` | `soak-20261104T083207Z` |
|---|---|---|
| Requests / dropped | 397,961 / 3,330 | 403,618 / 417 |
| Dropped after startup | 2,280 | 0 |
| Mean, minute 2 → minute 14 | 6 → 24 ms | 8 → 16 ms |
| Worst minute's mean | 129 ms (minute 6) | 16.5 ms |
| saas-app CPU at the end | ~79 % | ~61 % |
| Slowest group p95, minute 2 → 14 | not available | 28 → 69 ms |

- **The first run had four bad minutes.** Minutes 6 to 9 had means of 129, 98, 91 and 62 ms, with saas-app at 82–90 % CPU and 2,280 dropped iterations, then it recovered. Why is not known.
- **The second run's 417 drops were all in the first 30 seconds,** as k6's users logged in. Its 11 s maximum was not investigated.
- **These are not comparable with the 350 req/s soaks.** Rate and length differ, and they reach fewer rows.

## How far to trust it

- **Same code, same settings, very different results.** Knees of ~430, ~497 and ~573 req/s, and 79 % against 61 % CPU at one rate. The cause is unknown. This host runs other guests, which was not ruled out.
- One 350 req/s soak on each side. Identical settings have previously broken at ~264 and ~353 req/s.
- The soak's rows are all dated today, the worst case for the `days` windows.
- These are `mixed` runs only. `MIX=read` was not re-run.

## Still open

- **Where the next limit is.** A soak run to its stop rule would find it.
- **The variation between runs,** and the stalls that are probably part of it. Until it is understood, a single knee cannot prove a gain under about 100 req/s.
- **Miss cost on the deploy** (124–179 ms at ~18 K rows). Low-traffic owners rarely get a hit.
- **A scores miss still reads every row in the window** for its totals.
- **`preAllocatedVUs` equal to `maxVUs`** from [2026-11-03.md](2026-11-03.md) is still untested.
